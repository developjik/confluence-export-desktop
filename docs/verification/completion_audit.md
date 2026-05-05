# Completion Audit

Audited at: 2026-05-05T01:37:24+09:00

Objective: update program documentation to match the current `docs\PRD_v1.0.md` CME-only product definition.

## Current Product Definition

Confluence Export Desktop is a Windows GUI/CLI Job Runner for `confluence-markdown-exporter==4.1.1`.

The app owns:

- Job storage and editing
- Windows Credential Manager token storage
- CME config generation and merge
- Preview/Dry Run validation wrapper
- Export Now execution through the CME adapter
- Run history and logs
- PyInstaller onedir packaging

CME owns:

- Confluence crawling
- Markdown conversion
- Attachment export and link rewriting
- Skip unchanged and stale cleanup
- `confluence-lock.json`

## Documentation Updated

| File | Current role |
| --- | --- |
| `README.md` | Operational entry point for users/developers, including GUI flow, CLI quickstart, storage paths, and external gates. |
| `docs\PRD_v1.0.md` | Current PRD. CLI scope now explicitly includes `list-jobs`. |
| `docs\CME_FEATURE_SUPPORT.md` | Current CME scope/option mapping and GUI surface. |
| `docs\verification\verification_report.md` | Current verification summary. |
| `docs\verification\requirement_audit.md` | Requirement-to-evidence audit for PRD v1.0. |
| `docs\verification\contract_audit.md` | Current contract audit without internal exporter artifacts. |
| `docs\verification\manual_verification_checklist.md` | External verification checklist for package, live Confluence, and UAT. |
| `docs\verification\uat_observation_template.md` | UAT template aligned with the current GUI flow. |

## Local Verification Evidence

Latest local coverage report: `docs\verification\coverage_report.md`

- `compileall`: pass
- `unittest`: pass, 61 tests
- source CLI `check`: pass
- Credential Manager smoke: pass
- optional built CLI `check`: supported when built with `scripts\build.ps1 -IncludeCli`
- built GUI exists: pass
- built apps smoke: pass

## Stale Content Removed From Active Verification Docs

The active verification docs no longer claim support for these superseded internal-exporter behaviors:

- internal Confluence client
- internal Markdown exporter
- app-owned manifest schema
- app-owned conflict/deleted folders
- page-level Preview diff
- Setup Checker or Logs sections in the GUI

Those items remain mentioned only where they are explicitly documented as non-goals or superseded context.

## Remaining External Evidence

| Item | Status | How to collect |
| --- | --- | --- |
| Live Confluence export | not collected in this workspace | `.\scripts\verify_external_gates.ps1 -Mode LiveConfluence` with real credentials |
| Clean Windows without Python | not collected in this workspace | `.\scripts\verify_external_gates.ps1 -Mode Package` on a clean VM |
| Non-developer GUI UAT | not collected in this workspace | use `uat_observation_template.md` |

## Completion Verdict

Documentation is current for the locally implemented CME-only product surface. Local verification passes; the remaining items require external credentials, a clean Windows machine, or a human UAT participant.
