from __future__ import annotations

import os
import sys

from .errors import AppError


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "ConfluenceExportDesktop"


def auto_start_command() -> str:
    exe = sys.executable
    if getattr(sys, "frozen", False):
        return f'"{exe}"'
    return f'"{exe}" -m confluence_sync_tool.gui'


def set_windows_auto_start(enabled: bool) -> None:
    if os.name != "nt":
        raise AppError("Config", "AUTO_START_WINDOWS_ONLY", "Windows 자동 시작은 Windows에서만 설정할 수 있습니다.", sys.platform, False)
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, auto_start_command())
            else:
                try:
                    winreg.DeleteValue(key, RUN_VALUE)
                except FileNotFoundError:
                    pass
    except AppError:
        raise
    except Exception as exc:
        raise AppError("Config", "AUTO_START_UPDATE_FAILED", "Windows 자동 시작 설정을 저장하지 못했습니다.", str(exc), False) from exc
