from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QCloseEvent, QFont, QFontDatabase, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .cli import _credential_store
from .cme_backend import CME_SCOPES, DEFAULT_CME_CONFIG, apply_common_job_options, deep_merge, default_cme_config_json, parse_cme_config_json, test_cme_connection
from .engine import SyncEngine
from .errors import AppError, classify_exception
from .models import DEFAULT_EXPORT_OPTIONS, DEFAULT_SCHEDULE, Job, normalize_schedule
from .paths import default_workspace, ensure_app_dirs
from .scheduler import RunCoordinator, SchedulerRuntime, next_run_at
from .security import mask_sensitive
from .startup import set_windows_auto_start
from .storage import JobStore, load_run_history, load_scheduler_events, load_settings, save_app_setting, save_settings, stable_job_id
from .tray_runtime import TrayRuntime
from .validation import validate_auth_input, validate_job, validate_schedule


HREF_OPTIONS = ("absolute", "relative", "wiki")
SCHEDULE_KIND_LABELS = {
    "daily": "매일",
    "weekdays": "주중",
    "weekly": "매주",
    "monthly": "매월",
    "multiple_daily": "하루 여러 번",
}
SCHEDULE_KIND_VALUES = {label: value for value, label in SCHEDULE_KIND_LABELS.items()}
DAY_LABELS = ((1, "월"), (2, "화"), (3, "수"), (4, "목"), (5, "금"), (6, "토"), (7, "일"))
HOUR_VALUES = tuple(f"{hour:02d}" for hour in range(24))
MINUTE_VALUES = ("00", "15", "30", "45")
KOREA_TZ = timezone(timedelta(hours=9), "KST")
RUN_HISTORY_LIMIT = 10
BG = "#f4f6f8"
SURFACE = "#ffffff"
BORDER = "#d8dee8"
TEXT = "#1f2937"
MUTED = "#667085"
ACCENT = "#2563eb"
ACCENT_DARK = "#1d4ed8"
FOCUS = "#84a9ff"
DANGER = "#b42318"
SUCCESS = "#067647"
WARNING = "#b54708"
MONO = "Consolas"
APP_FONT = "Malgun Gothic"
_APP_FONT_CONFIGURED = False


def _asset_path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    if hasattr(sys, "_MEIPASS"):
        return base / "confluence_sync_tool" / "assets" / name
    return base / "assets" / name


def configure_application_font() -> None:
    global _APP_FONT_CONFIGURED
    app = QApplication.instance()
    if app is None or _APP_FONT_CONFIGURED:
        return
    for font_path in (Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "malgun.ttf", Path("C:/Windows/Fonts/malgun.ttf")):
        if font_path.exists():
            QFontDatabase.addApplicationFont(str(font_path))
            break
    app.setFont(QFont(APP_FONT, 10))
    _APP_FONT_CONFIGURED = True


def format_plan_display(plan: dict[str, object]) -> str:
    items = plan.get("items") if isinstance(plan.get("items"), list) else []
    summary = plan.get("summary") if isinstance(plan.get("summary"), dict) else {}
    warnings = plan.get("warnings") if isinstance(plan.get("warnings"), list) else []
    lines = [
        "동기화 계획",
        f"계획 ID: {plan.get('plan_id', '')}",
        f"작업 ID: {plan.get('job_id', '')}",
        f"범위: {plan.get('scope', '')}",
        "",
        "요약",
        json.dumps(summary, ensure_ascii=False, indent=2),
        "",
        "실행 예정 CME 작업",
    ]
    lines.extend(_format_plan_items_with_badges(_filter_plan_items(items, {"create", "update"})) or ["- none"])
    lines.extend(["", "건너뜀 / 오류"])
    lines.extend(_format_plan_items_with_badges(_filter_plan_items(items, {"skip", "error"})) or ["- none"])
    if warnings:
        lines.extend(["", "경고"])
        lines.extend(f"- {warning}" for warning in warnings)
    return "\n".join(lines) + "\n"


def _filter_plan_items(items: object, actions: set[str]) -> list[dict[str, object]]:
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict) and str(item.get("action")) in actions]


def _format_plan_items_with_badges(items: list[dict[str, object]]) -> list[str]:
    rows = []
    for item in items:
        action = str(item.get("action") or "")
        badge = {
            "create": "[CREATE]",
            "update": "[UPDATE]",
            "skip": "[SKIP]",
            "error": "[ERROR]",
        }.get(action, f"[{action.upper()}]")
        title = item.get("title") or ""
        path = item.get("target_path") or item.get("current_path") or ""
        reason = item.get("reason") or ""
        rows.append(f"- {badge} {title} -> {path} ({reason})")
    return rows


