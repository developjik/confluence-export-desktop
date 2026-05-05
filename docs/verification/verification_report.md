# Verification Report

Updated at: 2026-05-05T01:37:24+09:00  
Baseline: `docs/PRD_v1.0.md`  
Mode: `cme-only`

## Summary

- Local verification status: pass
- Current product boundary: Windows GUI/CLI runner for `confluence-markdown-exporter==4.1.1`
- Superseded boundary removed from verification: internal exporter, internal manifest, conflict/deleted preservation, page-level preview diff
- External evidence still required: live Confluence export, clean Windows without Python, non-developer GUI UAT

## Local Command Evidence

Latest generated coverage: [coverage_report.md](coverage_report.md)

| Check | Result |
| --- | --- |
| `python -m compileall -q src tests scripts` | pass |
| `python -m unittest` | pass, 41 tests |
| `python -m confluence_sync_tool.cli check` | pass |
| `python scripts\credential_manager_smoke.py` | pass |
| built CLI `check` | pass |
| built GUI exists | pass |
| `python scripts\smoke_built_apps.py` | pass |

## Verified Product Contracts

- `SyncEngine` uses the CME exporter adapter for apply.
- Preview and Dry Run validate Job/CME config/target path and do not compute an internal page diff.
- Dry Run preserves workspace content.
- GUI and CLI expose CME job options and no internal backend selector.
- CLI commands are `check`, `login`, `logout`, `list-jobs`, `add-job`, `preview`, `dry-run`, `run`, and `validate`.
- Token storage uses Windows Credential Manager and smoke tests confirm token-stdin output does not leak the sentinel token.
- Built CLI imports the CME package from the PyInstaller bundle.
- Built GUI launches from `dist\confluence-sync\confluence-sync.exe`.

## Release Gate Status

| Gate | Status | Evidence |
| --- | --- | --- |
| Compile and tests | pass | `coverage_report.md` |
| CME-only engine and config | pass | `tests/test_cme_backend.py`, `tests/test_engine.py` |
| GUI/CLI surface | pass | `tests/test_exporter_gui_cli.py` |
| Credential handling | pass | `tests/test_security_validation.py`, `scripts/credential_manager_smoke.py` |
| Built package smoke | pass locally | `scripts/smoke_built_apps.py` |
| Live Confluence export | external remaining | requires real base URL, email, token, and target page/space/org |
| Clean Windows without Python | external remaining | requires clean VM/package evidence |
| Non-developer GUI UAT | external remaining | requires completed UAT observation |

## Notes

`docs/verification/requirement_audit.*` and `docs/verification/contract_audit.*` now track the CME-only PRD v1.0 shape. Older evidence that referenced manifests, conflicts, deleted folders, or internal exporters is superseded.
