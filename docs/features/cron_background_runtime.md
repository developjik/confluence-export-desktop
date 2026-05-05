# Cron Scheduling and Background Runtime

기준일: 2026-05-05
상태: Future feature spec

## 0. Document Position

이 문서는 현재 MVP PRD의 후속 기능 기준 문서다. 현재 MVP PRD는 scheduler, daemon, background sync를 non-goal로 둔다. 이 문서는 그 non-goal을 다음 제품 단계에서 해제하고, GUI 중심 제품으로 확장하기 위한 새 계약을 정의한다.

이 기능이 제품화되면 최종 사용자 배포물의 기본 인터페이스는 GUI가 된다. CLI는 최종 사용자 기능 표면에서 제거하거나 숨긴다. GUI는 현재 제품에서 노출하는 연결, Job 관리, 수동 실행 기능에 예약 실행과 background runtime을 추가한다. Validate, preview, dry-run은 최종 사용자 GUI 기능 표면에 다시 추가하지 않는다.

## 1. Purpose

Confluence Sync Tool은 현재 사용자가 GUI에서 Job을 만들고 `지금 동기화`를 눌러 수동 실행하는 구조다. 이후 예약 실행을 GUI에서 설정하려면, GUI 창을 닫은 뒤에도 예약된 Job을 실행할 수 있는 background runtime이 필요하다.

이 문서는 schedule 설정, background 실행, system tray 동작, Job 실행 정책의 제품/기술 계약을 먼저 정의한다. 실제 구현 문서는 이 계약을 기준으로 작성한다.

이 문서에서 cron은 내부 scheduler 구현 개념을 가리킨다. 사용자는 `0 9 * * *` 같은 cron expression을 직접 입력하지 않는다.

제품 관점에서 목표 상태는 "현재 앱의 수동 동기화 기능 + 예약 동기화 + tray/background 상주 실행"이다.

## 1.1 Confirmed Decisions

| Topic | Decision |
| --- | --- |
| User schedule input | Preset UI로 제공한다. 예: 매일, 주중, 매주, 매월, 하루 여러 번. |
| Schedule time basis | 한국시간 기준으로 설정하고 계산한다. |
| Raw cron expression | 1차 GUI 범위에서 제공하지 않는다. |
| Quit while running | 실행 중인 Job이 있으면 완전 종료를 허용하지 않는다. |
| `next_run_at` | Job 설정의 authoritative field로 저장하지 않는다. Scheduler가 계산하는 파생값으로 취급한다. |
| Misfire/skip events | 실행되지 않은 예약 event도 기록한다. |
| Tray failure | Tray 초기화 실패 시 background runtime을 비활성화하고 사용자에게 알린다. |
| End-user CLI | 후속 GUI 제품에서는 최종 사용자 기능 표면에서 제거한다. |
| GUI feature parity | 기존 CLI 핵심 기능은 GUI에서 접근 가능해야 한다. |
| Fully terminated app | 앱이 완전히 종료된 상태에서는 예약 실행을 보장하지 않는다. Windows 로그인 자동 시작은 별도 opt-in 기능으로 제공한다. |

## 2. Current Baseline

- GUI 창을 닫으면 앱 프로세스가 종료된다.
- GUI의 background thread는 장시간 sync 중 화면 응답성을 유지하기 위한 작업 스레드이며, 앱 종료 후 상주하는 background runtime이 아니다.
- CLI는 현재 login, job 관리, preview, dry-run, run을 제공하지만, 후속 GUI 제품에서는 최종 사용자 인터페이스에서 제거된다.
- GUI는 현재 Sync Now 중심이다. 후속 GUI 제품에서는 인증, Job 관리, run, run history/log 확인, schedule 설정을 제공해야 한다. Validate, preview, dry-run은 GUI에 노출하지 않는다.
- 실제 sync 실행 로직은 `SyncEngine`과 CME adapter가 담당한다.

## 3. Problem

예약 Job은 사용자가 지정한 시간에 자동으로 실행되어야 한다. 하지만 GUI 프로세스가 종료되면 다음 실행 시간을 감시하고 `SyncEngine`을 호출할 주체가 사라진다.

