from __future__ import annotations

import os
from pathlib import Path


APP_NAME = "ConfluenceExportDesktop"
WORKSPACE_LOG_DIR_NAME = ".logs"


def app_config_dir() -> Path:
    root = os.environ.get("APPDATA")
    if root:
        return Path(root) / APP_NAME / "app"
    return Path.home() / ".config" / APP_NAME / "app"


def app_log_dir() -> Path:
    root = os.environ.get("APPDATA")
    if root:
        return Path(root) / APP_NAME / "logs"
    return Path.home() / ".local" / "state" / APP_NAME / "logs"


def workspace_log_dir(workspace: Path) -> Path:
    return workspace / WORKSPACE_LOG_DIR_NAME


def scheduler_events_file(config_dir: Path | None = None) -> Path:
    return (config_dir or app_config_dir()) / "scheduler_events.jsonl"


def default_workspace() -> Path:
    return Path.home() / "Documents" / APP_NAME


def jobs_file(config_dir: Path | None = None) -> Path:
    return (config_dir or app_config_dir()) / "jobs.json"


def ensure_app_dirs() -> None:
    app_config_dir().mkdir(parents=True, exist_ok=True)
    app_log_dir().mkdir(parents=True, exist_ok=True)
    default_workspace().mkdir(parents=True, exist_ok=True)
