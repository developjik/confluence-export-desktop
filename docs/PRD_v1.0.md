# PRD v1.0: Confluence Export Desktop

작성일: 2026-05-05  
제품 정의: Python 없이 실행되는 `confluence-markdown-exporter` 기반 Windows GUI/CLI Job Runner  
기준 엔진: `confluence-markdown-exporter==4.1.1`

## 1. Summary

Confluence Export Desktop은 사용자가 Confluence page, page tree, space, organization export를 GUI 또는 CLI Job으로 실행할 수 있게 하는 Windows 앱이다.

앱은 자체 Markdown 변환기나 자체 Confluence crawler를 유지하지 않는다. 실제 export, Markdown 변환, attachment 처리, skip/cleanup, lockfile 관리는 CME가 담당한다. 앱은 CME 실행을 사용자 PC에서 쉽게 설정, 저장, 실행, 기록하는 wrapper 역할을 한다.

## 2. Product Principles

- CME가 제공하는 기능은 가능한 한 그대로 노출한다.
- internal exporter, internal manifest, internal conflict/delete 기록은 제품 범위에서 제외한다.
- Preview/Dry Run은 CME 동작을 복제하지 않고 실행 전 검증과 예정 scope 표시만 수행한다.
- 최종 사용자의 PC에는 Python 설치가 필요 없어야 한다.
- API token은 Windows Credential Manager에 저장하고 JSON/config/log에는 평문으로 남기지 않는다.

## 3. Goals

| ID | Goal | Success Criteria |
| --- | --- | --- |
| G-01 | CME-only export runner 제공 | 모든 Export Now 실행이 CME adapter 경로만 사용한다. |
| G-02 | GUI에서 모든 주요 CME 기능 설정 | 작업 설정 화면이 scope, URL, href, attachment, cleanup, skip, connection 옵션과 raw CME JSON을 제공한다. |
| G-03 | CLI에서도 동일한 Job 실행 가능 | login, logout, list-jobs, add-job, preview, dry-run, run, validate, check 명령이 동작한다. |
| G-04 | Python 없는 Windows 실행 | PyInstaller onedir GUI/CLI가 built smoke를 통과한다. |
| G-05 | 안전한 인증 저장 | token은 Credential Manager에 저장되고 출력/log에서 마스킹된다. |

## 4. Non-Goals

| ID | Non-Goal |
| --- | --- |
| NG-01 | 자체 Confluence REST crawler 구현 |
| NG-02 | 자체 Markdown 변환기 구현 |
| NG-03 | 자체 attachment policy 구현 |
| NG-04 | 자체 manifest 기반 create/update/skip 판단 |
| NG-05 | 자체 conflict 기록 또는 deleted 기록 |
| NG-06 | CME 동작을 Preview에서 page 단위 diff로 재현 |
| NG-07 | 스케줄러, daemon, background sync |
| NG-08 | 양방향 sync 또는 Confluence write-back |

## 5. Users

| User | Need |
| --- | --- |
| Product/PM | Confluence 문서를 로컬 Markdown snapshot으로 내려받아 AI/검색/백업에 사용한다. |
| Engineer | page tree, space, org 단위 export를 반복 실행하고 결과를 재사용한다. |
| Non-developer user | Python/CLI 지식 없이 GUI에서 Job을 만들고 실행한다. |

## 6. Core User Journeys

### 6.1 First Run

1. 사용자가 GUI를 실행한다.
2. 연결 화면에서 Confluence 기본 URL, 이메일, API 토큰을 입력한다.
3. 앱은 token을 Windows Credential Manager에 저장한다.
4. 사용자는 저장 후 바로 작업 설정 화면에서 Job을 등록할 수 있다.
5. 필요 시 연결 테스트를 눌러 CME auth/client 경로로 연결을 확인한다.

### 6.2 Create Job

1. 사용자가 작업 설정 화면에서 작업 이름, Confluence URL, 저장 폴더를 입력한다.
2. CME Scope를 선택한다.
3. 필요 시 Page Href, Attachment Href, Attachment Export All, Skip Unchanged, Cleanup Stale 등을 조정한다.
4. 고급 옵션은 CME Config JSON에 입력한다.
5. Save 시 Job validation이 실행된다.

