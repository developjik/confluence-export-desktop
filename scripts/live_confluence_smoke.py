from __future__ import annotations

import hashlib
import json
import locale
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import _path  # noqa: F401


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "dist" / "confluence-export-cli" / "confluence-export-cli.exe"
DEFAULT_EVIDENCE_ROOT = ROOT / "docs" / "verification" / "external_evidence"


def decode_output(data: bytes | None) -> str:
    if not data:
        return ""
    encodings = ["utf-8", locale.getpreferredencoding(False), "cp949"]
    seen = set()
    for encoding in encodings:
        if not encoding or encoding in seen:
            continue
        seen.add(encoding)
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", errors="replace")


def subprocess_env(appdata: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["APPDATA"] = str(appdata)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def required_env() -> tuple[dict[str, str], dict[str, str] | None]:
    keys = {
        "CONFLUENCE_EXPORT_BASE_URL": "Confluence Cloud base URL",
        "CONFLUENCE_EXPORT_EMAIL": "Confluence login email",
        "CONFLUENCE_EXPORT_API_TOKEN": "Confluence API token",
        "CONFLUENCE_EXPORT_PAGE_URL": "Confluence test page URL with at least two children",
    }
    missing = [key for key in keys if not os.environ.get(key)]
    if missing:
        return {}, {"ok": False, "missing_env": missing, "descriptions": keys}
    return {key: os.environ[key] for key in keys}, None


def safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in value)


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def run_cli(name: str, args: list[str], appdata: Path, evidence_dir: Path, redact: str, input_text: str | None = None, timeout: int = 120) -> dict:
    stdout_file = evidence_dir / f"stdout-{safe_name(name)}.txt"
    stderr_file = evidence_dir / f"stderr-{safe_name(name)}.txt"
    proc = subprocess.run(
        args,
        cwd=ROOT,
        env=subprocess_env(appdata),
        input=input_text.encode("utf-8") if input_text is not None else None,
        capture_output=True,
        timeout=timeout,
    )
    stdout = decode_output(proc.stdout).replace(redact, "****")
    stderr = decode_output(proc.stderr).replace(redact, "****")
    write_text(stdout_file, stdout)
    write_text(stderr_file, stderr)
    return {
        "name": name,
        "args": [arg if arg != redact else "****" for arg in args],
        "returncode": proc.returncode,
        "stdout_file": str(stdout_file),
        "stderr_file": str(stderr_file),
        "stdout_tail": stdout[-5000:],
        "stderr_tail": stderr[-5000:],
    }


def tree_hash(path: Path) -> str:
    if not path.exists():
        return "missing"
    files = sorted(item for item in path.rglob("*") if item.is_file())
    if not files:
        return "empty"
    digest = hashlib.sha256()
    for file_path in files:
        relative = file_path.relative_to(path).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(file_path.read_bytes()).hexdigest().encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def parse_json_stdout(result: dict) -> dict:
    try:
        text = Path(str(result["stdout_file"])).read_text(encoding="utf-8")
        return json.loads(text)
    except Exception as exc:
        return {"ok": False, "parse_error": str(exc)}


def token_leak_files(paths: list[Path], token: str) -> list[str]:
    leaks: list[str] = []
    token_bytes = token.encode("utf-8")
    for root in paths:
        if not root.exists():
            continue
        for file_path in root.rglob("*"):
            if not file_path.is_file():
                continue
            try:
                if token_bytes in file_path.read_bytes():
                    leaks.append(str(file_path))
            except OSError:
                continue
    return leaks


def export_summary(workspace: Path) -> dict:
    if not workspace.exists():
        return {"exists": False, "file_count": 0, "markdown_count": 0, "lockfile_exists": False, "paths": []}
    files = sorted(item for item in workspace.rglob("*") if item.is_file())
    paths = [item.relative_to(workspace).as_posix() for item in files[:50]]
    return {
        "exists": True,
        "file_count": len(files),
        "markdown_count": len([item for item in files if item.suffix.lower() == ".md"]),
        "lockfile_exists": (workspace / "confluence-lock.json").exists(),
        "paths": paths,
    }


