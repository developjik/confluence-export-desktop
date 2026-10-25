# V2 계획 — Rust + Tauri 전면 포팅 및 UI/UX 재수립

기준일: 2026-10-25
상태: **1차 구현 완료** — 아래 골별 결과 참조

## 1. 목표 (Goals)

| # | 목표 | 완료 조건 | 결과(2026-10-25) |
|---|---|---|---|
| G1 | CME 의존성 제거 — Atlassian REST API 직접 호출 | `confluence-markdown-exporter` 의존 없이 page/space/org 크롤·첨부·변환·skip·cleanup 전 과정이 Rust로 동작 | ✅ `src-tauri/src/{confluence,converter,exporter}`로 구현. CME 의존 없음 |
| G2 | 백엔드 전면 Rust 전환 | 모든 비즈니스 로직이 Rust 크레이트로 구현, `cargo test` 통과 | ✅ 41개 단위 테스트 통과(URL/scheduler/lockfile/paths/converter 통합) |
| G3 | UI/UX 전면 재수립 | 사이드바 + 6개 화면 + 라이브 실행 뷰의 새 디자인 시스템 | ✅ React+Tailwind, 목업 브라우저 스모크로 6화면+실행모달 검증 |
| G4 | 단일 데스크톱 앱 패키징 | Tauri 2 번들(macOS 빌드 + Windows 인스톨러 CI) | ✅ `npx tauri build` 로컬 + `.github/workflows/build-v2.yml` (Windows NSIS/macOS app) |
| G5 | v1 자산 마이그레이션 경로 | v1 설정/작업 가져오기 + Windows Credential Manager 토큰 이관 | ✅ `import_v1` 커맨드 + 연결 화면 버튼(Windows에서 토큰 직접 읽기) |
| G6 | 검증 게이트 | cargo test / tsc+vite / tauri build / 목업 UI 스모크 | ✅ 전부 통과 |

비목표(명시적 제외): Jira enrichment(후순위), CME 출력과의 바이트 단위 동일성(lockfile 스키마 v2로 새로 시작), Confluence Data Center 지원(Cloud 기준).

### 차기 작업 (후보)

- 실제 Confluence 스페이스 대상 라이브 스모크(토큰 필요) 및 변환 품질 반복 개선(희귀 매크로)
- REST v2 API 전환 검토
- Jira enrichment, 첨부파일 업로드 시점 검증 등

## 2. 아키텍처

```
┌────────────────────────────── Tauri 2 앱 ──────────────────────────────┐
│  ui/ (React + TS + Tailwind)          src-tauri/ (Rust)                │
│  ┌────────────────────┐  IPC(commands │ ┌───────────────────────────┐  │
│  │ 화면 6종 + 실행 모달 │◀─+ events/    │─│ commands.rs (thin layer)  │  │
│  │ 디자인 시스템(theme) │  channel)     │ ├───────────────────────────┤  │
│  └────────────────────┘               │ │ exporter  (오케스트레이션) │  │
│                                       │ │  ├─ lockfile (스킵/정리)   │  │
│                                       │ │  ├─ paths    (템플릿)      │  │
│                                       │ │  └─ progress (취소/통계)   │  │
│                                       │ │ converter (storage→MD)    │  │
│                                       │ │ confluence (REST client)  │  │
│                                       │ │ scheduler / storage       │  │
│                                       │ │ credentials (keyring)     │  │
│                                       │ └───────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────┘
```

- **API**: Confluence Cloud REST v1(content/space/attachment — CME 기본 동작과 동일 경로). v2 전환은 후순위.
- **인증**: Basic(email:token). 자격증명은 OS 키체인(keyring 크레이트) — Windows Credential Manager / macOS Keychain.
- **동시성**: tokio + reqwest, 작업별 동시 요청 상한(기본 8), 429/5xx 지수 백오프.
- **저장 위치**: `{config_dir}/ConfluenceExportDesktop/` — `settings.json`, `jobs.json`, `runs.jsonl`, `logs/app.log`. 실행 이력은 앱 레벨(runs.jsonl) + 대상 폴더(`run_history.json`) 이중 기록.

## 3. 모듈 구성 (Rust)

