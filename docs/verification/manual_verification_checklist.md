# Manual Verification Checklist

Generated from `docs/PRD_v1.0.md` for the current CME-only product.

Local automated verification is passing:

- `python -m unittest`
- `python scripts\verify_release.py`
- `python scripts\smoke_built_apps.py`

External verification can be captured with:

```powershell
.\scripts\verify_external_gates.ps1 -Mode Package
.\scripts\verify_external_gates.ps1 -Mode LiveConfluence
```

To prepare a handoff bundle for a clean VM, live verifier, or UAT participant:

```powershell
.\scripts\create_external_verification_bundle.ps1
```

To import returned evidence:

```powershell
.\scripts\import_external_evidence.ps1 -EvidencePath <path-to-evidence-folder-or-zip> -RunVerification
```

## PKG / Clean Windows Without Python

Purpose: prove the installer EXE and default onedir GUI build run on a user machine without Python, pip, repository checkout, or PATH configuration.

Required environment:

- Clean Windows 10 or Windows 11 VM
- No Python installation
- Built `dist\ConfluenceExportDesktopSetup-0.1.0.exe`, plus `dist\confluence-export-desktop` folder or the external verification bundle

Steps:

1. Copy `dist\ConfluenceExportDesktopSetup-0.1.0.exe` to the VM.
2. Run the installer.
3. Launch `Confluence Export Desktop` from the Start menu.
4. Confirm Windows Apps & Features shows an uninstall entry.
5. Optional: copy `dist\confluence-export-desktop` and launch `dist\confluence-export-desktop\confluence-export-desktop.exe` as the portable fallback.
6. Optional: copy the repo `scripts` folder and run `.\scripts\verify_external_gates.ps1 -Mode Package`.

Pass criteria:

- GUI opens without Python installed.
- Installer completes and creates a Start menu entry.
- Uninstall entry exists.
- `연결`, `작업`, `작업 설정` sidebar sections are visible.
- `Setup Checker` and `Logs` sections are not visible.
- Moving the onedir folders does not break startup.
- `external_gates.json` reports `python_install_detected: false`.

Evidence to save:

- Screenshot of GUI first screen
- Screenshot of installer completion or Apps & Features entry
- VM image/version note
- Any antivirus/EDR warning note
- Generated `external_gates.json`, if using the script

## Live Confluence Verification

Purpose: prove the optional packaged developer CLI can authenticate and run a CME export against Confluence Cloud.

Required input:

- Confluence Cloud base URL
- Email
- API token
- Test page, space, or org URL
- Disposable local target directory

Recommended automated runner:

```powershell
.\scripts\build.ps1 -IncludeCli
$env:CONFLUENCE_EXPORT_BASE_URL = "https://company.atlassian.net"
$env:CONFLUENCE_EXPORT_EMAIL = "user@example.com"
$env:CONFLUENCE_EXPORT_API_TOKEN = "<token>"
$env:CONFLUENCE_EXPORT_PAGE_URL = "https://company.atlassian.net/wiki/spaces/SPACE/pages/123456"
.\scripts\verify_external_gates.ps1 -Mode LiveConfluence
```

Manual equivalent:

1. Run `Get-Content token.txt | confluence-export-cli login --base-url <url> --email <email> --token-stdin --test`.
2. Create a Job with `confluence-export-cli add-job --job-id live-smoke --name "Live Smoke" --url <page-url> --target-dir <workspace> --include-children`.
3. Run `confluence-export-cli preview --job live-smoke`.
4. Run `confluence-export-cli dry-run --job live-smoke`.
5. Run `confluence-export-cli run --job live-smoke`.
6. Run `confluence-export-cli logout`.
7. Inspect the target directory, `run_history.json`, `.logs\app.log`, and `confluence-lock.json`.

Pass criteria:

- Login connection test succeeds.
- Preview reports the intended CME scope and URL list.
- Dry Run does not change workspace content.
- Run writes Markdown and/or attachment output as expected for the selected source.
- `run_history.json` records a successful `cme_apply` run.
- `confluence-lock.json` exists when CME creates a lockfile for the export.
- API token is not present in app config, workspace files, run history, logs, or evidence files.
- Logout succeeds.

Evidence to save:

- Redacted command output or generated `external_gates.json`
- Redacted `run_history.json` sample
- Workspace hash before/after dry-run
- Target directory file summary
- Token leak scan result

## UAT: Non-Developer GUI Flow

Purpose: prove a non-developer can complete the core GUI flow without Python, pip, PATH, or CLI knowledge.

Required participant:

- One product-team-style user who is not expected to know Python or CLI workflows

Steps:

1. Provide only the onedir GUI build and test Confluence credentials.
2. Ask the participant to open the app.
3. Ask the participant to enter `Confluence 기본 URL`, `이메일`, and `API 토큰`.
4. Confirm `저장 후 작업 만들기` is disabled before a successful `연결 테스트`.
5. Ask the participant to click `연결 테스트`.
6. Confirm a success/failure message appears.
7. Confirm `저장 후 작업 만들기` is enabled only after a successful test for the current input values.
8. Ask the participant to click `저장 후 작업 만들기`.
9. Ask the participant to create and save a Job.
10. Confirm the Job actions are `지금 내보내기`, `편집`, `대상 폴더 열기`, and `삭제`.
11. Ask the participant to run `지금 내보내기`.
12. Confirm the button changes to `내보내기 중...` and conflicting action buttons are disabled while the run is active.
13. Confirm `최근 내보내기` is a table and shows recent runs in latest-first order with 한국시간, success/failure, 생성/업데이트, 삭제, 건너뜀, 오류 counts.
14. Observe without coaching except for credential values.

Pass criteria:

- User completes the flow without Python or CLI help.
- User can identify the selected Job name, scope, target directory, URL, and recent sync table.
- Korean labels and short helper text are visible in the main GUI flow.
- At least one controlled failure message is understandable and actionable.

Evidence to save:

- Participant role
- Completion time
- Blockers or UX issues
- Screenshots or notes
- Completed `uat_observation_template.md`
