from __future__ import annotations

import argparse
import unittest

from confluence_sync_tool.cli import EXIT_BY_CATEGORY, build_parser
from confluence_sync_tool.gui import format_plan_display, format_run_history_rows, format_run_summary


class GuiCliTests(unittest.TestCase):
    def test_cli_contains_required_commands_and_excludes_schedule(self):
        parser = build_parser()
        actions = [action for action in parser._actions if isinstance(action, argparse._SubParsersAction)]
        commands = set(actions[0].choices)
        for command in {"check", "login", "logout", "list-jobs", "add-job", "preview", "dry-run", "run", "validate"}:
            self.assertIn(command, commands)
        self.assertNotIn("schedule", commands)
        self.assertNotIn("run-all", commands)

    def test_cli_add_job_exposes_cme_options_only(self):
        args = build_parser().parse_args(
            [
                "add-job",
                "--name",
                "Docs",
                "--url",
                "https://company.atlassian.net/wiki/spaces/PROD",
                "--target-dir",
                "C:/tmp/docs",
                "--page-href",
                "wiki",
                "--attachment-href",
                "absolute",
                "--attachment-export-all",
                "--no-cleanup-stale",
                "--cme-scope",
                "spaces",
                "--cme-cloud-id",
                "cloud-123",
                "--timeout",
                "11",
                "--max-workers",
                "3",
            ]
        )
        self.assertEqual(args.page_href, "wiki")
        self.assertEqual(args.attachment_href, "absolute")
        self.assertTrue(args.attachment_export_all)
        self.assertFalse(args.cleanup_stale)
        self.assertEqual(args.cme_scope, "spaces")
        self.assertEqual(args.cme_cloud_id, "cloud-123")
        self.assertEqual(args.timeout, 11)
        self.assertEqual(args.max_workers, 3)
        self.assertFalse(hasattr(args, "backend"))
        self.assertFalse(hasattr(args, "attachment_policy"))
        defaults = build_parser().parse_args(
            [
                "add-job",
                "--name",
                "Docs",
                "--url",
                "https://company.atlassian.net/wiki/spaces/PROD",
                "--target-dir",
                "C:/tmp/docs",
            ]
        )
        self.assertTrue(defaults.attachment_export_all)
        self.assertFalse(defaults.enable_jira_enrichment)

    def test_cli_exit_code_contract(self):
        self.assertEqual(EXIT_BY_CATEGORY["Config"], 1)
        self.assertEqual(EXIT_BY_CATEGORY["Validation"], 1)
        self.assertEqual(EXIT_BY_CATEGORY["Auth"], 2)
        self.assertEqual(EXIT_BY_CATEGORY["Network"], 3)
        self.assertEqual(EXIT_BY_CATEGORY["Confluence API"], 3)
        self.assertEqual(EXIT_BY_CATEGORY["File System"], 4)
        self.assertEqual(EXIT_BY_CATEGORY["Conflict"], 5)

    def test_gui_source_exposes_cme_job_runner_labels_and_removes_internal_backend_choice(self):
        import inspect

        import confluence_sync_tool.gui as gui_module

        source = inspect.getsource(gui_module)
        for label in [
            "Confluence 문서 동기화",
            "1260x860",
            "_scrollable_frame",
            "MouseWheel",
            "연결",
            "작업",
            "작업 설정",
            "AppTitle.TLabel",
            "Status.TLabel",
            "Treeview",
            "padding=[(\"selected\", \"14 8 14 8\")",
            "선택한 작업",
            "FieldName.TLabel",
            "FieldValue.TLabel",
            "_job_summary_row",
            "set_job_summary",
            "작업명",
            "저장 폴더",
            "최근 동기화",
            "한국시간",
            "run_history_table",
            "동기화 성공",
            "생성/업데이트",
            "지금 동기화",
            "동기화 중...",
            "set_running_controls",
            "Edit.TButton",
            "set_jobs_pane_ratio",
            "편집",
            "대상 폴더 열기",
            "삭제",
            "예약",
            "매일",
            "주중",
            "매주",
            "매월",
            "하루 여러 번",
            "등록된 시각",
            "없는 날짜는 그 달에 실행하지 않습니다.",
            "다음 실행",
            "최근 이벤트",
            "schedule_from_editor",
            "start_background_runtime",
            "SchedulerRuntime",
            "RunCoordinator",
            "TrayRuntime",
            "app-256.png",
            "저장 후 작업 만들기",
            "연결 테스트",
            "테스트 중...",
            "연결 테스트 성공",
            "이제 저장 후 작업 만들기를 진행할 수 있습니다.",
            "1. 연결 테스트",
            "2. 저장 및 작업 생성",
            "계정 관리",
            "저장된 토큰 삭제",
            "state=\"disabled\"",
            "API 토큰은 Windows Credential Manager에만 저장됩니다.",
            "Confluence 접속 정보를 입력하고 연결 테스트를 통과해야 저장할 수 있습니다.",
            "현재 입력한 연결 정보로 연결 테스트를 먼저 통과해야 저장할 수 있습니다.",
            "connection_verified_fingerprint",
            "update_connection_actions",
            "Confluence URL",
            "기본 정보",
            "CME 옵션",
            "CME 범위",
            "페이지 링크",
            "첨부파일 링크",
            "첨부파일 전체 저장",
            "페이지 경로 표시",
            "페이지 속성을 Front Matter로 저장",
            "문서 제목 포함",
            "Jira 정보 보강",
            "변경 없는 파일 건너뛰기",
            "사라진 파일 정리",
            "SSL 검증",
            "타임아웃(초)",
            "동시 작업 수",
            "export_options_from_editor",
            "editing_job_id",
            "format_plan_display",
            "threading.Thread",
            "run_background",
            "큰 Confluence 문서 트리는 시간이 걸릴 수 있습니다.",
            "format_job_run_history_rows",
            "format_run_history_rows",
            "format_run_summary",
        ]:
            self.assertIn(label, source)
        for removed_label in [
            "Setup Checker",
            "Run Setup Checker",
            "Refresh Logs",
            "checker_tab",
            "logs_tab",
            "format_job_log_details",
            "run_setup_checker",
            "refresh_logs",
            "CME Cloud ID",
            "작업 상세",
            "최근 결과",
            "job_detail_text",
            "result_text",
            "selected_job_summary",
            "last_sync_summary",
            "동기화 상태",
            "sync_status",
            "새로고침",
            "연결 테스트 상태",
            "connection_result_summary",
            "connection_status",
            "연결 정보가 변경되었습니다. 연결 테스트를 다시 실행하세요.",
            "text=\"검증\"",
            "text=\"미리보기\"",
            "text=\"드라이런\"",
            "validate_selected",
            "preview_selected",
            "dry_run_selected",
            "로그 열기",
            "open_log_button",
            "open_selected_log",
            "실행 결과",
            "output_text",
            "직접 입력",
            "schedule_direct_time",
            "add_schedule_time_from_direct",
            "고급 JSON",
            "CME Config JSON",
            "cme_config_text",
        ]:
            self.assertNotIn(removed_label, source)
        self.assertNotIn("Exporter Backend", source)
        self.assertNotIn("attachment_policy", source)

    def test_gui_build_spec_includes_tray_icon_assets(self):
        from pathlib import Path

        spec = Path("packaging/confluence-sync-gui.spec").read_text(encoding="utf-8")
        self.assertIn("app-32.png", spec)
        self.assertIn("app-256.png", spec)

    def test_plan_display_focuses_on_cme_job_and_skip_errors(self):
        text = format_plan_display(
            {
                "plan_id": "p1",
                "job_id": "j1",
                "summary": {"create": 0, "update": 1, "skip": 0, "error": 0},
                "items": [
                    {"action": "update", "title": "CME export", "target_path": "C:/docs", "reason": "CME spaces job"},
                    {"action": "skip", "title": "Same", "target_path": "C:/docs", "reason": "no change"},
                ],
                "warnings": ["runtime decides exact page changes"],
            }
        )
        self.assertIn("[UPDATE]", text)
        self.assertIn("[SKIP]", text)
        self.assertIn("실행 예정 CME 작업", text)
        self.assertNotIn("[DELETE CANDIDATE]", text)
        self.assertNotIn("[CONFLICT]", text)

    def test_run_summary_formats_recent_sync_for_gui(self):
        text = format_run_summary(
            {
                "finished_at": "2026-05-04T16:23:45+00:00",
                "status": "success",
                "summary": {"created": 4, "updated": 0, "deleted": 1, "skipped": 2, "errors": 0},
            }
        )
        self.assertIn("2026-05-05 01:23:45 · 성공", text)
        self.assertIn("문서 생성/업데이트 4건 · 삭제 1건 · 건너뜀 2건 · 오류 0건", text)

    def test_run_history_rows_show_latest_first_in_korean_time(self):
        rows = format_run_history_rows(
            [
                {
                    "finished_at": "2026-05-04T15:00:00+00:00",
                    "status": "failed",
                    "summary": {"created": 1, "updated": 0, "deleted": 0, "skipped": 0, "errors": 1},
                },
                {
                    "finished_at": "2026-05-04T16:23:45+00:00",
                    "status": "success",
                    "summary": {"created": 4, "updated": 0, "deleted": 1, "skipped": 2, "errors": 0},
                },
            ]
        )
        self.assertEqual(rows[0], ("2026-05-05 01:23:45", "성공", "4", "1", "2", "0"))
        self.assertEqual(rows[1][0], "2026-05-05 00:00:00")

if __name__ == "__main__":
    unittest.main()