CLI 삭제 이후에는 Windows Task Scheduler가 CLI를 호출하는 방식도 기본 선택지가 될 수 없다. 따라서 GUI 중심 제품 구조에서는 앱이 창을 닫은 뒤에도 background 또는 tray 상태로 살아 있어야 한다.

또한 사용자가 CLI 없이도 모든 핵심 작업을 GUI에서 끝낼 수 있어야 한다. 예약 실행은 수동 실행 기능을 대체하는 것이 아니라, 동일한 Job 실행 엔진 위에 자동 trigger를 추가하는 기능이다.

## 4. Goals

| ID | Goal |
| --- | --- |
| BG-G-01 | 사용자가 GUI에서 Job별 preset schedule을 설정할 수 있다. |
| BG-G-02 | GUI 창을 닫아도 앱은 background/tray 상태로 유지된다. |
| BG-G-03 | Background 상태에서도 예약된 Job이 정해진 시간에 실행된다. |
| BG-G-04 | 사용자는 tray 메뉴에서 앱을 다시 열거나 완전히 종료할 수 있다. |
| BG-G-05 | 앱 재시작 후 저장된 schedule을 복구하고 다음 실행 시간을 다시 계산한다. |
| BG-G-06 | 실행 중인 Job의 중복 실행을 방지한다. |
| BG-G-07 | 예약 실행 결과는 기존 run history/log 체계에 기록된다. |
| BG-G-08 | CLI 없이도 인증, Job 생성/수정/삭제, run을 GUI에서 수행할 수 있다. |
| BG-G-09 | 사용자는 GUI에서 schedule 상태, 다음 실행 예정 시간, 마지막 scheduler event를 확인할 수 있다. |

## 5. Non-Goals

| ID | Non-Goal |
| --- | --- |
| BG-NG-01 | 1차 구현에서 Windows Service를 만들지 않는다. |
| BG-NG-02 | 서버 또는 cloud-hosted scheduler를 만들지 않는다. |
| BG-NG-03 | Confluence write-back 또는 양방향 sync를 포함하지 않는다. |
| BG-NG-04 | 앱이 완전히 종료된 상태에서 자체적으로 실행되는 것을 보장하지 않는다. |
| BG-NG-05 | 여러 PC 간 schedule 상태 동기화를 제공하지 않는다. |
| BG-NG-06 | 1차 GUI에서 raw cron expression 입력을 제공하지 않는다. |
| BG-NG-07 | 최종 사용자용 CLI backward compatibility를 보장하지 않는다. |
| BG-NG-08 | Windows Task Scheduler 기반 외부 예약 실행을 1차 제품 경로로 제공하지 않는다. |

## 6. Target User Behavior

### 6.1 Close Window

사용자가 GUI 창의 X 버튼을 누르면 앱은 완전히 종료되지 않는다.

Expected behavior:

- 메인 창을 숨긴다.
- System tray icon은 유지된다.
- Scheduler는 계속 실행된다.
- 예약된 Job은 background 상태에서 계속 실행된다.
- 첫 사용 시 "창을 닫아도 예약 동기화가 계속 실행됩니다" 안내를 표시할 수 있다.

### 6.2 Open From Tray

사용자가 tray icon 또는 tray menu의 `열기`를 선택하면 메인 창을 다시 표시한다.

Expected behavior:

- 기존 앱 프로세스를 재사용한다.
- Scheduler 상태를 유지한다.
- 최근 실행 상태와 다음 실행 시간을 GUI에 표시한다.

### 6.3 Quit From Tray

사용자가 tray menu의 `종료`를 선택하면 앱을 완전히 종료한다.

Expected behavior:

- Scheduler를 중지한다.
- 실행 중인 Job이 있으면 완전 종료를 거부하고 현재 실행이 끝난 뒤 다시 종료하라는 안내를 표시한다.
- 완전 종료 후에는 예약 Job이 실행되지 않는다.

### 6.4 Manual Sync While Scheduler Is Active

사용자는 schedule이 켜진 Job도 수동으로 `지금 동기화`할 수 있다.

Expected behavior:

