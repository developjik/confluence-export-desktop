use serde::{Deserialize, Serialize};

pub const SCOPES: &[&str] = &["auto", "pages", "pages-with-descendants", "spaces", "orgs"];

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum Scope {
    Auto,
    Pages,
    PagesWithDescendants,
    Spaces,
    Orgs,
}

impl Scope {
    pub fn as_str(&self) -> &'static str {
        match self {
            Scope::Auto => "auto",
            Scope::Pages => "pages",
            Scope::PagesWithDescendants => "pages-with-descendants",
            Scope::Spaces => "spaces",
            Scope::Orgs => "orgs",
        }
    }

    pub fn parse(value: &str) -> Option<Self> {
        SCOPES.iter().find(|s| **s == value).map(|s| match *s {
            "auto" => Scope::Auto,
            "pages" => Scope::Pages,
            "pages-with-descendants" => Scope::PagesWithDescendants,
            "spaces" => Scope::Spaces,
            _ => Scope::Orgs,
        })
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "lowercase")]
pub enum HrefMode {
    Absolute,
    #[default]
    Relative,
    Wiki,
}

impl HrefMode {
    pub fn parse(value: &str) -> Option<Self> {
        match value {
            "absolute" => Some(HrefMode::Absolute),
            "relative" => Some(HrefMode::Relative),
            "wiki" => Some(HrefMode::Wiki),
            _ => None,
        }
    }
}

pub const DEFAULT_PAGE_PATH: &str = "{space_name}/{homepage_title}/{ancestor_titles}/{page_title}.md";
pub const DEFAULT_ATTACHMENT_PATH: &str =
    "{space_name}/attachments/{attachment_file_id}{attachment_extension}";

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(default)]
pub struct ExportOptions {
    /// v1 compatibility alias: `cme_scope`.
    #[serde(alias = "cme_scope")]
    pub scope: String,
    /// v1 compatibility alias: `cme_urls`. Newline or comma separated.
    #[serde(alias = "cme_urls")]
    pub urls: String,
    /// v1 compatibility alias: `cme_config_json`. Accepted but ignored beyond validation.
    #[serde(alias = "cme_config_json")]
    pub config_json: String,
    #[serde(alias = "page_href")]
    pub page_link: String,
    #[serde(alias = "attachment_href")]
    pub attachment_link: String,
    pub attachment_export_all: bool,
    pub page_breadcrumbs: bool,
    pub page_properties_as_front_matter: bool,
    /// Emit standard front matter fields (title/url/space/version/dates).
    pub front_matter_standard: bool,
    pub include_document_title: bool,
    pub skip_unchanged: bool,
    pub cleanup_stale: bool,
    #[serde(alias = "timeout")]
    pub timeout_seconds: u64,
    /// v1 compatibility alias: `max_workers`.
    #[serde(alias = "max_workers")]
    pub max_requests: usize,
    pub verify_ssl: bool,
    pub page_path: String,
    pub attachment_path: String,
    /// v1 compatibility alias: `filename_length`.
    #[serde(alias = "filename_length")]
    pub filename_max_length: usize,
}

