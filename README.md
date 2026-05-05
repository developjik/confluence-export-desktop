# Confluence Sync Tool

Current baseline: 2026-05-05  
Product baseline: Windows GUI Job Runner with background scheduling for `confluence-markdown-exporter==4.1.1`

Confluence Sync Tool lets a Windows user save and run repeatable Confluence export jobs without installing Python on the final user PC. The app stores job settings, keeps the API token in Windows Credential Manager, builds a CME config at run time, and records run history/logs. CME owns the actual Confluence crawl, Markdown conversion, attachments, skip/cleanup, and lockfile behavior.

## Documentation

- Product requirements: [docs/PRD_v1.0.md](docs/PRD_v1.0.md)
- Background scheduling spec: [docs/features/cron_background_runtime.md](docs/features/cron_background_runtime.md)
- CME option mapping: [docs/CME_FEATURE_SUPPORT.md](docs/CME_FEATURE_SUPPORT.md)
- Local verification summary: [docs/verification/coverage_report.md](docs/verification/coverage_report.md)
- External/manual verification: [docs/verification/manual_verification_checklist.md](docs/verification/manual_verification_checklist.md)

New development and verification should use `docs/PRD_v1.0.md` for the MVP baseline and `docs/features/cron_background_runtime.md` for the GUI/background scheduling baseline.

## Repository Layout

- Runtime source lives under `src/confluence_sync_tool`.
- `tests` contains the local unit and GUI/CLI source-contract tests.
- `scripts` contains build, release verification, and external evidence helpers.
- `packaging` contains PyInstaller specs. The GUI spec is the default release path; the CLI spec is retained for developer and live-smoke support.
- `build`, `__pycache__`, and test/tool caches are generated artifacts and are ignored. They can be deleted at any time.
- `dist` is also generated, but it may contain the current packaged app used by smoke verification and handoff testing.

## What The App Owns

- PySide6 Windows GUI with `연결`, `작업`, `작업 설정` sidebar sections
- GUI actions for login/logout, job management, manual run, and scheduled run
- Job storage under `%APPDATA%\ConfluenceSync\app`
- Windows Credential Manager token storage
- CME config generation and advanced JSON merge
- Preview/Dry Run remain engine/developer verification paths and are not exposed as final-user GUI actions
- Sync Now execution through the CME adapter
- Preset schedule configuration and tray/background scheduler runtime
- Run history and logs in the target workspace
- PyInstaller onedir packaging for the GUI app. Developer CLI source and optional CLI packaging remain for automation/live-smoke support, but the default user build is GUI-only.

## What CME Owns

- Confluence page/page-tree/space/org traversal
- Markdown conversion fidelity
- Attachment export and link rewriting
- Skip unchanged behavior
- Stale file cleanup
- `confluence-lock.json` management
- Jira enrichment when configured

## Development Commands

```powershell
$py = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
$env:PYTHONPATH = (Resolve-Path .\src).Path

& $py -m compileall -q src tests scripts
& $py -m unittest

$env:PYTHON_EXE = $py
.\scripts\build.ps1
& $py scripts\smoke_built_apps.py
& $py scripts\verify_release.py
```

Build the optional developer CLI only when a live CLI smoke or CLI package handoff is needed:

```powershell
.\scripts\build.ps1 -IncludeCli
```

## GUI Flow

1. Run `dist\confluence-sync\confluence-sync.exe`.
2. On `연결`, enter Confluence base URL, email, and API token.
3. Run `연결 테스트`. The token is not saved until the connection flow succeeds.
4. Select `저장 후 작업 만들기`.
5. On `작업 설정`, enter the Confluence URL, target folder, schedule preset/times, CME scope/options, and optional `CME Config JSON`.
6. Save the job, return to `작업`, and use `지금 동기화`.
7. Turn on `예약 사용` for jobs that should run while the GUI is alive in tray/background mode.

Supported CME scopes are `auto`, `pages`, `pages-with-descendants`, `spaces`, and `orgs`.

## Storage Locations

- Settings: `%APPDATA%\ConfluenceSync\app\settings.json`
- Jobs: `%APPDATA%\ConfluenceSync\app\jobs.json`
- Scheduler events: `%APPDATA%\ConfluenceSync\app\scheduler_events.jsonl`
- App log: `%APPDATA%\ConfluenceSync\logs\app.log`
- Job run history: `<target-dir>\run_history.json`
- Job log: `<target-dir>\.logs\app.log`
- CME lockfile: `<target-dir>\confluence-lock.json`

API tokens must not appear in these files. They are stored through Windows Credential Manager and injected into a temporary CME config only while a run is executing.

## External Gates

Package verification:

```powershell
.\scripts\verify_external_gates.ps1 -Mode Package
```

Live Confluence verification currently uses developer automation and may require a developer CLI/script entrypoint:

```powershell
$env:CONFLUENCE_SYNC_BASE_URL = "https://company.atlassian.net"
$env:CONFLUENCE_SYNC_EMAIL = "user@example.com"
$env:CONFLUENCE_SYNC_API_TOKEN = "<token>"
$env:CONFLUENCE_SYNC_PAGE_URL = "https://company.atlassian.net/wiki/spaces/SPACE/pages/123456"
.\scripts\verify_external_gates.ps1 -Mode LiveConfluence
```

Current local verification passes. Clean Windows without Python and non-developer GUI UAT remain external evidence items.
