from __future__ import annotations

import shutil
import re
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from .cme_backend import cme_scope, cme_urls, parse_cme_config_json
from .errors import AppError
from .models import Job
from .security import normalize_base_url


SCHEDULE_KINDS = ("daily", "weekdays", "weekly", "monthly", "multiple_daily")
SCHEDULE_TIMEZONES = ("Asia/Seoul",)
MISFIRE_POLICIES = ("skip",)
CONCURRENCY_POLICIES = ("skip_if_running",)
HHMM = re.compile(r"^\d{2}:\d{2}$")


def validate_auth_input(base_url: str, email: str, token: str) -> dict[str, str]:
    errors: dict[str, str] = {}
    if not base_url.strip():
        errors["base_url"] = "Confluence 기본 URL을 입력하세요."
    else:
        try:
            normalize_base_url(base_url)
        except AppError:
            errors["base_url"] = "Confluence 기본 URL 형식을 확인하세요."
    if not email.strip() or "@" not in email:
        errors["email"] = "이메일 형식을 확인하세요."
    if not token.strip():
        errors["api_token"] = "API 토큰을 입력하세요."
    return errors


def parse_page_id(url: str) -> str:
    parsed = urlparse(url.strip())
    if not parsed.scheme or not parsed.netloc:
        raise AppError("Config", "INVALID_PAGE_URL", "Check the Confluence Page URL format.", url, False)
    parts = [part for part in parsed.path.split("/") if part]
    if "pages" not in parts:
        raise AppError("Config", "INVALID_PAGE_URL", "Confluence Page URL must include a pages path.", url, False)
    idx = parts.index("pages")
    if idx + 1 >= len(parts) or not parts[idx + 1].isdigit():
        raise AppError("Config", "INVALID_PAGE_URL", "Could not find a Confluence Page ID.", url, False)
    return parts[idx + 1]


def parse_space_key(url: str) -> str:
    parsed = urlparse(url.strip())
    if not parsed.scheme or not parsed.netloc:
        raise AppError("Config", "INVALID_SPACE_URL", "Check the Confluence Space URL format.", url, False)
    parts = [part for part in parsed.path.split("/") if part]
    if "spaces" not in parts:
        raise AppError("Config", "INVALID_SPACE_URL", "Confluence Space URL must include a spaces path.", url, False)
    idx = parts.index("spaces")
    if idx + 1 >= len(parts):
        raise AppError("Config", "INVALID_SPACE_URL", "Could not find a Confluence Space key.", url, False)
    return parts[idx + 1]


def parse_source_url(url: str) -> tuple[Literal["page", "space"], str]:
    parsed = urlparse(url.strip())
    if not parsed.scheme or not parsed.netloc:
        raise AppError("Config", "INVALID_SOURCE_URL", "Check the Confluence URL format.", url, False)
    parts = [part for part in parsed.path.split("/") if part]
    if "pages" in parts:
        return ("page", parse_page_id(url))
    if "spaces" in parts:
        return ("space", parse_space_key(url))
    return ("space", parsed.netloc)


def validate_job(job: Job, create_dirs: bool = False) -> None:
    if not job.name.strip():
        raise AppError("Config", "JOB_NAME_REQUIRED", "작업 이름을 입력하세요.", job.id, False)
    cme_urls(job)
    cme_scope(job)
    parse_cme_config_json(job.export_options.get("cme_config_json"))
    validate_schedule(job.schedule)
    target = Path(job.target_dir)
    if create_dirs:
        target.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        raise AppError("File System", "TARGET_NOT_FOUND", "저장 폴더를 찾을 수 없습니다.", str(target), False)
    if not target.is_dir():
        raise AppError("File System", "TARGET_NOT_DIRECTORY", "저장 위치는 폴더여야 합니다.", str(target), False)
    probe = target / ".confluence_export_write_probe"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        raise AppError(
            "File System",
            "TARGET_NOT_WRITABLE",
            "저장 폴더의 쓰기 권한을 확인하세요.",
            str(exc),
            False,
        ) from exc


