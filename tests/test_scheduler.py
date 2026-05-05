from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from confluence_sync_tool.models import DEFAULT_SCHEDULE, Job, normalize_schedule
from confluence_sync_tool.scheduler import KOREA_TZ, RunCoordinator, SchedulerRuntime, next_run_at, scheduler_event
from confluence_sync_tool.storage import append_scheduler_event, load_scheduler_events
from confluence_sync_tool.validation import validate_schedule

from tests.helpers import make_job, temp_workspace


class SchedulerTests(unittest.TestCase):
    def test_schedule_defaults_round_trip_as_disabled(self):
        job = Job.from_dict(
            {
                "id": "a",
                "name": "A",
                "confluence_url": "https://company.atlassian.net/wiki/pages/123456",
                "target_dir": "C:\\tmp",
            }
        )
        self.assertEqual(job.schedule, DEFAULT_SCHEDULE)
        self.assertFalse(job.schedule["enabled"])

    def test_next_run_daily_and_weekdays_use_korea_time(self):
        with temp_workspace() as root:
            job = make_job(root)
            job.schedule.update({"enabled": True, "kind": "daily", "times": ["09:00"]})
            now = datetime(2026, 5, 5, 8, 30, tzinfo=KOREA_TZ)
            self.assertEqual(next_run_at(job, now), datetime(2026, 5, 5, 9, 0, tzinfo=KOREA_TZ))
            now = datetime(2026, 5, 5, 9, 1, tzinfo=KOREA_TZ)
            self.assertEqual(next_run_at(job, now), datetime(2026, 5, 6, 9, 0, tzinfo=KOREA_TZ))
            job.schedule["kind"] = "weekdays"
            now = datetime(2026, 5, 8, 10, 0, tzinfo=KOREA_TZ)
            self.assertEqual(next_run_at(job, now), datetime(2026, 5, 11, 9, 0, tzinfo=KOREA_TZ))

    def test_next_run_multiple_daily_uses_nearest_time(self):
        with temp_workspace() as root:
            job = make_job(root)
            job.schedule.update({"enabled": True, "kind": "multiple_daily", "times": ["09:00", "13:00", "18:00"]})
            self.assertEqual(
                next_run_at(job, datetime(2026, 5, 5, 8, 30, tzinfo=KOREA_TZ)),
                datetime(2026, 5, 5, 9, 0, tzinfo=KOREA_TZ),
            )
            self.assertEqual(
                next_run_at(job, datetime(2026, 5, 5, 9, 1, tzinfo=KOREA_TZ)),
                datetime(2026, 5, 5, 13, 0, tzinfo=KOREA_TZ),
            )
            self.assertEqual(
                next_run_at(job, datetime(2026, 5, 5, 18, 1, tzinfo=KOREA_TZ)),
                datetime(2026, 5, 6, 9, 0, tzinfo=KOREA_TZ),
            )

    def test_next_run_weekly_selected_days(self):
        with temp_workspace() as root:
            job = make_job(root)
            job.schedule.update({"enabled": True, "kind": "weekly", "times": ["09:00"], "days_of_week": [1, 3, 5]})
            self.assertEqual(
                next_run_at(job, datetime(2026, 5, 5, 10, 0, tzinfo=KOREA_TZ)),
                datetime(2026, 5, 6, 9, 0, tzinfo=KOREA_TZ),
            )
            self.assertEqual(
                next_run_at(job, datetime(2026, 5, 8, 9, 1, tzinfo=KOREA_TZ)),
                datetime(2026, 5, 11, 9, 0, tzinfo=KOREA_TZ),
            )

    def test_next_run_monthly_31_skips_missing_month(self):
        with temp_workspace() as root:
            job = make_job(root)
            job.schedule.update({"enabled": True, "kind": "monthly", "times": ["09:00"], "day_of_month": 31})
            self.assertEqual(
                next_run_at(job, datetime(2026, 2, 1, 0, 0, tzinfo=KOREA_TZ)),
                datetime(2026, 3, 31, 9, 0, tzinfo=KOREA_TZ),
            )

    def test_old_schedule_time_is_migrated_to_times(self):
        schedule = normalize_schedule({"enabled": True, "kind": "daily", "time": "10:30"})
        self.assertEqual(schedule["times"], ["10:30"])
        self.assertNotIn("time", schedule)

    def test_validate_schedule_rejects_bad_time(self):
        schedule = normalize_schedule(None)
        schedule["times"] = ["24:00"]
        with self.assertRaisesRegex(Exception, "INVALID_SCHEDULE_TIME"):
            validate_schedule(schedule)

    def test_validate_schedule_rejects_bad_weekly_and_monthly_values(self):
        weekly = normalize_schedule({"kind": "weekly", "times": ["09:00"], "days_of_week": [1, 8]})
        with self.assertRaisesRegex(Exception, "INVALID_SCHEDULE_DAYS"):
            validate_schedule(weekly)
        monthly = normalize_schedule({"kind": "monthly", "times": ["09:00"], "day_of_month": 32})
        with self.assertRaisesRegex(Exception, "INVALID_SCHEDULE_MONTH_DAY"):
            validate_schedule(monthly)

    def test_run_coordinator_blocks_same_job_and_global_limit(self):
        coordinator = RunCoordinator(global_worker_limit=1)
        self.assertTrue(coordinator.try_acquire("a"))
        self.assertFalse(coordinator.try_acquire("a"))
        self.assertFalse(coordinator.try_acquire("b"))
        coordinator.release("a")
        self.assertTrue(coordinator.try_acquire("b"))
        coordinator.release("b")

    def test_scheduler_event_jsonl_masks_and_loads(self):
        old_appdata = os.environ.get("APPDATA")
        with temp_workspace() as root:
            os.environ["APPDATA"] = str(Path(root) / "appdata")
            try:
                event = scheduler_event(
                    "job-a",
                    "scheduled_due",
                    datetime(2026, 5, 5, 9, 0, tzinfo=KOREA_TZ),
                    "token=sentinel-secret-token",
                )
                append_scheduler_event(event)
                rows = load_scheduler_events()
                self.assertEqual(rows[-1]["job_id"], "job-a")
                self.assertNotIn("sentinel-secret-token", (Path(os.environ["APPDATA"]) / "ConfluenceSync" / "app" / "scheduler_events.jsonl").read_text())
            finally:
                if old_appdata is None:
                    os.environ.pop("APPDATA", None)
                else:
                    os.environ["APPDATA"] = old_appdata

    def test_scheduler_runtime_skips_already_running_job(self):
        with temp_workspace() as root:
            appdata = Path(root) / "appdata"
            old_appdata = os.environ.get("APPDATA")
            os.environ["APPDATA"] = str(appdata)
            try:
                job = make_job(root)
                job.schedule.update({"enabled": True, "kind": "daily", "times": ["09:00"]})
                coordinator = RunCoordinator(global_worker_limit=1)
                self.assertTrue(coordinator.try_acquire(job.id))
                runtime = SchedulerRuntime(lambda: [job], lambda _job: {}, coordinator=coordinator)
                runtime.tick(datetime(2026, 5, 5, 9, 1, tzinfo=KOREA_TZ))
                events = load_scheduler_events()
                self.assertTrue(any(event["event_type"] == "scheduled_skipped_already_running" for event in events))
                coordinator.release(job.id)
            finally:
                if old_appdata is None:
                    os.environ.pop("APPDATA", None)
                else:
                    os.environ["APPDATA"] = old_appdata

    def test_scheduler_runtime_records_misfire_skip(self):
        with temp_workspace() as root:
            appdata = Path(root) / "appdata"
            old_appdata = os.environ.get("APPDATA")
            os.environ["APPDATA"] = str(appdata)
            try:
                job = make_job(root)
                job.schedule.update({"enabled": True, "kind": "daily", "times": ["09:00"]})
                calls = []
                runtime = SchedulerRuntime(lambda: [job], lambda _job: calls.append(_job.id), misfire_grace_seconds=60)
                runtime.tick(datetime(2026, 5, 5, 10, 30, tzinfo=KOREA_TZ))
                events = load_scheduler_events()
                self.assertFalse(calls)
                self.assertTrue(any(event["event_type"] == "scheduled_misfired_skipped" for event in events))
            finally:
                if old_appdata is None:
                    os.environ.pop("APPDATA", None)
                else:
                    os.environ["APPDATA"] = old_appdata


if __name__ == "__main__":
    unittest.main()
