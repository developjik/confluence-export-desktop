export type Scope = "auto" | "pages" | "pages-with-descendants" | "spaces" | "orgs";
export type HrefMode = "absolute" | "relative" | "wiki";
export type ScheduleKind = "daily" | "weekly" | "monthly";
export type RunStatus = "running" | "succeeded" | "failed" | "cancelled";

export interface ExportOptions {
  scope: Scope;
  urls: string;
  config_json: string;
  page_link: HrefMode;
  attachment_link: HrefMode;
  attachment_export_all: boolean;
  page_breadcrumbs: boolean;
  page_properties_as_front_matter: boolean;
  front_matter_standard: boolean;
  include_document_title: boolean;
  skip_unchanged: boolean;
  cleanup_stale: boolean;
  timeout_seconds: number;
  max_requests: number;
  verify_ssl: boolean;
  page_path: string;
  attachment_path: string;
  filename_max_length: number;
}

export interface Schedule {
  enabled: boolean;
  kind: ScheduleKind;
  times: string[];
  days_of_week: number[];
  day_of_month: number | null;
  timezone: string;
  paused: boolean;
}

export interface Job {
  id: string;
  name: string;
  confluence_url: string;
  target_dir: string;
  include_children: boolean;
  include_attachments: boolean;
  enabled: boolean;
  export_options: ExportOptions;
  schedule: Schedule;
  created_at: string;
  updated_at: string;
}

export interface RunStats {
  pages_total: number;
  pages_exported: number;
  pages_skipped: number;
  pages_failed: number;
  attachments_total: number;
  attachments_exported: number;
  attachments_skipped: number;
  files_removed: number;
}

export interface RunRecord {
  id: string;
  job_id: string;
  job_name: string;
  started_at: string;
  finished_at: string | null;
  status: RunStatus;
  trigger: string;
  scope: string;
  urls: string[];
  target_dir: string;
  stats: RunStats;
  error: string | null;
}

export interface AppSettings {
  base_url: string;
  email: string;
  theme: string;
  log_level: string;
  default_max_requests: number;
}

export interface StateSnapshot {
  settings: AppSettings;
  has_token: boolean;
  jobs: Job[];
  runs: RunRecord[];
  app_version: string;
}

export type ProgressEvent =
  | { type: "phase"; phase: string }
  | { type: "message"; text: string }
  | { type: "total"; total: number }
  | { type: "pageStart"; id: string; title: string }
  | { type: "pageDone"; id: string; title: string; outcome: string; path: string | null }
  | { type: "stats"; stats: RunStats };

export interface AppError {
  category: string;
  code: string;
  message: string;
  detail: string;
  retryable: boolean;
}

export interface V1ImportSummary {
  settings_imported: boolean;
  jobs_imported: number;
  jobs_skipped: number;
  token_imported: boolean;
}

export const DEFAULT_EXPORT_OPTIONS: ExportOptions = {
  scope: "auto",
  urls: "",
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
};

export const DEFAULT_SCHEDULE: Schedule = {
  enabled: false,
  kind: "daily",
  times: ["09:00"],
  days_of_week: [1, 2, 3, 4, 5],
  day_of_month: null,
  timezone: "Asia/Seoul",
  paused: false,
};

export function newJob(baseUrl = ""): Job {
  const now = new Date().toISOString();
  return {
    id: "",
    name: "",
    confluence_url: baseUrl,
    target_dir: "",
    include_children: true,
    include_attachments: true,
    enabled: true,
    export_options: { ...DEFAULT_EXPORT_OPTIONS },
    schedule: { ...DEFAULT_SCHEDULE, times: ["09:00"], days_of_week: [1, 2, 3, 4, 5] },
    created_at: now,
    updated_at: now,
  };
}

export const SCOPE_LABELS: Record<Scope, string> = {
  auto: "자동",
  pages: "단일 페이지",
  "pages-with-descendants": "하위 페이지 포함",
  spaces: "스페이스 전체",
  orgs: "사이트 전체",
};

export const HREF_MODE_LABELS: Record<HrefMode, string> = {
  absolute: "내보내기 루트 기준",
  relative: "파일 상대 경로",
  wiki: "Confluence URL",
};

export const WEEKDAY_LABELS = ["월", "화", "수", "목", "금", "토", "일"];