def main() -> int:
    env, missing = required_env()
    if missing:
        print(json.dumps(missing, ensure_ascii=False, indent=2))
        return 1
    if not CLI.exists():
        print(
            json.dumps(
                {
                    "ok": False,
                    "reason": "developer CLI missing; build with scripts/build.ps1 -IncludeCli to run this developer smoke",
                    "path": str(CLI),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    token = env["CONFLUENCE_EXPORT_API_TOKEN"]
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    evidence_root = Path(os.environ.get("CONFLUENCE_EXPORT_EVIDENCE_DIR", DEFAULT_EVIDENCE_ROOT))
    evidence_dir = evidence_root / f"{timestamp}-live-python"
    appdata = evidence_dir / "appdata"
    workspace = evidence_dir / "workspace"
    appdata.mkdir(parents=True, exist_ok=True)
    workspace.mkdir(parents=True, exist_ok=True)

    job_id = f"live-smoke-{timestamp}"
    commands: list[dict] = []
    logged_in = False
    try:
        login = run_cli(
            "live-login",
            [str(CLI), "login", "--base-url", env["CONFLUENCE_EXPORT_BASE_URL"], "--email", env["CONFLUENCE_EXPORT_EMAIL"], "--token-stdin", "--test"],
            appdata,
            evidence_dir,
            token,
            input_text=token,
            timeout=120,
        )
        commands.append(login)
        logged_in = login["returncode"] == 0

        commands.append(run_cli("live-add-job", [str(CLI), "add-job", "--job-id", job_id, "--name", "Live Smoke", "--url", env["CONFLUENCE_EXPORT_PAGE_URL"], "--target-dir", str(workspace), "--include-children"], appdata, evidence_dir, token, timeout=60))
        preview = run_cli("live-preview", [str(CLI), "preview", "--job", job_id], appdata, evidence_dir, token, timeout=120)
        commands.append(preview)
        before_dry_run_hash = tree_hash(workspace)
        dry_run = run_cli("live-dry-run", [str(CLI), "dry-run", "--job", job_id], appdata, evidence_dir, token, timeout=120)
        commands.append(dry_run)
        after_dry_run_hash = tree_hash(workspace)
        commands.append(run_cli("live-run", [str(CLI), "run", "--job", job_id], appdata, evidence_dir, token, timeout=180))
    finally:
        before_dry_run_hash = locals().get("before_dry_run_hash", tree_hash(workspace))
        after_dry_run_hash = locals().get("after_dry_run_hash", tree_hash(workspace))
        if logged_in:
            commands.append(run_cli("live-logout", [str(CLI), "logout"], appdata, evidence_dir, token, timeout=60))

    preview_json = parse_json_stdout(commands[2]) if len(commands) > 2 else {}
    preview_items = preview_json.get("items") if isinstance(preview_json.get("items"), list) else []
    exported = export_summary(workspace)
    leaks = token_leak_files([appdata, workspace, evidence_dir], token)
    ok = (
        all(command["returncode"] == 0 for command in commands)
        and len(preview_items) >= 1
        and before_dry_run_hash == after_dry_run_hash
        and int(exported.get("file_count", 0)) > 0
        and not leaks
    )
    result = {
        "ok": ok,
        "evidence_dir": str(evidence_dir),
        "job_id": job_id,
        "commands": commands,
        "preview_items": len(preview_items),
        "dry_run_hash_before": before_dry_run_hash,
        "dry_run_hash_after": after_dry_run_hash,
        "dry_run_preserved_workspace": before_dry_run_hash == after_dry_run_hash,
        "export": exported,
        "token_leak_files": leaks,
        "pass_criteria": {
            "all_commands_ok": all(command["returncode"] == 0 for command in commands),
            "preview_reports_cme_job": len(preview_items) >= 1,
            "dry_run_does_not_change_workspace": before_dry_run_hash == after_dry_run_hash,
            "export_created_files": int(exported.get("file_count", 0)) > 0,
            "token_not_found_in_evidence": not leaks,
        },
    }
    result_path = evidence_dir / "live_confluence_smoke.json"
    write_text(result_path, json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