### 6.3 Preview / Dry Run

1. 사용자가 Preview 또는 Dry Run을 실행한다.
2. 앱은 Job name, target path, CME URL, CME scope, CME JSON 문법을 검증한다.
3. 앱은 실행 예정 scope, URL 목록, warning을 표시한다.
4. 앱은 workspace export 결과를 변경하지 않는다.

### 6.4 Export Now

1. 사용자가 Export Now를 누른다.
2. 앱은 Credential Manager에서 token을 읽는다.
3. 앱은 CME config를 임시 파일로 생성하고 인증 정보를 주입한다.
4. 앱은 CME를 in-process adapter로 실행한다.
5. CME가 Confluence export, Markdown conversion, attachment export, skip/cleanup, lockfile 갱신을 수행한다.
6. 앱은 run history와 job log에 결과를 기록한다.

## 7. Scope

### 7.1 In Scope

| ID | Feature |
| --- | --- |
| S-01 | Windows GUI |
| S-02 | Windows CLI |
| S-03 | Windows Credential Manager 인증 저장 |
| S-04 | Job 저장/편집/삭제 |
| S-05 | CME page export |
| S-06 | CME page-with-descendants export |
| S-07 | CME space export |
| S-08 | CME organization export |
| S-09 | CME Config JSON override |
| S-10 | Preview/Dry Run validation wrapper |
| S-11 | Export Now execution |
| S-12 | run history storage |
| S-13 | PyInstaller onedir packaging |

### 7.2 Out of Scope

| ID | Feature |
| --- | --- |
| O-01 | internal backend 선택 |
| O-02 | internal manifest schema |
| O-03 | internal conflict folder |
| O-04 | internal deleted folder |
| O-05 | page-level Preview diff |
| O-06 | scheduler |
| O-07 | cloud-hosted service |
| O-08 | Confluence write-back |

## 8. Functional Requirements

### 8.1 Auth

| ID | Requirement | Acceptance Criteria |
| --- | --- | --- |
| FR-AUTH-01 | Base URL, Email, API Token을 입력할 수 있어야 한다. | GUI 연결 화면과 CLI login에서 입력 가능하다. |
| FR-AUTH-02 | API Token은 Credential Manager에 저장해야 한다. | settings/jobs/run history/logs에 token 평문이 없어야 한다. |
| FR-AUTH-03 | 연결 테스트는 CME auth/client 경로를 사용해야 한다. | internal ConfluenceClient가 없어야 한다. |
| FR-AUTH-06 | 연결 테스트는 저장 전 입력값으로 실행되어야 하며, 통과한 입력값만 저장할 수 있어야 한다. | Base URL, Email, API Token을 입력한 뒤 연결 테스트를 통과해야 저장 후 작업 만들기 버튼이 활성화되고 성공 알림이 표시된다. |
| FR-AUTH-04 | Logout은 저장된 credential을 삭제해야 한다. | logout 후 token lookup이 실패한다. |
| FR-AUTH-05 | 출력과 로그는 token을 마스킹해야 한다. | token 문자열이 stdout/stderr/log에 나타나지 않는다. |

### 8.2 Job

| ID | Requirement | Acceptance Criteria |
| --- | --- | --- |
| FR-JOB-01 | Job은 이름, URL(s), target directory, include children, CME options를 저장해야 한다. | 저장 후 재로드 시 동일 값이 유지된다. |
| FR-JOB-02 | 모든 Job은 CME Job이어야 한다. | Job model과 GUI/CLI에 internal backend 선택지가 없다. |
| FR-JOB-03 | URL은 하나 이상 입력해야 한다. | 빈 URL은 validation error가 된다. |
| FR-JOB-04 | 저장 폴더는 존재하거나 생성 가능해야 한다. | Save/Add Job에서 생성 및 write probe가 성공한다. |
| FR-JOB-05 | 기존 Job은 CME-only 옵션으로 로드되어야 한다. | 기본값 merge 후 CME 옵션이 존재한다. |

### 8.3 CME Scope

