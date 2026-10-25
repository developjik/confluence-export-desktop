use std::path::PathBuf;

/// v2 app data root: `{config_dir}/ConfluenceExportDesktop`.
/// v1 used `{config_dir}/ConfluenceExportDesktop/app` — kept for migration reads.
pub fn app_data_dir() -> PathBuf {
    let base = dirs::config_dir().unwrap_or_else(|| PathBuf::from("."));
    base.join("ConfluenceExportDesktop")
}

pub fn v1_app_data_dir() -> PathBuf {
    app_data_dir().join("app")
}

pub fn settings_path() -> PathBuf {
    app_data_dir().join("settings.json")
}

pub fn jobs_path() -> PathBuf {
    app_data_dir().join("jobs.json")
}

pub fn runs_path() -> PathBuf {
    app_data_dir().join("runs.jsonl")
}

pub fn scheduler_state_path() -> PathBuf {
    app_data_dir().join("scheduler_state.json")
}

pub fn logs_dir() -> PathBuf {
    app_data_dir().join("logs")
}

pub fn target_run_history_path(target_dir: &std::path::Path) -> PathBuf {
    target_dir.join("run_history.json")
}

pub fn target_lockfile_path(target_dir: &std::path::Path) -> PathBuf {
    target_dir.join("confluence-export.lock.json")
}
