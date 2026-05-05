from __future__ import annotations

import threading
import uuid
import calendar
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, TypeVar

from .errors import AppError, classify_exception
from .models import Job
from .storage import append_app_log, append_scheduler_event


KOREA_TZ = timezone(timedelta(hours=9), "KST")
SCHEDULER_EVENT_TYPES = {
    "scheduled_due",
    "scheduled_started",
    "scheduled_completed",
    "scheduled_failed",
    "scheduled_skipped_already_running",
    "scheduled_misfired_skipped",
}

T = TypeVar("T")


def korea_now() -> datetime:
    return datetime.now(KOREA_TZ)


def parse_schedule_time(value: str) -> tuple[int, int]:
    hour_text, minute_text = value.split(":", 1)
    return int(hour_text), int(minute_text)


def schedule_times(schedule: dict[str, object]) -> list[tuple[int, int]]:
    values = schedule.get("times")
    if not isinstance(values, list) or not values:
        values = [schedule.get("time") or "09:00"]
    parsed = sorted({parse_schedule_time(str(value)) for value in values})
    return parsed


def schedule_matches_date(job: Job, day: datetime) -> bool:
    schedule = job.schedule
    kind = str(schedule.get("kind") or "daily")
    if kind in {"daily", "multiple_daily"}:
        return True
    if kind == "weekdays":
        return day.weekday() < 5
    if kind == "weekly":
        days = schedule.get("days_of_week")
        if not isinstance(days, list) or not days:
            return False
        return (day.weekday() + 1) in {int(item) for item in days}
    if kind == "monthly":
        day_of_month = schedule.get("day_of_month")
        if day_of_month is None:
            return False
        target_day = int(day_of_month)
        last_day = calendar.monthrange(day.year, day.month)[1]
        return target_day <= last_day and day.day == target_day
    return False


def schedule_occurrences_between(job: Job, start: datetime, end: datetime) -> list[datetime]:
    if not job.enabled or not bool(job.schedule.get("enabled")) or bool(job.schedule.get("paused")):
        return []
    start = start.astimezone(KOREA_TZ)
    end = end.astimezone(KOREA_TZ)
    current_day = start.replace(hour=0, minute=0, second=0, microsecond=0)
    end_day = end.replace(hour=0, minute=0, second=0, microsecond=0)
    occurrences: list[datetime] = []
    while current_day <= end_day:
        if schedule_matches_date(job, current_day):
            for hour, minute in schedule_times(job.schedule):
                candidate = current_day.replace(hour=hour, minute=minute)
                if start < candidate <= end:
                    occurrences.append(candidate)
        current_day += timedelta(days=1)
    return sorted(occurrences)


def next_run_at(job: Job, now: datetime | None = None) -> datetime | None:
    if not job.enabled or not bool(job.schedule.get("enabled")) or bool(job.schedule.get("paused")):
        return None
    current = (now or korea_now()).astimezone(KOREA_TZ)
    horizon = current + timedelta(days=400)
    occurrences = schedule_occurrences_between(job, current, horizon)
    return occurrences[0] if occurrences else None


def is_due(job: Job, now: datetime | None = None) -> bool:
    current = (now or korea_now()).astimezone(KOREA_TZ)
    scheduled = next_run_at(job, current - timedelta(days=1))
    return scheduled is not None and scheduled <= current


def scheduler_event(
    job_id: str,
    event_type: str,
    scheduled_at: datetime | None,
    result: str,
    *,
    observed_at: datetime | None = None,
    run_id: str | None = None,
    message: str = "",
) -> dict[str, object]:
    if event_type not in SCHEDULER_EVENT_TYPES:
        raise AppError("Config", "INVALID_SCHEDULER_EVENT", "Scheduler event type을 확인하세요.", event_type, False)
    observed = observed_at or korea_now()
    return {
        "event_id": f"scheduled-{uuid.uuid4().hex[:12]}",
        "job_id": job_id,
        "event_type": event_type,
        "scheduled_at": scheduled_at.astimezone(KOREA_TZ).isoformat(timespec="seconds") if scheduled_at else None,
        "observed_at": observed.astimezone(KOREA_TZ).isoformat(timespec="seconds"),
        "result": result,
        "run_id": run_id,
        "message": message,
    }