| ID | Requirement | Acceptance Criteria |
| --- | --- | --- |
| FR-SCOPE-01 | `pages` scope를 지원해야 한다. | page URL 목록을 CME pages 실행으로 전달한다. |
| FR-SCOPE-02 | `pages-with-descendants` scope를 지원해야 한다. | page URL 목록을 CME descendants 실행으로 전달한다. |
| FR-SCOPE-03 | `spaces` scope를 지원해야 한다. | space URL 목록을 CME space 실행으로 전달한다. |
| FR-SCOPE-04 | `orgs` scope를 지원해야 한다. | base URL 목록을 CME organization 실행으로 전달한다. |
| FR-SCOPE-05 | `auto` scope를 지원해야 한다. | URL과 include children 값으로 scope가 결정된다. |

### 8.4 CME Options

| ID | Requirement | Acceptance Criteria |
| --- | --- | --- |
| FR-CME-01 | GUI/CLI는 `page_href`를 설정할 수 있어야 한다. | `absolute`, `relative`, `wiki`를 지원한다. |
| FR-CME-02 | GUI/CLI는 `attachment_href`를 설정할 수 있어야 한다. | `absolute`, `relative`, `wiki`를 지원한다. |
| FR-CME-03 | GUI/CLI는 `attachment_export_all`을 설정할 수 있어야 한다. | boolean 값이 CME config에 반영된다. |
| FR-CME-04 | GUI/CLI는 `page_breadcrumbs`를 설정할 수 있어야 한다. | boolean 값이 CME config에 반영된다. |
| FR-CME-05 | GUI/CLI는 `page_properties_as_front_matter`를 설정할 수 있어야 한다. | boolean 값이 CME config에 반영된다. |
| FR-CME-06 | GUI/CLI는 `include_document_title`을 설정할 수 있어야 한다. | boolean 값이 CME config에 반영된다. |
| FR-CME-07 | GUI/CLI는 `enable_jira_enrichment`를 설정할 수 있어야 한다. | boolean 값이 CME config에 반영된다. |
| FR-CME-08 | GUI/CLI는 `skip_unchanged`를 설정할 수 있어야 한다. | boolean 값이 CME config에 반영된다. |
| FR-CME-09 | GUI/CLI는 `cleanup_stale`을 설정할 수 있어야 한다. | boolean 값이 CME config에 반영된다. |
| FR-CME-10 | GUI/CLI는 `timeout`, `max_workers`, `verify_ssl`을 설정할 수 있어야 한다. | 값이 `connection_config`에 반영된다. |
| FR-CME-11 | Raw CME Config JSON을 지원해야 한다. | JSON object가 common options 이후 deep merge된다. |

### 8.5 Preview / Dry Run

| ID | Requirement | Acceptance Criteria |
| --- | --- | --- |
| FR-PREVIEW-01 | Preview는 CME config와 target path를 검증해야 한다. | invalid JSON, empty URL, invalid scope, unwritable target이 실패한다. |
| FR-PREVIEW-02 | Preview는 실행 예정 scope와 URL을 표시해야 한다. | plan output에 `scope`와 `urls`가 포함된다. |
| FR-PREVIEW-03 | Preview는 page-level diff를 계산하지 않아야 한다. | Confluence API나 CME export를 호출하지 않는다. |
| FR-DRY-01 | Dry Run은 workspace export 결과를 변경하지 않아야 한다. | dry-run 전후 workspace hash가 같다. |

### 8.6 Run

| ID | Requirement | Acceptance Criteria |
| --- | --- | --- |
| FR-RUN-01 | Export Now는 CME adapter를 실행해야 한다. | internal exporter import나 execution path가 없다. |
| FR-RUN-02 | 실행 직전 Credential Manager 인증을 CME config에 주입해야 한다. | token은 임시 CME config에만 존재하고 로그에 남지 않는다. |
| FR-RUN-03 | 성공/실패 run history를 기록해야 한다. | `run_history.json`에 run_id, mode, status, summary(created/updated/deleted/skipped/errors), error, cme 정보가 기록된다. |
| FR-RUN-04 | 실패 시 사용자 메시지와 technical message를 분리해야 한다. | error object가 `category`, `code`, `user_message`, `technical_message`, `retryable`을 포함한다. |

