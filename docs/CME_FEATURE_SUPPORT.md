# CME Feature Support

기준일: 2026-05-05  
기준 패키지: `confluence-markdown-exporter==4.1.1`
최신 PRD: [PRD v1.0](PRD_v1.0.md)

Confluence Sync Tool은 이제 internal exporter를 사용하지 않는다. 제품 경계는 “Python 없이 실행되는 CME GUI Job Runner”다.

핵심 결론:

- 모든 Job은 CME Job이다.
- 실제 Confluence export, Markdown 변환, attachment 처리, skip, cleanup, lockfile 처리는 CME가 담당한다.
- GUI는 Job 저장, Credential Manager 인증, CME config 생성, 실행 로그/run history, manual/scheduled run을 담당한다.
- internal Confluence client, internal Markdown exporter, manifest 기반 plan/apply, conflict/delete 기록은 제거 대상이며 기능 경계에 포함하지 않는다.

## Job Scopes

| Scope | 설명 |
| --- | --- |
| `pages` | 하나 이상의 page URL을 export한다. |
| `pages-with-descendants` | page URL과 모든 하위 페이지를 export한다. |
| `spaces` | 하나 이상의 space URL 전체를 export한다. |
| `orgs` | 하나 이상의 Confluence base URL 전체를 export한다. |
| `auto` | URL과 `Include Children` 값으로 scope를 자동 선택한다. |

`auto` 규칙:

- URL에 `/pages/`가 있고 `Include Children=true`면 `pages-with-descendants`
- URL에 `/pages/`가 있고 `Include Children=false`면 `pages`
- URL에 `/spaces/`만 있으면 `spaces`
- 그 외 base URL은 `orgs`

## Current GUI Surface

현재 GUI는 PySide6 기반이며 `연결`, `작업`, `작업 설정` 좌측 사이드바 섹션으로 구성된다.

- `연결`: Confluence 기본 URL, 이메일, API 토큰 입력, `연결 테스트`, `저장 후 작업 만들기`, 저장된 토큰 삭제.
- `작업`: 저장된 Job 목록, 선택한 작업 요약, 최근 동기화 표, `지금 동기화`, `편집`, `대상 폴더 열기`, `삭제`.
- `작업 설정`: `기본 정보`, `CME 옵션`, `예약`, `고급 JSON` 하위 탭.

GUI 작업 화면은 Run을 제공한다. Validate, Preview, Dry Run은 최종 사용자 GUI에 노출하지 않고 엔진/개발자 검증 경로로 유지한다.

## GUI Fields

| Field | CME mapping |
| --- | --- |
| `Confluence URL` | CME 실행 대상 URL. 쉼표로 여러 URL 입력 가능. |
| `하위 페이지 포함` | `auto` scope에서 page URL을 `pages` 또는 `pages-with-descendants`로 결정한다. |
| `CME 범위` | `auto`, `pages`, `pages-with-descendants`, `spaces`, `orgs`. |
| `페이지 링크` | `export.page_href`: `absolute`, `relative`, `wiki`. |
| `첨부파일 링크` | `export.attachment_href`: `absolute`, `relative`, `wiki`. |
| `첨부파일 전체 저장` | `export.attachment_export_all`. |
| `페이지 경로 표시` | `export.page_breadcrumbs`. |
| `페이지 속성을 Front Matter로 저장` | `export.page_properties_as_front_matter`. |
| `문서 제목 포함` | `export.include_document_title`. |
| `Jira 정보 보강` | `export.enable_jira_enrichment`. |
| `변경 없는 파일 건너뛰기` | `export.skip_unchanged`. |
| `사라진 파일 정리` | `export.cleanup_stale`. |
| `SSL 검증` | `connection_config.verify_ssl`. |
| `타임아웃(초)` | `connection_config.timeout`. |
| `동시 작업 수` | `connection_config.max_workers`. |
| `CME Config JSON` | CME 원본 config override. GUI 공통 옵션보다 우선한다. |

적용 우선순위:

1. 앱의 기본 CME config template
2. GUI 공통 옵션
3. `CME Config JSON`
4. 실행 직전 `output_path`와 Windows Credential Manager 인증 정보 주입

## CME Config JSON

GUI가 모든 주요 옵션을 노출하지만, CME의 전체 설정 표면은 `CME Config JSON`으로 전달한다. 아래 옵션은 기본 템플릿에 포함된다.

### `export`

| Key | 기본값 | 설명 |
| --- | --- | --- |
| `log_level` | `INFO` | CME log level. |
| `output_path` | Job target dir | 실행 직전 target directory로 덮어쓴다. |
| `page_href` | `relative` | Page link style. |
| `page_path` | `{space_name}/{homepage_title}/{ancestor_titles}/{page_title}.md` | Page output path template. |
| `attachment_href` | `relative` | Attachment link style. |
| `attachment_path` | `{space_name}/attachments/{attachment_file_id}{attachment_extension}` | Attachment output path template. |
| `attachment_export_all` | `true` | 참조되지 않은 attachment까지 export. 기본으로 모든 첨부파일을 저장한다. |
| `page_breadcrumbs` | `true` | Markdown breadcrumb 포함. |
| `page_properties_as_front_matter` | `true` | Page Properties macro를 YAML front matter로 변환. |
| `filename_encoding` | CME 기본 치환표 | 파일명 문자 치환 규칙. |
| `filename_length` | `255` | 파일명 최대 길이. |
| `filename_lowercase` | `false` | 경로/파일명 lowercase 강제. |
| `include_document_title` | `false` | Markdown 상단 document title heading 포함. |
| `enable_jira_enrichment` | `false` | Jira issue link enrichment. Jira 인증이 추가로 필요할 수 있어 기본값은 꺼둔다. |
| `skip_unchanged` | `true` | Lockfile 기준 unchanged page skip. |
| `cleanup_stale` | `true` | 이동/삭제된 page의 stale local file 정리. |
| `lockfile_name` | `confluence-lock.json` | CME lockfile 이름. |
| `existence_check_batch_size` | `250` | stale cleanup existence check batch size. |