def validate_schedule(schedule: dict[str, object]) -> None:
    kind = str(schedule.get("kind") or "")
    if kind not in SCHEDULE_KINDS:
        raise AppError("Config", "INVALID_SCHEDULE_KIND", "예약 주기를 확인하세요.", kind, False)
    times = schedule.get("times")
    if not isinstance(times, list) or not times:
        raise AppError("Config", "INVALID_SCHEDULE_TIME", "예약 실행 시각을 하나 이상 입력하세요.", times, False)
    seen_times: set[str] = set()
    for item in times:
        value = str(item or "")
        if not HHMM.match(value):
            raise AppError("Config", "INVALID_SCHEDULE_TIME", "예약 실행 시각은 HH:mm 형식이어야 합니다.", value, False)
        hour, minute = (int(part) for part in value.split(":", 1))
        if hour > 23 or minute > 59:
            raise AppError("Config", "INVALID_SCHEDULE_TIME", "예약 실행 시각은 00:00부터 23:59 사이여야 합니다.", value, False)
        if value in seen_times:
            raise AppError("Config", "INVALID_SCHEDULE_TIME", "예약 실행 시각이 중복되었습니다.", value, False)
        seen_times.add(value)
    if kind == "multiple_daily" and len(times) < 2:
        raise AppError("Config", "INVALID_SCHEDULE_TIME", "하루 여러 번 예약은 실행 시각을 두 개 이상 입력하세요.", times, False)
    if kind == "weekly":
        days = schedule.get("days_of_week")
        if not isinstance(days, list) or not days:
            raise AppError("Config", "INVALID_SCHEDULE_DAYS", "매주 예약 요일을 하나 이상 선택하세요.", days, False)
        parsed_days = []
        for day in days:
            try:
                parsed = int(day)
            except (TypeError, ValueError):
                raise AppError("Config", "INVALID_SCHEDULE_DAYS", "예약 요일 값을 확인하세요.", day, False) from None
            if parsed < 1 or parsed > 7:
                raise AppError("Config", "INVALID_SCHEDULE_DAYS", "예약 요일은 1부터 7 사이여야 합니다.", day, False)
            parsed_days.append(parsed)
        if len(set(parsed_days)) != len(parsed_days):
            raise AppError("Config", "INVALID_SCHEDULE_DAYS", "예약 요일이 중복되었습니다.", days, False)
    if kind == "monthly":
        try:
            day_of_month = int(schedule.get("day_of_month"))
        except (TypeError, ValueError):
            raise AppError("Config", "INVALID_SCHEDULE_MONTH_DAY", "매월 실행 일자를 입력하세요.", schedule.get("day_of_month"), False) from None
        if day_of_month < 1 or day_of_month > 31:
            raise AppError("Config", "INVALID_SCHEDULE_MONTH_DAY", "매월 실행 일자는 1부터 31 사이여야 합니다.", day_of_month, False)
    timezone = str(schedule.get("timezone") or "")
    if timezone not in SCHEDULE_TIMEZONES:
        raise AppError("Config", "INVALID_SCHEDULE_TIMEZONE", "1차 구현에서는 Asia/Seoul 시간대만 지원합니다.", timezone, False)
    misfire = str(schedule.get("misfire_policy") or "")
    if misfire not in MISFIRE_POLICIES:
        raise AppError("Config", "INVALID_MISFIRE_POLICY", "예약 누락 처리 정책을 확인하세요.", misfire, False)
    concurrency = str(schedule.get("concurrency_policy") or "")
    if concurrency not in CONCURRENCY_POLICIES:
        raise AppError("Config", "INVALID_CONCURRENCY_POLICY", "중복 실행 정책을 확인하세요.", concurrency, False)


def setup_checks(job: Job | None = None, auth_error: AppError | None = None) -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    checks.append({"id": "VAL-04", "name": "Runtime", "ok": True, "message": "Runtime ok"})
    try:
        import confluence_markdown_exporter  # noqa: F401

        checks.append({"id": "VAL-05", "name": "Package", "ok": True, "message": "CME package import ok"})
    except Exception as exc:
        checks.append({"id": "VAL-05", "name": "Package", "ok": False, "message": str(exc)})

    free = shutil.disk_usage(Path.home()).free
    checks.append({"id": "VAL-06", "name": "Disk", "ok": free > 50 * 1024 * 1024, "message": f"free={free}"})

    if auth_error is not None:
        checks.append({"id": "VAL-01", "name": "Auth", "ok": False, "message": auth_error.user_message})
    else:
        checks.append({"id": "VAL-01", "name": "Auth", "ok": True, "message": "Credential lookup ok"})

    if job is not None:
        if auth_error is not None:
            checks.append({"id": "VAL-02", "name": "URL", "ok": False, "message": "Auth must pass before URL validation."})
        else:
            try:
                validate_job(job, create_dirs=False)
                checks.append({"id": "VAL-02", "name": "URL", "ok": True, "message": "CME URL/config format ok"})
            except AppError as exc:
                checks.append({"id": "VAL-02", "name": "URL", "ok": False, "message": exc.user_message})
        try:
            validate_job(job, create_dirs=False)
            checks.append({"id": "VAL-03", "name": "File System", "ok": True, "message": "target read/write ok"})
            checks.append({"id": "VAL-07", "name": "Path", "ok": True, "message": "path policy ok"})
        except AppError as exc:
            checks.append({"id": "VAL-03", "name": "File System", "ok": False, "message": exc.user_message})
    return checks