### 8.7 GUI

| ID | Requirement | Acceptance Criteria |
| --- | --- | --- |
| FR-GUI-01 | GUI는 연결, 작업, 작업 설정 섹션을 제공해야 한다. | Setup Checker와 Logs 섹션 없이 인증 저장 후 Job 등록 흐름이 source와 smoke에서 확인된다. |
| FR-GUI-02 | 작업 설정 화면은 CME 옵션을 노출해야 한다. | internal backend selector가 없다. |
| FR-GUI-03 | GUI의 Export Now는 background thread에서 실행되어야 한다. | GUI가 장시간 작업 중 응답 불능 상태가 되지 않고, 실행 중에는 지금 내보내기 버튼이 내보내기 중...으로 바뀌며 충돌 가능한 작업 버튼이 비활성화된다. |
| FR-GUI-04 | 연결 섹션은 인증 저장 후 Job 등록 화면으로 바로 이동할 수 있어야 한다. | 저장 후 작업 만들기로 Credential Manager 저장 후 작업 설정 화면이 열린다. |
| FR-GUI-05 | 작업 섹션은 테이블, 선택한 작업 요약, 주요 실행 action을 한 화면에 제공해야 한다. | 선택한 Job의 작업명, 범위, 저장 폴더, URL이 라벨-값 행으로 표시되고 목록 상단에는 새 작업만 표시된다. |
| FR-GUI-06 | 작업 설정 화면은 기본 정보, CME 옵션, 예약, 고급 JSON으로 입력을 분리해야 한다. | 일반 설정과 raw CME JSON 편집이 섞이지 않는다. |
| FR-GUI-07 | GUI의 사용자-facing 라벨과 핵심 안내 문구는 한국어로 제공해야 한다. | Confluence/CME 고유 용어를 제외한 섹션, 버튼, 필드명, 짧은 안내문이 한국어다. |
| FR-GUI-08 | 연결 화면의 동작은 테스트, 저장/작업 생성, 계정 관리 영역으로 분리해야 한다. | 연결 테스트, 저장 후 작업 만들기, 저장된 토큰 삭제 버튼이 서로 다른 영역에 표시된다. |
| FR-GUI-09 | 연결 테스트 결과는 별도 상태 패널 없이 알림과 버튼 활성 상태로 제공해야 한다. | 성공/실패 시 알림이 표시되고, 성공한 입력값에서만 저장 후 작업 만들기 버튼이 활성화된다. |
| FR-GUI-10 | 작업 화면의 직접 action은 지금 내보내기, 편집, 대상 폴더 열기, 삭제만 제공해야 한다. | Preview/Dry Run 버튼은 GUI 작업 화면에 표시하지 않는다. |
| FR-GUI-11 | 작업 화면은 상세 JSON/최근 결과 JSON/별도 내보내기 상태 패널 없이 선택한 작업 요약과 최근 내보내기 표를 보여야 한다. | 작업 화면에 선택한 작업과 최근 내보내기 표가 표시되고 큰 JSON 결과 패널과 내보내기 상태 섹션은 없다. |
| FR-GUI-12 | 작업 선택 시 최근 내보내기 기록을 표로 보여야 한다. | 최근 10회 실행의 한국시간, 성공/실패, 문서 생성/업데이트, 삭제, 건너뜀, 오류 수가 최신순으로 표시된다. |

### 8.8 CLI

| ID | Requirement | Acceptance Criteria |
| --- | --- | --- |
| FR-CLI-01 | `check` 명령을 제공해야 한다. | runtime, package, disk, credential lookup check가 JSON으로 출력된다. |
| FR-CLI-02 | `login`/`logout` 명령을 제공해야 한다. | token stdin login과 logout smoke가 통과한다. |
| FR-CLI-03 | `add-job` 명령을 제공해야 한다. | CME scope/options를 argument로 받을 수 있다. |
| FR-CLI-04 | `preview`, `dry-run`, `run`, `validate` 명령을 제공해야 한다. | 저장된 Job ID로 실행 가능하다. |
| FR-CLI-05 | CLI 출력은 JSON이어야 한다. | 자동화가 stdout JSON을 parse할 수 있다. |
| FR-CLI-06 | `list-jobs` 명령을 제공해야 한다. | 저장된 Job 목록을 schema_version과 함께 JSON으로 출력한다. |