### `connection_config`

| Key | 기본값 | 설명 |
| --- | --- | --- |
| `backoff_and_retry` | `true` | Atlassian SDK retry/backoff. |
| `backoff_factor` | `2` | exponential backoff multiplier. |
| `max_backoff_seconds` | `60` | retry 최대 대기 시간. |
| `max_backoff_retries` | `5` | 최대 retry 횟수. |
| `retry_status_codes` | `[413, 429, 502, 503, 504]` | retry 대상 HTTP status code. |
| `verify_ssl` | `true` | SSL 인증서 검증. |
| `timeout` | `30` | API request timeout seconds. |
| `use_v2_api` | `false` | Confluence REST API v2 사용. |
| `max_workers` | `20` | 병렬 export worker 수. |

### `auth`

Confluence auth는 앱이 Windows Credential Manager에서 읽어 실행 직전에 CME config로 주입한다. 사용자가 `CME Config JSON`에 `auth`를 넣을 수는 있지만, Confluence base URL에 대한 username/token 값은 실행 직전 값이 우선한다.

Jira enrichment를 쓰려면 CME가 요구하는 Jira auth 구성이 별도로 필요할 수 있다.

## Preview / Dry Run

CME-only 구조에서 Preview는 internal diff가 아니다. Preview/Dry Run은 다음만 수행한다.

- Job name, target directory, CME URL, CME scope, CME JSON 문법 검증
- 실행 예정 scope와 URL 수 표시
- 정확한 page-level create/update/skip/remove는 `Sync Now` 중 CME lockfile과 Confluence API 결과로 결정된다는 warning 표시

이 방식은 CME 동작을 복제하지 않기 위한 의도적인 설계다.

## Developer CLI Examples

The final-user build is GUI-first. Build the optional developer CLI with `scripts\build.ps1 -IncludeCli` before using the packaged examples below.

Page with descendants:

```powershell
.\dist\confluence-sync-cli\confluence-sync-cli.exe add-job `
  --name "Product Docs" `
  --url "https://company.atlassian.net/wiki/spaces/PROD/pages/123/Root" `
  --target-dir "C:\Users\developjik\Desktop\docs" `
  --cme-scope pages-with-descendants
```

Space:

```powershell
.\dist\confluence-sync-cli\confluence-sync-cli.exe add-job `
  --name "PROD Space" `
  --url "https://company.atlassian.net/wiki/spaces/PROD" `
  --target-dir "C:\Users\developjik\Desktop\prod-space" `
  --cme-scope spaces
```

Org:

```powershell
.\dist\confluence-sync-cli\confluence-sync-cli.exe add-job `
  --name "Company Confluence" `
  --url "https://company.atlassian.net" `
  --target-dir "C:\Users\developjik\Desktop\company-confluence" `
  --cme-scope orgs
```

Common options:

```powershell
.\dist\confluence-sync-cli\confluence-sync-cli.exe add-job `
  --name "PROD Space" `
  --url "https://company.atlassian.net/wiki/spaces/PROD" `
  --target-dir "C:\Users\developjik\Desktop\prod-space" `
  --cme-scope spaces `
  --page-href wiki `
  --attachment-href relative `
  --attachment-export-all `
  --skip-unchanged `
  --cleanup-stale `
  --timeout 60 `
  --max-workers 10
```

Advanced JSON override:

```json
{
  "export": {
    "page_href": "absolute",
    "attachment_href": "absolute",
    "page_path": "{space_key}/{ancestor_titles}/{page_title}.md",
    "attachment_path": "{space_key}/attachments/{attachment_file_id}{attachment_extension}",
    "skip_unchanged": true,
    "cleanup_stale": true
  },
  "connection_config": {
    "timeout": 60,
    "max_workers": 10,
    "verify_ssl": true
  }
}
```

## Verification

자동 검증 범위:

- `python -m compileall -q src tests`
- `python -m unittest`
- `scripts\build.ps1`
- `python scripts\smoke_built_apps.py`
- `scripts\build.ps1 -IncludeCli` only when a packaged developer CLI or live CLI smoke is required

테스트는 다음을 확인한다.

- CME config template이 CME 4.1.1 주요 `export`/`connection_config` 옵션을 포함한다.
- GUI가 internal backend 선택지를 노출하지 않고 CME 옵션만 노출한다.
- Preview/Dry Run은 workspace를 변경하지 않는다.
- Apply는 CME exporter adapter만 호출하고 run history/job log에 CME 결과를 남긴다.
- 실패 시 error object와 failed run history가 기록된다.

## Notes

- 기능 기준은 `confluence-markdown-exporter==4.1.1`이다. CME 버전을 올리면 config template과 이 문서를 다시 audit해야 한다.
- `cleanup_stale=true`면 CME가 lockfile 기준 stale local file을 정리할 수 있다. 원문 snapshot만 누적 보관하려면 false로 설정한다.
- `CME Config JSON`은 강력하지만 JSON 문법 오류가 있으면 Job validation에서 실패한다.