- 같은 Job이 이미 실행 중이면 수동 실행을 막고 현재 실행 상태를 보여준다.
- 다른 Job은 concurrency policy에 따라 실행 가능 여부를 결정한다.

## 7. Functional Requirements

### 7.0 GUI Feature Parity After CLI Removal

후속 제품에서 CLI를 최종 사용자 인터페이스에서 제거하려면 GUI가 기존 CLI의 핵심 기능을 흡수해야 한다.

| ID | Requirement |
| --- | --- |
| BG-FR-GUI-01 | GUI는 Confluence base URL, email, API token 입력과 연결 테스트를 제공해야 한다. |
| BG-FR-GUI-02 | GUI는 Credential Manager에 저장된 token 삭제 또는 로그아웃 기능을 제공해야 한다. |
| BG-FR-GUI-03 | GUI는 Job 생성, 수정, 삭제, 목록 조회를 제공해야 한다. |
| BG-FR-GUI-04 | GUI는 최종 사용자 화면에 validate, preview, dry-run 버튼을 제공하지 않아야 한다. |
| BG-FR-GUI-05 | GUI는 manual run을 실행할 수 있어야 한다. |
| BG-FR-GUI-06 | GUI는 run history를 표시할 수 있어야 한다. |
| BG-FR-GUI-07 | GUI는 manual run, scheduled run 모두 같은 run history view에서 확인할 수 있어야 한다. |
| BG-FR-GUI-08 | GUI는 job log 위치를 `<target-dir>\.logs\app.log` 기준으로 열거나 확인할 수 있어야 한다. |
| BG-FR-GUI-09 | CLI 제거 후에도 packaging, smoke test, release verification은 GUI entrypoint 기준으로 유지되어야 한다. |

### 7.1 Schedule Configuration

| ID | Requirement |
| --- | --- |
| BG-FR-SCH-01 | Job 설정 화면은 schedule on/off를 제공해야 한다. |
| BG-FR-SCH-02 | Job 설정 화면은 raw cron expression이 아니라 쉬운 preset schedule을 제공해야 한다. |
| BG-FR-SCH-03 | 1차 preset은 `매일`, `주중`, `매주`, `매월`, `하루 여러 번`을 포함해야 한다. |
| BG-FR-SCH-04 | Job 설정 화면은 실행 시각을 `HH:mm` 형식으로 하나 이상 입력할 수 있어야 한다. |
| BG-FR-SCH-05 | 실행 시각은 한국시간 기준으로 저장하고 계산해야 한다. |
| BG-FR-SCH-06 | GUI는 저장 전에 schedule kind와 실행 시각을 검증해야 한다. |
| BG-FR-SCH-07 | GUI는 scheduler가 계산한 다음 실행 예정 시간을 표시해야 한다. |
| BG-FR-SCH-08 | 1차 구현에서 timezone 선택 UI는 제공하지 않는다. |
| BG-FR-SCH-09 | Schedule이 켜져 있지만 앱 자동 시작이 꺼져 있으면, GUI는 완전 종료 상태에서는 예약 실행이 보장되지 않는다고 표시해야 한다. |
| BG-FR-SCH-10 | Job이 disabled 상태이면 schedule도 실행 대상에서 제외해야 한다. 단, `enabled`와 `schedule.enabled`의 의미는 UI에서 구분해 표시해야 한다. |
| BG-FR-SCH-11 | `매주` schedule은 월-일 중 하나 이상의 요일을 선택할 수 있어야 한다. |
| BG-FR-SCH-12 | `매월` schedule은 1-31일 중 하나를 선택할 수 있어야 하며, 해당 날짜가 없는 달은 실행하지 않는다. |
| BG-FR-SCH-13 | `하루 여러 번` schedule은 실행 시각을 두 개 이상 저장하고 가장 가까운 다음 시각을 계산해야 한다. |

### 7.2 Background Runtime

