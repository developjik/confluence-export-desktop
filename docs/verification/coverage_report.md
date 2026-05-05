# Verification Coverage Report

Generated at: 2026-05-05T10:38:22+09:00

- Mode: gui-background-runtime
- OK: True

## Checks

- cme_only_engine: SyncEngine uses CME exporter adapter only
- cme_only_gui: GUI exposes CME Job options and no internal backend selector
- cme_config_template: CME 4.1.1 export and connection_config options are present
- dry_run_wrapper: Preview/Dry Run validate config and do not calculate internal page diffs
- packaging: PyInstaller bundles GUI and confluence-markdown-exporter modules

## Command Results

- compileall: 0
- unittest: 0
- credential_manager_smoke: 0
- built_gui_exists: 0
- built_apps_smoke: 0

## External Remaining

- Live Confluence export still requires real credentials and target page/space/org.
- Clean Windows machine without Python still requires external verification.
