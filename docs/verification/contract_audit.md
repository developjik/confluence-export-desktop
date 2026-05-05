# Contract Audit

Generated at: 2026-05-05T01:37:24+09:00  
Baseline: `docs/PRD_v1.0.md`

## Summary

- Contract items: 14
- Current product mode: `cme-only`
- External or partial: `GUI-UX-LABELS-01`, `PACKAGING-STRUCTURE-01`, `LIVE-CONFLUENCE-01`

| ID | Status | Evidence | Missing |
| --- | --- | --- | --- |
| DOC-PRD-01 | present | `docs/PRD_v1.0.md` |  |
| DOC-CME-01 | present | `docs/CME_FEATURE_SUPPORT.md` |  |
| CLI-COMMANDS-01 | automated | parser exposes `check`, `login`, `logout`, `list-jobs`, `add-job`, `preview`, `dry-run`, `run`, `validate` |  |
| CLI-JSON-01 | automated | `emit_json`, CLI smoke outputs parseable JSON |  |
| DATA-JOBS-01 | automated | `Job.to_dict/from_dict`, `JobStore`, export option round-trip tests |  |
| DATA-PLAN-01 | automated | `SyncPlan.to_dict`, preview wrapper tests |  |
| DATA-RUN-HISTORY-01 | automated | `append_run_history`, apply success/failure tests |  |
| CME-CONFIG-01 | automated | `DEFAULT_CME_CONFIG`, `apply_common_job_options`, `deep_merge`, config tests |  |
| CME-ADAPTER-01 | automated | `execute_cme`, injected exporter tests, no internal backend selector |  |
| DRY-RUN-WRITE-01 | automated | `SyncEngine.dry_run`, workspace hash test |  |
| GUI-UX-LABELS-01 | partial_external | GUI source label/action assertions | manual GUI/UAT observation |
| SECURITY-01 | automated | Credential Manager smoke, token masking tests, temp config lifecycle |  |
| PACKAGING-STRUCTURE-01 | partial_external | PyInstaller specs, build script, built app smoke | clean Windows VM without Python |
| LIVE-CONFLUENCE-01 | external_required | `scripts\verify_external_gates.ps1 -Mode LiveConfluence` | real credentials and target URL |

## Removed Contracts

The active contract set no longer includes app-owned manifest, conflict, deleted-folder, or internal Markdown conversion contracts. Those behaviors are outside the PRD v1.0 product boundary and belong to CME where applicable.