impl Default for ExportOptions {
    fn default() -> Self {
        Self {
            scope: "auto".into(),
            urls: String::new(),
            config_json: String::new(),
            page_link: "relative".into(),
            attachment_link: "relative".into(),
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
            page_path: DEFAULT_PAGE_PATH.into(),
            attachment_path: DEFAULT_ATTACHMENT_PATH.into(),
            filename_max_length: 120,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "lowercase")]
pub enum ScheduleKind {
    #[default]
    Daily,
    Weekly,
    Monthly,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(default)]
pub struct Schedule {
    pub enabled: bool,
    pub kind: ScheduleKind,
    /// "HH:MM" entries.
    pub times: Vec<String>,
    /// ISO weekday numbers, 1=Monday .. 7=Sunday.
    pub days_of_week: Vec<u8>,
    pub day_of_month: Option<u8>,
    pub timezone: String,
    pub paused: bool,
}

impl Default for Schedule {
    fn default() -> Self {
        Self {
            enabled: false,
            kind: ScheduleKind::Daily,
            times: vec!["09:00".into()],
            days_of_week: vec![1, 2, 3, 4, 5],
            day_of_month: None,
            timezone: "Asia/Seoul".into(),
            paused: false,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(default)]
pub struct Job {
    pub id: String,
    pub name: String,
    pub confluence_url: String,
    pub target_dir: String,
    pub include_children: bool,
    pub include_attachments: bool,
    pub enabled: bool,
    pub export_options: ExportOptions,
    pub schedule: Schedule,
    pub created_at: String,
    pub updated_at: String,
}

impl Default for Job {
    fn default() -> Self {
        let now = chrono::Utc::now().to_rfc3339();
        Self {
            id: uuid::Uuid::new_v4().to_string(),
            name: String::new(),
            confluence_url: String::new(),
            target_dir: String::new(),
            include_children: true,
            include_attachments: true,
            enabled: true,
            export_options: ExportOptions::default(),
            schedule: Schedule::default(),
            created_at: now.clone(),
            updated_at: now,
        }
    }
}

impl Job {
    /// Resolve `auto` scope the same way v1 did, based on the first URL.
    pub fn resolve_scope(&self) -> AppScopeOrErr {
        let scope = Scope::parse(&self.export_options.scope)
            .unwrap_or(Scope::Auto);
        if scope != Scope::Auto {
            return Ok(scope);
        }
        let first = self.export_urls()?.into_iter().next().unwrap_or_default();
        if first.contains("/spaces/") && !first.contains("/pages/") {
            return Ok(Scope::Spaces);
        }
        if first.contains("/pages/") {
            return Ok(if self.include_children {
                Scope::PagesWithDescendants
            } else {
                Scope::Pages
            });
        }
        Ok(Scope::Orgs)
    }

    pub fn export_urls(&self) -> Result<Vec<String>, crate::error::AppError> {
        let raw = if self.export_options.urls.trim().is_empty() {
            self.confluence_url.clone()
        } else {
            self.export_options.urls.clone()
        };
        let urls: Vec<String> = raw
            .split(|c: char| c.is_whitespace() || c == ',')
            .map(str::trim)
            .filter(|s| !s.is_empty())
            .map(str::to_string)
            .collect();
        if urls.is_empty() {
            return Err(crate::error::AppError::config(
                "URL_REQUIRED",
                "내보낼 Confluence URL을 하나 이상 입력하세요.",
                raw,
            ));
        }
        Ok(urls)
    }
}

type AppScopeOrErr = Result<Scope, crate::error::AppError>;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum RunStatus {
    Running,
    Succeeded,
    Failed,
    Cancelled,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq)]
pub struct RunStats {
    pub pages_total: usize,
    pub pages_exported: usize,
    pub pages_skipped: usize,
    pub pages_failed: usize,
    pub attachments_total: usize,
    pub attachments_exported: usize,
    pub attachments_skipped: usize,
    pub files_removed: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct RunRecord {
    pub id: String,
    pub job_id: String,
    pub job_name: String,
    pub started_at: String,
    pub finished_at: Option<String>,
    pub status: RunStatus,
    pub trigger: String,
    pub scope: String,
    pub urls: Vec<String>,
    pub target_dir: String,
    pub stats: RunStats,
    pub error: Option<String>,
}

impl Default for RunRecord {
    fn default() -> Self {
        Self {
            id: uuid::Uuid::new_v4().to_string(),
            job_id: String::new(),
            job_name: String::new(),
            started_at: chrono::Utc::now().to_rfc3339(),
            finished_at: None,
            status: RunStatus::Running,
            trigger: "manual".into(),
            scope: String::new(),
            urls: Vec::new(),
            target_dir: String::new(),
            stats: RunStats::default(),
            error: None,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(default)]
pub struct AppSettings {
    pub base_url: String,
    pub email: String,
    pub theme: String,
    pub log_level: String,
    pub default_max_requests: usize,
}

impl Default for AppSettings {
    fn default() -> Self {
        Self {
            base_url: String::new(),
            email: String::new(),
            theme: "system".into(),
            log_level: "info".into(),
            default_max_requests: 8,
        }
    }
}
