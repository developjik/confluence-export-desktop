#!/usr/bin/env python3
"""Read-only local migration preflight. Never converts lock entries or contacts Confluence."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import stat
import sys

LIMIT = 8 * 1024 * 1024

def inspect_lock(root: Path, name: str) -> dict:
    path = root / name
    try:
        before = path.lstat()
    except FileNotFoundError:
        return {"status": "absent"}
    if not stat.S_ISREG(before.st_mode):
        return {"status": "unsafe", "reason": "not a regular non-symlink file"}
    if before.st_size > LIMIT:
        return {"status": "unsafe", "reason": "larger than 8 MiB; inspect locally without uploading"}
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as file:
            opened = os.fstat(file.fileno())
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino) or not stat.S_ISREG(opened.st_mode):
                return {"status": "unsafe", "reason": "file changed during open"}
            data = file.read(LIMIT + 1)
            after = os.fstat(file.fileno())
        if len(data) > LIMIT or (after.st_size, after.st_mtime_ns) != (opened.st_size, opened.st_mtime_ns):
            return {"status": "unsafe", "reason": "file changed during read"}
        value = json.loads(data)
    except (OSError, ValueError, UnicodeError):
        return {"status": "unreadable", "reason": "not readable JSON; preserve the file, do not repair in place"}
    if name == "confluence-lock.json":
        return {"status": "legacy-present", "automatic_conversion": False, "schema_inferred": False}
    if isinstance(value, dict) and value.get("schema_version") == 2 and isinstance(value.get("pages"), dict):
        return {"status": "v2-present", "page_entries": len(value["pages"])}
    return {"status": "unknown-schema", "automatic_conversion": False}

def preflight(legacy: Path, proposed: Path) -> dict:
    old = legacy.resolve(strict=True)
    if not old.is_dir():
        raise ValueError("legacy directory must exist")
    new = proposed.resolve(strict=False)
    if old == new or old in new.parents or new in old.parents:
        raise ValueError("v2 target must be separate, not the same directory or a parent/child of legacy")
    # Do not resolve away a symlink and then describe it as a fresh target.
    for part in [proposed, *proposed.parents]:
        if part.is_symlink():
            raise ValueError("v2 target must not pass through a symlink")
    if new.exists():
        if not new.is_dir():
            raise ValueError("v2 target must be an absent or empty directory")
        if any(new.iterdir()):
            raise ValueError("v2 target is not empty; choose a fresh directory for the first migration")
    locks = {name: inspect_lock(old, name) for name in ("confluence-lock.json", "confluence-export.lock.json")}
    ready = all(row["status"] not in ("unsafe", "unreadable", "unknown-schema") for row in locks.values())
    return {"schema": "confluence-migration-preflight/v1", "read_only": True,
            "network_requests": 0, "ready_for_manual_guide": ready,
            "locks": locks, "automatic_checksum_reuse": False,
            "required_settings": {"scope": "spaces", "one_space_per_target": True,
                "cleanup_stale": False, "skip_unchanged": True, "schedule_enabled": False},
            "warning": "This is not a migration or a backup. Preserve legacy output and locks separately. The selected v2 space is downloaded once; unchanged legacy spaces remain an archive, not current v2 output.",
            "guide": "docs/MIGRATION_V1_V2.md"}

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy-dir", required=True, type=Path)
    parser.add_argument("--v2-target", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = preflight(args.legacy_dir, args.v2_target)
    except (OSError, ValueError):
        # Error strings can contain private paths. Keep stdout/stderr share-safe by default.
        print("Preflight refused: check that legacy exists and v2 is a fresh separate non-symlink directory.", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ready_for_manual_guide"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
