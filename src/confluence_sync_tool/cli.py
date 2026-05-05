from __future__ import annotations

import argparse
import getpass
import json
import sys

from .cme_backend import default_cme_config_json, test_cme_connection
from .engine import SyncEngine
from .errors import AppError, classify_exception
from .models import DEFAULT_EXPORT_OPTIONS, Job
from .paths import ensure_app_dirs
from .security import WindowsCredentialStore, mask_sensitive
from .storage import JobStore, load_settings, save_settings, stable_job_id
from .validation import setup_checks, validate_auth_input, validate_job


EXIT_BY_CATEGORY = {
    "Config": 1,
    "Validation": 1,
    "Auth": 2,
    "Network": 3,
    "Confluence API": 3,
    "File System": 4,
    "Conflict": 5,
}


def json_text(data: object) -> str:
    return json.dumps(data, ensure_ascii=True, indent=2)


def emit_json(data: object, *, stream=sys.stdout) -> None:
    print(json_text(data), file=stream)


def console_safe_text(value: object) -> str:
    return mask_sensitive(str(value)).encode("ascii", errors="backslashreplace").decode("ascii")


def _credential_store() -> WindowsCredentialStore:
    return WindowsCredentialStore()


def _engine() -> SyncEngine:
    return SyncEngine()


def _auth_error_from_settings() -> AppError | None:
    try:
        settings = load_settings()
        base_url = str(settings.get("base_url") or "")
        email = str(settings.get("email") or "")
        if not base_url or not email:
            raise AppError("Auth", "CME_AUTH_SETTINGS_REQUIRED", "Run login first.", "", False)
        token = _credential_store().read(base_url, email)
        if not token:
            raise AppError("Auth", "TOKEN_NOT_FOUND", "Stored API token was not found. Run login first.", "", False)
        return None
    except Exception as exc:
        return classify_exception(exc)


def cmd_check(args: argparse.Namespace) -> int:
    ensure_app_dirs()
    checks = setup_checks()
    emit_json({"ok": all(item["ok"] for item in checks), "checks": checks})
    return 0 if all(item["ok"] for item in checks) else 1


def cmd_login(args: argparse.Namespace) -> int:
    token = resolve_login_token(args)
    errors = validate_auth_input(args.base_url, args.email, token)
    if errors:
        emit_json({"ok": False, "errors": errors})
        return 1
    store = _credential_store()
    key = store.write(args.base_url, args.email, token)
    save_settings(args.base_url, args.email)
    if args.test:
        result = test_cme_connection(args.base_url, args.email, token)
    else:
        result = {"ok": True, "account": "not tested"}
    emit_json({"ok": True, "credential_key": key, "connection": result})
    return 0


def resolve_login_token(args: argparse.Namespace) -> str:
    if getattr(args, "token_stdin", False):
        return sys.stdin.read().strip()
    if args.token:
        return args.token
    if sys.stdin.isatty():
        return getpass.getpass("API Token: ").strip()
    return ""


def cmd_logout(args: argparse.Namespace) -> int:
    settings = load_settings()
    _credential_store().delete(settings.get("base_url", ""), settings.get("email", ""))
    emit_json({"ok": True})
    return 0


def cmd_list_jobs(args: argparse.Namespace) -> int:
    jobs = [job.to_dict() for job in JobStore().load()]
    emit_json({"schema_version": 1, "jobs": jobs})
    return 0


def cmd_add_job(args: argparse.Namespace) -> int:
    store = JobStore()
    existing = store.load()
    job_id = args.job_id or stable_job_id(args.name, {job.id for job in existing})
    export_options = dict(DEFAULT_EXPORT_OPTIONS)
    export_options.update(
        {
            "cme_scope": args.cme_scope,
            "cme_urls": args.cme_urls or args.url,
            "cme_config_json": args.cme_config_json or default_cme_config_json(args.target_dir),
            "page_href": args.page_href,
            "attachment_href": args.attachment_href,
            "attachment_export_all": args.attachment_export_all,
            "page_breadcrumbs": args.page_breadcrumbs,
            "page_properties_as_front_matter": args.page_properties_as_front_matter,
            "include_document_title": args.include_document_title,
            "enable_jira_enrichment": args.enable_jira_enrichment,
            "skip_unchanged": args.skip_unchanged,
            "cleanup_stale": args.cleanup_stale,
            "timeout": args.timeout,
            "max_workers": args.max_workers,
            "verify_ssl": args.verify_ssl,
        }
    )
    job = Job(
        id=job_id,
        name=args.name,
        confluence_url=args.url,
        target_dir=args.target_dir,
        include_children=args.include_children,
        include_attachments=False,
        export_options=export_options,
    )
    validate_job(job, create_dirs=True)
    store.upsert(job)
    emit_json({"ok": True, "job": job.to_dict()})
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    job = JobStore().get(args.job)
    checks = setup_checks(job, auth_error=_auth_error_from_settings())
    emit_json({"ok": all(item["ok"] for item in checks), "checks": checks})
    return 0 if all(item["ok"] for item in checks) else 1


