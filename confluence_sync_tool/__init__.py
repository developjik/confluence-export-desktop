from __future__ import annotations

from pathlib import Path


_SRC_PACKAGE = Path(__file__).resolve().parents[1] / "src" / "confluence_sync_tool"

if _SRC_PACKAGE.is_dir():
    __path__.append(str(_SRC_PACKAGE))

__version__ = "0.1.0"
