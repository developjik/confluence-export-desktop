# Confluence Export Desktop (v2 — Rust + Tauri)

Current baseline: 2026-10-25
v2 아키텍처: Rust 백엔드 + Tauri 2 데스크톱 앱, Atlassian REST API 직접 연동(CME 의존 제거), 새로운 UI/UX

v2는 Confluence 페이지/스페이스/사이트 전체를 Markdown + 첨부파일로 내보내는 데스크톱 앱입니다. Python이나
`confluence-markdown-exporter`(CME) 없이 자체 Rust 엔진이 크롤·변환·스킵·정리를 수행합니다. v1(PySide6 + CME
래퍼) 코드는 `src/confluence_sync_tool`에 참조용으로 남아 있습니다.

- 계획/골: [docs/V2_PLAN.md](docs/V2_PLAN.md)
- v1 제품 요구사항(참조): [docs/PRD_v1.0.md](docs/PRD_v1.0.md)
- 문서 웹사이트(GitHub Pages): https://developjik.github.io/confluence-export-desktop/ — main 브랜치 push 시 자동 갱신

## What v2 Owns (전부 Rust)

- Confluence Cloud REST API 클라이언트(재시도/백오프/페이지네이션, TLS 상시 검증)
- Storage format → Markdown 변환기(헤딩/표/리스트/코드/링크 3종 모드/이미지/패널/expand/태스크/페이지 속성 → front matter/breadcrumbs)
- 익스포터 오케스트레이션: 경로 템플릿, lockfile(v2 스키마) 기반 skip-unchanged, stale cleanup, 첨부파일
- 프리셋 스케줄러(매일/매주/매월, 타임존), 트레이 상주, 창 닫기 → 트레이
- OS 키체인 자격증명(Windows 자격 증명 관리자 / macOS 키체인) + v1 토큰 이관(Windows)
- React UI: 대시보드 / 연결 / 작업 / 작업 편집(5섹션) / 실행 기록 / 설정 + 라이브 실행 뷰(단계·카운터·로그·취소)

## 아키텍처

```
ui/ (React + TS + Tailwind)   ←IPC→   src-tauri/ (Rust)
                                       ├─ confluence/ (REST client, URL 파싱)
                                       ├─ converter/  (storage → Markdown)
                                       ├─ exporter/   (lockfile, 경로, 오케스트레이션)
                                       ├─ scheduler / storage / credentials / commands
                                       └─ Tauri 앱(트레이, 스케줄러 루프)
```

- API는 Confluence Cloud REST v1(content/space/attachment)을 사용합니다(v2 API 전환은 로드맵).
- 저장 위치: `{config_dir}/ConfluenceExportDesktop/` — `settings.json`, `jobs.json`, `runs.jsonl`, `logs/app.log`.
- 실행 이력은 앱 레벨(`runs.jsonl`)과 대상 폴더(`run_history.json`)에 이중 기록.
- lockfile: `<target>/confluence-export.lock.json` (schema v2). v1/CME lockfile과 호환되지 않아 첫 실행 시 전체
  재동기화됩니다.

## 개발

요구 사항: Rust 1.82+, Node 20+

```bash
npm install

# 프론트엔드만 (브라우저 목업 모드 — http://localhost:5173)
npm run dev:ui

# 데스크톱 앱 실행
npm run tauri:dev

# 검증
cargo test --manifest-path src-tauri/Cargo.toml --lib
npm run build:ui        # tsc + vite build

# 배포 빌드 (macOS: .app/.dmg)
npm run tauri:build
```

Windows 인스톨러(NSIS)는 GitHub Actions에서 빌드합니다: `.github/workflows/build-v2.yml`
(`Build v2` 워크플로 — push/tag 시 Rust 테스트 → Windows NSIS + macOS 앱 아티팩트).

## UI 흐름

1. `연결` — Base URL/이메일/API 토큰 입력 → `연결 테스트` → `저장`. 토큰은 OS 키체인에만 저장.
   (v1 사용자는 `v1 설정 가져오기`로 작업/설정/토큰을 이관 — Windows는 토큰 포함.)
2. `작업` → `새 작업` — 5섹션 편집기(기본 정보/범위/콘텐츠 옵션/고급/예약)에서 설정 후 저장.
3. `지금 내보내기` — 라이브 실행 뷰에서 단계(수집→변환→첨부→정리)와 페이지별 로그를 실시간 확인, 취소 가능.
4. `예약 사용`을 켜면 앱이 트레이에 있는 동안 매일/매주/매월 자동 실행됩니다.

## 지원 범위

- Scope: `auto`, `pages`, `pages-with-descendants`, `spaces`, `orgs` (v1과 동일한 auto 규칙)
- 링크 모드: `absolute`(내보내기 루트 기준), `relative`(파일 상대), `wiki`(Confluence URL)
- 경로 템플릿 토큰: `{space_name} {space_key} {homepage_title} {ancestor_titles} {page_title}` /
  첨부 `{attachment_file_id} {attachment_file_name} {attachment_extension}` 등
- 미지원 매크로는 `<!-- 지원되지 않는 매크로: ... -->` 코멘트로 폴백(변환 품질은 반복 개선 대상)
- 비목표: Jira enrichment(후순위), Data Center 지원

## v1(레거시) 안내

- v1 코드/문서/패키징은 그대로 유지(`src/confluence_sync_tool`, `scripts/*.ps1`, `packaging/`).
- v1 데이터 위치: `{config_dir}/ConfluenceExportDesktop/app/` — v2의 `v1 설정 가져오기`가 읽습니다.
- v1 lockfile(`confluence-lock.json`)은 v2에서 사용하지 않습니다.