def record_scheduler_event(event: dict[str, object]) -> None:
    append_scheduler_event(event)
    append_app_log(
        "scheduler_event "
        f"job_id={event.get('job_id')} "
        f"type={event.get('event_type')} "
        f"result={event.get('result')} "
        f"scheduled_at={event.get('scheduled_at')}"
    )


@dataclass
class RunCoordinator:
    global_worker_limit: int = 1

    def __post_init__(self) -> None:
        self._lock = threading.Lock()
        self._running_jobs: set[str] = set()
        self._active_count = 0

    @property
    def active_count(self) -> int:
        with self._lock:
            return self._active_count

    def is_running(self, job_id: str | None = None) -> bool:
        with self._lock:
            if job_id is None:
                return self._active_count > 0
            return job_id in self._running_jobs

    def try_acquire(self, job_id: str) -> bool:
        with self._lock:
            if job_id in self._running_jobs:
                return False
            if self._active_count >= max(1, self.global_worker_limit):
                return False
            self._running_jobs.add(job_id)
            self._active_count += 1
            return True

    def release(self, job_id: str) -> None:
        with self._lock:
            if job_id in self._running_jobs:
                self._running_jobs.remove(job_id)
                self._active_count = max(0, self._active_count - 1)

    def run(self, job: Job, work: Callable[[], T]) -> T:
        if not self.try_acquire(job.id):
            raise AppError("Conflict", "JOB_ALREADY_RUNNING", "이미 실행 중인 작업입니다.", job.id, True)
        try:
            return work()
        finally:
            self.release(job.id)


class SchedulerRuntime:
    def __init__(
        self,
        load_jobs: Callable[[], list[Job]],
        run_job: Callable[[Job], dict[str, object]],
        *,
        coordinator: RunCoordinator | None = None,
        tick_seconds: int = 30,
        misfire_grace_seconds: int = 120,
        schedule_paused: Callable[[], bool] | None = None,
        notify_failure: Callable[[Job, Exception], None] | None = None,
    ) -> None:
        self.load_jobs = load_jobs
        self.run_job = run_job
        self.coordinator = coordinator or RunCoordinator()
        self.tick_seconds = max(1, tick_seconds)
        self.misfire_grace_seconds = max(0, misfire_grace_seconds)
        self.schedule_paused = schedule_paused or (lambda: False)
        self.notify_failure = notify_failure
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_due_key: set[tuple[str, str]] = set()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="ConfluenceSyncScheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.wait(self.tick_seconds):
            self.tick()

    def tick(self, now: datetime | None = None) -> None:
        if self.schedule_paused():
            return
        observed = (now or korea_now()).astimezone(KOREA_TZ)
        for job in self.load_jobs():
            if not job.enabled or not bool(job.schedule.get("enabled")) or bool(job.schedule.get("paused")):
                continue
            for scheduled in schedule_occurrences_between(job, observed - timedelta(days=1), observed):
                due_key = (job.id, scheduled.isoformat(timespec="seconds"))
                if due_key in self._last_due_key:
                    continue
                self._last_due_key.add(due_key)
                record_scheduler_event(scheduler_event(job.id, "scheduled_due", scheduled, "due", observed_at=observed))
                if observed - scheduled > timedelta(seconds=self.misfire_grace_seconds):
                    record_scheduler_event(scheduler_event(job.id, "scheduled_misfired_skipped", scheduled, "skipped", observed_at=observed))
                    continue
                if not self.coordinator.try_acquire(job.id):
                    record_scheduler_event(
                        scheduler_event(job.id, "scheduled_skipped_already_running", scheduled, "skipped", observed_at=observed)
                    )
                    continue
                threading.Thread(target=self._run_due_job, args=(job, scheduled), daemon=True).start()

    def _run_due_job(self, job: Job, scheduled: datetime) -> None:
        run_id = None
        record_scheduler_event(scheduler_event(job.id, "scheduled_started", scheduled, "started"))
        try:
            run = self.run_job(job)
            run_id = str(run.get("run_id") or "")
            record_scheduler_event(scheduler_event(job.id, "scheduled_completed", scheduled, "success", run_id=run_id))
        except Exception as exc:
            error = classify_exception(exc)
            record_scheduler_event(scheduler_event(job.id, "scheduled_failed", scheduled, "failed", message=error.user_message))
            if self.notify_failure:
                self.notify_failure(job, exc)
        finally:
            self.coordinator.release(job.id)
