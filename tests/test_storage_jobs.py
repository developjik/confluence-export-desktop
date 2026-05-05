from __future__ import annotations

import unittest
from pathlib import Path

from confluence_sync_tool.models import Job
from confluence_sync_tool.storage import JobStore, stable_job_id

from tests.helpers import temp_workspace


class StorageJobTests(unittest.TestCase):
    def test_ut_job_01_same_name_gets_unique_ids(self):
        first = stable_job_id("Product Docs", set())
        second = stable_job_id("Product Docs", {first})
        self.assertNotEqual(first, second)

    def test_e2e_job_01_jobs_persist_after_reload(self):
        with temp_workspace() as root:
            path = Path(root) / "jobs.json"
            store = JobStore(path)
            job = Job("product-docs", "Product Docs", "https://company.atlassian.net/wiki/pages/123456", str(Path(root) / "job"))
            store.upsert(job)
            reloaded = JobStore(path).load()
            self.assertEqual(len(reloaded), 1)
            self.assertEqual(reloaded[0].id, "product-docs")

    def test_fr_job_01_upsert_updates_existing_job(self):
        with temp_workspace() as root:
            path = Path(root) / "jobs.json"
            store = JobStore(path)
            first_target = Path(root) / "job-a"
            second_target = Path(root) / "job-b"
            store.upsert(Job("product-docs", "Product Docs", "https://company.atlassian.net/wiki/pages/123456", str(first_target)))
            store.upsert(Job("product-docs", "Updated Docs", "https://company.atlassian.net/wiki/pages/789000", str(second_target), include_children=False))
            reloaded = store.load()
            self.assertEqual(len(reloaded), 1)
            self.assertEqual(reloaded[0].name, "Updated Docs")
            self.assertEqual(reloaded[0].target_dir, str(second_target))
            self.assertFalse(reloaded[0].include_children)

    def test_data_jobs_01_export_options_round_trip(self):
        with temp_workspace() as root:
            path = Path(root) / "jobs.json"
            store = JobStore(path)
            job = Job(
                "product-docs",
                "Product Docs",
                "https://company.atlassian.net/wiki/pages/123456",
                str(Path(root) / "job"),
                export_options={
                    "cme_scope": "pages",
                    "page_href": "wiki",
                    "attachment_href": "absolute",
                    "attachment_export_all": True,
                    "page_breadcrumbs": False,
                    "cleanup_stale": False,
                    "timeout": 11,
                },
            )
            store.upsert(job)
            reloaded = JobStore(path).load()[0]
            self.assertEqual(reloaded.export_options["cme_scope"], "pages")
            self.assertEqual(reloaded.export_options["page_href"], "wiki")
            self.assertEqual(reloaded.export_options["attachment_href"], "absolute")
            self.assertTrue(reloaded.export_options["attachment_export_all"])
            self.assertFalse(reloaded.export_options["page_breadcrumbs"])
            self.assertFalse(reloaded.export_options["cleanup_stale"])
            self.assertEqual(reloaded.export_options["timeout"], 11)

    def test_ut_job_03_enabled_is_stored_but_not_scheduler(self):
        job = Job("a", "A", "https://company.atlassian.net/wiki/pages/123456", "C:\\tmp", enabled=False)
        self.assertFalse(job.enabled)

    def test_data_jobs_02_schedule_round_trip(self):
        with temp_workspace() as root:
            path = Path(root) / "jobs.json"
            store = JobStore(path)
            job = Job(
                "product-docs",
                "Product Docs",
                "https://company.atlassian.net/wiki/pages/123456",
                str(Path(root) / "job"),
                schedule={
                    "enabled": True,
                    "kind": "weekly",
                    "times": ["09:30", "18:00"],
                    "days_of_week": [1, 3, 5],
                    "day_of_month": None,
                    "timezone": "Asia/Seoul",
                },
            )
            store.upsert(job)
            reloaded = JobStore(path).load()[0]
            self.assertTrue(reloaded.schedule["enabled"])
            self.assertEqual(reloaded.schedule["kind"], "weekly")
            self.assertEqual(reloaded.schedule["times"], ["09:30", "18:00"])
            self.assertEqual(reloaded.schedule["days_of_week"], [1, 3, 5])
            self.assertIsNone(reloaded.schedule["day_of_month"])
            self.assertEqual(reloaded.schedule["misfire_policy"], "skip")

    def test_data_jobs_03_old_schedule_time_migrates_after_reload(self):
        with temp_workspace() as root:
            path = Path(root) / "jobs.json"
            store = JobStore(path)
            job = Job(
                "product-docs",
                "Product Docs",
                "https://company.atlassian.net/wiki/pages/123456",
                str(Path(root) / "job"),
                schedule={"enabled": True, "kind": "daily", "time": "10:15", "timezone": "Asia/Seoul"},
            )
            store.upsert(job)
            reloaded = JobStore(path).load()[0]
            self.assertEqual(reloaded.schedule["times"], ["10:15"])
            self.assertNotIn("time", reloaded.schedule)


if __name__ == "__main__":
    unittest.main()
