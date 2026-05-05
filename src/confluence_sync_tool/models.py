from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_EXPORT_OPTIONS = {
    "cme_scope": "auto",
    "cme_urls": "",
    "cme_cloud_id": "",
    "cme_config_json": "",
    "page_href": "relative",
    "attachment_href": "relative",
    "attachment_export_all": True,
    "page_breadcrumbs": True,
    "page_properties_as_front_matter": True,
    "include_document_title": True,
    "enable_jira_enrichment": False,
    "skip_unchanged": True,
    "cleanup_stale": True,
    "timeout": 30,
    "max_workers": 20,
    "verify_ssl": True,
}


DEFAULT_SCHEDULE = {
    "enabled": False,
    "kind": "daily",
    "times": ["09:00"],
    "days_of_week": [1, 2, 3, 4, 5],
    "day_of_month": None,
    "timezone": "Asia/Seoul",
    "misfire_policy": "skip",
    "concurrency_policy": "skip_if_running",
    "paused": False,
}


def normalize_schedule(value: object) -> dict[str, Any]:
    schedule = dict(DEFAULT_SCHEDULE)
    schedule["times"] = list(DEFAULT_SCHEDULE["times"])
    schedule["days_of_week"] = list(DEFAULT_SCHEDULE["days_of_week"])
    if isinstance(value, dict):
        schedule.update({key: value.get(key) for key in DEFAULT_SCHEDULE if key in value})
        if "times" not in value and value.get("time"):
            schedule["times"] = [str(value["time"])]
    if not isinstance(schedule.get("times"), list):
        schedule["times"] = [str(schedule.get("times") or "09:00")]
    if not isinstance(schedule.get("days_of_week"), list):
        schedule["days_of_week"] = list(DEFAULT_SCHEDULE["days_of_week"])
    return schedule


@dataclass
class Job:
    id: str
    name: str
    confluence_url: str
    target_dir: str
    include_children: bool = True
    include_attachments: bool = False
    enabled: bool = True
    export_options: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_EXPORT_OPTIONS))
    schedule: dict[str, Any] = field(default_factory=lambda: normalize_schedule(None))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Job":
        opts = dict(DEFAULT_EXPORT_OPTIONS)
        opts.update(data.get("export_options") or {})
        schedule = normalize_schedule(data.get("schedule"))
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            confluence_url=str(data["confluence_url"]),
            target_dir=str(data["target_dir"]),
            include_children=bool(data.get("include_children", True)),
            include_attachments=bool(data.get("include_attachments", False)),
            enabled=bool(data.get("enabled", True)),
            export_options=opts,
            schedule=schedule,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def workspace(self) -> Path:
        return Path(self.target_dir)


@dataclass
class PlanItem:
    action: str
    page_id: str | None
    title: str | None
    current_path: str | None
    target_path: str | None
    local_hash: str | None
    reason: str
    safe_to_apply: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SyncPlan:
    schema_version: int
    plan_id: str
    job_id: str
    created_at: str
    scope: str
    urls: list[str]
    local_snapshot_hash: str
    summary: dict[str, int]
    items: list[PlanItem]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["items"] = [item.to_dict() for item in self.items]
        return data