def _safe_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _format_timestamp(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return "시간 없음"
    try:
        normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return text.replace("T", " ").split(".")[0]
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=KOREA_TZ)
    return parsed.astimezone(KOREA_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _run_counts(run: dict[str, object]) -> tuple[int, int, int, int]:
    summary = run.get("summary") if isinstance(run.get("summary"), dict) else {}
    cme = run.get("cme") if isinstance(run.get("cme"), dict) else {}
    stats = cme.get("stats") if isinstance(cme.get("stats"), dict) else {}
    created = _safe_int(summary.get("created") if isinstance(summary, dict) else 0)
    updated = _safe_int(summary.get("updated") if isinstance(summary, dict) else 0)
    exported = created + updated
    if not exported and isinstance(stats, dict):
        exported = _safe_int(stats.get("exported"))
    deleted = _safe_int(summary.get("deleted") if isinstance(summary, dict) else None)
    if not deleted and isinstance(stats, dict):
        deleted = _safe_int(stats.get("removed"))
    skipped = _safe_int(summary.get("skipped") if isinstance(summary, dict) else None)
    if not skipped and isinstance(stats, dict):
        skipped = _safe_int(stats.get("skipped"))
    errors = _safe_int(summary.get("errors") if isinstance(summary, dict) else None)
    if not errors and isinstance(stats, dict):
        errors = _safe_int(stats.get("failed"))
    return exported, deleted, skipped, errors


def format_run_history_row(run: object) -> tuple[str, str, str, str, str, str]:
    if not isinstance(run, dict):
        return ("기록 없음", "-", "-", "-", "-", "-")
    status = str(run.get("status") or "")
    status_label = {"success": "성공", "failed": "실패"}.get(status, status or "상태 없음")
    trigger = str(run.get("trigger") or "")
    if trigger == "scheduled":
        status_label = f"{status_label}(예약)"
    elif trigger == "manual":
        status_label = f"{status_label}(수동)"
    finished_at = _format_timestamp(run.get("finished_at") or run.get("started_at"))
    exported, deleted, skipped, errors = _run_counts(run)
    return (finished_at, status_label, str(exported), str(deleted), str(skipped), str(errors))


def format_run_history_rows(runs: object, limit: int = RUN_HISTORY_LIMIT) -> list[tuple[str, str, str, str, str, str]]:
    if not isinstance(runs, list):
        return []
    valid_runs = [run for run in runs if isinstance(run, dict)]
    return [format_run_history_row(run) for run in reversed(valid_runs[-limit:])]


def format_run_summary(run: object) -> str:
    if not isinstance(run, dict):
        return "아직 동기화 기록이 없습니다."
    status = str(run.get("status") or "")
    status_label = {"success": "성공", "failed": "실패"}.get(status, status or "상태 없음")
    finished_at = _format_timestamp(run.get("finished_at") or run.get("started_at"))
    exported, deleted, skipped, errors = _run_counts(run)
    lines = [
        f"{finished_at} · {status_label}",
        f"문서 생성/업데이트 {exported}건 · 삭제 {deleted}건 · 건너뜀 {skipped}건 · 오류 {errors}건",
    ]
    error = run.get("error")
    if isinstance(error, dict) and error.get("user_message"):
        lines.append(f"오류: {error['user_message']}")
    return "\n".join(lines)


def format_job_run_history_rows(job: Job) -> list[tuple[str, str, str, str, str, str]]:
    try:
        history = load_run_history(job)
    except Exception as exc:
        error = classify_exception(exc)
        return [("읽기 실패", error.user_message, "-", "-", "-", "-")]
    runs = history.get("runs") if isinstance(history, dict) else []
    return format_run_history_rows(runs)


class StatusBadge(QLabel):
    def __init__(self, text: str = "준비됨", tone: str = "info") -> None:
        super().__init__(text)
        self.setObjectName("StatusBadge")
        self.set_tone(tone)

    def set_tone(self, tone: str) -> None:
        palette = {
            "info": ("#eef4ff", "#1849a9"),
            "success": ("#ecfdf3", SUCCESS),
            "warning": ("#fffaeb", WARNING),
            "error": ("#fef3f2", DANGER),
            "muted": ("#f2f4f7", MUTED),
        }.get(tone, ("#eef4ff", "#1849a9"))
        self.setStyleSheet(
            f"QLabel#StatusBadge {{ background: {palette[0]}; color: {palette[1]};"
            " border-radius: 12px; padding: 5px 10px; font-weight: 600; }"
        )


class ConfluenceSyncApp(QMainWindow):
    background_success = Signal(object)
    background_error = Signal(object)
    progress_message = Signal(str)
    show_window_requested = Signal()
    quit_requested = Signal()
    toggle_pause_requested = Signal()
    scheduled_failure = Signal(object, object)

    def __init__(self) -> None:
        super().__init__()
        configure_application_font()
        ensure_app_dirs()
        self.setWindowTitle("Confluence 문서 동기화")
        self.resize(1260, 860)
        self.setMinimumSize(1040, 720)
        self._set_window_icon()
        self.store = JobStore()
        self.editing_job_id: str | None = None
        self.connection_verified_fingerprint: str | None = None
        self.busy = False
        self.current_worker_label = ""
        self.current_success: Callable[[object], None] | None = None
        self.current_error: Callable[[Exception], None] | None = None
        settings = load_settings()
        self.coordinator = RunCoordinator(global_worker_limit=int(settings.get("global_worker_limit") or 1))
        self.scheduler_runtime: SchedulerRuntime | None = None
        self.tray_runtime: TrayRuntime | None = None
        self.tray_available = False
        self.close_notice_shown = False
        self.global_schedule_paused = bool(settings.get("schedule_paused"))
        self.auto_start = bool(settings.get("auto_start"))

        self.background_success.connect(self.finish_background_success)
        self.background_error.connect(self.finish_background_error)
        self.progress_message.connect(self.set_status_text)
        self.show_window_requested.connect(self.show_from_tray)
        self.quit_requested.connect(self.quit_from_tray)
        self.toggle_pause_requested.connect(self.toggle_pause_from_tray)
        self.scheduled_failure.connect(self.notify_scheduled_failure)

        self._build()
        self.refresh_jobs()
        self.start_background_runtime()

    def _set_window_icon(self) -> None:
        icon = _asset_path("app.ico")
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))

    def _build(self) -> None:
        self.setStyleSheet(APP_STYLESHEET)
        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        side_rail = QFrame()
        side_rail.setObjectName("SidebarFrame")
        side_rail_layout = QVBoxLayout(side_rail)
        side_rail_layout.setContentsMargins(14, 16, 14, 14)
        side_rail_layout.setSpacing(14)
        brand = QLabel("Confluence Sync")
        brand.setObjectName("SidebarBrand")
        brand.setWordWrap(True)
        product_hint = QLabel("Markdown workspace")
        product_hint.setObjectName("SidebarHint")
        side_rail_layout.addWidget(brand)
        side_rail_layout.addWidget(product_hint)
        self.sidebar = QListWidget()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(184)
        self.sidebar.setSpacing(4)
        self.sidebar.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        for text in ("연결", "작업", "작업 설정"):
            item = QListWidgetItem(text)
            item.setSizeHint(QSize(0, 46))
            self.sidebar.addItem(item)
        self.sidebar.currentRowChanged.connect(self.show_page)
        side_rail_layout.addWidget(self.sidebar, 1)
        sidebar_footer = QLabel("Local-first · KST")
        sidebar_footer.setObjectName("SidebarHint")
        side_rail_layout.addWidget(sidebar_footer)
        layout.addWidget(side_rail)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(26, 22, 26, 22)
        content_layout.setSpacing(16)
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(3)
        app_title = QLabel("Confluence 문서 동기화")
        app_title.setObjectName("AppTitle")
        subtitle = QLabel("Confluence 문서를 로컬 Markdown 작업으로 저장하고 수동/예약 동기화합니다.")
        subtitle.setObjectName("MutedLabel")
        subtitle.setWordWrap(True)
        title_box.addWidget(app_title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box, 1)
        self.status_badge = StatusBadge("준비됨", "info")
        self.status_badge.setMinimumWidth(104)
        header.addWidget(self.status_badge, 0, Qt.AlignTop)
        content_layout.addLayout(header)

        self.pages = QStackedWidget()
        content_layout.addWidget(self.pages, 1)
        layout.addWidget(content, 1)
        self.setCentralWidget(root)

        self._build_settings()
        self._build_jobs()
        self._build_editor()
        self.sidebar.setCurrentRow(0)

    def show_page(self, index: int) -> None:
        if 0 <= index < self.pages.count():
            self.pages.setCurrentIndex(index)

    def _build_settings(self) -> None:
        page = self._page()
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setSpacing(12)
        layout.addWidget(self._section_header("연결 정보", "Confluence 접속 정보를 입력하고 연결 테스트를 통과해야 저장할 수 있습니다."))
        settings = load_settings()
        self.base_url = QLineEdit(str(settings.get("base_url", "")))
        self.email = QLineEdit(str(settings.get("email", "")))
        self.token = QLineEdit()
        self.token.setEchoMode(QLineEdit.Password)
        self._prepare_line_edit(self.base_url, "https://your-domain.atlassian.net/wiki")
        self._prepare_line_edit(self.email, "name@company.com")
        self._prepare_line_edit(self.token, "Confluence API token")
        form = QGridLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        self._add_form_row(form, 0, "Confluence 기본 URL", self.base_url)
        self._add_form_row(form, 1, "이메일", self.email)
        self._add_form_row(form, 2, "API 토큰", self.token)
        layout.addLayout(form)
        layout.addWidget(self._helper("API 토큰은 Windows Credential Manager에만 저장됩니다."))

        action_grid = QGridLayout()
        action_grid.setHorizontalSpacing(12)
        action_grid.setVerticalSpacing(12)

        actions = self._step_card("1. 연결 테스트", "현재 입력한 정보로 Confluence에 연결되는지 확인합니다.")
        self.test_connection_button = self._button("연결 테스트", "primary")
        self.test_connection_button.clicked.connect(self.test_connection)
        actions.layout().addWidget(self.test_connection_button)
        action_grid.addWidget(actions, 0, 0)

        proceed = self._step_card("2. 저장 및 작업 생성", "성공한 연결 정보만 저장할 수 있습니다.")
        self.save_create_button = self._button("저장 후 작업 만들기", "primary")
        self.save_create_button.setEnabled(False)
        self.save_create_button.clicked.connect(lambda: self.save_settings(open_editor=True))
        proceed.layout().addWidget(self.save_create_button)
        action_grid.addWidget(proceed, 0, 1)

        account = self._step_card("계정 관리", "현재 저장된 API 토큰을 이 PC에서 삭제합니다.")
        self.logout_button = self._button("저장된 토큰 삭제", "secondary")
        self.logout_button.clicked.connect(self.logout)
        account.layout().addWidget(self.logout_button)
        action_grid.addWidget(account, 1, 0)

        background = self._step_card("Background 실행", "앱이 tray/background 상태일 때 예약된 작업을 실행합니다.")
        self.global_pause_check = QCheckBox("스케줄 전역 일시정지")
        self.global_pause_check.setChecked(self.global_schedule_paused)
        self.global_pause_check.stateChanged.connect(lambda _state: self.toggle_global_pause())
        self.auto_start_check = QCheckBox("Windows 로그인 시 자동 시작(opt-in)")
        self.auto_start_check.setChecked(self.auto_start)
        self.auto_start_check.stateChanged.connect(lambda _state: self.save_auto_start_setting())
        background.layout().addWidget(self.global_pause_check)
        background.layout().addWidget(self.auto_start_check)
        background.layout().addWidget(self._helper("자동 시작이 꺼져 있으면 앱을 완전히 종료한 동안 예약 실행은 보장되지 않습니다."))
        action_grid.addWidget(background, 1, 1)
        action_grid.setColumnStretch(0, 1)
        action_grid.setColumnStretch(1, 1)
        layout.addLayout(action_grid)

        layout.addStretch(1)
        page.layout().addWidget(card)
        self.pages.addWidget(page)
        for field in (self.base_url, self.email, self.token):
            field.textChanged.connect(self.connection_inputs_changed)
        self.update_connection_actions()

    def _build_jobs(self) -> None:
        page = self._page()
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        left = self._card()
        left.setMinimumWidth(320)
        left_layout = QVBoxLayout(left)
        header = QHBoxLayout()
        header.addWidget(self._title("작업 목록"), 1)
        self.new_job_button = self._button("새 작업", "primary")
        self.new_job_button.clicked.connect(self.new_job)
        header.addWidget(self.new_job_button)
        left_layout.addLayout(header)
        self.job_list_stack = QStackedWidget()
        self.empty_jobs_view = self._empty_jobs_view()
        self.job_list = QListWidget()
        self.job_list.setObjectName("JobList")
        self.job_list.setSelectionMode(QListWidget.SingleSelection)
        self.job_list.itemSelectionChanged.connect(self.update_job_details)
        self.job_list.itemDoubleClicked.connect(lambda _item: self.edit_selected())
        self.job_list_stack.addWidget(self.empty_jobs_view)
        self.job_list_stack.addWidget(self.job_list)
        left_layout.addWidget(self.job_list_stack, 1)
        splitter.addWidget(left)

        right = self._card()
        right_layout = QVBoxLayout(right)
        detail_header = QHBoxLayout()
        detail_header.addWidget(self._title("선택한 작업"), 1)
        self.sync_button = self._button("지금 동기화", "primary")
        self.sync_button.clicked.connect(self.run_selected)
        detail_header.addWidget(self.sync_button)
        right_layout.addLayout(detail_header)

        action_row = QHBoxLayout()
        self.edit_button = self._button("편집", "secondary")
        self.edit_button.clicked.connect(self.edit_selected)
        self.open_target_button = self._button("대상 폴더 열기", "secondary")
        self.open_target_button.clicked.connect(self.open_selected_target)
        self.delete_button = self._button("삭제", "danger")
        self.delete_button.clicked.connect(self.delete_selected)
        action_row.addWidget(self.edit_button)
        action_row.addWidget(self.open_target_button)
        action_row.addStretch(1)
        action_row.addWidget(self.delete_button)
        right_layout.addLayout(action_row)

        self.summary_grid = QGridLayout()
        self.summary_grid.setHorizontalSpacing(18)
        self.summary_grid.setVerticalSpacing(8)
        self.job_summary_labels: dict[str, QLabel] = {}
        for row, key, label in (
            (0, "name", "작업명"),
            (1, "scope", "범위"),
            (2, "schedule", "예약"),
            (3, "next_run", "다음 실행"),
            (4, "last_event", "최근 이벤트"),
            (5, "target", "저장 폴더"),
            (6, "url", "URL"),
        ):
            self._job_summary_row(row, key, label)
        right_layout.addLayout(self.summary_grid)

        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        right_layout.addWidget(divider)
        right_layout.addWidget(self._title("최근 동기화"))
        self.run_history_table = QTableWidget(0, 6)
        self.run_history_table.setHorizontalHeaderLabels(["한국시간", "결과", "문서", "삭제", "건너뜀", "오류"])
        self.run_history_table.verticalHeader().setVisible(False)
        self.run_history_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.run_history_table.setSelectionMode(QTableWidget.NoSelection)
        self.run_history_table.setAlternatingRowColors(True)
        self.run_history_table.setShowGrid(False)
        self.run_history_table.setWordWrap(False)
        self.run_history_table.setCornerButtonEnabled(False)
        self.run_history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, 6):
            self.run_history_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeToContents)
        right_layout.addWidget(self.run_history_table, 1)
        splitter.addWidget(right)
        splitter.setSizes([360, 860])
        page.layout().addWidget(splitter)
        self.pages.addWidget(page)

    def _build_editor(self) -> None:
        self.job_name = QLineEdit()
        self.job_url = QLineEdit()
        self.job_target = QLineEdit(str(default_workspace() / "jobs" / "product-docs"))
        self.job_target.setObjectName("PathField")
        self._prepare_line_edit(self.job_name, "Product docs")
        self._prepare_line_edit(self.job_url, "https://your-domain.atlassian.net/wiki/spaces/SPACE")
        self._prepare_line_edit(self.job_target, str(default_workspace() / "jobs" / "product-docs"))
        self.include_children = QCheckBox("하위 페이지 포함")
        self.include_children.setChecked(True)
        self.option_cme_scope = QComboBox()
        self.option_cme_scope.addItems(CME_SCOPES)
        self.option_page_href = QComboBox()
        self.option_page_href.addItems(HREF_OPTIONS)
        self.option_attachment_href = QComboBox()
        self.option_attachment_href.addItems(HREF_OPTIONS)
        self.option_attachment_export_all = QCheckBox("첨부파일 전체 저장")
        self.option_page_breadcrumbs = QCheckBox("페이지 경로 표시")
        self.option_page_properties_as_front_matter = QCheckBox("페이지 속성을 Front Matter로 저장")
        self.option_include_document_title = QCheckBox("문서 제목 포함")
        self.option_enable_jira_enrichment = QCheckBox("Jira 정보 보강")
        self.option_skip_unchanged = QCheckBox("변경 없는 파일 건너뛰기")
        self.option_cleanup_stale = QCheckBox("사라진 파일 정리")
        self.option_verify_ssl = QCheckBox("SSL 검증")
        self.option_timeout = QSpinBox()
        self.option_timeout.setRange(1, 3600)
        self.option_max_workers = QSpinBox()
        self.option_max_workers.setRange(1, 128)
        self.schedule_enabled = QCheckBox("예약 사용")
        self.schedule_kind = QComboBox()
        self.schedule_kind.addItems(tuple(SCHEDULE_KIND_VALUES))
        self.schedule_hour = QComboBox()
        self.schedule_hour.addItems(HOUR_VALUES)
        self.schedule_minute = QComboBox()
        self.schedule_minute.addItems(MINUTE_VALUES)
        self.schedule_day_checks = {day: QCheckBox(label) for day, label in DAY_LABELS}
        self.schedule_day_of_month = QComboBox()
        self.schedule_day_of_month.addItems(tuple(str(day) for day in range(1, 32)))
        self.schedule_paused = QCheckBox("이 작업 예약 일시정지")
        self.schedule_times_list = QListWidget()
        self.cme_config_text = QTextEdit("{}")
        self.cme_config_text.setFontFamily(MONO)
        self.cme_config_text.setAcceptRichText(False)
        self.cme_config_text.setLineWrapMode(QTextEdit.NoWrap)
        self.cme_config_text.textChanged.connect(self.update_cme_config_preview)
        self.cme_config_preview = QTextEdit()
        self.cme_config_preview.setFontFamily(MONO)
        self.cme_config_preview.setAcceptRichText(False)
        self.cme_config_preview.setReadOnly(True)
        self.cme_config_preview.setLineWrapMode(QTextEdit.NoWrap)

        page = self._page()
        card = self._card()
        layout = QVBoxLayout(card)
        header = QHBoxLayout()
        self.editor_status = QLabel("새 작업")
        self.editor_status.setObjectName("PageTitle")
        header.addWidget(self.editor_status, 1)
        self.new_editor_job_button = self._button("새 작업", "secondary")
        self.new_editor_job_button.clicked.connect(self.new_job)
        self.save_job_button = self._button("작업 저장", "primary")
        self.save_job_button.clicked.connect(self.save_job)
        header.addWidget(self.new_editor_job_button)
        header.addWidget(self.save_job_button)
        layout.addLayout(header)

        self.editor_pages = QTabWidget()
        self.editor_pages.addTab(self._build_editor_basic_tab(), "기본 정보")
        self.editor_pages.addTab(self._build_editor_options_tab(), "CME 옵션")
        self.editor_pages.addTab(self._build_editor_schedule_tab(), "예약")
        self.editor_pages.addTab(self._build_editor_json_tab(), "고급 JSON")
        layout.addWidget(self.editor_pages, 1)
        page.layout().addWidget(card)
        self.pages.addWidget(page)
        self._connect_editor_preview_signals()
        self.set_export_options(dict(DEFAULT_EXPORT_OPTIONS))
        self.set_schedule_options(dict(DEFAULT_SCHEDULE))

    def _build_editor_basic_tab(self) -> QWidget:
        tab = QWidget()
        tab.setObjectName("TabSurface")
        layout = QVBoxLayout(tab)
        layout.addWidget(self._section_header("가져올 문서와 저장 위치", "Confluence 페이지, 페이지 트리, 스페이스, 조직 URL을 작업으로 저장합니다."))
        form = QGridLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        self._add_form_row(form, 0, "작업 이름", self.job_name)
        self._add_form_row(form, 1, "Confluence URL", self.job_url)
        target_row = QHBoxLayout()
        target_row.addWidget(self.job_target, 1)
        choose_button = self._button("찾아보기", "secondary")
        choose_button.clicked.connect(self.choose_target)
        target_row.addWidget(choose_button)
        self._add_form_row(form, 2, "저장 폴더", target_row)
        layout.addLayout(form)
        layout.addWidget(self._helper("여러 URL은 쉼표로 구분합니다. 내려받은 Markdown 파일과 첨부파일이 저장될 로컬 폴더를 지정하세요."))
        layout.addWidget(self.include_children)
        layout.addStretch(1)
        return tab

    def _build_editor_options_tab(self) -> QWidget:
        tab = QWidget()
        tab.setObjectName("TabSurface")
        layout = QVBoxLayout(tab)
        layout.addWidget(self._section_header("가져오기 범위", "대부분은 auto 그대로 두면 URL과 하위 페이지 포함 여부로 자동 결정됩니다."))
        form = QGridLayout()
        self._add_form_row(form, 0, "CME 범위", self.option_cme_scope)
        layout.addLayout(form)
        layout.addWidget(self._section_header("링크와 첨부파일", "내려받은 문서 안의 링크와 첨부파일 처리 방식을 선택합니다."))
        href_form = QGridLayout()
        self._add_form_row(href_form, 0, "페이지 링크", self.option_page_href)
        self._add_form_row(href_form, 1, "첨부파일 링크", self.option_attachment_href)
        layout.addLayout(href_form)
        checks = QGridLayout()
        for index, check in enumerate(
            (
                self.option_attachment_export_all,
                self.option_page_breadcrumbs,
                self.option_page_properties_as_front_matter,
                self.option_include_document_title,
                self.option_enable_jira_enrichment,
                self.option_skip_unchanged,
                self.option_cleanup_stale,
                self.option_verify_ssl,
            )
        ):
            checks.addWidget(check, index // 2, index % 2)
        layout.addLayout(checks)
        layout.addWidget(self._section_header("연결 옵션", "큰 문서 트리에서는 타임아웃과 동시 작업 수를 조정할 수 있습니다."))
        connection = QGridLayout()
        self._add_form_row(connection, 0, "타임아웃(초)", self.option_timeout)
        self._add_form_row(connection, 1, "동시 작업 수", self.option_max_workers)
        layout.addLayout(connection)
        layout.addStretch(1)
        return tab

    def _build_editor_json_tab(self) -> QWidget:
        tab = QWidget()
        tab.setObjectName("TabSurface")
        layout = QVBoxLayout(tab)
        layout.addWidget(self._section_header("CME Override JSON", "기본 설정으로 부족할 때 추가할 CME 설정만 입력합니다. 비워 두거나 {}를 사용해도 됩니다."))
        layout.addWidget(self.cme_config_text, 1)
        layout.addWidget(self._section_header("최종 설정 미리보기", "위 옵션과 Override JSON이 합쳐진 실행 설정입니다. 이 영역은 읽기 전용입니다."))
        layout.addWidget(self.cme_config_preview, 1)
        layout.addWidget(self._helper("인증 정보는 저장하지 마세요. 실행 직전에 Windows Credential Manager 값이 우선 적용됩니다."))
        return tab

    def _build_editor_schedule_tab(self) -> QWidget:
        tab = QWidget()
        tab.setObjectName("TabSurface")
        layout = QVBoxLayout(tab)
        layout.addWidget(self._section_header("예약 실행", "앱이 tray/background 상태로 실행 중일 때 예약된 시간에 같은 동기화 엔진을 실행합니다."))
        layout.addWidget(self.schedule_enabled)
        self.schedule_enabled.stateChanged.connect(lambda _state: self.update_schedule_condition_visibility())
        form = QGridLayout()
        self._add_form_row(form, 0, "예약 주기", self.schedule_kind)
        self.weekly_widget = QWidget()
        weekly_layout = QHBoxLayout(self.weekly_widget)
        weekly_layout.setContentsMargins(0, 0, 0, 0)
        for check in self.schedule_day_checks.values():
            weekly_layout.addWidget(check)
            check.stateChanged.connect(lambda _state: self.update_editor_next_run())
        weekly_layout.addStretch(1)
        self._add_form_row(form, 1, "요일", self.weekly_widget)
        self._add_form_row(form, 2, "매월 실행 일자", self.schedule_day_of_month)
        layout.addLayout(form)
        layout.addWidget(self._helper("없는 날짜는 그 달에 실행하지 않습니다."))
        self.schedule_kind.currentTextChanged.connect(lambda _text: self.update_schedule_condition_visibility())
        layout.addWidget(self._section_header("실행 시각", "하나 이상의 실행 시각을 등록하세요."))
        time_row = QHBoxLayout()
        time_row.addWidget(self.schedule_hour)
        time_row.addWidget(QLabel(":"))
        time_row.addWidget(self.schedule_minute)
        self.schedule_hour.currentTextChanged.connect(lambda _text: self.update_editor_next_run())
        self.schedule_minute.currentTextChanged.connect(lambda _text: self.update_editor_next_run())
        self.add_schedule_time_button = self._button("추가", "secondary")
        self.add_schedule_time_button.clicked.connect(self.add_schedule_time_from_picker)
        time_row.addWidget(self.add_schedule_time_button)
        time_row.addStretch(1)
        layout.addLayout(time_row)
        layout.addWidget(self._title("등록된 시각"))
        times = QHBoxLayout()
        self.schedule_times_list.setFixedHeight(110)
        times.addWidget(self.schedule_times_list, 1)
        self.remove_schedule_time_button = self._button("삭제", "secondary")
        self.remove_schedule_time_button.clicked.connect(self.remove_selected_schedule_time)
        times.addWidget(self.remove_schedule_time_button)
        layout.addLayout(times)
        layout.addWidget(self._helper("시간대: Asia/Seoul"))
        layout.addWidget(self.schedule_paused)
        self.schedule_day_of_month.currentTextChanged.connect(lambda _text: self.update_editor_next_run())
        self.schedule_paused.stateChanged.connect(lambda _state: self.update_editor_next_run())
        self.schedule_next_run_label = self._helper("다음 실행: -")
        layout.addWidget(self.schedule_next_run_label)
        layout.addWidget(self._helper("Windows 로그인 자동 시작이 꺼져 있으면 앱을 완전히 종료한 동안의 예약 실행은 보장되지 않습니다."))
        layout.addStretch(1)
        self.update_schedule_condition_visibility()
        return tab

    def _connect_editor_preview_signals(self) -> None:
        for combo in (self.option_cme_scope, self.option_page_href, self.option_attachment_href):
            combo.currentTextChanged.connect(lambda _text: self.update_cme_config_preview())
        for check in (
            self.option_attachment_export_all,
            self.option_page_breadcrumbs,
            self.option_page_properties_as_front_matter,
            self.option_include_document_title,
            self.option_enable_jira_enrichment,
            self.option_skip_unchanged,
            self.option_cleanup_stale,
            self.option_verify_ssl,
        ):
            check.stateChanged.connect(lambda _state: self.update_cme_config_preview())
        for spin in (self.option_timeout, self.option_max_workers):
            spin.valueChanged.connect(lambda _value: self.update_cme_config_preview())
        self.job_target.textChanged.connect(lambda _text: self.update_cme_config_preview())

    def _page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        return page

    def _card(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("Card")
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        return frame

    def _prepare_line_edit(self, field: QLineEdit, placeholder: str) -> None:
        field.setPlaceholderText(placeholder)
        field.setClearButtonEnabled(True)

    def _title(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("SectionTitle")
        return label

    def _helper(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("MutedLabel")
        label.setWordWrap(True)
        return label

    def _section_header(self, title: str, helper: str) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self._title(title))
        layout.addWidget(self._helper(helper))
        return box

    def _step_card(self, title: str, helper: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("InsetCard")
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QVBoxLayout(frame)
        layout.setSpacing(8)
        layout.addWidget(self._section_header(title, helper))
        return frame

    def _empty_jobs_view(self) -> QWidget:
        view = QWidget()
        layout = QVBoxLayout(view)
        layout.setAlignment(Qt.AlignCenter)
        title = QLabel("저장된 작업이 없습니다")
        title.setObjectName("SectionTitle")
        title.setAlignment(Qt.AlignCenter)
        helper = self._helper("Confluence URL과 저장 폴더를 지정해 첫 작업을 만들어 보세요.")
        helper.setAlignment(Qt.AlignCenter)
        action = self._button("새 작업 만들기", "primary")
        action.clicked.connect(self.new_job)
        layout.addStretch(1)
        layout.addWidget(title)
        layout.addWidget(helper)
        layout.addWidget(action, 0, Qt.AlignCenter)
        layout.addStretch(1)
        return view

    def _job_list_item_widget(self, job: Job) -> QWidget:
        widget = QFrame()
        widget.setObjectName("JobCard")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(5)
        title = QLabel(job.name or "이름 없는 작업")
        title.setObjectName("JobCardTitle")
        title.setWordWrap(True)
        status = QLabel(self._job_card_status(job))
        status.setObjectName("MutedLabel")
        status.setWordWrap(False)
        target = QLabel(self._compact_path(job.target_dir))
        target.setObjectName("MutedLabel")
        target.setWordWrap(False)
        layout.addWidget(title)
        layout.addWidget(status)
        layout.addWidget(target)
        return widget

    def _job_card_status(self, job: Job) -> str:
        latest = self._latest_run_status(job)
        if latest:
            return f"{self.format_schedule_status(job)} · 최근 {latest}"
        return f"{self.format_schedule_status(job)} · 아직 실행 기록 없음"

    def _latest_run_status(self, job: Job) -> str:
        try:
            history = load_run_history(job)
        except Exception:
            return "기록 읽기 실패"
        runs = history.get("runs") if isinstance(history, dict) else []
        if not isinstance(runs, list) or not runs:
            return ""
        latest = next((run for run in reversed(runs) if isinstance(run, dict)), None)
        if latest is None:
            return ""
        status = str(latest.get("status") or "")
        return {"success": "성공", "failed": "실패"}.get(status, status or "상태 없음")

    def _compact_path(self, value: str, max_length: int = 36) -> str:
        text = str(value or "").strip()
        if len(text) <= max_length:
            return text or "-"
        return f"...{text[-(max_length - 3):]}"

    def _button(self, text: str, role: str) -> QPushButton:
        button = QPushButton(text)
        button.setProperty("role", role)
        button.setCursor(Qt.PointingHandCursor)
        button.setIcon(self._button_icon(text, role))
        button.setIconSize(QSize(16, 16))
        return button

    def _button_icon(self, text: str, role: str) -> QIcon:
        icon = QStyle.StandardPixmap.SP_DialogApplyButton
        if role == "danger" or "삭제" in text:
            icon = QStyle.StandardPixmap.SP_TrashIcon
        elif "저장" in text:
            icon = QStyle.StandardPixmap.SP_DialogSaveButton
        elif "열기" in text or "찾아보기" in text:
            icon = QStyle.StandardPixmap.SP_DirOpenIcon
        elif "동기화" in text or "테스트" in text:
            icon = QStyle.StandardPixmap.SP_BrowserReload
        elif "새" in text or "만들기" in text or "추가" in text:
            icon = QStyle.StandardPixmap.SP_FileIcon
        elif "편집" in text:
            icon = QStyle.StandardPixmap.SP_FileDialogDetailedView
        return self.style().standardIcon(icon)

    def _add_form_row(self, form: QGridLayout, row: int, label: str, field: QWidget | QHBoxLayout) -> None:
        label_widget = QLabel(label)
        label_widget.setObjectName("FieldLabel")
        form.addWidget(label_widget, row, 0, Qt.AlignTop)
        if isinstance(field, QHBoxLayout):
            form.addLayout(field, row, 1)
        else:
            form.addWidget(field, row, 1)
        form.setColumnStretch(1, 1)

    def _job_summary_row(self, row: int, key: str, label: str) -> None:
        name = QLabel(label)
        name.setObjectName("FieldLabel")
        value = QLabel("-")
        value.setObjectName("FieldValue")
        value.setWordWrap(True)
        self.summary_grid.addWidget(name, row, 0, Qt.AlignTop)
        self.summary_grid.addWidget(value, row, 1)
        self.summary_grid.setColumnStretch(1, 1)
        self.job_summary_labels[key] = value

    def choose_target(self) -> None:
        if not self.ensure_not_busy():
            return
        selected = QFileDialog.getExistingDirectory(self, "저장 폴더 선택")
        if selected:
            self.job_target.setText(selected)

    def new_job(self) -> None:
        if not self.ensure_not_busy():
            return
        self.editing_job_id = None
        self.editor_status.setText("새 작업")
        self.job_name.setText("")
        self.job_url.setText("")
        self.job_target.setText(str(default_workspace() / "jobs" / "product-docs"))
        self.include_children.setChecked(True)
        defaults = dict(DEFAULT_EXPORT_OPTIONS)
        defaults["cme_config_json"] = "{}"
        self.set_export_options(defaults)
        self.set_schedule_options(dict(DEFAULT_SCHEDULE))
        self.editor_pages.setCurrentIndex(0)
        self.sidebar.setCurrentRow(2)
        self.set_status_text("새 작업 작성 중")

    def edit_selected(self) -> None:
        if not self.ensure_not_busy():
            return
        try:
            job = self.selected_job()
            self.editing_job_id = job.id
            self.editor_status.setText(f"편집 중: {job.id}")
            self.job_name.setText(job.name)
            self.job_url.setText(str(job.export_options.get("cme_urls") or job.confluence_url))
            self.job_target.setText(job.target_dir)
            self.include_children.setChecked(job.include_children)
            self.set_export_options(job.export_options)
            self.set_schedule_options(job.schedule)
            self.editor_pages.setCurrentIndex(0)
            self.sidebar.setCurrentRow(2)
            self.set_status_text(f"작업 편집 중: {job.name}")
        except Exception as exc:
            self.show_error(exc)

    def set_export_options(self, options: dict[str, object]) -> None:
        merged = dict(DEFAULT_EXPORT_OPTIONS)
        merged.update(options or {})
        self._set_combo(self.option_cme_scope, str(merged["cme_scope"]), "auto")
        self._set_combo(self.option_page_href, str(merged["page_href"]), "relative")
        self._set_combo(self.option_attachment_href, str(merged["attachment_href"]), "relative")
        self.option_attachment_export_all.setChecked(bool(merged["attachment_export_all"]))
        self.option_page_breadcrumbs.setChecked(bool(merged["page_breadcrumbs"]))
        self.option_page_properties_as_front_matter.setChecked(bool(merged["page_properties_as_front_matter"]))
        self.option_include_document_title.setChecked(bool(merged["include_document_title"]))
        self.option_enable_jira_enrichment.setChecked(bool(merged["enable_jira_enrichment"]))
        self.option_skip_unchanged.setChecked(bool(merged["skip_unchanged"]))
        self.option_cleanup_stale.setChecked(bool(merged["cleanup_stale"]))
        self.option_verify_ssl.setChecked(bool(merged["verify_ssl"]))
        self.option_timeout.setValue(int(merged["timeout"]))
        self.option_max_workers.setValue(int(merged["max_workers"]))
        self.set_cme_config_json(self.display_cme_override_json(merged.get("cme_config_json")))
        self.update_cme_config_preview()

    def set_schedule_options(self, schedule: dict[str, object]) -> None:
        merged = normalize_schedule(schedule)
        self.schedule_enabled.setChecked(bool(merged["enabled"]))
        self._set_combo(self.schedule_kind, SCHEDULE_KIND_LABELS.get(str(merged["kind"]), "매일"), "매일")
        self.set_schedule_times(merged["times"])
        first_time = self.schedule_times_from_list()[0] if self.schedule_times_from_list() else "09:00"
        if ":" in first_time:
            hour, minute = first_time.split(":", 1)
            self._set_combo(self.schedule_hour, hour, "09")
            self._set_combo(self.schedule_minute, minute, "00")
        selected_days: set[int] = set()
        for item in merged["days_of_week"]:
            try:
                selected_days.add(int(item))
            except (TypeError, ValueError):
                continue
        for day, check in self.schedule_day_checks.items():
            check.setChecked(day in selected_days)
        self._set_combo(self.schedule_day_of_month, str(merged["day_of_month"] or 1), "1")
        self.schedule_paused.setChecked(bool(merged["paused"]))
        self.update_schedule_condition_visibility()

    def schedule_from_editor(self) -> dict[str, object]:
        schedule = normalize_schedule(None)
        schedule.update(
            {
                "enabled": self.schedule_enabled.isChecked(),
                "kind": SCHEDULE_KIND_VALUES.get(self.schedule_kind.currentText(), "daily"),
                "times": self.schedule_times_from_list() or ["09:00"],
                "days_of_week": [day for day, check in self.schedule_day_checks.items() if check.isChecked()],
                "day_of_month": int(self.schedule_day_of_month.currentText() or 1),
                "timezone": "Asia/Seoul",
                "misfire_policy": "skip",
                "concurrency_policy": "skip_if_running",
                "paused": self.schedule_paused.isChecked(),
            }
        )
        return schedule

    def _set_combo(self, combo: QComboBox, value: str, fallback: str) -> None:
        index = combo.findText(value)
        if index < 0:
            index = combo.findText(fallback)
        combo.setCurrentIndex(max(0, index))

    def schedule_times_from_list(self) -> list[str]:
        return sorted(dict.fromkeys(self.schedule_times_list.item(index).text() for index in range(self.schedule_times_list.count())))

    def set_schedule_times(self, values: object) -> None:
        self.schedule_times_list.clear()
        source = values if isinstance(values, list) else ["09:00"]
        for value in sorted(dict.fromkeys(str(item) for item in source if str(item).strip())):
            self.schedule_times_list.addItem(value)

    def add_schedule_time(self, value: str) -> None:
        value = value.strip()
        if not value:
            return
        existing = set(self.schedule_times_from_list())
        existing.add(value)
        self.set_schedule_times(sorted(existing))

    def add_schedule_time_from_picker(self) -> None:
        self.add_schedule_time(f"{self.schedule_hour.currentText()}:{self.schedule_minute.currentText()}")
        self.update_schedule_condition_visibility()

    def remove_selected_schedule_time(self) -> None:
        for item in self.schedule_times_list.selectedItems():
            self.schedule_times_list.takeItem(self.schedule_times_list.row(item))
        self.update_schedule_condition_visibility()

    def update_schedule_condition_visibility(self) -> None:
        kind = SCHEDULE_KIND_VALUES.get(self.schedule_kind.currentText(), "daily")
        enabled = self.schedule_enabled.isChecked()
        self.weekly_widget.setVisible(kind == "weekly")
        self.schedule_day_of_month.setVisible(kind == "monthly")
        for widget in (
            self.schedule_kind,
            self.weekly_widget,
            self.schedule_day_of_month,
            self.schedule_hour,
            self.schedule_minute,
            self.add_schedule_time_button,
            self.remove_schedule_time_button,
            self.schedule_times_list,
            self.schedule_paused,
        ):
            widget.setEnabled(enabled)
        self.update_editor_next_run()

    def update_editor_next_run(self) -> None:
        if not hasattr(self, "schedule_next_run_label"):
            return
        job = Job(
            id=self.editing_job_id or "draft",
            name=self.job_name.text() or "draft",
            confluence_url=self.job_url.text() or "https://example.atlassian.net/wiki",
            target_dir=self.job_target.text() or str(default_workspace()),
            include_children=self.include_children.isChecked(),
            export_options=self.export_options_from_editor(),
            schedule=self.schedule_from_editor(),
        )
        next_run = next_run_at(job)
        self.schedule_next_run_label.setText(f"다음 실행: {_format_timestamp(next_run.isoformat()) if next_run else '-'}")

    def export_options_from_editor(self) -> dict[str, object]:
        return {
            "cme_scope": self.option_cme_scope.currentText(),
            "cme_urls": self.job_url.text(),
            "cme_config_json": self.get_cme_config_json(),
            "page_href": self.option_page_href.currentText(),
            "attachment_href": self.option_attachment_href.currentText(),
            "attachment_export_all": self.option_attachment_export_all.isChecked(),
            "page_breadcrumbs": self.option_page_breadcrumbs.isChecked(),
            "page_properties_as_front_matter": self.option_page_properties_as_front_matter.isChecked(),
            "include_document_title": self.option_include_document_title.isChecked(),
            "enable_jira_enrichment": self.option_enable_jira_enrichment.isChecked(),
            "skip_unchanged": self.option_skip_unchanged.isChecked(),
            "cleanup_stale": self.option_cleanup_stale.isChecked(),
            "verify_ssl": self.option_verify_ssl.isChecked(),
            "timeout": self.option_timeout.value(),
            "max_workers": self.option_max_workers.value(),
        }

    def display_cme_override_json(self, value: object) -> str:
        text = str(value or "").strip()
        if not text:
            return "{}"
        try:
            data = parse_cme_config_json(text)
        except AppError:
            return text
        default = json.loads(default_cme_config_json(self.job_target.text()))
        if data == default:
            return "{}"
        return json.dumps(data, ensure_ascii=False, indent=2)

    def set_cme_config_json(self, value: str) -> None:
        self.cme_config_text.setPlainText(value)

    def get_cme_config_json(self) -> str:
        return self.cme_config_text.toPlainText().strip() or "{}"

    def update_cme_config_preview(self) -> None:
        if not hasattr(self, "cme_config_preview"):
            return
        try:
            config = copy.deepcopy(DEFAULT_CME_CONFIG)
            preview_job = Job(
                id=self.editing_job_id or "draft",
                name=self.job_name.text() or "draft",
                confluence_url=self.job_url.text() or "https://example.atlassian.net/wiki",
                target_dir=self.job_target.text() or str(default_workspace()),
                include_children=self.include_children.isChecked(),
                export_options=self.export_options_from_editor(),
                schedule=self.schedule_from_editor() if hasattr(self, "schedule_times_list") else dict(DEFAULT_SCHEDULE),
            )
            apply_common_job_options(config, preview_job)
            deep_merge(config, parse_cme_config_json(self.get_cme_config_json()))
            config["export"]["output_path"] = str(preview_job.workspace)  # type: ignore[index]
            self.cme_config_preview.setPlainText(json.dumps(config, ensure_ascii=False, indent=2))
        except Exception as exc:
            error = classify_exception(exc if isinstance(exc, Exception) else Exception(str(exc)))
            self.cme_config_preview.setPlainText(f"JSON 형식을 확인하세요.\n{error.user_message}")

    def save_job(self) -> None:
        if not self.ensure_not_busy():
            return
        existing = self.store.load()
        job_id = self.editing_job_id or stable_job_id(self.job_name.text(), {job.id for job in existing})
        job = Job(
            id=job_id,
            name=self.job_name.text(),
            confluence_url=self.job_url.text(),
            target_dir=self.job_target.text(),
            include_children=self.include_children.isChecked(),
            include_attachments=False,
            export_options=self.export_options_from_editor(),
            schedule=self.schedule_from_editor(),
        )
        try:
            validate_schedule(job.schedule)
            validate_job(job, create_dirs=True)
            self.store.upsert(job)
            self.editing_job_id = job.id
            self.editor_status.setText(f"편집 중: {job.id}")
            self.refresh_jobs(select_job_id=job.id)
            self.set_status_text(f"작업 저장됨: {job.name}", "success")
            self.sidebar.setCurrentRow(1)
            QMessageBox.information(self, "저장됨", "작업이 저장되었습니다.")
        except Exception as exc:
            self.show_error(exc)

    def refresh_jobs(self, select_job_id: str | None = None) -> None:
        self.job_list.clear()
        jobs = self.store.load()
        self.job_list_stack.setCurrentIndex(1 if jobs else 0)
        for job in jobs:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, job.id)
            widget = self._job_list_item_widget(job)
            item.setSizeHint(QSize(0, 92))
            self.job_list.addItem(item)
            self.job_list.setItemWidget(item, widget)
        if jobs:
            target = select_job_id if select_job_id in {job.id for job in jobs} else jobs[0].id
            for row in range(self.job_list.count()):
                if self.job_list.item(row).data(Qt.UserRole) == target:
                    self.job_list.setCurrentRow(row)
                    break
        self.update_job_details()

    def selected_job(self) -> Job:
        items = self.job_list.selectedItems()
        if not items:
            raise AppError("Config", "NO_JOB_SELECTED", "작업을 선택하세요.", "", False)
        return self.store.get(str(items[0].data(Qt.UserRole)))

    def update_job_details(self) -> None:
        try:
            job = self.selected_job()
        except Exception:
            self.set_job_actions_enabled(False)
            self.set_job_summary(None)
            self.set_run_history_rows([])
            return
        self.set_job_actions_enabled(True)
        scope = str(job.export_options.get("cme_scope") or "auto")
        urls = str(job.export_options.get("cme_urls") or job.confluence_url)
        self.set_job_summary(job, scope, urls)
        self.set_run_history_rows(format_job_run_history_rows(job))

    def set_job_actions_enabled(self, enabled: bool) -> None:
        enabled = enabled and not self.busy
        for widget in (self.sync_button, self.edit_button, self.open_target_button, self.delete_button):
            widget.setEnabled(enabled)

    def set_job_summary(self, job: Job | None, scope: str = "-", urls: str = "-") -> None:
        if job is None:
            values = {
                "name": "작업을 선택하세요.",
                "scope": "-",
                "schedule": "-",
                "next_run": "-",
                "last_event": "-",
                "target": "-",
                "url": "-",
            }
        else:
            next_run = next_run_at(job)
            values = {
                "name": job.name or "-",
                "scope": scope or "-",
                "schedule": self.format_schedule_status(job),
                "next_run": _format_timestamp(next_run.isoformat()) if next_run else "-",
                "last_event": self.format_last_scheduler_event(job.id),
                "target": job.target_dir or "-",
                "url": urls or "-",
            }
        for key, value in values.items():
            self.job_summary_labels[key].setText(value)

    def format_schedule_status(self, job: Job) -> str:
        schedule = job.schedule
        if not job.enabled:
            return "작업 비활성"
        if not bool(schedule.get("enabled")):
            return "꺼짐"
        if bool(schedule.get("paused")):
            return "일시정지"
        label = SCHEDULE_KIND_LABELS.get(str(schedule.get("kind")), str(schedule.get("kind")))
        times = schedule.get("times")
        if not isinstance(times, list) or not times:
            times = [schedule.get("time") or "09:00"]
        time_text = ", ".join(str(value) for value in times)
        if schedule.get("kind") == "weekly":
            day_names = {day: label for day, label in DAY_LABELS}
            days = schedule.get("days_of_week") if isinstance(schedule.get("days_of_week"), list) else []
            labels = []
            for day in days:
                try:
                    labels.append(day_names.get(int(day), str(day)))
                except (TypeError, ValueError):
                    labels.append(str(day))
            return f"{label} {'/'.join(labels)} {time_text}"
        if schedule.get("kind") == "monthly":
            return f"{label} {schedule.get('day_of_month')}일 {time_text}"
        return f"{label} {time_text}"

    def format_last_scheduler_event(self, job_id: str) -> str:
        for event in reversed(load_scheduler_events(limit=100)):
            if event.get("job_id") == job_id:
                return f"{event.get('event_type')} · {event.get('result')}"
        return "-"

    def set_run_history_rows(self, rows: list[tuple[str, str, str, str, str, str]]) -> None:
        self.run_history_table.setRowCount(0)
        if not rows:
            rows = [("기록 없음", "-", "-", "-", "-", "-")]
        for row, values in enumerate(rows):
            self.run_history_table.insertRow(row)
            for column, value in enumerate(values):
                self.run_history_table.setItem(row, column, QTableWidgetItem(value))

    def open_selected_target(self) -> None:
        if not self.ensure_not_busy():
            return
        try:
            path = Path(self.selected_job().target_dir)
            path.mkdir(parents=True, exist_ok=True)
            os.startfile(path)  # type: ignore[attr-defined]
        except Exception as exc:
            self.show_error(exc)

    def _engine(self, progress: Callable[[str, int, int], None] | None = None) -> SyncEngine:
        return SyncEngine(progress=progress)

    def run_selected(self) -> None:
        try:
            job = self.selected_job()
            engine = self._engine(self.threadsafe_progress)
            self.run_background(
                "지금 동기화",
                lambda: self.coordinator.run(job, lambda: engine.apply(job, trigger="manual")),
                self.write_sync_result,
                self.show_sync_error,
                self.write_sync_text,
            )
        except Exception as exc:
            self.show_error(exc)

    def run_background(
        self,
        label: str,
        work: Callable[[], object],
        on_success: Callable[[object], None],
        on_error: Callable[[Exception], None] | None = None,
        on_start: Callable[[str], None] | None = None,
    ) -> None:
        if self.busy:
            QMessageBox.information(self, "실행 중", "이미 실행 중인 작업이 있습니다.")
            return
        self.busy = True
        self.current_worker_label = label
        self.current_success = on_success
        self.current_error = on_error
        self.set_status_text(f"{label} 실행 중", "warning")
        self.set_running_controls(label, True)
        start_text = f"{label} 실행 중...\n큰 Confluence 문서 트리는 시간이 걸릴 수 있습니다.\n"
        if on_start is None:
            self.set_status_text(start_text)
        else:
            on_start(start_text)

        def worker() -> None:
            try:
                result = work()
            except Exception as exc:
                self.background_error.emit(exc)
            else:
                self.background_success.emit(result)

        threading.Thread(target=worker, daemon=True).start()

    def finish_background_success(self, result: object) -> None:
        label = self.current_worker_label
        callback = self.current_success
        self.busy = False
        self.set_running_controls(label, False)
        self.set_status_text(f"{label} 완료", "success")
        self.current_worker_label = ""
        self.current_success = None
        self.current_error = None
        if callback is not None:
            callback(result)

    def finish_background_error(self, exc: object) -> None:
        callback = self.current_error
        label = self.current_worker_label
        self.busy = False
        self.set_running_controls(label, False)
        self.set_status_text("오류", "error")
        self.current_worker_label = ""
        self.current_success = None
        self.current_error = None
        if callback is None:
            self.show_error(exc if isinstance(exc, Exception) else Exception(str(exc)))
        else:
            callback(exc if isinstance(exc, Exception) else Exception(str(exc)))

    def set_running_controls(self, label: str, running: bool) -> None:
        enabled = not running
        for widget in (
            self.new_job_button,
            self.sync_button,
            self.edit_button,
            self.open_target_button,
            self.delete_button,
            self.save_job_button,
            self.new_editor_job_button,
            self.test_connection_button,
            self.logout_button,
        ):
            widget.setEnabled(enabled)
        self.sync_button.setText("동기화 중..." if running and label == "지금 동기화" else "지금 동기화")
        self.test_connection_button.setText("테스트 중..." if running and label == "연결 테스트" else "연결 테스트")
        if running:
            self.save_create_button.setEnabled(False)
        else:
            self.update_connection_actions()
            self.set_job_actions_enabled(bool(self.job_list.selectedItems()))

    def delete_selected(self) -> None:
        if not self.ensure_not_busy():
            return
        try:
            job = self.selected_job()
            if QMessageBox.question(self, "작업 삭제", f"'{job.name}' 작업을 삭제할까요?") != QMessageBox.Yes:
                return
            self.store.delete(job.id)
            self.refresh_jobs()
            self.set_status_text(f"작업 삭제됨: {job.name}", "warning")
        except Exception as exc:
            self.show_error(exc)

    def save_settings(self, open_editor: bool = False) -> None:
        if not self.ensure_not_busy():
            return
        token = self.token.text()
        if not token:
            token = _credential_store().read(self.base_url.text(), self.email.text()) or ""
        errors = validate_auth_input(self.base_url.text(), self.email.text(), token)
        if errors:
            QMessageBox.critical(self, "연결 정보", "\n".join(errors.values()))
            return
        if self.connection_verified_fingerprint != self._connection_fingerprint(self.base_url.text(), self.email.text(), token):
            QMessageBox.critical(self, "연결 테스트 필요", "현재 입력한 연결 정보로 연결 테스트를 먼저 통과해야 저장할 수 있습니다.")
            return
        try:
            if self.token.text():
                _credential_store().write(self.base_url.text(), self.email.text(), self.token.text())
            save_settings(self.base_url.text(), self.email.text())
            self.token.setText("")
            self.set_status_text("연결 정보 저장됨", "success")
            if open_editor:
                self.new_job()
            else:
                QMessageBox.information(self, "저장됨", "연결 정보가 저장되었습니다.")
        except Exception as exc:
            self.show_error(exc)

    def test_connection(self) -> None:
        if not self.ensure_not_busy():
            return
        try:
            base_url = self.base_url.text()
            email = self.email.text()
            token = self.token.text() or _credential_store().read(base_url, email)
            if not token:
                raise AppError("Auth", "TOKEN_NOT_FOUND", "API 토큰을 입력하거나 먼저 저장하세요.", "", False)
            errors = validate_auth_input(base_url, email, token)
            if errors:
                QMessageBox.critical(self, "연결 정보", "\n".join(errors.values()))
                return
            fingerprint = self._connection_fingerprint(base_url, email, token)
            self.run_background(
                "연결 테스트",
                lambda: test_cme_connection(base_url, email, token),
                lambda result: self.write_connection_result(result, fingerprint),
                self.show_connection_error,
                self.write_connection_text,
            )
        except Exception as exc:
            self.show_connection_error(exc)

    def logout(self) -> None:
        if not self.ensure_not_busy():
            return
        _credential_store().delete(self.base_url.text(), self.email.text())
        self.connection_verified_fingerprint = None
        self.update_connection_actions()
        self.set_status_text("저장된 API 토큰 삭제됨", "warning")

    def save_auto_start_setting(self) -> None:
        enabled = self.auto_start_check.isChecked()
        try:
            set_windows_auto_start(enabled)
            save_app_setting("auto_start", enabled)
            self.auto_start = enabled
            if enabled:
                self.set_status_text("Windows 로그인 자동 시작 설정이 저장되었습니다.", "success")
            else:
                self.set_status_text("자동 시작 꺼짐: 완전 종료 중 예약 실행은 보장되지 않습니다.", "warning")
        except Exception as exc:
            self.auto_start_check.blockSignals(True)
            self.auto_start_check.setChecked(not enabled)
            self.auto_start_check.blockSignals(False)
            self.show_error(exc)

    def toggle_global_pause(self) -> None:
        self.global_schedule_paused = self.global_pause_check.isChecked()
        save_app_setting("schedule_paused", self.global_schedule_paused)
        self.set_status_text("스케줄 일시정지" if self.global_schedule_paused else "스케줄 재개", "warning" if self.global_schedule_paused else "success")

    def start_background_runtime(self) -> None:
        if os.environ.get("CONFLUENCE_SYNC_DISABLE_TRAY") == "1":
            self.tray_available = False
            self.scheduler_runtime = SchedulerRuntime(
                self.store.load,
                self.run_scheduled_job,
                coordinator=self.coordinator,
                schedule_paused=lambda: self.global_schedule_paused,
                notify_failure=lambda job, exc: self.scheduled_failure.emit(job, exc),
            )
            self.scheduler_runtime.start()
            return
        self.tray_runtime = TrayRuntime(
            icon_path=_asset_path("app-256.png"),
            show_window=lambda: self.show_window_requested.emit(),
            quit_app=lambda: self.quit_requested.emit(),
            toggle_pause=lambda: self.toggle_pause_requested.emit(),
        )
        self.tray_available = self.tray_runtime.start()
        if not self.tray_available:
            detail = f" ({self.tray_runtime.last_error})" if self.tray_runtime.last_error else ""
            self.set_status_text(f"Tray 초기화 실패: 창을 닫으면 앱이 종료됩니다.{detail}", "warning")
            return
        self.scheduler_runtime = SchedulerRuntime(
            self.store.load,
            self.run_scheduled_job,
            coordinator=self.coordinator,
            schedule_paused=lambda: self.global_schedule_paused,
            notify_failure=lambda job, exc: self.scheduled_failure.emit(job, exc),
        )
        self.scheduler_runtime.start()

    def run_scheduled_job(self, job: Job) -> dict[str, object]:
        return self._engine().apply(job, trigger="scheduled")

    def notify_scheduled_failure(self, job: object, exc: object) -> None:
        if not isinstance(job, Job) or not isinstance(exc, Exception):
            return
        error = classify_exception(exc)
        self.set_status_text(f"예약 실행 실패: {job.name}", "error")
        self.update_job_details()
        if self.tray_runtime is not None:
            try:
                self.tray_runtime.notify("Confluence Sync 예약 실패", f"{job.name}: {error.user_message}")
            except Exception:
                pass

    def show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.update_job_details()

    def quit_from_tray(self) -> None:
        if self.busy or self.coordinator.is_running():
            QMessageBox.information(self, "실행 중", "현재 실행 중인 작업이 끝난 뒤 다시 종료하세요.")
            return
        if self.scheduler_runtime is not None:
            self.scheduler_runtime.stop()
        if self.tray_runtime is not None:
            self.tray_runtime.stop()
        QApplication.instance().quit()

    def toggle_pause_from_tray(self) -> None:
        self.global_pause_check.setChecked(not self.global_pause_check.isChecked())

    def ensure_not_busy(self) -> bool:
        if self.busy or self.coordinator.is_running():
            QMessageBox.information(self, "실행 중", "현재 작업이 끝날 때까지 기다려 주세요.")
            return False
        return True

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.busy or self.coordinator.is_running():
            QMessageBox.information(self, "실행 중", "현재 작업이 끝난 뒤 창을 닫아 주세요.")
            event.ignore()
            return
        if not self.tray_available:
            event.accept()
            return
        event.ignore()
        self.hide()
        if not self.close_notice_shown:
            self.close_notice_shown = True
            QMessageBox.information(self, "Background 실행", "창을 닫아도 예약 동기화가 tray/background에서 계속 실행됩니다.")

    def write_sync_text(self, text: str) -> None:
        self.set_status_text(mask_sensitive(text).strip().splitlines()[0])

    def write_sync_result(self, data: object) -> None:
        summary = data.get("summary") if isinstance(data, dict) and isinstance(data.get("summary"), dict) else {}
        created = int(summary.get("created", 0)) if isinstance(summary, dict) else 0
        updated = int(summary.get("updated", 0)) if isinstance(summary, dict) else 0
        deleted = int(summary.get("deleted", 0)) if isinstance(summary, dict) else 0
        skipped = int(summary.get("skipped", 0)) if isinstance(summary, dict) else 0
        errors = int(summary.get("errors", 0)) if isinstance(summary, dict) else 0
        if errors:
            self.set_status_text("동기화 완료", "warning")
            self.update_job_details()
            QMessageBox.warning(self, "동기화 완료", "동기화가 끝났지만 오류가 기록되었습니다.")
            return
        exported = created + updated
        self.set_status_text(f"동기화 성공 · 생성/업데이트 {exported} · 삭제 {deleted} · 건너뜀 {skipped}", "success")
        self.update_job_details()
        QMessageBox.information(self, "동기화 성공", "Confluence 문서 동기화가 완료되었습니다.")

    def show_sync_error(self, exc: Exception) -> None:
        error = classify_exception(exc)
        self.set_status_text("동기화 실패", "error")
        try:
            self.set_run_history_rows(format_job_run_history_rows(self.selected_job()))
        except Exception:
            pass
        QMessageBox.critical(self, error.category, error.user_message)

    def write_connection_text(self, text: str) -> None:
        self.set_status_text(mask_sensitive(text).strip().splitlines()[0])

    def write_connection_result(self, data: object, fingerprint: str) -> None:
        ok = isinstance(data, dict) and data.get("ok") is True
        if ok:
            self.connection_verified_fingerprint = fingerprint
            self.update_connection_actions()
            self.set_status_text("연결 테스트 성공", "success")
            QMessageBox.information(self, "연결 테스트 성공", "Confluence 연결 테스트를 통과했습니다. 이제 저장 후 작업 만들기를 진행할 수 있습니다.")
            return
        self.connection_verified_fingerprint = None
        self.update_connection_actions()
        self.set_status_text("연결 테스트 실패", "error")

    def show_connection_error(self, exc: Exception) -> None:
        self.connection_verified_fingerprint = None
        self.update_connection_actions()
        error = classify_exception(exc)
        self.set_status_text("연결 테스트 실패", "error")
        QMessageBox.critical(self, error.category, error.user_message)

    def connection_inputs_changed(self, *_args: object) -> None:
        self.connection_verified_fingerprint = None
        self.update_connection_actions()

    def update_connection_actions(self) -> None:
        token = self.token.text()
        if not token:
            try:
                token = _credential_store().read(self.base_url.text(), self.email.text()) or ""
            except Exception:
                token = ""
        verified = self.connection_verified_fingerprint == self._connection_fingerprint(self.base_url.text(), self.email.text(), token)
        self.save_create_button.setEnabled(bool(verified) and not self.busy)

    def _connection_fingerprint(self, base_url: str, email: str, token: str) -> str:
        payload = json.dumps({"base_url": base_url.strip(), "email": email.strip(), "token": token}, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def threadsafe_progress(self, text: str, _current: int, _total: int) -> None:
        self.progress_message.emit(mask_sensitive(text).strip().splitlines()[0] if text.strip() else "준비됨")

    def set_status_text(self, text: str, tone: str = "info") -> None:
        clean = mask_sensitive(text).strip().splitlines()[0] if text.strip() else "준비됨"
        self.status_badge.setText(clean)
        self.status_badge.set_tone(tone)

    def show_error(self, exc: Exception) -> None:
        error = classify_exception(exc)
        self.set_status_text("오류", "error")
        QMessageBox.critical(self, error.category, error.user_message)


APP_STYLESHEET = f"""
QMainWindow, QWidget {{
    background: {BG};
    color: {TEXT};
    font-family: "{APP_FONT}";
    font-size: 10pt;
}}
QLabel {{
    background: transparent;
}}
QFrame#SidebarFrame {{
    background: #101828;
    border: 0;
    min-width: 212px;
    max-width: 212px;
}}
QLabel#SidebarBrand {{
    color: white;
    font-size: 14pt;
    font-weight: 800;
}}
QLabel#SidebarHint {{
    color: #98a2b3;
    font-size: 9pt;
}}
QListWidget#Sidebar {{
    background: transparent;
    color: #d1d5db;
    border: 0;
    padding: 6px 0;
    font-weight: 600;
    outline: 0;
}}
QListWidget#Sidebar::item {{
    border-radius: 8px;
    padding: 11px 12px;
    margin: 2px 0;
}}
QListWidget#Sidebar::item:hover {{
    background: #1d2939;
    color: white;
}}
QListWidget#Sidebar::item:selected {{
    background: {ACCENT};
    color: white;
}}
QLabel#AppTitle {{
    font-size: 19pt;
    font-weight: 800;
}}
QLabel#PageTitle {{
    font-size: 14pt;
    font-weight: 700;
}}
QLabel#SectionTitle {{
    font-size: 12pt;
    font-weight: 700;
}}
QLabel#MutedLabel {{
    color: {MUTED};
}}
QLabel#FieldLabel {{
    color: {MUTED};
    font-weight: 600;
    min-width: 150px;
}}
QLabel#FieldValue {{
    color: {TEXT};
}}
QFrame#Card {{
    background: {SURFACE};
    border: 1px solid #e4e9f2;
    border-radius: 8px;
    padding: 18px;
}}
QFrame#InsetCard {{
    background: #f8fafc;
    border: 1px solid #e4e9f2;
    border-radius: 8px;
    padding: 12px;
}}
QFrame#JobCard {{
    background: #ffffff;
    border: 1px solid #e4e9f2;
    border-radius: 8px;
}}
QFrame#JobCard:hover {{
    border-color: #b9c8f8;
    background: #fbfdff;
}}
QLabel#JobCardTitle {{
    font-weight: 700;
    color: {TEXT};
}}
QLineEdit, QTextEdit, QComboBox, QSpinBox, QListWidget, QTableWidget {{
    background: white;
    border: 1px solid #ccd4e0;
    border-radius: 6px;
    padding: 7px;
    selection-background-color: #dbeafe;
}}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus {{
    border: 1px solid {FOCUS};
}}
QLineEdit#PathField {{
    font-family: "{MONO}";
}}
QListWidget#JobList {{
    border: 0;
    background: transparent;
    padding: 0;
}}
QListWidget#JobList::viewport {{
    background: transparent;
}}
QListWidget#JobList::item {{
    margin: 0 0 8px 0;
    border-radius: 8px;
}}
QListWidget#JobList::item:selected {{
    background: #dbeafe;
}}
QTableWidget {{
    gridline-color: #e4e9f2;
    alternate-background-color: #f8fafc;
    border: 1px solid #e4e9f2;
}}
QHeaderView::section {{
    background: #f8fafc;
    border: 0;
    border-right: 1px solid #e4e9f2;
    border-bottom: 1px solid #e4e9f2;
    padding: 8px;
    font-weight: 700;
}}
QTabWidget::pane {{
    border: 1px solid #e4e9f2;
    border-radius: 8px;
    background: white;
    top: -1px;
}}
QWidget#TabSurface {{
    background: white;
}}
QSplitter::handle {{
    background: #edf2f7;
}}
QSplitter::handle:hover {{
    background: #d9e3f0;
}}
QTabBar::tab {{
    background: #f1f5f9;
    color: {MUTED};
    padding: 10px 18px;
    border: 1px solid #d9e1ee;
    border-bottom: 0;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    margin-right: 3px;
}}
QTabBar::tab:hover {{
    background: #e8eef7;
    color: {TEXT};
}}
QTabBar::tab:selected {{
    background: white;
    color: {TEXT};
    font-weight: 700;
}}
QPushButton {{
    border-radius: 7px;
    padding: 8px 14px;
    font-weight: 700;
    min-height: 20px;
}}
QPushButton[role="primary"] {{
    background: {ACCENT};
    color: white;
    border: 1px solid {ACCENT};
}}
QPushButton[role="primary"]:hover {{
    background: {ACCENT_DARK};
    border-color: {ACCENT_DARK};
}}
QPushButton[role="secondary"] {{
    background: white;
    color: {TEXT};
    border: 1px solid #cbd5e1;
}}
QPushButton[role="secondary"]:hover {{
    background: #f8fafc;
    border-color: #9aa8bd;
}}
QPushButton[role="danger"] {{
    background: {DANGER};
    color: white;
    border: 1px solid {DANGER};
}}
QPushButton[role="danger"]:hover {{
    background: #912018;
    border-color: #912018;
}}
QPushButton:disabled {{
    background: #eef2f6;
    color: #98a2b3;
    border-color: #d7dee8;
}}
QCheckBox {{
    spacing: 8px;
}}
"""


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    configure_application_font()
    window = ConfluenceSyncApp()
    window.show()
    return int(app.exec())


if __name__ == "__main__":
    raise SystemExit(main())
