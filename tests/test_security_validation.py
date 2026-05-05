from __future__ import annotations

import unittest
from pathlib import Path

from confluence_sync_tool.errors import ALLOWED_CATEGORIES, AppError
from confluence_sync_tool.models import DEFAULT_EXPORT_OPTIONS, Job
from confluence_sync_tool.paths import workspace_log_dir
from confluence_sync_tool.security import MemoryCredentialStore, credential_key, mask_sensitive
from confluence_sync_tool.storage import JobStore, append_job_log, save_settings
from confluence_sync_tool.validation import parse_page_id, setup_checks, validate_auth_input, validate_job

from tests.helpers import make_job, temp_workspace


class SecurityValidationTests(unittest.TestCase):
    def test_ut_auth_01_auth_input_validation(self):
        errors = validate_auth_input("", "bad-email", "")
        self.assertIn("base_url", errors)
        self.assertIn("email", errors)
        self.assertIn("api_token", errors)

    def test_sec_02_masks_sensitive_values(self):
        text = "Authorization: Basic abcdef token=super-secret Cookie: a=b"
        masked = mask_sensitive(text)
        self.assertNotIn("abcdef", masked)
        self.assertNotIn("super-secret", masked)
        self.assertIn("****", masked)

    def test_it_auth_03_credential_key_is_stable(self):
        a = credential_key("HTTPS://Company.Atlassian.Net/wiki", "User@Example.com")
        b = credential_key("https://company.atlassian.net", "user@example.com")
        self.assertEqual(a, b)

    def test_it_auth_02_memory_credential_logout(self):
        store = MemoryCredentialStore()
        store.write("https://company.atlassian.net", "u@example.com", "sentinel-token")
        self.assertEqual(store.read("https://company.atlassian.net", "u@example.com"), "sentinel-token")
        store.delete("https://company.atlassian.net", "u@example.com")
        self.assertIsNone(store.read("https://company.atlassian.net", "u@example.com"))

    def test_ut_log_02_allowed_error_categories(self):
        self.assertIn("File System", ALLOWED_CATEGORIES)
        err = AppError("Bad", "X", "user message", "technical")
        self.assertEqual(err.category, "Unknown")

    def test_ut_log_03_error_object_separates_messages(self):
        err = AppError("Config", "BAD", "user message", "technical detail", False)
        data = err.to_dict()
        self.assertEqual(data["user_message"], "user message")
        self.assertEqual(data["technical_message"], "technical detail")

    def test_sec_01_token_is_not_written_to_json_files(self):
        with temp_workspace() as root:
            config = Path(root) / "app"
            workspace = Path(root) / "workspace"
            token = "sentinel-super-secret-token"
            save_settings("https://company.atlassian.net", "u@example.com", config)
            store = JobStore(config / "jobs.json")
            store.upsert(make_job(workspace, job_id="a"))
            written = "\n".join(path.read_text(encoding="utf-8") for path in config.rglob("*.json"))
            self.assertNotIn(token, written)

    def test_sec_03_crash_text_is_masked(self):
        crash_text = "RuntimeError: failed with token=sentinel-super-secret-token"
        self.assertNotIn("sentinel-super-secret-token", mask_sensitive(crash_text))

    def test_sec_01_job_log_masks_token(self):
        with temp_workspace() as root:
            workspace = Path(root) / "workspace"
            workspace.mkdir()
            job = Job("a", "A", "https://company.atlassian.net/wiki/pages/123456", str(workspace))
            append_job_log(job, "token=sentinel-super-secret-token")
            log_text = (workspace_log_dir(workspace) / "app.log").read_text(encoding="utf-8")
            self.assertNotIn("sentinel-super-secret-token", log_text)

    def test_od_05_job_log_rotation(self):
        with temp_workspace() as root:
            workspace = Path(root) / "workspace"
            workspace.mkdir()
            job = Job("a", "A", "https://company.atlassian.net/wiki/pages/123456", str(workspace))
            append_job_log(job, "first line", max_bytes=1, backups=2)
            append_job_log(job, "second line", max_bytes=1, backups=2)
            self.assertTrue((workspace_log_dir(workspace) / "app.log").exists())
            self.assertTrue((workspace_log_dir(workspace) / "app.log.1").exists())

    def test_it_fs_01_target_directory_validation(self):
        with temp_workspace() as root:
            missing = make_job(root)
            missing.target_dir = str(Path(root) / "missing")
            with self.assertRaises(AppError):
                validate_job(missing)
            Path(missing.target_dir).mkdir(parents=True)
            validate_job(missing)

    def test_setup_checks_for_cme_job(self):
        with temp_workspace() as root:
            job = make_job(root)
            checks = setup_checks(job)
            by_id = {item["id"]: item for item in checks}
            self.assertTrue(by_id["VAL-01"]["ok"])
            self.assertTrue(by_id["VAL-02"]["ok"])
            self.assertTrue(by_id["VAL-03"]["ok"])
            self.assertIn("VAL-07", by_id)

    def test_val_01_auth_error_blocks_url_check(self):
        with temp_workspace() as root:
            job = make_job(root)
            auth_error = AppError("Auth", "TOKEN_NOT_FOUND", "Stored API token was not found.", "", False)
            checks = setup_checks(job, auth_error=auth_error)
            by_id = {item["id"]: item for item in checks}
            self.assertFalse(by_id["VAL-01"]["ok"])
            self.assertFalse(by_id["VAL-02"]["ok"])

    def test_ut_job_02_page_url_validation_helper_still_parses_page_ids(self):
        self.assertEqual(parse_page_id("https://company.atlassian.net/wiki/spaces/A/pages/123456/Title"), "123456")
        with self.assertRaises(AppError):
            parse_page_id("https://company.atlassian.net/wiki/spaces/A")

    def test_default_export_options_do_not_expose_internal_backend(self):
        self.assertNotIn("backend", DEFAULT_EXPORT_OPTIONS)
        self.assertIn("cme_scope", DEFAULT_EXPORT_OPTIONS)
        self.assertTrue(DEFAULT_EXPORT_OPTIONS["attachment_export_all"])
        self.assertFalse(DEFAULT_EXPORT_OPTIONS["enable_jira_enrichment"])


if __name__ == "__main__":
    unittest.main()