| ID | Requirement |
| --- | --- |
| BG-FR-RUN-01 | 앱 시작 시 scheduler를 초기화하고 enabled schedule을 로드해야 한다. |
| BG-FR-RUN-02 | 창 닫기 동작은 기본적으로 hide-to-tray로 처리해야 한다. |
| BG-FR-RUN-03 | 완전 종료는 tray menu 또는 명시적 종료 액션으로만 수행해야 한다. |
| BG-FR-RUN-04 | Background 상태에서 예약 시간이 도달하면 `SyncEngine`을 호출해야 한다. |
| BG-FR-RUN-05 | Scheduler는 GUI thread를 block하지 않아야 한다. |
| BG-FR-RUN-06 | Scheduler는 GUI widget 상태를 직접 읽지 않고 저장된 Job config와 runtime state만 사용해야 한다. |
| BG-FR-RUN-07 | 앱 시작, sleep/resume, clock 변경 이후 scheduler는 다음 실행 시간을 다시 계산해야 한다. |
| BG-FR-RUN-08 | Windows 로그인 자동 시작은 1차 구현에서 opt-in 설정으로 제공해야 한다. |

### 7.3 Tray

| ID | Requirement |
| --- | --- |
| BG-FR-TRAY-01 | 앱은 Windows system tray icon을 제공해야 한다. |
| BG-FR-TRAY-02 | Tray menu는 최소 `열기`, `스케줄 일시정지/재개`, `종료`를 제공해야 한다. |
| BG-FR-TRAY-03 | 예약 Job 실행 실패 시 tray notification을 표시할 수 있어야 한다. |
| BG-FR-TRAY-04 | Tray icon이 초기화되지 못하면 background runtime을 활성화하지 않아야 한다. |
| BG-FR-TRAY-05 | Tray icon 초기화 실패 시 앱은 사용자에게 창 닫기 시 앱이 종료된다는 안내를 표시해야 한다. |
| BG-FR-TRAY-06 | Tray icon 초기화 실패 상태에서 X 버튼은 기존처럼 앱을 종료해야 한다. |
| BG-FR-TRAY-07 | Tray menu의 일시정지/재개는 전역 schedule pause로 동작해야 하며, 현재 실행 중인 sync를 강제로 중단하지 않는다. |

### 7.4 Execution Policy

| ID | Requirement |
| --- | --- |
| BG-FR-EXE-01 | 같은 Job은 동시에 두 번 실행되지 않아야 한다. |
| BG-FR-EXE-02 | 같은 Job의 이전 실행이 아직 진행 중이면 새 예약 trigger는 skip해야 한다. |
| BG-FR-EXE-03 | 앱이 꺼져 있던 동안 놓친 실행은 misfire policy에 따라 처리해야 한다. |
| BG-FR-EXE-04 | 예약 실행도 수동 실행과 같은 credential, validation, filesystem policy를 사용해야 한다. |
| BG-FR-EXE-05 | 예약 실행 실패는 run history/log에 기록해야 한다. |
| BG-FR-EXE-06 | 실행 중인 Job이 하나라도 있으면 완전 종료 요청을 거부해야 한다. |
| BG-FR-EXE-07 | Manual run과 scheduled run은 같은 Job에 대해 같은 concurrency lock을 공유해야 한다. |
| BG-FR-EXE-08 | 서로 다른 Job의 동시 실행은 global worker limit을 초과하지 않아야 한다. 기본값은 1로 둔다. |
| BG-FR-EXE-09 | 예약 실행으로 생성된 run history는 `mode` 또는 별도 field로 scheduled/manual trigger를 구분할 수 있어야 한다. |

### 7.5 Scheduler Event Logging

예약 runtime은 실행된 Job뿐 아니라 실행되지 않은 scheduler event도 추적 가능하게 기록해야 한다.

| ID | Requirement |
| --- | --- |
| BG-FR-EVT-01 | 예약 trigger 시도는 app log에 기록해야 한다. |
| BG-FR-EVT-02 | 실제 sync를 실행한 event는 기존 run history/log에도 기록해야 한다. |
| BG-FR-EVT-03 | 중복 실행 방지로 skip된 event는 app log와 scheduler event log에 기록해야 한다. |
| BG-FR-EVT-04 | misfire policy 때문에 skip된 event는 app log와 scheduler event log에 기록해야 한다. |
| BG-FR-EVT-05 | scheduler event는 최소 Job ID, event type, scheduled time, observed time, result를 포함해야 한다. |
| BG-FR-EVT-06 | Scheduler event는 구조화된 파일에 저장해야 한다. 기본 위치는 app data 아래 `scheduler_events.jsonl`로 둔다. |
| BG-FR-EVT-07 | Scheduler event log는 rotation 또는 보관 개수 제한을 가져야 한다. |