## 9. Data Model

### 9.1 Job

```json
{
  "id": "product-docs",
  "name": "Product Docs",
  "confluence_url": "https://company.atlassian.net/wiki/spaces/PROD/pages/123456/Root",
  "target_dir": "C:\\Users\\user\\Documents\\product-docs",
  "include_children": true,
  "include_attachments": false,
  "enabled": true,
  "export_options": {
    "cme_scope": "pages-with-descendants",
    "cme_urls": "https://company.atlassian.net/wiki/spaces/PROD/pages/123456/Root",
    "cme_config_json": "{}",
    "page_href": "relative",
    "attachment_href": "relative",
    "attachment_export_all": true,
    "page_breadcrumbs": true,
    "page_properties_as_front_matter": true,
    "include_document_title": false,
    "enable_jira_enrichment": false,
    "skip_unchanged": true,
    "cleanup_stale": true,
    "timeout": 30,
    "max_workers": 20,
    "verify_ssl": true
  }
}
```

`include_attachments`는 backward compatibility field다. 실제 attachment 정책은 CME config와 `attachment_export_all`이 결정한다.

### 9.2 Preview Plan

```json
{
  "schema_version": 1,
  "plan_id": "20260505-001413-product-docs-cme-plan",
  "job_id": "product-docs",
  "created_at": "2026-05-05T00:14:13+09:00",
  "scope": "pages-with-descendants",
  "urls": [
    "https://company.atlassian.net/wiki/spaces/PROD/pages/123456/Root"
  ],
  "local_snapshot_hash": "sha256:...",
  "summary": {
    "create": 0,
    "update": 1,
    "skip": 0,
    "error": 0
  },
  "items": [
    {
      "action": "update",
      "page_id": null,
      "title": "CME export",
      "current_path": null,
      "target_path": "C:\\Users\\user\\Documents\\product-docs",
      "local_hash": null,
      "reason": "CME pages-with-descendants job; 1 URL(s). Exact skips and cleanup are decided by CME at run time.",
      "safe_to_apply": true
    }
  ],
  "warnings": [
    "Preview validates CME config/auth shape and target path only. CME calculates page-level changes during Export Now."
  ]
}
```

### 9.3 Run History

```json
{
  "schema_version": 1,
  "runs": [
    {
      "run_id": "20260505-001413-product-docs",
      "job_id": "product-docs",
      "mode": "cme_apply",
      "started_at": "2026-05-05T00:14:13+09:00",
      "finished_at": "2026-05-05T00:14:30+09:00",
      "status": "success",
      "summary": {
        "created": 10,
        "updated": 0,
        "deleted": 1,
        "skipped": 2,
        "errors": 0
      },
      "error": null,
      "cme": {
        "command": "pages-with-descendants",
        "urls": [
          "https://company.atlassian.net/wiki/spaces/PROD/pages/123456/Root"
        ],
        "output_path": "C:\\Users\\user\\Documents\\product-docs",
        "stats": {
          "exported": 10,
          "skipped": 2,
          "failed": 0,
          "removed": 1
        }
      }
    }
  ]
}
```

## 10. Architecture

```text
GUI / CLI
  -> JobStore
  -> Windows Credential Manager
  -> Validation
  -> SyncEngine
  -> CME Backend Adapter
  -> confluence-markdown-exporter
  -> Target Directory
```

### 10.1 App Responsibilities

- GUI/CLI input handling
- Job persistence
- Credential Manager integration
- CME config template and merge
- temporary CME config file generation
- run history and logs
- package build and smoke verification

### 10.2 CME Responsibilities

- Confluence API crawling
- page tree/space/org traversal
- Markdown conversion fidelity
- attachment download and link rewriting
- skip unchanged
- cleanup stale
- lockfile management
- Jira enrichment where configured

## 11. Packaging

