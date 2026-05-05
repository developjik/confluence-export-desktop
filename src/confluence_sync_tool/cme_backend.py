from __future__ import annotations

import copy
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .errors import AppError
from .models import Job
from .security import WindowsCredentialStore
from .storage import load_settings

ProgressCallback = Callable[[str, int, int], None]

CME_SCOPES = ("auto", "pages", "pages-with-descendants", "spaces", "orgs")

DEFAULT_CME_CONFIG: dict[str, object] = {
    "export": {
        "log_level": "INFO",
        "output_path": ".",
        "page_href": "relative",
        "page_path": "{space_name}/{homepage_title}/{ancestor_titles}/{page_title}.md",
        "attachment_href": "relative",
        "attachment_path": "{space_name}/attachments/{attachment_file_id}{attachment_extension}",
        "attachment_export_all": True,
        "page_breadcrumbs": True,
        "page_properties_as_front_matter": True,
        "filename_encoding": '"<":"_",">":"_",":":"_","\\"":"_","/":"_","\\\\":"_","|":"_","?":"_","*":"_","\\u0000":"_","[":"_","]":"_","\'":"_","`":"_"',
        "filename_length": 255,
        "filename_lowercase": False,
        "include_document_title": False,
        "enable_jira_enrichment": False,
        "skip_unchanged": True,
        "cleanup_stale": True,
        "lockfile_name": "confluence-lock.json",
        "existence_check_batch_size": 250,
    },
    "connection_config": {
        "backoff_and_retry": True,
        "backoff_factor": 2,
        "max_backoff_seconds": 60,
        "max_backoff_retries": 5,
        "retry_status_codes": [413, 429, 502, 503, 504],
        "verify_ssl": True,
        "timeout": 30,
        "use_v2_api": False,
        "max_workers": 20,
    },
    "auth": {"confluence": {}, "jira": {}},
}


@dataclass(frozen=True)
class CmeExportResult:
    command: str
    urls: list[str]
    output_path: str
    stats: dict[str, int]


def is_cme_job(job: Job) -> bool:
    return True


def default_cme_config_json(target_dir: str | None = None) -> str:
    config = copy.deepcopy(DEFAULT_CME_CONFIG)
    if target_dir:
        config["export"]["output_path"] = target_dir  # type: ignore[index]
    return json.dumps(config, ensure_ascii=False, indent=2)