Recommended event types:

| Event Type | Meaning |
| --- | --- |
| `scheduled_due` | 예약 시간이 도달했다. |
| `scheduled_started` | 예약 실행이 시작됐다. |
| `scheduled_completed` | 예약 실행이 성공했다. |
| `scheduled_failed` | 예약 실행이 실패했다. |
| `scheduled_skipped_already_running` | 같은 Job이 이미 실행 중이라 skip했다. |
| `scheduled_misfired_skipped` | 앱이 꺼져 있었거나 scheduler가 늦게 깨어나 skip했다. |

## 8. Proposed Architecture

1차 구현은 GUI 프로세스 내부에 scheduler와 tray runtime을 둔다.

```text
ConfluenceSyncApp
  - main GUI
  - job editor
  - schedule editor
  - run controls
  - status view

TrayRuntime
  - show main window
  - pause/resume schedules
  - quit app
  - notification

SchedulerRuntime
  - load enabled scheduled jobs
  - calculate next run time in Asia/Seoul
  - trigger due jobs
  - enforce concurrency policy
  - record scheduler events

RunCoordinator
  - own per-job running locks
  - own global worker limit
  - route manual and scheduled runs through one execution path
  - reject unsafe quit while work is running

SyncEngine
  - validate job
  - run CME adapter
  - write run history/logs
```

Design notes:

- CLI 제거 후에도 `SyncEngine`은 GUI와 분리된 library module로 유지한다.
- Scheduler는 GUI widget 상태를 직접 읽지 않는다. 저장된 Job schedule config를 기준으로 동작한다.
- Scheduler event는 thread-safe 방식으로 GUI에 전달한다.
- Long-running sync는 `RunCoordinator` 또는 executor로 분리한다. GUI의 `busy` flag 하나로 scheduler/manual concurrency를 판단하지 않는다.
- GUI는 runtime 상태를 표시할 뿐, scheduler의 authoritative state 저장소가 되지 않는다.

## 9. Data Model Extension

Job model에는 사용자가 설정한 schedule 원본값만 저장한다. 구현 시 top-level schedule field 여러 개보다 `schedule` object로 묶는 방식을 권장한다.

Recommended shape:

```json
{
  "schedule": {
    "enabled": false,
    "kind": "daily",
    "times": ["09:00"],
    "days_of_week": [1, 2, 3, 4, 5],
    "day_of_month": null,
    "timezone": "Asia/Seoul",
    "misfire_policy": "skip",
    "concurrency_policy": "skip_if_running",
    "paused": false
  }
}
```

| Field | Type | Description |
| --- | --- | --- |
| `schedule.enabled` | bool | 예약 실행 사용 여부 |
| `schedule.kind` | string | `daily`, `weekdays`, `weekly`, `monthly`, `multiple_daily` preset 구분 |
| `schedule.times` | string[] | 한국시간 기준 실행 시각 목록, 각 값은 `HH:mm` |
| `schedule.days_of_week` | number[] | `weekly`에서 사용하는 요일 목록. 월요일=1, 일요일=7 |
| `schedule.day_of_month` | number \| null | `monthly`에서 사용하는 실행 일자. 1-31 |
| `schedule.timezone` | string | 1차 구현에서는 `Asia/Seoul` 고정 |
| `schedule.misfire_policy` | string | 앱이 꺼져 있던 동안 놓친 실행 처리 정책 |
| `schedule.concurrency_policy` | string | 실행 중 중복 trigger 처리 정책 |
| `schedule.paused` | bool | 전역 일시정지와 별개인 Job 단위 일시정지 여부 |

Recommended defaults:

