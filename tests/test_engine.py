from __future__ import annotations

import os
import unittest
from pathlib import Path

from confluence_sync_tool.cme_backend import CmeExportResult
from confluence_sync_tool.engine import SyncEngine
from confluence_sync_tool.errors import AppError
from confluence_sync_tool.hashing import tree_hash
from confluence_sync_tool.paths import workspace_log_dir
from confluence_sync_tool.storage import load_run_history

from tests.helpers import make_job, temp_workspace


class EngineTests(unittest.TestCase):
    def fake_exporter(self, exported: int = 1, skipped: int = 0, removed: int = 0):
        def exporter(job, progress):
            if progress:
                progress("fake cme started", 0, 1)
                progress("fake cme finished", 1, 1)
            return CmeExportResult(
                command="pages-with-descendants",
                urls=[job.confluence_url],
                output_path=str(job.workspace),
                stats={"exported": exported, "skipped": skipped, "failed": 0, "removed": removed},
            )

        return exporter

    def test_dry_run_does_not_mutate_workspace(self):
        with temp_workspace() as root:
            job = make_job(root)
            engine = SyncEngine(cme_exporter=self.fake_exporter())
            before = tree_hash(job.workspace)
            plan = engine.dry_run(job)
            after = tree_hash(job.workspace)
            self.assertEqual(before, after)
            self.assertEqual(plan.summary["update"], 1)
            self.assertIn("CME", plan.items[0].reason)

    def test_dry_run_writes_only_app_log_outside_workspace(self):
        old_appdata = os.environ.get("APPDATA")
        with temp_workspace() as root:
            appdata = Path(root) / "appdata"
            os.environ["APPDATA"] = str(appdata)
            try:
                job = make_job(root)
                engine = SyncEngine(cme_exporter=self.fake_exporter())
                before = tree_hash(job.workspace)
                engine.dry_run(job)
                after = tree_hash(job.workspace)
                self.assertEqual(before, after)
                app_log = appdata / "ConfluenceSync" / "logs" / "app.log"
                self.assertTrue(app_log.exists())
                self.assertIn("mode=dry_run", app_log.read_text(encoding="utf-8"))
                self.assertFalse((workspace_log_dir(job.workspace) / "app.log").exists())
            finally:
                if old_appdata is None:
                    os.environ.pop("APPDATA", None)
                else:
                    os.environ["APPDATA"] = old_appdata

    def test_apply_records_cme_run_history(self):
        with temp_workspace() as root:
            job = make_job(root)
            engine = SyncEngine(cme_exporter=self.fake_exporter(exported=3, skipped=2, removed=1))
            run = engine.apply(job)
            self.assertEqual(run["status"], "success")
            self.assertEqual(run["mode"], "cme_apply")
            self.assertEqual(run["summary"], {"created": 3, "updated": 0, "deleted": 1, "skipped": 2, "errors": 0})
            history = load_run_history(job)
            self.assertEqual(history["schema_version"], 1)
            self.assertEqual(history["runs"][-1]["cme"]["stats"]["exported"], 3)
            self.assertEqual(history["runs"][-1]["cme"]["stats"]["removed"], 1)

    def test_apply_records_trigger_for_scheduled_runs(self):
        with temp_workspace() as root:
            job = make_job(root)
            engine = SyncEngine(cme_exporter=self.fake_exporter())
            run = engine.apply(job, trigger="scheduled")
            self.assertEqual(run["trigger"], "scheduled")
            self.assertEqual(load_run_history(job)["runs"][-1]["trigger"], "scheduled")

    def test_apply_failure_records_error_and_raises(self):
        with temp_workspace() as root:
            job = make_job(root)

            def failing_exporter(job, progress):
                raise AppError("Confluence API", "CME_EXPORT_FAILED", "CME failed.", "fixture", True)

            engine = SyncEngine(cme_exporter=failing_exporter)
            with self.assertRaises(AppError) as ctx:
                engine.apply(job)
            self.assertEqual(ctx.exception.code, "CME_EXPORT_FAILED")
            run = load_run_history(job)["runs"][-1]
            self.assertEqual(run["status"], "failed")
            self.assertEqual(run["error"]["category"], "Confluence API")
            self.assertEqual(run["summary"]["errors"], 1)
            self.assertIn("status=failed", (workspace_log_dir(job.workspace) / "app.log").read_text(encoding="utf-8"))

    def test_progress_callback_receives_cme_events(self):
        with temp_workspace() as root:
            job = make_job(root)
            events: list[tuple[str, int, int]] = []
            engine = SyncEngine(
                progress=lambda message, done, total: events.append((message, done, total)),
                cme_exporter=self.fake_exporter(),
            )
            engine.apply(job)
            self.assertIn(("fake cme started", 0, 1), events)
            self.assertIn(("fake cme finished", 1, 1), events)


if __name__ == "__main__":
    unittest.main()