| ID | Requirement | Acceptance Criteria |
| --- | --- | --- |
| PKG-01 | The GUI must be built as the default PyInstaller onedir app; the CLI is an optional developer/support build. | `dist\confluence-export-desktop\confluence-export-desktop.exe` exists after `scripts\build.ps1`; `dist\confluence-export-cli\confluence-export-cli.exe` exists only when built with `-IncludeCli`. |
| PKG-02 | CME package must be bundled. | GUI packaging collects `confluence_markdown_exporter`; optional built CLI can run `check` when included. |
| PKG-03 | User PC must not need Python. | package gate passes on a clean Windows machine without Python. |
| PKG-04 | Built GUI must launch. | smoke starts GUI and confirms the process remains running. |
| PKG-05 | Release distribution must provide a Windows installer EXE. | `scripts\build_installer.ps1` creates `dist\ConfluenceExportDesktopSetup-<version>.exe`; installer smoke can install, launch, and uninstall from a temp directory. |

## 12. Security

| ID | Requirement | Acceptance Criteria |
| --- | --- | --- |
| SEC-01 | API token must never be stored in jobs/settings/run history/logs. | token leak scan finds no token. |
| SEC-02 | CLI login should support stdin token input. | token does not appear in shell history arguments. |
| SEC-03 | Logs and errors must be masked. | known secret patterns are replaced with `****`. |
| SEC-04 | Temporary CME config should be created only for execution. | temp directory is removed after execution. |

## 13. Error Handling

| Category | Meaning |
| --- | --- |
| Config | invalid Job, invalid CME JSON, missing settings |
| Validation | target path or dry-run mutation failure |
| Auth | missing or invalid credentials |
| Network | transport/connectivity failures |
| Confluence API | CME/Confluence API execution failure |
| File System | target/log/history write failure |

Errors must expose user-facing and technical messages separately.

## 14. Validation Gates

| Gate | Requirement | Evidence |
| --- | --- | --- |
| GATE-01 | compile succeeds | `python -m compileall -q src tests scripts` |
| GATE-02 | unit tests pass | `python -m unittest` |
| GATE-03 | built GUI app passes smoke | `python scripts\smoke_built_apps.py` |
| GATE-04 | release verifier passes | `python scripts\verify_release.py` |
| GATE-05 | package includes CME | packaging spec collects CME modules; optional built CLI `check` can be used when the CLI build is included |
| GATE-06 | GUI launches | built GUI smoke passes |
| GATE-07 | token is not leaked | credential and built-app smoke pass |
| GATE-08 | installer builds | `scripts\build_installer.ps1` and `scripts\smoke_installer.ps1` |
| GATE-09 | live Confluence export works | external live credentials required |
| GATE-10 | clean Windows without Python works | external clean machine required |

## 15. Test Plan

| Test ID | Coverage |
| --- | --- |
| UT-AUTH-01 | auth input validation |
| UT-JOB-01 | stable Job ID |
| UT-JOB-02 | URL helper parsing |
| UT-JOB-03 | enabled field persistence |
| UT-CME-01 | default CME config template, attachment_export_all=true and enable_jira_enrichment=false defaults |
| UT-CME-02 | advanced CME JSON merge |
| UT-CME-03 | scope and multi-URL validation |
| IT-ENGINE-01 | Preview uses CME-only plan |
| IT-ENGINE-02 | Dry Run does not mutate workspace |
| IT-ENGINE-03 | Export Now records CME run history |
| IT-ENGINE-04 | failed CME run records error |
| IT-GUI-01 | GUI source exposes CME controls and no backend selector |
| IT-CLI-01 | CLI exposes CME options and no backend argument |
| PKG-01 | built GUI launch |
| PKG-02 | optional built CLI check when `-IncludeCli` is used |

## 16. Release Criteria

Release is acceptable when:

- all local validation gates pass,
- GUI and developer CLI expose no internal backend path,
- CME package import is covered by GUI packaging and optional built CLI checks,
- built GUI launches,
- built app smoke passes,
- external live Confluence verification is either passed or explicitly marked as remaining external evidence,
- clean Windows no-Python verification is either passed or explicitly marked as remaining external evidence.

## 17. References

- [CME Feature Support](CME_FEATURE_SUPPORT.md)
- `confluence-markdown-exporter==4.1.1`