| Field | Default |
| --- | --- |
| `schedule.enabled` | `false` |
| `schedule.kind` | `daily` |
| `schedule.times` | `["09:00"]` |
| `schedule.days_of_week` | `[1, 2, 3, 4, 5]` |
| `schedule.day_of_month` | `null` |
| `schedule.timezone` | `Asia/Seoul` |
| `schedule.misfire_policy` | `skip` |
| `schedule.concurrency_policy` | `skip_if_running` |
| `schedule.paused` | `false` |

The following values are derived scheduler state, not authoritative Job config:

| Field | Source | Rule |
| --- | --- | --- |
| `next_run_at` | Scheduler calculation | GUI 표시용으로 계산한다. 앱 시작 시 반드시 재계산한다. |
| `last_scheduled_run_at` | Scheduler event/run history | Job config가 아니라 실행 기록에서 조회한다. |
| `last_scheduler_event` | Scheduler event log | 최근 scheduler event 표시용이다. |

## 9.1 Runtime State and Event Storage

Scheduler runtime state는 Job config와 분리한다.

| State | Storage | Rule |
| --- | --- | --- |
| Current running jobs | In-memory `RunCoordinator` | manual/scheduled run 모두 같은 lock registry를 사용한다. |
| Global schedule pause | App settings | Tray menu의 일시정지/재개 상태를 저장한다. |
| Scheduler event history | `%APPDATA%\ConfluenceSync\app\scheduler_events.jsonl` | skip/misfire/due/start/complete/fail event를 구조화된 JSONL로 기록한다. |
| Job sync history | `<target-dir>\run_history.json` | 실제 `SyncEngine` 실행 결과만 기록한다. |
| Job log | `<target-dir>\.logs\app.log` | 실제 실행 로그를 기록한다. |

Scheduler event JSONL은 최소 아래 필드를 포함한다.

```json
{
  "event_id": "scheduled-...",
  "job_id": "product-docs",
  "event_type": "scheduled_due",
  "scheduled_at": "2026-05-05T09:00:00+09:00",
  "observed_at": "2026-05-05T09:00:02+09:00",
  "result": "started",
  "run_id": null,
  "message": ""
}
```

## 10. Policy Decisions To Confirm

구현 전에 아래 정책을 확정해야 한다.

| Topic | Recommended Decision |
| --- | --- |
| X button behavior | Hide to tray |
| Real quit location | Tray menu `종료` |
| Startup behavior | User option: Windows login auto-start |
| Misfire policy | Default skip missed runs |
| Same Job concurrency | Default skip if running |
| Multiple Job concurrency | Limit by global worker count, default 1 |
| Timezone | Korea time only in first implementation, store `Asia/Seoul` |
| Notification | Notify on failure, optional on success |
| Schedule pause | Global pause plus per-Job schedule toggle |
| Tray failure | Disable background runtime and use normal close-to-exit behavior |
| End-user CLI | Remove or hide from final user distribution after GUI parity is complete |

## 11. Verification Plan