def parse_cme_config_json(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return copy.deepcopy(value)
    text = str(value or "").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AppError("Config", "CME_CONFIG_JSON_INVALID", "CME 설정 JSON 형식을 확인하세요.", str(exc), False) from exc
    if not isinstance(data, dict):
        raise AppError("Config", "CME_CONFIG_JSON_INVALID", "CME 설정 JSON은 object여야 합니다.", type(data).__name__, False)
    return data


def cme_urls(job: Job) -> list[str]:
    raw = str(job.export_options.get("cme_urls") or job.confluence_url or "")
    urls = [part for part in re.split(r"[\s,]+", raw.strip()) if part]
    if not urls:
        raise AppError("Config", "CME_URL_REQUIRED", "CME export URL을 하나 이상 입력하세요.", raw, False)
    return urls


def cme_scope(job: Job) -> str:
    scope = str(job.export_options.get("cme_scope", "auto"))
    if scope not in CME_SCOPES:
        raise AppError("Config", "CME_SCOPE_INVALID", "CME scope 값을 확인하세요.", scope, False)
    if scope != "auto":
        return scope
    first = cme_urls(job)[0]
    if "/spaces/" in first and "/pages/" not in first:
        return "spaces"
    if "/pages/" in first:
        return "pages-with-descendants" if job.include_children else "pages"
    return "orgs"


def build_cme_config(job: Job, token: str, settings: dict[str, object] | None = None) -> dict[str, object]:
    settings = settings or load_settings()
    base_url = str(settings.get("base_url") or "").rstrip("/")
    email = str(settings.get("email") or "")
    if not base_url or not email:
        raise AppError("Auth", "CME_AUTH_SETTINGS_REQUIRED", "Confluence Base URL과 Email을 먼저 저장하세요.", "", False)
    if not token:
        raise AppError("Auth", "TOKEN_NOT_FOUND", "저장된 API Token이 없습니다. login을 먼저 실행하세요.", "", False)

    config = copy.deepcopy(DEFAULT_CME_CONFIG)
    apply_common_job_options(config, job)
    deep_merge(config, parse_cme_config_json(job.export_options.get("cme_config_json")))
    config["export"]["output_path"] = str(job.workspace)  # type: ignore[index]
    auth = config.setdefault("auth", {"confluence": {}, "jira": {}})
    confluence_auth = auth.setdefault("confluence", {})  # type: ignore[union-attr]
    confluence_auth[base_url] = {  # type: ignore[index]
        "username": email,
        "api_token": token,
        "pat": "",
    }
    auth.setdefault("jira", {})  # type: ignore[union-attr]
    return config


def apply_common_job_options(config: dict[str, object], job: Job) -> None:
    export = config["export"]  # type: ignore[index]
    page_href = str(job.export_options.get("page_href", "relative"))
    if page_href in {"absolute", "relative", "wiki"}:
        export["page_href"] = page_href  # type: ignore[index]
    attachment_href = str(job.export_options.get("attachment_href", "relative"))
    if attachment_href in {"absolute", "relative", "wiki"}:
        export["attachment_href"] = attachment_href  # type: ignore[index]
    export["include_document_title"] = bool(job.export_options.get("include_document_title", False))  # type: ignore[index]
    export["attachment_export_all"] = bool(job.export_options.get("attachment_export_all", True))  # type: ignore[index]
    export["page_breadcrumbs"] = bool(job.export_options.get("page_breadcrumbs", True))  # type: ignore[index]
    export["page_properties_as_front_matter"] = bool(job.export_options.get("page_properties_as_front_matter", True))  # type: ignore[index]
    export["enable_jira_enrichment"] = bool(job.export_options.get("enable_jira_enrichment", False))  # type: ignore[index]
    export["skip_unchanged"] = bool(job.export_options.get("skip_unchanged", True))  # type: ignore[index]
    export["cleanup_stale"] = bool(job.export_options.get("cleanup_stale", True))  # type: ignore[index]
    connection_config = config["connection_config"]  # type: ignore[index]
    connection_config["verify_ssl"] = bool(job.export_options.get("verify_ssl", True))  # type: ignore[index]
    connection_config["timeout"] = int(job.export_options.get("timeout", 30))  # type: ignore[index]
    connection_config["max_workers"] = int(job.export_options.get("max_workers", 20))  # type: ignore[index]


def deep_merge(base: dict[str, object], override: dict[str, object]) -> dict[str, object]:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_merge(base[key], value)  # type: ignore[arg-type,index]
        else:
            base[key] = value
    return base


def write_cme_config(path: Path, config: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def run_cme_export(job: Job, progress: ProgressCallback | None = None) -> CmeExportResult:
    settings = load_settings()
    token = WindowsCredentialStore().read(str(settings.get("base_url") or ""), str(settings.get("email") or ""))
    if not token:
        raise AppError("Auth", "TOKEN_NOT_FOUND", "저장된 API Token이 없습니다. login을 먼저 실행하세요.", "", False)
    config = build_cme_config(job, token, settings)
    urls = cme_urls(job)
    scope = cme_scope(job)
    with tempfile.TemporaryDirectory(prefix="confluence-export-cme-") as temp_root:
        config_path = Path(temp_root) / "app_data.json"
        write_cme_config(config_path, config)
        return execute_cme(scope, urls, config_path, progress)


def test_cme_connection(base_url: str, email: str, token: str) -> dict[str, object]:
    if not base_url.strip() or not email.strip() or not token.strip():
        raise AppError("Auth", "CME_AUTH_SETTINGS_REQUIRED", "Confluence auth settings are required.", "", False)
    config = copy.deepcopy(DEFAULT_CME_CONFIG)
    normalized_base_url = base_url.rstrip("/")
    auth = config.setdefault("auth", {"confluence": {}, "jira": {}})
    confluence_auth = auth.setdefault("confluence", {})  # type: ignore[union-attr]
    confluence_auth[normalized_base_url] = {  # type: ignore[index]
        "username": email,
        "api_token": token,
        "pat": "",
    }
    with tempfile.TemporaryDirectory(prefix="confluence-export-cme-test-") as temp_root:
        config_path = Path(temp_root) / "app_data.json"
        write_cme_config(config_path, config)
        previous_config = os.environ.get("CME_CONFIG_PATH")
        os.environ["CME_CONFIG_PATH"] = str(config_path)
        try:
            from confluence_markdown_exporter import api_clients
            from confluence_markdown_exporter.utils import app_data_store

            app_data_store.APP_CONFIG_PATH = config_path
            api_clients._confluence_clients.clear()
            api_clients._jira_clients.clear()
            if hasattr(api_clients._thread_local, "clients"):
                api_clients._thread_local.clients = {}
            api_clients.get_confluence_instance(normalized_base_url)
            return {"ok": True, "account": email}
        except BaseException as exc:
            if isinstance(exc, AppError):
                raise
            if exc.__class__.__name__ == "AuthNotConfiguredError":
                raise AppError("Auth", "CME_AUTH_NOT_CONFIGURED", "CME auth configuration is invalid.", str(exc), False) from exc
            raise AppError("Confluence API", "CME_CONNECTION_TEST_FAILED", "CME connection test failed.", str(exc), True) from exc
        finally:
            if previous_config is None:
                os.environ.pop("CME_CONFIG_PATH", None)
            else:
                os.environ["CME_CONFIG_PATH"] = previous_config


def execute_cme(scope: str, urls: list[str], config_path: Path, progress: ProgressCallback | None = None) -> CmeExportResult:
    try:
        return _execute_cme(scope, urls, config_path, progress)
    except ImportError as exc:
        raise AppError(
            "Config",
            "CME_NOT_INSTALLED",
            "confluence-markdown-exporter 패키지가 설치되어 있지 않습니다.",
            str(exc),
            False,
        ) from exc
    except BaseException as exc:
        if exc.__class__.__name__ == "AuthNotConfiguredError":
            raise AppError("Auth", "CME_AUTH_NOT_CONFIGURED", "CME 인증 설정을 확인하세요.", str(exc), False) from exc
        if isinstance(exc, AppError):
            raise
        raise AppError("Confluence API", "CME_EXPORT_FAILED", "CME export 실행에 실패했습니다.", str(exc), True) from exc


def _execute_cme(scope: str, urls: list[str], config_path: Path, progress: ProgressCallback | None = None) -> CmeExportResult:
    previous_config = os.environ.get("CME_CONFIG_PATH")
    os.environ["CME_CONFIG_PATH"] = str(config_path)
    try:
        from confluence_markdown_exporter import confluence as cme_confluence
        from confluence_markdown_exporter import api_clients
        from confluence_markdown_exporter.utils import app_data_store
        from confluence_markdown_exporter.utils.lockfile import LockfileManager
        from confluence_markdown_exporter.utils.rich_console import get_stats
        from confluence_markdown_exporter.utils.rich_console import reset_stats
        from confluence_markdown_exporter.utils.rich_console import setup_logging

        app_data_store.APP_CONFIG_PATH = config_path
        cme_confluence.settings = app_data_store.get_settings()
        api_clients._confluence_clients.clear()
        api_clients._jira_clients.clear()
        if hasattr(api_clients._thread_local, "clients"):
            api_clients._thread_local.clients = {}
        reset_lockfile_manager(LockfileManager)
        setup_logging(cme_confluence.settings.export.log_level)
        if progress:
            progress(f"cme {scope} started", 0, len(urls))
        reset_stats(total=len(urls))
        LockfileManager.init()
        exported_base_urls: set[str] = set()
        for index, url in enumerate(urls, 1):
            if progress:
                progress(f"cme exporting {url}", index, len(urls))
            if scope == "pages":
                page = cme_confluence.Page.from_url(url)
                exported_base_urls.add(page.base_url)
                LockfileManager.mark_seen([page.id])
                if LockfileManager.should_export(page):
                    LockfileManager.record_page(page, page.export())
                    get_stats().inc_exported()
                else:
                    get_stats().inc_skipped()
            elif scope == "pages-with-descendants":
                page = cme_confluence.Page.from_url(url)
                exported_base_urls.add(page.base_url)
                page.export_with_descendants()
            elif scope == "spaces":
                space = cme_confluence.Space.from_url(url)
                exported_base_urls.add(space.base_url)
                space.export()
            elif scope == "orgs":
                org = cme_confluence.Organization.from_url(url)
                exported_base_urls.add(org.base_url)
                org.export()
            else:
                raise AppError("Config", "CME_SCOPE_INVALID", "CME scope 값을 확인하세요.", scope, False)
        for base_url in exported_base_urls:
            cme_confluence.sync_removed_pages(base_url)
        stats = get_stats()
        if progress:
            progress(f"cme {scope} finished", len(urls), len(urls))
        return CmeExportResult(
            command=scope,
            urls=urls,
            output_path=str(cme_confluence.settings.export.output_path),
            stats={
                "total": stats.total,
                "exported": stats.exported,
                "skipped": stats.skipped,
                "failed": stats.failed,
                "removed": stats.removed,
                "attachments_exported": stats.attachments_exported,
                "attachments_skipped": stats.attachments_skipped,
                "attachments_failed": stats.attachments_failed,
                "attachments_removed": stats.attachments_removed,
            },
        )
    finally:
        if previous_config is None:
            os.environ.pop("CME_CONFIG_PATH", None)
        else:
            os.environ["CME_CONFIG_PATH"] = previous_config


def reset_lockfile_manager(lockfile_manager: object) -> None:
    lockfile_manager._lockfile_path = None
    lockfile_manager._lock = None
    lockfile_manager._output_path = None
    lockfile_manager._all_entries_snapshot = {}
    lockfile_manager._seen_page_ids = set()
