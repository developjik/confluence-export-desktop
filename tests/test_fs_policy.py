from __future__ import annotations

import unittest
import shutil
from pathlib import Path

from confluence_sync_tool.errors import AppError
from confluence_sync_tool.fs_policy import (
    atomic_write_bytes,
    atomic_write_text,
    content_filename,
    filesystem_path,
    iter_files,
    path_for_io,
    read_file_bytes,
    safe_join,
    sanitize_component,
)

from tests.helpers import temp_workspace


class FileSystemPolicyTests(unittest.TestCase):
    def test_windows_filename_sanitize_is_deterministic(self):
        value = 'CON <bad>: name. '
        self.assertEqual(sanitize_component(value), sanitize_component(value))
        self.assertEqual(sanitize_component("CON"), "CON_")
        self.assertNotIn("<", sanitize_component(value))
        self.assertEqual(sanitize_component("Cafe\u0301"), sanitize_component("Caf\u00e9"))
        self.assertLessEqual(len(sanitize_component("x" * 240)), 120)

    def test_gate_11_same_title_collision_safe(self):
        self.assertEqual(content_filename("Overview", "123"), "Overview.md")
        self.assertEqual(content_filename("Overview", "456"), "Overview.md")

    def test_path_traversal_blocked(self):
        with temp_workspace() as root:
            with self.assertRaises(AppError):
                safe_join(Path(root), "..\\outside.md")

    def test_ut_fs_01_atomic_write_text(self):
        with temp_workspace() as root:
            path = Path(root) / "a" / "file.txt"
            atomic_write_text(path, "hello")
            self.assertEqual(path.read_text(encoding="utf-8"), "hello")
            leftovers = list(path.parent.glob("*.tmp"))
            self.assertEqual(leftovers, [])

    def test_atomic_writes_use_short_temp_names_for_deep_paths(self):
        with temp_workspace() as root:
            root_path = Path(root)
            folder_len = max(1, 220 - len(str(root_path)) - 1)
            parent = root_path / ("d" * folder_len)
            path = parent / ("f" * 24 + ".txt")
            self.assertGreater(len(str(parent / f".{path.name}.abcdefgh.tmp")), 260)
            atomic_write_text(path, "hello")
            self.assertEqual(path.read_text(encoding="utf-8"), "hello")

            binary = parent / ("b" * 24 + ".bin")
            atomic_write_bytes(binary, b"data")
            self.assertEqual(binary.read_bytes(), b"data")

    def test_long_path_read_helpers_support_paths_over_windows_limit(self):
        with temp_workspace() as root:
            root_path = Path(root)
            folder_len = max(1, 250 - len(str(root_path)) - 1)
            parent = root_path / ("d" * folder_len)
            path = parent / ("f" * 24 + ".txt")
            try:
                atomic_write_text(path, "hello")
                self.assertGreater(len(str(path)), 260)
                self.assertEqual(read_file_bytes(path), b"hello")
                self.assertIn(path_for_io(path), list(iter_files(root_path)))
            finally:
                if path_for_io(parent).exists():
                    shutil.rmtree(filesystem_path(parent), ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
