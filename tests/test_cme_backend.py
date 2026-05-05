from __future__ import annotations

import json
import unittest
from pathlib import Path

from confluence_sync_tool.cme_backend import CmeExportResult, build_cme_config, default_cme_config_json
from confluence_sync_tool.engine import SyncEngine
from confluence_sync_tool.models import DEFAULT_EXPORT_OPTIONS, Job
from confluence_sync_tool.storage import load_run_history
from confluence_sync_tool.validation import validate_job

from tests.helpers import temp_workspace


class CmeBackendTests(unittest.TestCase):
    def make_cme_job(self, root: str | Path, **options: object) -> Job:
        target = Path(root) / "cme-job"
        target.mkdir(parents=True)
        export_options = dict(DEFAULT_EXPORT_OPTIONS)
        export_options.update(
            {
                "cme_scope": "orgs",
                "cme_urls": "https://company.atlassian.net",
                "cme_config_json": default_cme_config_json(str(target)),
            }
        )
        export_options.update(options)
        return Job("cme", "CME", "https://company.atlassian.net", str(target), export_options=export_options)

    def test_default_cme_config_exposes_known_export_and_connection_options(self):
        config = json.loads(default_cme_config_json("C:/docs"))
        for key in {
            "log_level",
            "output_path",
            "page_href",
            "page_path",
            "attachment_href",
            "attachment_path",
            "attachment_export_all",
            "page_breadcrumbs",
            "page_properties_as_front_matter",
            "filename_encoding",
            "filename_length",
            "filename_lowercase",
            "include_document_title",
            "enable_jira_enrichment",
            "skip_unchanged",
            "cleanup_stale",
            "lockfile_name",
            "existence_check_batch_size",
        }:
            self.assertIn(key, config["export"])
        for key in {
            "backoff_and_retry",
            "backoff_factor",
            "max_backoff_seconds",
            "max_backoff_retries",
            "retry_status_codes",
            "verify_ssl",
            "timeout",
            "use_v2_api",
            "max_workers",
        }:
            self.assertIn(key, config["connection_config"])
        self.assertTrue(config["export"]["attachment_export_all"])
        self.assertFalse(config["export"]["include_document_title"])
        self.assertFalse(config["export"]["enable_jira_enrichment"])

    def test_build_cme_config_merges_common_and_advanced_options_and_injects_credential(self):
        with temp_workspace() as root:
            job = self.make_cme_job(
                root,
                page_href="wiki",
                attachment_href="absolute",
                attachment_export_all=True,
                timeout=9,
                max_workers=2,
                cme_config_json=json.dumps(
                    {
                        "export": {"page_href": "absolute", "page_path": "{space_key}/{page_id}.md"},
                        "connection_config": {"timeout": 11, "max_workers": 3},
                    }
                ),
            )
            config = build_cme_config(
                job,
                "secret-token",
                {"base_url": "https://company.atlassian.net", "email": "user@example.com"},
            )
            self.assertEqual(config["export"]["page_href"], "absolute")
            self.assertEqual(config["export"]["attachment_href"], "absolute")
            self.assertTrue(config["export"]["attachment_export_all"])
            self.assertEqual(config["export"]["page_path"], "{space_key}/{page_id}.md")
            self.assertEqual(config["connection_config"]["timeout"], 11)
            self.assertEqual(config["connection_config"]["max_workers"], 3)
            self.assertEqual(config["auth"]["confluence"]["https://company.atlassian.net"]["username"], "user@example.com")
            self.assertEqual(config["auth"]["confluence"]["https://company.atlassian.net"]["api_token"], "secret-token")
            self.assertNotIn("cloud_id", config["auth"]["confluence"]["https://company.atlassian.net"])

    def test_validate_job_accepts_cme_org_and_multiple_urls(self):
        with temp_workspace() as root:
            job = self.make_cme_job(
                root,
                cme_scope="orgs",
                cme_urls="https://company.atlassian.net https://second.atlassian.net",
            )
            validate_job(job)

    def test_cme_preview_and_apply_use_cme_exporter_only(self):
        with temp_workspace() as root:
            job = self.make_cme_job(root)
            calls = []

            def fake_exporter(job: Job, progress):
                calls.append(job.id)
                if progress:
                    progress("fake cme", 1, 1)
                return CmeExportResult("orgs", ["https://company.atlassian.net"], str(job.workspace), {"exported": 2, "skipped": 1, "failed": 0})

            engine = SyncEngine(cme_exporter=fake_exporter)
            plan = engine.preview(job)
            self.assertEqual(plan.summary["update"], 1)
            run = engine.apply(job)
            self.assertEqual(calls, ["cme"])
            self.assertEqual(run["mode"], "cme_apply")
            self.assertEqual(run["summary"]["created"], 2)
            self.assertEqual(run["summary"]["skipped"], 1)
            self.assertEqual(load_run_history(job)["runs"][-1]["cme"]["command"], "orgs")


if __name__ == "__main__":
    unittest.main()
