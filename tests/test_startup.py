from __future__ import annotations

import unittest

from confluence_sync_tool.startup import RUN_KEY, RUN_VALUE, auto_start_command


class StartupTests(unittest.TestCase):
    def test_auto_start_command_points_to_gui_entrypoint_in_source(self):
        command = auto_start_command()
        self.assertIn("confluence_sync_tool.gui", command)

    def test_windows_run_key_contract(self):
        self.assertIn("CurrentVersion\\Run", RUN_KEY)
        self.assertEqual(RUN_VALUE, "ConfluenceExportDesktop")


if __name__ == "__main__":
    unittest.main()
