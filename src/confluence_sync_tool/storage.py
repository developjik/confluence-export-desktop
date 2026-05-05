from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from .errors import AppError
from .fs_policy import atomic_write_text, sanitize_component
from .models import Job
from .paths import app_config_dir, app_log_dir, jobs_file, scheduler_events_file, workspace_log_dir
from .security import mask_sensitive
from .timeutil import now_iso


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AppError(
            "Config",
            "JSON_INVALID",
            f"{path.name} 파일 형식을 확인하세요.",
            str(exc),
            False,
        ) from exc


def write_json(path: Path, data: Any) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    atomic_write_text(path, text)


def settings_path(config_dir: Path | None = None) -> Path:
    return (config_dir or app_config_dir()) / "settings.json"


def load_settings(config_dir: Path | None = None) -> dict[str, Any]:
    defaults = {
        "schema_version": 1,
        "base_url": "",
        "email": "",
        "schedule_paused": False,
        "auto_start": False,
        "global_worker_limit": 1,
    }
    data = read_json(settings_path(config_dir), defaults)
    defaults.update(data if isinstance(data, dict) else {})
    return defaults


def save_settings(base_url: str, email: str, config_dir: Path | None = None) -> None:
    path = settings_path(config_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = load_settings(config_dir)
    data.update({"schema_version": 1, "base_url": base_url, "email": email})
    write_json(path, data)


def save_app_setting(key: str, value: Any, config_dir: Path | None = None) -> None:
    path = settings_path(config_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = load_settings(config_dir)
    data[key] = value
    write_json(path, data)


def stable_job_id(name: str, existing_ids: set[str]) -> str:
    base = sanitize_component(name, "job").lower()
    base = re.sub(r"[^a-z0-9_-]+", "-", base).strip("-") or "job"
    candidate = base
    while candidate in existing_ids:
        candidate = f"{base}-{uuid.uuid4().hex[:8]}"
    return candidate


class JobStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or jobs_file()

    def load(self) -> list[Job]:
        data = read_json(self.path, {"schema_version": 1, "jobs": []})
        return [Job.from_dict(item) for item in data.get("jobs", [])]

    def save_all(self, jobs: list[Job]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        write_json(self.path, {"schema_version": 1, "jobs": [job.to_dict() for job in jobs]})

    def upsert(self, job: Job) -> None:
        jobs = self.load()
        for idx, existing in enumerate(jobs):
            if existing.id == job.id:
                jobs[idx] = job
                self.save_all(jobs)
                return
        jobs.append(job)
        self.save_all(jobs)

    def delete(self, job_id: str) -> None:
        self.save_all([job for job in self.load() if job.id != job_id])

    def get(self, job_id: str) -> Job:
        for job in self.load():
            if job.id == job_id:
                return job
        raise AppError("Config", "JOB_NOT_FOUND", "Job을 찾을 수 없습니다.", job_id, False)


def run_history_path(job: Job) -> Path:
    return job.workspace / "run_history.json"


def load_run_history(job: Job) -> dict[str, Any]:
    return read_json(run_history_path(job), {"schema_version": 1, "runs": []})


def append_run_history(job: Job, run: dict[str, Any]) -> None:
    history = load_run_history(job)
    history.setdefault("schema_version", 1)
    history.setdefault("runs", []).append(run)
    write_json(run_history_path(job), history)


def rotate_log_if_needed(path: Path, max_bytes: int, backups: int) -> None:
    if not path.exists() or path.stat().st_size <= max_bytes:
        return
    for idx in range(backups, 0, -1):
        src = path.with_name(f"{path.name}.{idx}")
        dst = path.with_name(f"{path.name}.{idx + 1}")
        if idx == backups and src.exists():
            src.unlink()
        elif src.exists():
            src.replace(dst)
    path.replace(path.with_name(f"{path.name}.1"))


def append_log_line(path: Path, message: str, max_bytes: int = 1_000_000, backups: int = 3) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rotate_log_if_needed(path, max_bytes, backups)
    line = f"{now_iso()} {mask_sensitive(message)}\n"
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(line)


def append_app_log(message: str, max_bytes: int = 1_000_000, backups: int = 3) -> None:
    append_log_line(app_log_dir() / "app.log", message, max_bytes=max_bytes, backups=backups)


def append_job_log(job: Job, message: str, max_bytes: int = 1_000_000, backups: int = 3) -> None:
    append_log_line(workspace_log_dir(job.workspace) / "app.log", message, max_bytes=max_bytes, backups=backups)


def append_scheduler_event(event: dict[str, Any], max_bytes: int = 1_000_000, backups: int = 3, path: Path | None = None) -> None:
    target = path or scheduler_events_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    rotate_log_if_needed(target, max_bytes, backups)
    safe_event = {key: mask_sensitive(value) if isinstance(value, str) else value for key, value in event.items()}
    line = json.dumps(safe_event, ensure_ascii=False, sort_keys=True) + "\n"
    with target.open("a", encoding="utf-8", newline="\n") as f:
        f.write(line)


def load_scheduler_events(limit: int = 50, path: Path | None = None) -> list[dict[str, Any]]:
    target = path or scheduler_events_file()
    if not target.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in target.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            rows.append(data)
    return rows
