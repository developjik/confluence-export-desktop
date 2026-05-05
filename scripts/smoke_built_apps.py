from __future__ import annotations

import json
import locale
import os
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUI = ROOT / "dist" / "confluence-sync" / "confluence-sync.exe"


def decode_output(data: bytes | None) -> str:
    if not data:
        return ""
    encodings = ["utf-8", locale.getpreferredencoding(False), "cp949"]
    seen = set()
    for encoding in encodings:
        if not encoding or encoding in seen:
            continue
        seen.add(encoding)
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", errors="replace")


def limited_env(appdata: str | None = None) -> dict[str, str]:
    keep = {}
    for key in ("SystemRoot", "WINDIR", "APPDATA", "USERPROFILE", "TEMP", "TMP"):
        value = os.environ.get(key)
        if value:
            keep[key] = value
    if appdata:
        keep["APPDATA"] = appdata
    system_root = keep.get("SystemRoot") or keep.get("WINDIR") or r"C:\Windows"
    keep["PATH"] = str(Path(system_root) / "System32")
    keep["PYTHONUTF8"] = "1"
    keep["PYTHONIOENCODING"] = "utf-8"
    keep["CONFLUENCE_SYNC_DISABLE_TRAY"] = "1"
    return keep


def smoke_gui_launch() -> dict:
    if not GUI.exists():
        return {"ok": False, "reason": "built GUI missing", "path": str(GUI)}
    proc = subprocess.Popen([str(GUI)], cwd=ROOT, env=limited_env(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(3)
        running = proc.poll() is None
        return {"ok": running, "running_after_seconds": 3, "path": str(GUI), "pid": proc.pid}
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


def main() -> int:
    result = {
        "built_gui_launch": smoke_gui_launch(),
    }
    result["ok"] = result["built_gui_launch"]["ok"]
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
