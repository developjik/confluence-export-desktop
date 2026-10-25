import type {
  AppError,
  AppSettings,
  Job,
  ProgressEvent,
  RunRecord,
  StateSnapshot,
  V1ImportSummary,
} from "./types";

export interface ConnectionTestResultT {
  display_name: string;
  email: string | null;
}

export const isTauri = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

export async function invoke<T>(command: string, args?: Record<string, unknown>): Promise<T> {
  if (!isTauri) {
    return mockInvoke<T>(command, args);
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<T>(command, args);
}

export function toAppError(err: unknown): AppError {
  if (typeof err === "object" && err !== null && "code" in err && "message" in err) {
    return err as AppError;
  }
  const detail = err instanceof Error ? err.message : String(err);
  return { category: "Ui", code: "UNKNOWN", message: "요청이 실패했습니다.", detail, retryable: false };
}

// ---------- typed wrappers ----------

export const api = {
  getState: () => invoke<StateSnapshot>("get_state"),
  testConnection: (baseUrl: string, email: string, token: string) =>
    invoke<ConnectionTestResultT>("test_connection", { baseUrl, email, token }),
  saveConnection: (baseUrl: string, email: string, token: string) =>
    invoke<void>("save_connection", { baseUrl, email, token }),
  clearToken: () => invoke<void>("clear_token"),
  saveJob: (job: Job) => invoke<Job>("save_job", { job }),
  deleteJob: (jobId: string) => invoke<void>("delete_job", { jobId }),
  duplicateJob: (jobId: string) => invoke<Job>("duplicate_job", { jobId }),
  saveSettings: (settings: AppSettings) => invoke<void>("save_settings", { settings }),
  getRuns: (jobId?: string) => invoke<RunRecord[]>("get_runs", { jobId: jobId ?? null }),
  getNextRuns: () => invoke<Record<string, string | null>>("get_next_runs"),
  isJobRunning: (jobId: string) => invoke<boolean>("is_job_running", { jobId }),
  cancelRun: (jobId: string) => invoke<boolean>("cancel_run", { jobId }),
  openFolder: (path: string) => invoke<void>("open_folder", { path }),
  importV1: () => invoke<V1ImportSummary>("import_v1"),
};

export interface ConnectionTestResultT {
  display_name: string;
  email: string | null;
}

// Browser mock backend so the UI can be developed/verified without Tauri.
const mockJobs: Job[] = [
  {
    id: "demo-1",
    name: "제품 문서 스페이스",
    confluence_url: "https://team.atlassian.net/wiki/spaces/PROD",
    target_dir: "/Users/user/Documents/prod-docs",
    include_children: true,
    include_attachments: true,
    enabled: true,
    export_options: {
      scope: "auto",
      urls: "https://team.atlassian.net/wiki/spaces/PROD",
      config_json: "",
      page_link: "relative",
      attachment_link: "relative",
      attachment_export_all: true,
      page_breadcrumbs: true,
      page_properties_as_front_matter: true,
      front_matter_standard: true,
      include_document_title: false,
      skip_unchanged: true,
      cleanup_stale: true,
      timeout_seconds: 30,
      max_requests: 8,
      verify_ssl: true,
      page_path: "{space_name}/{homepage_title}/{ancestor_titles}/{page_title}.md",
      attachment_path: "{space_name}/attachments/{attachment_file_id}{attachment_extension}",
      filename_max_length: 120,
    },
    schedule: {
      enabled: true,
      kind: "daily",
      times: ["09:00"],
      days_of_week: [1, 2, 3, 4, 5],
      day_of_month: null,
      timezone: "Asia/Seoul",
      paused: false,
    },
    created_at: "2026-10-01T02:00:00Z",
    updated_at: "2026-10-20T02:00:00Z",
  },
];

const mockState = {
  settings: {
    base_url: "https://team.atlassian.net",
    email: "user@team.io",
    theme: "system",
    log_level: "info",
    default_max_requests: 8,
  },
  hasToken: true,
  runs: [
    {
      id: "run-1",
      job_id: "demo-1",
      job_name: "제품 문서 스페이스",
      started_at: new Date(Date.now() - 3600_000 * 5).toISOString(),
      finished_at: new Date(Date.now() - 3600_000 * 5 + 42_000).toISOString(),
      status: "succeeded",
      trigger: "scheduled",
      scope: "spaces",
      urls: ["https://team.atlassian.net/wiki/spaces/PROD"],
      target_dir: "/Users/user/Documents/prod-docs",
      stats: {
        pages_total: 48,
        pages_exported: 12,
        pages_skipped: 36,
        pages_failed: 0,
        attachments_total: 30,
        attachments_exported: 4,
        attachments_skipped: 26,
        files_removed: 1,
      },
      error: null,
    },
    {
      id: "run-2",
      job_id: "demo-1",
      job_name: "제품 문서 스페이스",
      started_at: new Date(Date.now() - 3600_000 * 29).toISOString(),
      finished_at: new Date(Date.now() - 3600_000 * 29 + 18_000).toISOString(),
      status: "succeeded",
      trigger: "manual",
      scope: "spaces",
      urls: ["https://team.atlassian.net/wiki/spaces/PROD"],
      target_dir: "/Users/user/Documents/prod-docs",
      stats: {
        pages_total: 48,
        pages_exported: 48,
        pages_skipped: 0,
        pages_failed: 0,
        attachments_total: 30,
        attachments_exported: 30,
        attachments_skipped: 0,
        files_removed: 0,
      },
      error: null,
    },
  ] as RunRecord[],
  appVersion: "2.0.0 (browser-mock)",
};

export type MockRunListener = (event: ProgressEvent) => void;
let mockRunListener: MockRunListener | null = null;
let mockRunActive = false;

export function setMockRunListener(listener: MockRunListener | null) {
  mockRunListener = listener;
}

async function mockInvoke<T>(command: string, args?: Record<string, unknown>): Promise<T> {
  await delay(120);
  switch (command) {
    case "get_state":
      return {
        settings: mockState.settings,
        has_token: mockState.hasToken,
        jobs: mockJobs,
        runs: mockState.runs,
        app_version: mockState.appVersion,
      } as T;
    case "test_connection":
      return { display_name: "홍길동 (목업)", email: String(args?.email ?? "") } as T;
    case "save_connection":
      mockState.settings.base_url = String(args?.baseUrl ?? "");
      mockState.settings.email = String(args?.email ?? "");
      mockState.hasToken = true;
      return undefined as T;
    case "clear_token":
      mockState.hasToken = false;
      return undefined as T;
    case "save_job": {
      const job = args!.job as Job;
      if (!job.id) {
        job.id = `mock-${Date.now()}`;
        mockJobs.push(job);
      } else {
        const idx = mockJobs.findIndex((j) => j.id === job.id);
        if (idx >= 0) mockJobs[idx] = job;
      }
      return job as T;
    }
    case "delete_job": {
      const idx = mockJobs.findIndex((j) => j.id === args!.jobId);
      if (idx >= 0) mockJobs.splice(idx, 1);
      return undefined as T;
    }
    case "duplicate_job": {
      const source = mockJobs.find((j) => j.id === args!.jobId);
      const copy = { ...source!, id: `mock-${Date.now()}`, name: `${source!.name} (복제본)` };
      mockJobs.push(copy);
      return copy as T;
    }
    case "save_settings":
      Object.assign(mockState.settings, args!.settings, {
        base_url: mockState.settings.base_url,
        email: mockState.settings.email,
      });
      return undefined as T;
    case "get_runs":
      return mockState.runs.filter((r) => !args?.jobId || r.job_id === args.jobId) as T;
    case "get_next_runs": {
      const next = new Date(Date.now() + 3600_000 * 6).toISOString();
      return Object.fromEntries(mockJobs.map((j) => [j.id, j.schedule.enabled ? next : null])) as T;
    }
    case "is_job_running":
      return mockRunActive as T;
    case "cancel_run":
      mockRunActive = false;
      return true as T;
    case "open_folder":
      console.info("[mock] open folder", args?.path);
      return undefined as T;
    case "import_v1":
      return { settings_imported: false, jobs_imported: 0, jobs_skipped: 0, token_imported: false } as T;
    case "run_job": {
      mockRunActive = true;
      const job = mockJobs.find((j) => j.id === args!.jobId) ?? mockJobs[0];
      emitMockProgress();
      await delay(9000);
      mockRunActive = false;
      const run: RunRecord = {
        id: `mock-run-${Date.now()}`,
        job_id: job.id,
        job_name: job.name,
        started_at: new Date(Date.now() - 9000).toISOString(),
        finished_at: new Date().toISOString(),
        status: "succeeded",
        trigger: "manual",
        scope: job.export_options.scope,
        urls: [job.confluence_url],
        target_dir: job.target_dir,
        stats: {
          pages_total: 12,
          pages_exported: 9,
          pages_skipped: 3,
          pages_failed: 0,
          attachments_total: 6,
          attachments_exported: 2,
          attachments_skipped: 4,
          files_removed: 0,
        },
        error: null,
      };
      mockState.runs.unshift(run);
      return run as T;
    }
    default:
      throw new Error(`mock: unknown command ${command}`);
  }
}

function emitMockProgress() {
  const listener = mockRunListener;
  if (!listener) return;
  const titles = ["시작 가이드", "설정 방법", "FAQ", "릴리스 노트", "아키텍처 개요"];
  let index = 0;
  const phases = ["discover", "attachments", "convert", "cleanup", "done"];
  let phaseIndex = 0;
  const step = () => {
    if (!mockRunActive || !mockRunListener) return;
    if (phaseIndex < 3) {
      listener({ type: "phase", phase: phases[phaseIndex] });
      phaseIndex += 1;
    }
    if (phaseIndex === 3 && index < titles.length) {
      listener({ type: "total", total: titles.length });
      listener({ type: "pageStart", id: String(index), title: titles[index] });
      listener({
        type: "pageDone",
        id: String(index),
        title: titles[index],
        outcome: index === 2 ? "skipped" : "exported",
        path: `Product/${titles[index]}.md`,
      });
      listener({
        type: "stats",
        stats: {
          pages_total: titles.length,
          pages_exported: index + 1,
          pages_skipped: 0,
          pages_failed: 0,
          attachments_total: 6,
          attachments_exported: index,
          attachments_skipped: 6 - index,
          files_removed: 0,
        },
      });
      index += 1;
    } else if (phaseIndex === 3 && index >= titles.length) {
      listener({ type: "phase", phase: "cleanup" });
      phaseIndex += 1;
    }
    setTimeout(step, 450);
  };
  step();
}

function delay(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
