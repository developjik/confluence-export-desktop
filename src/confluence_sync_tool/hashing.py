from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .fs_policy import iter_files, path_exists, path_is_file, path_for_io, read_file_bytes


EMPTY_HASH = "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path_for_io(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def canonical_json(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(data: object) -> str:
    return sha256_text(canonical_json(data))


def tree_hash(root: Path, include: tuple[str, ...] = ("content", "assets", "metadata", "run_history.json")) -> str:
    h = hashlib.sha256()
    if not path_exists(root):
        return EMPTY_HASH
    root_for_io = path_for_io(root)
    for rel in include:
        path = root / rel
        if not path_exists(path):
            continue
        if path_is_file(path):
            h.update(rel.replace("\\", "/").encode("utf-8"))
            h.update(read_file_bytes(path))
            continue
        for file_path in iter_files(path):
            rel_path = file_path.relative_to(root_for_io).as_posix()
            h.update(rel_path.encode("utf-8"))
            h.update(read_file_bytes(file_path))
    return "sha256:" + h.hexdigest()