| 모듈 | 책임 |
|---|---|
| `models` | Job/Schedule/ExportOptions/RunRecord — v1 필드 호환 deserializer |
| `storage` | settings/jobs/runs JSON 영속화(원자적 쓰기) |
| `credentials` | keyring read/write/delete + v1 Windows Credential 직접 읽기(`#[cfg(windows)]`) |
| `confluence::client` | 인증 테스트(`/rest/api/user/current`), 페이지 조회(expand), 하위 재귀, 스페이스/전체 목록, 첨부 목록/다운로드 |
| `converter` | storage format(html5ever) → Markdown. 매크로/링크/표/코드/태스크/패널/페이지 속성→front matter |
| `exporter` | URL→scope 해석, 크롤, 변환, 첨부, lockfile 갱신, skip/unchanged, stale cleanup, 통계 |
| `scheduler` | daily/weekly/monthly 프리셋, 타임존(chrono-tz), misfire=skip, 중복 실행 방지 |
| `commands` | Tauri IPC thin layer + 진행 Channel + 취소 토큰 |

## 4. UI/UX 재수립 (새 디자인)

원칙: 한국어 퍼스트, 라이트/다크 테마, 카드 기반 정보 구조, 마법사式 작성이 아닌 섹션 폼, 모든 실행은 라이브 피드백.

| 화면 | 내용 |
|---|---|
| 대시보드 | 통계 카드(작업/활성 예약/오늘 실행/성공률), 최근 실행, 빠른 동작 |
| 연결 | 연결 프로필(베이스 URL/이메일/토큰), 실시간 연결 테스트 결과, v1 가져오기 |
| 작업 | 작업 카드 목록(범위/대상 폴더/예약/다음 실행/최근 상태), 즉시 실행·편집·폴더 열기·삭제 |
| 작업 편집 | 5섹션 폼: 기본 정보 / 범위(URL+scope+하위 포함) / 콘텐츠 옵션 / 고급(경로 템플릿·JSON) / 예약 |
| 실행 기록 | 실행 목록 + 상세(통계·로그 테일) |
| 설정 | 테마, 기본 동시 요청 수, 로그 레벨, 버전 정보 |
| 실행 모달 | 단계별 진행(나열/변환/첨부/정리), 실시간 카운터, 로그 스트림, 취소 |

디자인 시스템: CSS 변수 테마, Pretendard/시스템 폰트 스택, 8px 그리드, 12px 라운드 카드, 인디고 액센트, 상태 칩(성공/실패/건너뜀/예약).

## 5. 변환기 커버리지 (v2 초기)

지원: 헤딩/단락/강조/코드(인라인·블록·언어 매핑)/링크(외부·페이지·첨부·앵커, absolute·relative·wiki 모드)/이미지(첨부·외부, 폭)/리스트(중첩·태스크)/표(정렬; 병합 셀은 HTML 폴백)/인용/수평선/info·note·warning 패널/expand(details)/페이지 속성→YAML front matter/breadcrumbs/줄바꿈/유저 멘션/날짜 매크로.
폴백: 미지원 매크로는 `<!-- unsupported macro: ... -->` 코멘트(옵션으로 원문 유지).

## 6. Lockfile v2

`<target>/confluence-export.lock.json`, `schema_version: 2`, 페이지/첨부별 `version + path + hash`. skip_unchanged=버전 미변경 스킵, cleanup_stale=전체 범위 실행 후 미관측 항목 정리(space/org/하위 전체 스코프에서만 — 단일 페이지 실행 시 정리 안 함).

## 7. 마이그레이션

1. v1 `%APPDATA%\ConfluenceExportDesktop\app\{settings,jobs}.json` → v2 가져오기(대화 상자).
2. Windows: v1이 쓴 `ConfluenceExportDesktop:<base>:<email>` generic credential을 직접 읽어 keyring으로 재저장.
3. 기존 내보내기 폴더는 lockfile 스키마가 다르므로 첫 실행 시 전체 재동기화.

## 8. 검증 게이트

- `cargo test` (converter/paths/lockfile/scheduler/storage 단위 테스트)
- `npx tsc --noEmit && npm run build` (ui)
- `cargo tauri build` (macOS; Windows는 GitHub Actions 워크플로 추가)
- 목업 IPC 레이어로 브라우저 UI 스모크(반응/내비게이션/상태)

## 9. 리스크

- 변환 품질의 긴 꼬리(희귀 매크로) → 폴백 전략 + 반복 개선, v1 CME를 오라클로 diff.
- Confluence Cloud API 변경 → 클라이언트를 단일 모듈로 격리.
- Windows 인스톨러는 본 머신(macOS)에서 직접 빌드 불가 → CI로 해결.
