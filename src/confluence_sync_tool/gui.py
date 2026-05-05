from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import tkinter as tk
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from .cli import _credential_store
from .cme_backend import CME_SCOPES, default_cme_config_json, test_cme_connection
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
BG = "#f6f7f9"
SURFACE = "#ffffff"
BORDER = "#d8dee8"
TEXT = "#1f2937"
MUTED = "#667085"
ACCENT = "#2563eb"
DANGER = "#b42318"
MONO = ("Consolas", 10)


def _asset_path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    if hasattr(sys, "_MEIPASS"):
        return base / "confluence_sync_tool" / "assets" / name
    return base / "assets" / name


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


class ConfluenceSyncApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        ensure_app_dirs()
        self.title("Confluence 문서 동기화")
        self.geometry("1260x860")
        self.minsize(1040, 720)
        self.configure(background=BG)
        self._set_window_icon()
        self.store = JobStore()
        self.editing_job_id: str | None = None
        self.connection_verified_fingerprint: str | None = None
        self.busy = False
        settings = load_settings()
        self.global_schedule_paused = tk.BooleanVar(value=bool(settings.get("schedule_paused")))
        self.auto_start = tk.BooleanVar(value=bool(settings.get("auto_start")))
        self.coordinator = RunCoordinator(global_worker_limit=int(settings.get("global_worker_limit") or 1))
        self.scheduler_runtime: SchedulerRuntime | None = None
        self.tray_runtime: TrayRuntime | None = None
        self.tray_available = False
        self.close_notice_shown = False
        self.status_text = tk.StringVar(value="준비됨")
        self._build()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.refresh_jobs()
        self.start_background_runtime()

    def _set_window_icon(self) -> None:
        icon = _asset_path("app.ico")
        if not icon.exists():
            return
        try:
            self.iconbitmap(str(icon))
        except tk.TclError:
            pass
        try:
            self.iconbitmap(default=str(icon))
        except tk.TclError:
            pass

    def _build(self) -> None:
        self._apply_style()
        shell = ttk.Frame(self, style="App.TFrame", padding=(16, 14, 16, 10))
        shell.pack(fill="both", expand=True)

        header = ttk.Frame(shell, style="App.TFrame")
        header.pack(fill="x", pady=(0, 12))
        ttk.Label(header, text="Confluence 문서 동기화", style="AppTitle.TLabel").pack(side="left")
        ttk.Label(header, textvariable=self.status_text, style="Status.TLabel").pack(side="right")

        self.tabs = ttk.Notebook(shell, style="Modern.TNotebook")
        self.tabs.pack(fill="both", expand=True)
        self.settings_tab = ttk.Frame(self.tabs, style="App.TFrame", padding=12)
        self.jobs_tab = ttk.Frame(self.tabs, style="App.TFrame", padding=12)
        self.editor_tab = ttk.Frame(self.tabs, style="App.TFrame", padding=12)
        self.tabs.add(self.settings_tab, text="연결")
        self.tabs.add(self.jobs_tab, text="작업")
        self.tabs.add(self.editor_tab, text="작업 설정")

        self._build_settings()
        self._build_jobs()
        self._build_editor()

    def _apply_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", font=("Segoe UI", 10), foreground=TEXT)
        style.configure("App.TFrame", background=BG)
        style.configure("Card.TFrame", background=SURFACE, relief="solid", borderwidth=1)
        style.configure("Toolbar.TFrame", background=SURFACE)
        style.configure("AppTitle.TLabel", background=BG, foreground=TEXT, font=("Segoe UI Semibold", 16))
        style.configure("Title.TLabel", background=SURFACE, foreground=TEXT, font=("Segoe UI Semibold", 12))
        style.configure("Muted.TLabel", background=SURFACE, foreground=MUTED)
        style.configure("FieldName.TLabel", background=SURFACE, foreground=MUTED, font=("Segoe UI Semibold", 9))
        style.configure("FieldValue.TLabel", background=SURFACE, foreground=TEXT)
        style.configure("Status.TLabel", background="#eef4ff", foreground="#1849a9", padding=(10, 4), font=("Segoe UI Semibold", 9))
        style.configure("TButton", padding=(12, 7))
        style.configure("Accent.TButton", foreground="#ffffff", background=ACCENT)
        style.map("Accent.TButton", background=[("active", "#1d4ed8"), ("disabled", "#98a2b3")])
        style.configure("Edit.TButton", foreground="#ffffff", background="#475467")
        style.map("Edit.TButton", background=[("active", "#344054"), ("disabled", "#98a2b3")])
        style.configure("Danger.TButton", foreground="#ffffff", background=DANGER)
        style.map("Danger.TButton", background=[("active", "#912018"), ("disabled", "#98a2b3")])
        style.configure("TEntry", padding=4)
        style.configure("TCombobox", padding=4)
        style.configure("Modern.TNotebook", background=BG, borderwidth=0)
        style.configure("Modern.TNotebook.Tab", padding=(14, 8), font=("Segoe UI Semibold", 10))
        style.map(
            "Modern.TNotebook.Tab",
            background=[("selected", SURFACE), ("!selected", "#e9edf3")],
            foreground=[("selected", TEXT), ("!selected", MUTED)],
            padding=[("selected", "14 8 14 8"), ("!selected", "14 8 14 8")],
            expand=[("selected", "0 0 0 0"), ("!selected", "0 0 0 0")],
        )
        style.configure("Treeview", rowheight=28, fieldbackground=SURFACE, background=SURFACE, foreground=TEXT)
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", 10), padding=(6, 6))

    def _build_jobs(self) -> None:
        pane = ttk.PanedWindow(self.jobs_tab, orient="horizontal")
        pane.pack(fill="both", expand=True)
        self.jobs_pane = pane

        left = self._card(pane, padding=12)
        pane.add(left, weight=1)
        right = self._card(pane, padding=12)
        pane.add(right, weight=2)
        self.after_idle(self.set_jobs_pane_ratio)

        list_header = ttk.Frame(left, style="Toolbar.TFrame")
        list_header.pack(fill="x", pady=(0, 10))
        ttk.Label(list_header, text="작업 목록", style="Title.TLabel").pack(side="left")
        self.new_job_button = ttk.Button(list_header, text="새 작업", style="Accent.TButton", command=self.new_job)
        self.new_job_button.pack(side="right")

        columns = ("name", "scope", "schedule", "target")
        table_frame = ttk.Frame(left, style="Toolbar.TFrame")
        table_frame.pack(fill="both", expand=True)
        self.job_table = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        self.job_table.heading("name", text="이름")
        self.job_table.heading("scope", text="범위")
        self.job_table.heading("schedule", text="예약")
        self.job_table.heading("target", text="대상 폴더")
        self.job_table.column("name", width=150, minwidth=110)
        self.job_table.column("scope", width=90, minwidth=70)
        self.job_table.column("schedule", width=110, minwidth=85)
        self.job_table.column("target", width=180, minwidth=120)
        yscroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.job_table.yview)
        xscroll = ttk.Scrollbar(table_frame, orient="horizontal", command=self.job_table.xview)
        self.job_table.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.job_table.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        self.job_table.bind("<<TreeviewSelect>>", lambda _event: self.update_job_details())
        self.job_table.bind("<Double-1>", lambda _event: self.edit_selected())

        detail_header = ttk.Frame(right, style="Toolbar.TFrame")
        detail_header.pack(fill="x", pady=(0, 10))
        ttk.Label(detail_header, text="선택한 작업", style="Title.TLabel").pack(side="left")
        self.sync_button = ttk.Button(detail_header, text="지금 동기화", style="Accent.TButton", command=self.run_selected)
        self.sync_button.pack(side="right")

        action_row = ttk.Frame(right, style="Toolbar.TFrame")
        action_row.pack(fill="x", pady=(0, 8))
        self.edit_button = ttk.Button(action_row, text="편집", style="Edit.TButton", command=self.edit_selected)
        self.edit_button.pack(side="left")
        self.open_target_button = ttk.Button(action_row, text="대상 폴더 열기", command=self.open_selected_target)
        self.open_target_button.pack(side="left", padx=(6, 0))
        self.delete_button = ttk.Button(action_row, text="삭제", style="Danger.TButton", command=self.delete_selected)
        self.delete_button.pack(side="left", padx=(6, 0))

        summary_frame = ttk.Frame(right, style="Toolbar.TFrame")
        summary_frame.pack(fill="x", pady=(8, 16))
        summary_frame.columnconfigure(1, weight=1)
        self.job_summary_name = tk.StringVar(value="-")
        self.job_summary_scope = tk.StringVar(value="-")
        self.job_summary_schedule = tk.StringVar(value="-")
        self.job_summary_next_run = tk.StringVar(value="-")
        self.job_summary_last_event = tk.StringVar(value="-")
        self.job_summary_target = tk.StringVar(value="-")
        self.job_summary_url = tk.StringVar(value="-")
        self._job_summary_row(summary_frame, 0, "작업명", self.job_summary_name)
        self._job_summary_row(summary_frame, 1, "범위", self.job_summary_scope)
        self._job_summary_row(summary_frame, 2, "예약", self.job_summary_schedule)
        self._job_summary_row(summary_frame, 3, "다음 실행", self.job_summary_next_run)
        self._job_summary_row(summary_frame, 4, "최근 이벤트", self.job_summary_last_event)
        self._job_summary_row(summary_frame, 5, "저장 폴더", self.job_summary_target)
        self._job_summary_row(summary_frame, 6, "URL", self.job_summary_url)
        ttk.Separator(right, orient="horizontal").pack(fill="x", pady=(0, 14))
        ttk.Label(right, text="최근 동기화", style="Title.TLabel").pack(anchor="w", pady=(0, 6))
        history_frame = ttk.Frame(right, style="Toolbar.TFrame")
        history_frame.pack(fill="x", pady=(0, 16))
        history_columns = ("time", "status", "exported", "deleted", "skipped", "errors")
        self.run_history_table = ttk.Treeview(history_frame, columns=history_columns, show="headings", height=7, selectmode="none")
        self.run_history_table.heading("time", text="한국시간")
        self.run_history_table.heading("status", text="결과")
        self.run_history_table.heading("exported", text="생성/업데이트")
        self.run_history_table.heading("deleted", text="삭제")
        self.run_history_table.heading("skipped", text="건너뜀")
        self.run_history_table.heading("errors", text="오류")
        self.run_history_table.column("time", width=160, minwidth=145, anchor="w")
        self.run_history_table.column("status", width=70, minwidth=60, anchor="center")
        self.run_history_table.column("exported", width=105, minwidth=90, anchor="e")
        self.run_history_table.column("deleted", width=70, minwidth=60, anchor="e")
        self.run_history_table.column("skipped", width=70, minwidth=60, anchor="e")
        self.run_history_table.column("errors", width=70, minwidth=60, anchor="e")
        history_scroll = ttk.Scrollbar(history_frame, orient="vertical", command=self.run_history_table.yview)
        self.run_history_table.configure(yscrollcommand=history_scroll.set)
        self.run_history_table.grid(row=0, column=0, sticky="ew")
        history_scroll.grid(row=0, column=1, sticky="ns")
        history_frame.columnconfigure(0, weight=1)
        self.set_run_history_rows([])

    def _job_summary_row(self, parent: ttk.Frame, row: int, label: str, variable: tk.StringVar) -> None:
        ttk.Label(parent, text=label, style="FieldName.TLabel", width=10).grid(row=row, column=0, sticky="nw", padx=(0, 12), pady=3)
        ttk.Label(parent, textvariable=variable, style="FieldValue.TLabel", wraplength=620, justify="left").grid(
            row=row, column=1, sticky="ew", pady=3
        )

    def set_jobs_pane_ratio(self) -> None:
        if not hasattr(self, "jobs_pane"):
            return
        width = self.jobs_pane.winfo_width()
        if width <= 1:
            self.after(50, self.set_jobs_pane_ratio)
            return
        try:
            self.jobs_pane.sashpos(0, max(320, width // 3))
        except tk.TclError:
            pass

    def _build_editor(self) -> None:
        self.job_name = tk.StringVar()
        self.job_url = tk.StringVar()
        self.job_target = tk.StringVar(value=str(default_workspace() / "jobs" / "product-docs"))
        self.include_children = tk.BooleanVar(value=True)
        self.option_cme_scope = tk.StringVar(value=str(DEFAULT_EXPORT_OPTIONS["cme_scope"]))
        self.option_cme_cloud_id = tk.StringVar(value=str(DEFAULT_EXPORT_OPTIONS["cme_cloud_id"]))
        self.option_page_href = tk.StringVar(value=str(DEFAULT_EXPORT_OPTIONS["page_href"]))
        self.option_attachment_href = tk.StringVar(value=str(DEFAULT_EXPORT_OPTIONS["attachment_href"]))
        self.option_attachment_export_all = tk.BooleanVar(value=bool(DEFAULT_EXPORT_OPTIONS["attachment_export_all"]))
        self.option_page_breadcrumbs = tk.BooleanVar(value=bool(DEFAULT_EXPORT_OPTIONS["page_breadcrumbs"]))
        self.option_page_properties_as_front_matter = tk.BooleanVar(value=bool(DEFAULT_EXPORT_OPTIONS["page_properties_as_front_matter"]))
        self.option_include_document_title = tk.BooleanVar(value=bool(DEFAULT_EXPORT_OPTIONS["include_document_title"]))
        self.option_enable_jira_enrichment = tk.BooleanVar(value=bool(DEFAULT_EXPORT_OPTIONS["enable_jira_enrichment"]))
        self.option_skip_unchanged = tk.BooleanVar(value=bool(DEFAULT_EXPORT_OPTIONS["skip_unchanged"]))
        self.option_cleanup_stale = tk.BooleanVar(value=bool(DEFAULT_EXPORT_OPTIONS["cleanup_stale"]))
        self.option_verify_ssl = tk.BooleanVar(value=bool(DEFAULT_EXPORT_OPTIONS["verify_ssl"]))
        self.option_timeout = tk.StringVar(value=str(DEFAULT_EXPORT_OPTIONS["timeout"]))
        self.option_max_workers = tk.StringVar(value=str(DEFAULT_EXPORT_OPTIONS["max_workers"]))
        self.schedule_enabled = tk.BooleanVar(value=bool(DEFAULT_SCHEDULE["enabled"]))
        self.schedule_kind = tk.StringVar(value=SCHEDULE_KIND_LABELS[str(DEFAULT_SCHEDULE["kind"])])
        self.schedule_hour = tk.StringVar(value="09")
        self.schedule_minute = tk.StringVar(value="00")
        self.schedule_day_vars = {day: tk.BooleanVar(value=day <= 5) for day, _label in DAY_LABELS}
        self.schedule_day_of_month = tk.StringVar(value="1")
        self.schedule_paused = tk.BooleanVar(value=bool(DEFAULT_SCHEDULE["paused"]))
        self.cme_config_json = tk.StringVar(value=default_cme_config_json(self.job_target.get()))
        self.editor_status = tk.StringVar(value="새 작업")

        outer = self._card(self.editor_tab, padding=14)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer, style="Toolbar.TFrame")
        header.pack(fill="x", pady=(0, 12))
        ttk.Label(header, textvariable=self.editor_status, style="Title.TLabel").pack(side="left")
        self.save_job_button = ttk.Button(header, text="작업 저장", style="Accent.TButton", command=self.save_job)
        self.save_job_button.pack(side="right")
        self.new_editor_job_button = ttk.Button(header, text="새 작업", command=self.new_job)
        self.new_editor_job_button.pack(side="right", padx=(0, 6))

        self.editor_pages = ttk.Notebook(outer, style="Modern.TNotebook")
        self.editor_pages.pack(fill="both", expand=True)
        basics = ttk.Frame(self.editor_pages, style="App.TFrame", padding=12)
        options = ttk.Frame(self.editor_pages, style="App.TFrame", padding=12)
        schedule = ttk.Frame(self.editor_pages, style="App.TFrame", padding=12)
        self.editor_pages.add(basics, text="기본 정보")
        self.editor_pages.add(options, text="CME 옵션")
        self.editor_pages.add(schedule, text="예약")

        self._section_title(basics, "가져올 문서와 저장 위치")
        self._helper(basics, "Confluence 페이지, 페이지 트리, 스페이스, 조직 URL을 작업으로 저장합니다.")
        self._form_row(basics, "작업 이름", self.job_name)
        self._form_row(basics, "Confluence URL", self.job_url)
        self._helper(basics, "여러 URL은 쉼표로 구분합니다. 하위 페이지까지 가져오려면 아래 옵션을 켜세요.")
        target_row = ttk.Frame(basics, style="App.TFrame")
        target_row.pack(fill="x", pady=5)
        ttk.Label(target_row, text="저장 폴더", width=24, background=BG).pack(side="left")
        ttk.Entry(target_row, textvariable=self.job_target).pack(side="left", fill="x", expand=True)
        ttk.Button(target_row, text="찾아보기", command=self.choose_target).pack(side="left", padx=(6, 0))
        self._helper(basics, "내려받은 Markdown 파일과 첨부파일이 저장될 로컬 폴더입니다.")
        ttk.Checkbutton(basics, text="하위 페이지 포함", variable=self.include_children).pack(anchor="w", pady=(10, 0))

        self._section_title(schedule, "예약 실행")
        self._helper(schedule, "앱이 tray/background 상태로 실행 중일 때 예약된 시간에 같은 동기화 엔진을 실행합니다.")
        ttk.Checkbutton(schedule, text="예약 사용", variable=self.schedule_enabled).pack(anchor="w", pady=4)
        schedule_kind_row = ttk.Frame(schedule, style="App.TFrame")
        schedule_kind_row.pack(fill="x", pady=5)
        ttk.Label(schedule_kind_row, text="예약 주기", width=24, background=BG).pack(side="left")
        self.schedule_kind_combo = ttk.Combobox(schedule_kind_row, textvariable=self.schedule_kind, values=tuple(SCHEDULE_KIND_VALUES), state="readonly", width=30)
        self.schedule_kind_combo.pack(side="left")
        self.schedule_kind.trace_add("write", lambda *_args: self.update_schedule_condition_visibility())

        self.weekly_frame = ttk.Frame(schedule, style="App.TFrame")
        ttk.Label(self.weekly_frame, text="요일", width=24, background=BG).pack(side="left")
        for day, label in DAY_LABELS:
            ttk.Checkbutton(self.weekly_frame, text=label, variable=self.schedule_day_vars[day]).pack(side="left", padx=(0, 8))

        self.monthly_frame = ttk.Frame(schedule, style="App.TFrame")
        ttk.Label(self.monthly_frame, text="매월 실행 일자", width=24, background=BG).pack(side="left")
        ttk.Combobox(
            self.monthly_frame,
            textvariable=self.schedule_day_of_month,
            values=tuple(str(day) for day in range(1, 32)),
            state="readonly",
            width=8,
        ).pack(side="left")
        ttk.Label(self.monthly_frame, text="없는 날짜는 그 달에 실행하지 않습니다.", background=BG, foreground=MUTED).pack(side="left", padx=(8, 0))

        self._section_title(schedule, "실행 시각")
        time_row = ttk.Frame(schedule, style="App.TFrame")
        time_row.pack(fill="x", pady=5)
        ttk.Label(time_row, text="시각 선택", width=24, background=BG).pack(side="left")
        ttk.Combobox(time_row, textvariable=self.schedule_hour, values=HOUR_VALUES, state="readonly", width=5).pack(side="left")
        ttk.Label(time_row, text=":", background=BG).pack(side="left")
        ttk.Combobox(time_row, textvariable=self.schedule_minute, values=MINUTE_VALUES, state="readonly", width=5).pack(side="left")
        ttk.Button(time_row, text="추가", command=self.add_schedule_time_from_picker).pack(side="left", padx=(8, 0))
        times_row = ttk.Frame(schedule, style="App.TFrame")
        times_row.pack(fill="x", pady=5)
        ttk.Label(times_row, text="등록된 시각", width=24, background=BG).pack(side="left", anchor="n")
        self.schedule_times_list = tk.Listbox(times_row, height=5, exportselection=False)
        self.schedule_times_list.pack(side="left", fill="x", expand=True)
        ttk.Button(times_row, text="삭제", command=self.remove_selected_schedule_time).pack(side="left", padx=(8, 0), anchor="n")
        ttk.Label(schedule, text="시간대: Asia/Seoul", background=BG, foreground=MUTED).pack(anchor="w", pady=(4, 8))
        ttk.Checkbutton(schedule, text="이 작업 예약 일시정지", variable=self.schedule_paused).pack(anchor="w", pady=4)
        ttk.Label(
            schedule,
            text="Windows 로그인 자동 시작이 꺼져 있으면 앱을 완전히 종료한 동안의 예약 실행은 보장되지 않습니다.",
            background=BG,
            foreground=MUTED,
            wraplength=840,
        ).pack(anchor="w", pady=(10, 0))
        self.update_schedule_condition_visibility()

        self._section_title(options, "가져오기 범위")
        self._helper(options, "대부분은 auto 그대로 두면 URL과 하위 페이지 포함 여부로 자동 결정됩니다.")
        self._combobox_row(options, "CME 범위", self.option_cme_scope, CME_SCOPES)
        self._section_title(options, "링크와 첨부파일")
        self._combobox_row(options, "페이지 링크", self.option_page_href, HREF_OPTIONS)
        self._combobox_row(options, "첨부파일 링크", self.option_attachment_href, HREF_OPTIONS)
        for label, var in (
            ("첨부파일 전체 저장", self.option_attachment_export_all),
            ("페이지 경로 표시", self.option_page_breadcrumbs),
            ("페이지 속성을 Front Matter로 저장", self.option_page_properties_as_front_matter),
            ("문서 제목 포함", self.option_include_document_title),
            ("Jira 정보 보강", self.option_enable_jira_enrichment),
            ("변경 없는 파일 건너뛰기", self.option_skip_unchanged),
            ("사라진 파일 정리", self.option_cleanup_stale),
            ("SSL 검증", self.option_verify_ssl),
        ):
            ttk.Checkbutton(options, text=label, variable=var).pack(anchor="w", pady=2)
        self._section_title(options, "연결 옵션")
        self._entry_row(options, "타임아웃(초)", self.option_timeout)
        self._entry_row(options, "동시 작업 수", self.option_max_workers)

    def _build_settings(self) -> None:
        scrollable = self._scrollable_frame(self.settings_tab)
        card = self._card(scrollable, padding=14)
        card.pack(fill="both", expand=True)
        ttk.Label(card, text="연결 정보", style="Title.TLabel").pack(anchor="w", pady=(0, 8))
        self._helper(card, "Confluence 접속 정보를 입력하고 연결 테스트를 통과해야 저장할 수 있습니다.")
        settings = load_settings()
        self.base_url = tk.StringVar(value=settings.get("base_url", ""))
        self.email = tk.StringVar(value=settings.get("email", ""))
        self.token = tk.StringVar()
        self._entry_row(card, "Confluence 기본 URL", self.base_url)
        self._entry_row(card, "이메일", self.email)
        self._entry_row(card, "API 토큰", self.token, show="*")
        ttk.Label(card, text="API 토큰은 Windows Credential Manager에만 저장됩니다.", style="Muted.TLabel").pack(anchor="w", pady=(6, 14))

        ttk.Label(card, text="1. 연결 테스트", style="Title.TLabel").pack(anchor="w", pady=(4, 6))
        self._helper(card, "현재 입력한 정보로 Confluence에 연결되는지 확인합니다.")
        test_row = ttk.Frame(card, style="Toolbar.TFrame")
        test_row.pack(fill="x")
        self.test_connection_button = ttk.Button(test_row, text="연결 테스트", style="Accent.TButton", command=self.test_connection)
        self.test_connection_button.pack(side="left")

        ttk.Label(card, text="2. 저장 및 작업 생성", style="Title.TLabel").pack(anchor="w", pady=(18, 6))
        self._helper(card, "연결 테스트가 성공한 뒤에만 저장할 수 있습니다.")
        proceed_row = ttk.Frame(card, style="Toolbar.TFrame")
        proceed_row.pack(fill="x")
        self.save_create_button = ttk.Button(
            proceed_row,
            text="저장 후 작업 만들기",
            style="Accent.TButton",
            command=lambda: self.save_settings(open_editor=True),
            state="disabled",
        )
        self.save_create_button.pack(side="left")

        ttk.Separator(card, orient="horizontal").pack(fill="x", pady=(18, 12))
        ttk.Label(card, text="계정 관리", style="Title.TLabel").pack(anchor="w", pady=(0, 6))
        account_row = ttk.Frame(card, style="Toolbar.TFrame")
        account_row.pack(fill="x")
        self.logout_button = ttk.Button(account_row, text="저장된 토큰 삭제", command=self.logout)
        self.logout_button.pack(side="left")
        ttk.Separator(card, orient="horizontal").pack(fill="x", pady=(18, 12))
        ttk.Label(card, text="Background 실행", style="Title.TLabel").pack(anchor="w", pady=(0, 6))
        ttk.Checkbutton(card, text="스케줄 전역 일시정지", variable=self.global_schedule_paused, command=self.toggle_global_pause).pack(anchor="w", pady=4)
        ttk.Checkbutton(card, text="Windows 로그인 시 자동 시작(opt-in)", variable=self.auto_start, command=self.save_auto_start_setting).pack(anchor="w", pady=4)
        self._helper(card, "자동 시작이 꺼져 있으면 앱을 완전히 종료한 동안 예약 실행은 보장되지 않습니다.")
        for variable in (self.base_url, self.email, self.token):
            variable.trace_add("write", self.connection_inputs_changed)
        self.update_connection_actions()

    def _card(self, parent: tk.Misc, padding: int = 10) -> ttk.Frame:
        frame = ttk.Frame(parent, style="Card.TFrame", padding=padding)
        return frame

    def _scrollable_frame(self, parent: tk.Misc) -> ttk.Frame:
        container = ttk.Frame(parent, style="App.TFrame")
        container.pack(fill="both", expand=True)
        canvas = tk.Canvas(container, background=BG, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas, style="App.TFrame")
        window_id = canvas.create_window((0, 0), window=content, anchor="nw")

        def update_scroll_region(_event: tk.Event | None = None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def update_content_width(event: tk.Event) -> None:
            canvas.itemconfigure(window_id, width=event.width)

        def on_mousewheel(event: tk.Event) -> None:
            delta = getattr(event, "delta", 0)
            if delta:
                canvas.yview_scroll(int(-delta / 120), "units")

        def bind_wheel(_event: tk.Event) -> None:
            canvas.bind_all("<MouseWheel>", on_mousewheel)

        def unbind_wheel(_event: tk.Event) -> None:
            canvas.unbind_all("<MouseWheel>")

        content.bind("<Configure>", update_scroll_region)
        canvas.bind("<Configure>", update_content_width)
        canvas.bind("<Enter>", bind_wheel)
        canvas.bind("<Leave>", unbind_wheel)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        container.columnconfigure(0, weight=1)
        container.rowconfigure(0, weight=1)
        return content

    def _text_box(self, parent: tk.Misc, height: int) -> tk.Text:
        text = tk.Text(
            parent,
            height=height,
            wrap="word",
            relief="solid",
            borderwidth=1,
            background=SURFACE,
            foreground=TEXT,
            insertbackground=TEXT,
            font=MONO,
            padx=8,
            pady=8,
        )
        return text

    def _section_title(self, parent: tk.Misc, text: str) -> None:
        ttk.Label(parent, text=text, background=BG, foreground=TEXT, font=("Segoe UI Semibold", 11)).pack(anchor="w", pady=(8, 6))

    def _helper(self, parent: tk.Misc, text: str) -> None:
        ttk.Label(parent, text=text, background=BG, foreground=MUTED, wraplength=840).pack(anchor="w", pady=(0, 8))

    def _form_row(self, parent: tk.Misc, label: str, variable: tk.StringVar) -> None:
        self._entry_row(parent, label, variable)

    def _combobox_row(self, parent: tk.Misc, label: str, variable: tk.StringVar, values: tuple[str, ...]) -> None:
        row = ttk.Frame(parent, style="App.TFrame")
        row.pack(fill="x", pady=5)
        ttk.Label(row, text=label, width=24, background=BG).pack(side="left")
        ttk.Combobox(row, textvariable=variable, values=values, state="readonly", width=30).pack(side="left")

    def _entry_row(self, parent: tk.Misc, label: str, variable: tk.StringVar, show: str | None = None) -> None:
        row = ttk.Frame(parent, style="App.TFrame")
        row.pack(fill="x", pady=5)
        ttk.Label(row, text=label, width=24, background=BG).pack(side="left")
        ttk.Entry(row, textvariable=variable, show=show).pack(side="left", fill="x", expand=True)

    def choose_target(self) -> None:
        if not self.ensure_not_busy():
            return
        selected = filedialog.askdirectory()
        if selected:
            self.job_target.set(selected)

    def new_job(self) -> None:
        if not self.ensure_not_busy():
            return
        self.editing_job_id = None
        self.editor_status.set("새 작업")
        self.job_name.set("")
        self.job_url.set("")
        self.job_target.set(str(default_workspace() / "jobs" / "product-docs"))
        self.include_children.set(True)
        defaults = dict(DEFAULT_EXPORT_OPTIONS)
        defaults["cme_config_json"] = default_cme_config_json(self.job_target.get())
        self.set_export_options(defaults)
        self.set_schedule_options(dict(DEFAULT_SCHEDULE))
        self.editor_pages.select(0)
        self.tabs.select(self.editor_tab)
        self.status_text.set("새 작업 작성 중")

    def edit_selected(self) -> None:
        if not self.ensure_not_busy():
            return
        try:
            job = self.selected_job()
            self.editing_job_id = job.id
            self.editor_status.set(f"Editing {job.id}")
            self.job_name.set(job.name)
            self.job_url.set(job.export_options.get("cme_urls") or job.confluence_url)
            self.job_target.set(job.target_dir)
            self.include_children.set(job.include_children)
            self.set_export_options(job.export_options)
            self.set_schedule_options(job.schedule)
            self.editor_pages.select(0)
            self.tabs.select(self.editor_tab)
            self.status_text.set(f"작업 편집 중: {job.name}")
        except Exception as exc:
            self.show_error(exc)

    def set_export_options(self, options: dict[str, object]) -> None:
        merged = dict(DEFAULT_EXPORT_OPTIONS)
        merged.update(options or {})
        self.option_cme_scope.set(self._choice(str(merged["cme_scope"]), CME_SCOPES, "auto"))
        self.option_cme_cloud_id.set(str(merged["cme_cloud_id"]))
        self.option_page_href.set(self._choice(str(merged["page_href"]), HREF_OPTIONS, "relative"))
        self.option_attachment_href.set(self._choice(str(merged["attachment_href"]), HREF_OPTIONS, "relative"))
        self.option_attachment_export_all.set(bool(merged["attachment_export_all"]))
        self.option_page_breadcrumbs.set(bool(merged["page_breadcrumbs"]))
        self.option_page_properties_as_front_matter.set(bool(merged["page_properties_as_front_matter"]))
        self.option_include_document_title.set(bool(merged["include_document_title"]))
        self.option_enable_jira_enrichment.set(bool(merged["enable_jira_enrichment"]))
        self.option_skip_unchanged.set(bool(merged["skip_unchanged"]))
        self.option_cleanup_stale.set(bool(merged["cleanup_stale"]))
        self.option_verify_ssl.set(bool(merged["verify_ssl"]))
        self.option_timeout.set(str(merged["timeout"]))
        self.option_max_workers.set(str(merged["max_workers"]))
        self.set_cme_config_json(str(merged.get("cme_config_json") or default_cme_config_json(self.job_target.get())))

    def set_schedule_options(self, schedule: dict[str, object]) -> None:
        merged = normalize_schedule(schedule)
        self.schedule_enabled.set(bool(merged["enabled"]))
        self.schedule_kind.set(SCHEDULE_KIND_LABELS.get(str(merged["kind"]), "매일"))
        self.set_schedule_times(merged["times"])
        first_time = self.schedule_times_from_list()[0] if self.schedule_times_from_list() else "09:00"
        if ":" in first_time:
            hour, minute = first_time.split(":", 1)
            self.schedule_hour.set(self._choice(hour, HOUR_VALUES, "09"))
            self.schedule_minute.set(self._choice(minute, MINUTE_VALUES, "00"))
        selected_days: set[int] = set()
        for item in merged["days_of_week"]:
            try:
                selected_days.add(int(item))
            except (TypeError, ValueError):
                continue
        for day in self.schedule_day_vars:
            self.schedule_day_vars[day].set(day in selected_days)
        self.schedule_day_of_month.set(str(merged["day_of_month"] or 1))
        self.schedule_paused.set(bool(merged["paused"]))
        self.update_schedule_condition_visibility()

    def schedule_from_editor(self) -> dict[str, object]:
        schedule = normalize_schedule(None)
        schedule.update(
            {
                "enabled": self.schedule_enabled.get(),
                "kind": SCHEDULE_KIND_VALUES.get(self.schedule_kind.get(), "daily"),
                "times": self.schedule_times_from_list(),
                "days_of_week": [day for day, selected in self.schedule_day_vars.items() if selected.get()],
                "day_of_month": int(self.schedule_day_of_month.get() or 1),
                "timezone": "Asia/Seoul",
                "misfire_policy": "skip",
                "concurrency_policy": "skip_if_running",
                "paused": self.schedule_paused.get(),
            }
        )
        return schedule

    def _choice(self, value: str, choices: tuple[str, ...], fallback: str) -> str:
        return value if value in choices else fallback

    def schedule_times_from_list(self) -> list[str]:
        values = [str(self.schedule_times_list.get(index)) for index in range(self.schedule_times_list.size())]
        return sorted(dict.fromkeys(values))

    def set_schedule_times(self, values: object) -> None:
        self.schedule_times_list.delete(0, tk.END)
        source = values if isinstance(values, list) else ["09:00"]
        for value in sorted(dict.fromkeys(str(item) for item in source if str(item).strip())):
            self.schedule_times_list.insert(tk.END, value)

    def add_schedule_time(self, value: str) -> None:
        value = value.strip()
        if not value:
            return
        existing = set(self.schedule_times_from_list())
        if value not in existing:
            existing.add(value)
        self.set_schedule_times(sorted(existing))

    def add_schedule_time_from_picker(self) -> None:
        self.add_schedule_time(f"{self.schedule_hour.get()}:{self.schedule_minute.get()}")

    def remove_selected_schedule_time(self) -> None:
        selection = list(self.schedule_times_list.curselection())
        for index in reversed(selection):
            self.schedule_times_list.delete(index)

    def update_schedule_condition_visibility(self) -> None:
        kind = SCHEDULE_KIND_VALUES.get(self.schedule_kind.get(), "daily")
        self.weekly_frame.pack_forget()
        self.monthly_frame.pack_forget()
        if kind == "weekly":
            self.weekly_frame.pack(fill="x", pady=5)
        elif kind == "monthly":
            self.monthly_frame.pack(fill="x", pady=5)

    def export_options_from_editor(self) -> dict[str, object]:
        return {
            "cme_scope": self.option_cme_scope.get(),
            "cme_urls": self.job_url.get(),
            "cme_cloud_id": self.option_cme_cloud_id.get(),
            "cme_config_json": self.get_cme_config_json(),
            "page_href": self.option_page_href.get(),
            "attachment_href": self.option_attachment_href.get(),
            "attachment_export_all": self.option_attachment_export_all.get(),
            "page_breadcrumbs": self.option_page_breadcrumbs.get(),
            "page_properties_as_front_matter": self.option_page_properties_as_front_matter.get(),
            "include_document_title": self.option_include_document_title.get(),
            "enable_jira_enrichment": self.option_enable_jira_enrichment.get(),
            "skip_unchanged": self.option_skip_unchanged.get(),
            "cleanup_stale": self.option_cleanup_stale.get(),
            "verify_ssl": self.option_verify_ssl.get(),
            "timeout": self._int_option(self.option_timeout.get(), DEFAULT_EXPORT_OPTIONS["timeout"]),
            "max_workers": self._int_option(self.option_max_workers.get(), DEFAULT_EXPORT_OPTIONS["max_workers"]),
        }

    def _int_option(self, value: str, default: object) -> int:
        try:
            parsed = int(value)
        except ValueError:
            parsed = int(default)
        return max(1, parsed)

    def set_cme_config_json(self, value: str) -> None:
        self.cme_config_json.set(value)

    def get_cme_config_json(self) -> str:
        return self.cme_config_json.get().strip()

    def save_job(self) -> None:
        if not self.ensure_not_busy():
            return
        existing = self.store.load()
        job_id = self.editing_job_id or stable_job_id(self.job_name.get(), {job.id for job in existing})
        job = Job(
            id=job_id,
            name=self.job_name.get(),
            confluence_url=self.job_url.get(),
            target_dir=self.job_target.get(),
            include_children=self.include_children.get(),
            include_attachments=False,
            export_options=self.export_options_from_editor(),
            schedule=self.schedule_from_editor(),
        )
        try:
            validate_schedule(job.schedule)
            validate_job(job, create_dirs=True)
            self.store.upsert(job)
            self.editing_job_id = job.id
            self.editor_status.set(f"편집 중: {job.id}")
            self.refresh_jobs(select_job_id=job.id)
            self.status_text.set(f"작업 저장됨: {job.name}")
            self.tabs.select(self.jobs_tab)
            messagebox.showinfo("저장됨", "작업이 저장되었습니다.")
        except Exception as exc:
            self.show_error(exc)

    def refresh_jobs(self, select_job_id: str | None = None) -> None:
        for row in self.job_table.get_children():
            self.job_table.delete(row)
        jobs = self.store.load()
        for job in jobs:
            scope = str(job.export_options.get("cme_scope") or "auto")
            schedule = self.format_schedule_status(job)
            row_id = job.id
            self.job_table.insert("", "end", iid=row_id, values=(job.name, scope, schedule, job.target_dir))
        if jobs:
            target = select_job_id if select_job_id in {job.id for job in jobs} else jobs[0].id
            self.job_table.selection_set(target)
            self.job_table.focus(target)
            self.job_table.see(target)
        self.update_job_details()

    def selected_job(self) -> Job:
        selection = self.job_table.selection()
        if not selection:
            raise AppError("Config", "NO_JOB_SELECTED", "작업을 선택하세요.", "", False)
        return self.store.get(str(selection[0]))

    def update_job_details(self) -> None:
        try:
            job = self.selected_job()
        except Exception:
            self.set_job_summary(None)
            self.set_run_history_rows([])
            return
        scope = str(job.export_options.get("cme_scope") or "auto")
        urls = str(job.export_options.get("cme_urls") or job.confluence_url)
        self.set_job_summary(job, scope, urls)
        self.set_run_history_rows(format_job_run_history_rows(job))

    def set_job_summary(self, job: Job | None, scope: str = "-", urls: str = "-") -> None:
        if job is None:
            self.job_summary_name.set("작업을 선택하세요.")
            self.job_summary_scope.set("-")
            self.job_summary_schedule.set("-")
            self.job_summary_next_run.set("-")
            self.job_summary_last_event.set("-")
            self.job_summary_target.set("-")
            self.job_summary_url.set("-")
            return
        self.job_summary_name.set(job.name or "-")
        self.job_summary_scope.set(scope or "-")
        self.job_summary_schedule.set(self.format_schedule_status(job))
        next_run = next_run_at(job)
        self.job_summary_next_run.set(_format_timestamp(next_run.isoformat()) if next_run else "-")
        self.job_summary_last_event.set(self.format_last_scheduler_event(job.id))
        self.job_summary_target.set(job.target_dir or "-")
        self.job_summary_url.set(urls or "-")

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
            day_text = "/".join(labels)
            return f"{label} {day_text} {time_text}"
        if schedule.get("kind") == "monthly":
            return f"{label} {schedule.get('day_of_month')}일 {time_text}"
        return f"{label} {time_text}"

    def format_last_scheduler_event(self, job_id: str) -> str:
        for event in reversed(load_scheduler_events(limit=100)):
            if event.get("job_id") == job_id:
                return f"{event.get('event_type')} · {event.get('result')}"
        return "-"

    def set_run_history_rows(self, rows: list[tuple[str, str, str, str, str, str]]) -> None:
        if not hasattr(self, "run_history_table"):
            return
        for row_id in self.run_history_table.get_children():
            self.run_history_table.delete(row_id)
        if not rows:
            self.run_history_table.insert("", "end", values=("기록 없음", "-", "-", "-", "-", "-"))
            return
        for row in rows:
            self.run_history_table.insert("", "end", values=row)

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
            messagebox.showinfo("실행 중", "이미 실행 중인 작업이 있습니다.")
            return
        self.busy = True
        self.status_text.set(f"{label} 실행 중")
        self.configure(cursor="watch")
        self.set_running_controls(label, True)
        start_text = f"{label} 실행 중...\n큰 Confluence 문서 트리는 시간이 걸릴 수 있습니다.\n"
        if on_start is None:
            self.write_text(start_text)
        else:
            on_start(start_text)

        def worker() -> None:
            try:
                result = work()
            except Exception as exc:
                self.after(0, lambda exc=exc: self.finish_background_error(label, exc, on_error))
            else:
                self.after(0, lambda result=result: self.finish_background_success(label, on_success, result))

        threading.Thread(target=worker, daemon=True).start()

    def finish_background_success(self, label: str, on_success: Callable[[object], None], result: object) -> None:
        self.busy = False
        self.configure(cursor="")
        self.set_running_controls(label, False)
        self.status_text.set(f"{label} 완료")
        on_success(result)

    def finish_background_error(self, label: str, exc: Exception, on_error: Callable[[Exception], None] | None = None) -> None:
        self.busy = False
        self.configure(cursor="")
        self.set_running_controls(label, False)
        self.status_text.set("오류")
        if on_error is None:
            self.show_error(exc)
        else:
            on_error(exc)

    def set_running_controls(self, label: str, running: bool) -> None:
        state = "disabled" if running else "normal"
        for attr in (
            "new_job_button",
            "sync_button",
            "edit_button",
            "open_target_button",
            "delete_button",
            "save_job_button",
            "new_editor_job_button",
            "test_connection_button",
            "logout_button",
        ):
            if hasattr(self, attr):
                getattr(self, attr).configure(state=state)
        if hasattr(self, "sync_button"):
            text = "동기화 중..." if running and label == "지금 동기화" else "지금 동기화"
            self.sync_button.configure(text=text)
        if hasattr(self, "test_connection_button"):
            text = "테스트 중..." if running and label == "연결 테스트" else "연결 테스트"
            self.test_connection_button.configure(text=text)
        if running and hasattr(self, "save_create_button"):
            self.save_create_button.configure(state="disabled")
        elif hasattr(self, "save_create_button"):
            self.update_connection_actions()

    def delete_selected(self) -> None:
        if not self.ensure_not_busy():
            return
        try:
            job = self.selected_job()
            if not messagebox.askyesno("작업 삭제", f"'{job.name}' 작업을 삭제할까요?"):
                return
            self.store.delete(job.id)
            self.refresh_jobs()
            self.status_text.set(f"작업 삭제됨: {job.name}")
        except Exception as exc:
            self.show_error(exc)

    def save_settings(self, open_editor: bool = False) -> None:
        if not self.ensure_not_busy():
            return
        token = self.token.get()
        if not token:
            token = _credential_store().read(self.base_url.get(), self.email.get()) or ""
        errors = validate_auth_input(self.base_url.get(), self.email.get(), token)
        if errors:
            messagebox.showerror("연결 정보", "\n".join(errors.values()))
            return
        if self.connection_verified_fingerprint != self._connection_fingerprint(self.base_url.get(), self.email.get(), token):
            messagebox.showerror("연결 테스트 필요", "현재 입력한 연결 정보로 연결 테스트를 먼저 통과해야 저장할 수 있습니다.")
            return
        try:
            if self.token.get():
                _credential_store().write(self.base_url.get(), self.email.get(), self.token.get())
            save_settings(self.base_url.get(), self.email.get())
            self.token.set("")
            self.status_text.set("연결 정보 저장됨")
            if open_editor:
                self.new_job()
            else:
                messagebox.showinfo("저장됨", "연결 정보가 저장되었습니다.")
        except Exception as exc:
            self.show_error(exc)

    def test_connection(self) -> None:
        if not self.ensure_not_busy():
            return
        try:
            base_url = self.base_url.get()
            email = self.email.get()
            token = self.token.get() or _credential_store().read(base_url, email)
            if not token:
                raise AppError("Auth", "TOKEN_NOT_FOUND", "API 토큰을 입력하거나 먼저 저장하세요.", "", False)
            errors = validate_auth_input(base_url, email, token)
            if errors:
                messagebox.showerror("연결 정보", "\n".join(errors.values()))
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
        _credential_store().delete(self.base_url.get(), self.email.get())
        self.connection_verified_fingerprint = None
        self.update_connection_actions()
        self.status_text.set("저장된 API 토큰 삭제됨")

    def save_auto_start_setting(self) -> None:
        enabled = bool(self.auto_start.get())
        try:
            set_windows_auto_start(enabled)
            save_app_setting("auto_start", enabled)
            if enabled:
                self.status_text.set("Windows 로그인 자동 시작 설정이 저장되었습니다.")
            else:
                self.status_text.set("자동 시작 꺼짐: 완전 종료 중 예약 실행은 보장되지 않습니다.")
        except Exception as exc:
            self.auto_start.set(not enabled)
            self.show_error(exc)

    def toggle_global_pause(self) -> None:
        save_app_setting("schedule_paused", bool(self.global_schedule_paused.get()))
        self.status_text.set("스케줄 일시정지" if self.global_schedule_paused.get() else "스케줄 재개")

    def start_background_runtime(self) -> None:
        self.tray_runtime = TrayRuntime(
            icon_path=_asset_path("app-256.png"),
            show_window=lambda: self.after(0, self.show_from_tray),
            quit_app=lambda: self.after(0, self.quit_from_tray),
            toggle_pause=lambda: self.after(0, self.toggle_pause_from_tray),
        )
        self.tray_available = self.tray_runtime.start()
        if not self.tray_available:
            detail = f" ({self.tray_runtime.last_error})" if self.tray_runtime.last_error else ""
            self.status_text.set(f"Tray 초기화 실패: 창을 닫으면 앱이 종료됩니다.{detail}")
            return
        self.scheduler_runtime = SchedulerRuntime(
            self.store.load,
            self.run_scheduled_job,
            coordinator=self.coordinator,
            schedule_paused=lambda: bool(self.global_schedule_paused.get()),
            notify_failure=lambda job, exc: self.after(0, lambda job=job, exc=exc: self.notify_scheduled_failure(job, exc)),
        )
        self.scheduler_runtime.start()

    def run_scheduled_job(self, job: Job) -> dict[str, object]:
        return self._engine().apply(job, trigger="scheduled")

    def notify_scheduled_failure(self, job: Job, exc: Exception) -> None:
        error = classify_exception(exc)
        self.status_text.set(f"예약 실행 실패: {job.name}")
        self.update_job_details()
        if self.tray_runtime is not None:
            try:
                self.tray_runtime.notify("Confluence Sync 예약 실패", f"{job.name}: {error.user_message}")
            except Exception:
                pass

    def show_from_tray(self) -> None:
        self.deiconify()
        self.lift()
        self.focus_force()
        self.update_job_details()

    def quit_from_tray(self) -> None:
        if self.busy or self.coordinator.is_running():
            messagebox.showinfo("실행 중", "현재 실행 중인 작업이 끝난 뒤 다시 종료하세요.")
            return
        if self.scheduler_runtime is not None:
            self.scheduler_runtime.stop()
        if self.tray_runtime is not None:
            self.tray_runtime.stop()
        self.destroy()

    def toggle_pause_from_tray(self) -> None:
        self.global_schedule_paused.set(not self.global_schedule_paused.get())
        self.toggle_global_pause()

    def ensure_not_busy(self) -> bool:
        if self.busy or self.coordinator.is_running():
            messagebox.showinfo("실행 중", "현재 작업이 끝날 때까지 기다려 주세요.")
            return False
        return True

    def on_close(self) -> None:
        if self.busy or self.coordinator.is_running():
            messagebox.showinfo("실행 중", "현재 작업이 끝난 뒤 창을 닫아 주세요.")
            return
        if not self.tray_available:
            self.destroy()
            return
        self.withdraw()
        if not self.close_notice_shown:
            self.close_notice_shown = True
            messagebox.showinfo("Background 실행", "창을 닫아도 예약 동기화가 tray/background에서 계속 실행됩니다.")

    def write_result(self, data: object) -> None:
        self.write_text(mask_sensitive(json.dumps(data, ensure_ascii=False, indent=2)))

    def write_sync_text(self, text: str) -> None:
        self.status_text.set(mask_sensitive(text).strip().splitlines()[0])

    def write_sync_result(self, data: object) -> None:
        summary = data.get("summary") if isinstance(data, dict) and isinstance(data.get("summary"), dict) else {}
        created = int(summary.get("created", 0)) if isinstance(summary, dict) else 0
        updated = int(summary.get("updated", 0)) if isinstance(summary, dict) else 0
        exported = created + updated
        deleted = int(summary.get("deleted", 0)) if isinstance(summary, dict) else 0
        skipped = int(summary.get("skipped", 0)) if isinstance(summary, dict) else 0
        errors = int(summary.get("errors", 0)) if isinstance(summary, dict) else 0
        if errors:
            self.status_text.set("동기화 완료")
            self.update_job_details()
            messagebox.showwarning("동기화 완료", "동기화가 끝났지만 오류가 기록되었습니다.")
            return
        self.status_text.set("동기화 성공")
        self.update_job_details()
        messagebox.showinfo("동기화 성공", "Confluence 문서 동기화가 완료되었습니다.")

    def show_sync_error(self, exc: Exception) -> None:
        error = classify_exception(exc)
        self.status_text.set("동기화 실패")
        try:
            self.set_run_history_rows(format_job_run_history_rows(self.selected_job()))
        except Exception:
            pass
        messagebox.showerror(error.category, error.user_message)

    def write_connection_text(self, text: str) -> None:
        self.status_text.set(mask_sensitive(text).strip().splitlines()[0])

    def write_connection_result(self, data: object, fingerprint: str) -> None:
        ok = isinstance(data, dict) and data.get("ok") is True
        if ok:
            self.connection_verified_fingerprint = fingerprint
            messagebox.showinfo("연결 테스트 성공", "Confluence 연결 테스트를 통과했습니다. 이제 저장 후 작업 만들기를 진행할 수 있습니다.")
        else:
            self.connection_verified_fingerprint = None
        self.update_connection_actions()
        self.status_text.set("연결 테스트 성공" if ok else "연결 테스트 실패")

    def show_connection_error(self, exc: Exception) -> None:
        self.connection_verified_fingerprint = None
        self.update_connection_actions()
        error = classify_exception(exc)
        self.status_text.set("연결 테스트 실패")
        messagebox.showerror(error.category, error.user_message)

    def _connection_fingerprint(self, base_url: str, email: str, token: str) -> str:
        normalized = "\n".join([base_url.strip().rstrip("/"), email.strip().lower(), token])
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def connection_inputs_changed(self, *_args: object) -> None:
        if self.connection_verified_fingerprint is not None:
            self.connection_verified_fingerprint = None
        self.update_connection_actions()

    def update_connection_actions(self) -> None:
        if hasattr(self, "save_create_button"):
            state = "normal" if self.connection_verified_fingerprint is not None else "disabled"
            self.save_create_button.configure(state=state)

    def write_text(self, text: str) -> None:
        masked = mask_sensitive(text).strip()
        self.status_text.set(masked.splitlines()[0] if masked else "준비됨")

    def append_text(self, text: str) -> None:
        masked = mask_sensitive(text).strip()
        if masked:
            self.status_text.set(masked.splitlines()[0])

    def threadsafe_progress(self, message: str, done: int, total: int) -> None:
        suffix = f" ({done}/{total})" if total else ""
        self.after(0, lambda: self.append_text(f"{message}{suffix}\n"))

    def show_error(self, exc: Exception) -> None:
        error = classify_exception(exc)
        self.status_text.set("오류")
        messagebox.showerror(error.category, error.user_message)


def main() -> int:
    app = ConfluenceSyncApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
