# Requirement Audit

Generated at: 2026-05-05T01:37:24+09:00  
Baseline: `docs/PRD_v1.0.md`

## Summary

- Product mode: `cme-only`
- Current PRD: `docs/PRD_v1.0.md`
- Superseded PRD reference file: deleted
- Unmapped current requirement groups: none known
- External or partial: live Confluence export, clean Windows without Python, non-developer GUI UAT

## Requirement Mapping

| ID / Area | Status | Evidence | Missing |
| --- | --- | --- | --- |
| G-01 CME-only export runner | automated | `SyncEngine.apply`, `run_cme_export`, `test_cme_preview_and_apply_use_cme_exporter_only` |  |
| G-02 GUI exposes CME options | automated + manual external | `gui.py`, `test_gui_source_exposes_cme_job_runner_labels_and_removes_internal_backend_choice` | GUI UAT |
| G-03 CLI job execution | automated | `build_parser`, `test_cli_contains_required_commands_and_excludes_schedule` |  |
| G-04 Python-free Windows execution | local package smoke | `scripts\build.ps1`, `scripts\smoke_built_apps.py`, built GUI `dist` folder | clean Windows VM without Python |
| G-05 safe credential storage | automated | `WindowsCredentialStore`, `credential_manager_smoke.py`, `test_sec_01_token_is_not_written_to_json_files` |  |
| FR-AUTH-01 input auth values | automated + manual external | `validate_auth_input`, `gui.py`, `cmd_login` | GUI UAT |
| FR-AUTH-02 Credential Manager token storage | automated | `WindowsCredentialStore`, token-stdin smoke |  |
| FR-AUTH-03 CME connection test | code + external | `test_cme_connection`, GUI `연결 테스트`, CLI `login --test` | live Confluence credentials |
| FR-AUTH-04 logout deletes credential | automated | `cmd_logout`, memory credential logout test |  |
| FR-AUTH-05 token masking | automated | `mask_sensitive`, job log masking tests |  |
| FR-AUTH-06 save-after-test gating | source verified + manual external | GUI connection fingerprint/state checks in `gui.py` and source tests | GUI UAT |
| FR-JOB-01 job persistence | automated | `JobStore`, `test_e2e_job_01_jobs_persist_after_reload` |  |
| FR-JOB-02 CME-only jobs | automated | `DEFAULT_EXPORT_OPTIONS`, GUI/CLI tests assert no internal backend selector |  |
| FR-JOB-03 URL required | automated | `cme_urls`, `validate_job` |  |
| FR-JOB-04 target folder writable | automated | `validate_job`, filesystem validation tests |  |
| FR-JOB-05 backward-compatible option load | automated | `Job.from_dict`, export option round-trip tests |  |
| FR-SCOPE-01 pages | automated | `cme_scope`, `execute_cme`, CME backend tests | live export optional |
| FR-SCOPE-02 pages-with-descendants | automated | `cme_scope`, `execute_cme`, CME backend tests | live export optional |
| FR-SCOPE-03 spaces | automated | `cme_scope`, multiple URL validation tests | live export optional |
| FR-SCOPE-04 orgs | automated | `cme_scope`, org URL validation tests | live export optional |
| FR-SCOPE-05 auto | automated | `cme_scope` URL/include-children rules |  |
| FR-CME-01..11 CME options | automated | `DEFAULT_CME_CONFIG`, `apply_common_job_options`, config merge tests |  |
| FR-PREVIEW-01..03 preview wrapper | automated | `SyncEngine.preview`, `SyncPlan`, preview display tests |  |
| FR-DRY-01 dry-run no mutation | automated | `SyncEngine.dry_run`, workspace hash tests |  |
| FR-RUN-01 CME adapter run | automated | injected CME exporter tests |  |
| FR-RUN-02 credential injection | automated | `build_cme_config` credential injection test |  |
| FR-RUN-03 run history | automated | `append_run_history`, apply run history tests |  |
| FR-RUN-04 structured errors | automated | `AppError`, apply failure tests |  |
| FR-GUI-01..11 current GUI flow | source verified + manual external | GUI source assertions for sidebar sections, labels, actions, and removed legacy sections | GUI UAT |
| FR-CLI-01 check | automated | `cmd_check`, source parser tests; packaged CLI is optional with `scripts\build.ps1 -IncludeCli` |  |
| FR-CLI-02 login/logout | automated | `cmd_login`, `cmd_logout`, token-stdin smoke |  |
| FR-CLI-03 add-job | automated | `cmd_add_job`, CLI option tests |  |
| FR-CLI-04 preview/dry-run/run/validate | automated | parser tests, engine tests |  |
| FR-CLI-05 JSON output | automated | `emit_json`, CLI smoke output |  |
| FR-CLI-06 list-jobs | automated | `cmd_list_jobs`, parser tests |  |
| PKG-01..04 packaging | local package smoke | PyInstaller GUI spec, optional CLI spec, `scripts\build.ps1`, built GUI smoke | clean Windows VM without Python |
| SEC-01..04 security | automated | token leak tests, temp CME config lifecycle, masking tests |  |

## Gates

| Gate | Status | Evidence | Missing |
| --- | --- | --- | --- |
| GATE-01 compile succeeds | pass | `coverage_report.md` |  |
| GATE-02 unit tests pass | pass | `coverage_report.md` |  |
| GATE-03 built GUI app passes smoke | pass locally | `scripts\smoke_built_apps.py` | clean VM |
| GATE-04 release verifier passes | pass | `scripts\verify_release.py` |  |
| GATE-05 package includes CME | pass | PyInstaller hidden imports and optional built CLI `check` |  |
| GATE-06 GUI launches | pass locally | built GUI smoke | clean VM confirmation |
| GATE-07 token is not leaked | pass | security tests and credential smoke |  |
| GATE-08 live Confluence export works | external remaining | `verify_external_gates.ps1 -Mode LiveConfluence` | real credentials |
| GATE-09 clean Windows without Python works | external remaining | `verify_external_gates.ps1 -Mode Package` | clean VM |

## Superseded Requirement Families

These are not current requirements and should not be used as release evidence for PRD v1.0:

- `FR-EXP-*` internal Markdown exporter requirements
- `FR-CONFLICT-*` app-owned conflict preservation requirements
- `FR-DELETE-*` app-owned deleted folder requirements
- internal manifest gates such as `E2E-MANIFEST-01`
- old Setup Checker and Logs tab requirements