| ID | Scenario | Expected Result |
| --- | --- | --- |
| BG-V-01 | X 버튼으로 창을 닫는다. | 프로세스가 유지되고 tray icon이 보인다. |
| BG-V-02 | 창을 닫은 상태에서 예약 시간이 도달한다. | Job이 실행되고 run history/log에 기록된다. |
| BG-V-03 | Tray menu에서 `열기`를 선택한다. | 기존 메인 창이 다시 표시된다. |
| BG-V-04 | Tray menu에서 `종료`를 선택한다. | Scheduler가 중지되고 프로세스가 종료된다. |
| BG-V-05 | 같은 Job이 실행 중일 때 예약 시간이 다시 도달한다. | concurrency policy에 따라 중복 실행이 방지된다. |
| BG-V-06 | 앱을 종료했다가 다시 시작한다. | enabled schedule이 복구되고 다음 실행 시간이 다시 계산된다. |
| BG-V-07 | 잘못된 실행 시각을 저장한다. | 저장이 거부되고 사용자가 수정 가능한 오류가 표시된다. |
| BG-V-08 | 예약 실행 중 인증 오류가 발생한다. | 실패가 기록되고 사용자가 확인 가능한 상태/알림이 남는다. |
| BG-V-09 | 실행 중인 Job이 있을 때 tray `종료`를 선택한다. | 완전 종료가 거부되고 실행 완료 후 다시 종료하라는 안내가 표시된다. |
| BG-V-10 | Tray icon 초기화에 실패한다. | background runtime이 비활성화되고 X 버튼은 앱을 종료한다. |
| BG-V-11 | `주중` schedule을 09:00으로 저장한다. | 월-금 09:00 Asia/Seoul 기준 다음 실행 시간이 표시된다. |
| BG-V-12 | GUI 작업 화면을 확인한다. | validate, preview, dry-run 버튼은 없고 run과 schedule 기능만 표시된다. |
| BG-V-13 | Schedule이 켜진 Job을 수동 실행 중 예약 시간이 도달한다. | 같은 Job의 scheduled trigger가 skip되고 scheduler event에 기록된다. |
| BG-V-14 | 앱 자동 시작이 꺼진 상태에서 schedule을 켠다. | 완전 종료 중 예약 실행이 보장되지 않는다는 안내가 표시된다. |
| BG-V-15 | Scheduler event log가 rotation 기준을 초과한다. | 오래된 event가 정책대로 정리되고 최신 event 조회가 유지된다. |

## 12. Migration Notes

- 현재 Job에는 `enabled` 필드가 존재하지만 scheduler 의미가 아니다. 예약 기능 도입 시 `enabled`는 Job 전체 활성 여부, `schedule.enabled`는 예약 실행 활성 여부로 분리한다.
- 기존 Job 파일을 읽을 때 schedule 필드가 없으면 예약 비활성 상태로 취급한다.
- 기존 Job 파일에 `schedule.time`만 있으면 읽는 시점에 `schedule.times: [time]`으로 마이그레이션한다. 새 저장 형식에는 `schedule.time`을 쓰지 않는다.
- CLI 제거 시 기존 자동화/검증 스크립트가 CLI에 의존하는지 정리하고, 최종 release verification은 GUI entrypoint 기준으로 전환한다.
- Current MVP baseline 문서와 verification report는 수동 실행 앱 기준으로 유지한다. 이 문서는 후속 기능의 기준 문서다.
- `next_run_at`은 기존 Job JSON에 영속 설정값으로 추가하지 않는다. 필요한 경우 scheduler state 또는 GUI runtime에서 계산한다.

## 13. Open Questions

| ID | Question |
| --- | --- |
| BG-Q-01 | Windows 로그인 자동 시작 설정을 연결 탭에 둘 것인가, 전역 설정 화면을 새로 만들 것인가? |
| BG-Q-02 | 완료: 1차 preset은 `매일`, `주중`, `매주`, `매월`, `하루 여러 번`까지 포함한다. |
| BG-Q-03 | 예약 실행 성공 알림도 보여줄 것인가, 실패 알림만 보여줄 것인가? |
| BG-Q-04 | scheduler event log를 파일 크기 기준으로 rotation할 것인가, event 개수 기준으로 보관할 것인가? |
| BG-Q-05 | 개발자용 내부 CLI 또는 script entrypoint를 유지할 것인가, GUI smoke만 유지할 것인가? |

## 14. Suggested Implementation Phases

### Phase 0: GUI Parity and Product Boundary

- 최종 사용자 CLI 제거 범위 확정
- GUI logout/log open 기능 추가
- Release verification을 GUI entrypoint 기준으로 전환
- Current MVP PRD와 후속 background runtime PRD의 버전 관계 명시

### Phase 1: Runtime Contract

- X button hide-to-tray
- Tray menu: open, pause/resume, quit
- Manual sync remains unchanged
- No scheduled execution yet

### Phase 2: Schedule Model and UI

- Job schedule fields
- Schedule editor UI
- Preset/time validation
- Next run display

### Phase 3: Scheduler Runtime

- Load enabled schedules on app startup
- Trigger due Job execution
- Record scheduled run results
- Prevent duplicate execution

### Phase 4: Startup and Hardening

- Optional Windows login auto-start
- Misfire handling
- Notifications
- Recovery and verification scripts
