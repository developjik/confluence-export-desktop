from __future__ import annotations

import os
import re
import shutil
import unicodedata
import uuid
from pathlib import Path

from .errors import AppError
from .paths import WORKSPACE_LOG_DIR_NAME


INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def sanitize_component(value: str, fallback: str = "_untitled", max_length: int = 120) -> str:
    text = unicodedata.normalize("NFC", value or "")
    text = INVALID_CHARS.sub("_", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    if not text:
        text = fallback
    stem = text.split(".")[0].upper()
    if stem in RESERVED_NAMES:
        text = f"{text}_"
    if len(text) > max_length:
        text = text[:max_length].rstrip(" .") or fallback
    return text


def content_filename(title: str, page_id: str | None = None) -> str:
    return f"{sanitize_component(title)}.md"


def safe_join(root: Path, relative_path: str | Path) -> Path:
    root_resolved = root.resolve()
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise AppError(
            "Validation",
            "PATH_TRAVERSAL_BLOCKED",
            "페이지 제목 또는 저장 경로가 Windows 제한을 위반합니다.",
            f"Path escapes root: {relative_path}",
            False,
        ) from exc
    return candidate


def ensure_workspace(root: Path) -> None:
    for child in ("content", "assets", "metadata", "temp", WORKSPACE_LOG_DIR_NAME):
        os.makedirs(filesystem_path(root / child), exist_ok=True)


def filesystem_path(path: Path) -> str:
    text = str(path)
    if os.name != "nt" or text.startswith("\\\\?\\"):
        return text
    absolute = str(path.resolve(strict=False))
    if absolute.startswith("\\\\?\\"):
        return absolute
    if absolute.startswith("\\\\"):
        return "\\\\?\\UNC\\" + absolute[2:]
    return "\\\\?\\" + absolute


def path_for_io(path: Path) -> Path:
    return Path(filesystem_path(path))


def path_exists(path: Path) -> bool:
    return path_for_io(path).exists()


def path_is_file(path: Path) -> bool:
    return path_for_io(path).is_file()


def path_stat(path: Path) -> os.stat_result:
    return path_for_io(path).stat()


def read_file_bytes(path: Path) -> bytes:
    return path_for_io(path).read_bytes()


def iter_files(root: Path):
    root_path = path_for_io(root)
    if not root_path.exists():
        return
    for current, dirnames, filenames in os.walk(str(root_path)):
        dirnames.sort()
        for filename in sorted(filenames):
            yield Path(current) / filename


def _open_short_temp(parent: Path) -> tuple[int, Path]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    for _ in range(100):
        tmp_path = parent / f".tmp-{uuid.uuid4().hex[:8]}.tmp"
        try:
            return os.open(filesystem_path(tmp_path), flags, 0o666), tmp_path
        except FileExistsError:
            continue
    raise FileExistsError(f"Could not create a unique temporary file under {parent}")


def _cleanup_temp_file(path: Path) -> None:
    try:
        os.unlink(filesystem_path(path))
    except FileNotFoundError:
        return


def atomic_write_text(path: Path, text: str) -> None:
    os.makedirs(filesystem_path(path.parent), exist_ok=True)
    fd, tmp_path = _open_short_temp(path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(filesystem_path(tmp_path), filesystem_path(path))
    except Exception:
        try:
            _cleanup_temp_file(tmp_path)
        finally:
            raise


def atomic_write_bytes(path: Path, data: bytes) -> None:
    os.makedirs(filesystem_path(path.parent), exist_ok=True)
    fd, tmp_path = _open_short_temp(path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(filesystem_path(tmp_path), filesystem_path(path))
    except Exception:
        try:
            _cleanup_temp_file(tmp_path)
        finally:
            raise


def atomic_replace_file(src: Path, dst: Path) -> None:
    os.makedirs(filesystem_path(dst.parent), exist_ok=True)
    fd, tmp = _open_short_temp(dst.parent)
    os.close(fd)
    try:
        shutil.copy2(filesystem_path(src), filesystem_path(tmp))
        os.replace(filesystem_path(tmp), filesystem_path(dst))
    except Exception:
        try:
            _cleanup_temp_file(tmp)
        finally:
            raise