def cmd_preview(args: argparse.Namespace) -> int:
    job = JobStore().get(args.job)
    plan = _engine().preview(job)
    emit_json(plan.to_dict())
    return 0


def cmd_dry_run(args: argparse.Namespace) -> int:
    job = JobStore().get(args.job)
    plan = _engine().dry_run(job)
    emit_json(plan.to_dict())
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    job = JobStore().get(args.job)
    run = _engine().apply(job)
    emit_json(run)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="confluence-sync-cli")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("check")
    p.set_defaults(func=cmd_check)
    p = sub.add_parser("login")
    p.add_argument("--base-url", required=True)
    p.add_argument("--email", required=True)
    p.add_argument("--token")
    p.add_argument("--token-stdin", action="store_true", help="Read API token from stdin instead of command-line arguments.")
    p.add_argument("--test", action="store_true")
    p.set_defaults(func=cmd_login)
    p = sub.add_parser("logout")
    p.set_defaults(func=cmd_logout)
    p = sub.add_parser("list-jobs")
    p.set_defaults(func=cmd_list_jobs)
    p = sub.add_parser("add-job")
    p.add_argument("--job-id")
    p.add_argument("--name", required=True)
    p.add_argument("--url", required=True)
    p.add_argument("--target-dir", required=True)
    p.add_argument("--include-children", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--cme-scope", choices=("auto", "pages", "pages-with-descendants", "spaces", "orgs"), default=str(DEFAULT_EXPORT_OPTIONS["cme_scope"]))
    p.add_argument("--cme-urls", help="Whitespace, comma, or newline separated URLs. Defaults to --url.")
    p.add_argument("--cme-config-json", help="Advanced CME config JSON. Values override common GUI/developer CLI options.")
    p.add_argument("--page-href", choices=("absolute", "relative", "wiki"), default=str(DEFAULT_EXPORT_OPTIONS["page_href"]))
    p.add_argument("--attachment-href", choices=("absolute", "relative", "wiki"), default=str(DEFAULT_EXPORT_OPTIONS["attachment_href"]))
    p.add_argument("--attachment-export-all", action=argparse.BooleanOptionalAction, default=bool(DEFAULT_EXPORT_OPTIONS["attachment_export_all"]))
    p.add_argument("--page-breadcrumbs", action=argparse.BooleanOptionalAction, default=bool(DEFAULT_EXPORT_OPTIONS["page_breadcrumbs"]))
    p.add_argument(
        "--page-properties-as-front-matter",
        action=argparse.BooleanOptionalAction,
        default=bool(DEFAULT_EXPORT_OPTIONS["page_properties_as_front_matter"]),
    )
    p.add_argument("--include-document-title", action=argparse.BooleanOptionalAction, default=bool(DEFAULT_EXPORT_OPTIONS["include_document_title"]))
    p.add_argument("--enable-jira-enrichment", action=argparse.BooleanOptionalAction, default=bool(DEFAULT_EXPORT_OPTIONS["enable_jira_enrichment"]))
    p.add_argument("--skip-unchanged", action=argparse.BooleanOptionalAction, default=bool(DEFAULT_EXPORT_OPTIONS["skip_unchanged"]))
    p.add_argument("--cleanup-stale", action=argparse.BooleanOptionalAction, default=bool(DEFAULT_EXPORT_OPTIONS["cleanup_stale"]))
    p.add_argument("--timeout", type=int, default=int(DEFAULT_EXPORT_OPTIONS["timeout"]))
    p.add_argument("--max-workers", type=int, default=int(DEFAULT_EXPORT_OPTIONS["max_workers"]))
    p.add_argument("--verify-ssl", action=argparse.BooleanOptionalAction, default=bool(DEFAULT_EXPORT_OPTIONS["verify_ssl"]))
    p.set_defaults(func=cmd_add_job)
    for name, func in (("preview", cmd_preview), ("dry-run", cmd_dry_run), ("run", cmd_run), ("validate", cmd_validate)):
        p = sub.add_parser(name)
        p.add_argument("--job", required=True)
        p.set_defaults(func=func)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except Exception as exc:
        app_error = classify_exception(exc)
        emit_json({"ok": False, "error": app_error.to_dict()}, stream=sys.stderr)
        print(console_safe_text(exc), file=sys.stderr)
        return EXIT_BY_CATEGORY.get(app_error.category, 10)


if __name__ == "__main__":
    raise SystemExit(main())
