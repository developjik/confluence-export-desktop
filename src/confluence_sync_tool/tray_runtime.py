from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

from .errors import AppError
from .storage import append_app_log


class TrayRuntime:
    def __init__(
        self,
        *,
        icon_path: Path,
        show_window: Callable[[], None],
        quit_app: Callable[[], None],
        toggle_pause: Callable[[], None],
    ) -> None:
        self.icon_path = icon_path
        self.show_window = show_window
        self.quit_app = quit_app
        self.toggle_pause = toggle_pause
        self.icon = None
        self.thread: threading.Thread | None = None
        self.last_error = ""

    def start(self) -> bool:
        try:
            import pystray
            from PIL import Image

            if not self.icon_path.exists():
                raise FileNotFoundError(str(self.icon_path))
            image = Image.open(self.icon_path)
            self.icon = pystray.Icon(
                "ConfluenceSync",
                image,
                "Confluence Sync",
                menu=pystray.Menu(
                    pystray.MenuItem("열기", lambda _icon, _item: self.show_window()),
                    pystray.MenuItem("스케줄 일시정지/재개", lambda _icon, _item: self.toggle_pause()),
                    pystray.MenuItem("종료", lambda _icon, _item: self.quit_app()),
                ),
            )
            self.thread = threading.Thread(target=self.icon.run, name="ConfluenceSyncTray", daemon=True)
            self.thread.start()
            self.last_error = ""
            return True
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            try:
                append_app_log(f"tray_start_failed error={self.last_error}")
            except Exception:
                pass
            self.icon = None
            self.thread = None
            return False

    def stop(self) -> None:
        if self.icon is not None:
            self.icon.stop()
            self.icon = None
        self.thread = None

    def notify(self, title: str, message: str) -> None:
        if self.icon is not None:
            try:
                self.icon.notify(message, title)
            except Exception as exc:
                raise AppError("Unknown", "TRAY_NOTIFICATION_FAILED", "Tray 알림을 표시하지 못했습니다.", str(exc), True) from exc
