use std::fs;
use std::path::Path;

use crate::error::{AppError, AppResult};
use crate::models::{AppSettings, Job, RunRecord};
use crate::paths;

fn read_json<T: serde::de::DeserializeOwned>(path: &Path, fallback: T) -> T {
    match fs::read_to_string(path) {
        Ok(text) if !text.trim().is_empty() => match serde_json::from_str(&text) {
            Ok(value) => value,
            Err(err) => {
                tracing::warn!("failed to parse {}: {err}", path.display());
                fallback
            }
        },
        _ => fallback,
    }
}

fn atomic_write(path: &Path, contents: &str) -> AppResult<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .map_err(|err| AppError::new("Storage", "WRITE_FAILED", "설정 파일을 저장하지 못했습니다.", format!("{}: {err}", path.display()), false))?;
    }
    let tmp = path.with_extension("tmp");
    fs::write(&tmp, contents)
        .map_err(|err| AppError::new("Storage", "WRITE_FAILED", "설정 파일을 저장하지 못했습니다.", format!("{}: {err}", tmp.display()), false))?;
    fs::rename(&tmp, path)
        .map_err(|err| AppError::new("Storage", "WRITE_FAILED", "설정 파일을 저장하지 못했습니다.", format!("{}: {err}", path.display()), false))?;
    Ok(())
}

// ---------- settings ----------

pub fn load_settings() -> AppSettings {
    read_json(&paths::settings_path(), AppSettings::default())
}

pub fn save_settings(settings: &AppSettings) -> AppResult<()> {
    let text = serde_json::to_string_pretty(settings).unwrap();
    atomic_write(&paths::settings_path(), &text)
}

// ---------- jobs ----------

pub fn load_jobs() -> Vec<Job> {
    #[derive(serde::Deserialize, Default)]
    struct JobsFile {
        #[serde(default)]
        jobs: Vec<Job>,
    }
    read_json(&paths::jobs_path(), JobsFile::default()).jobs
}

pub fn save_jobs(jobs: &[Job]) -> AppResult<()> {
    #[derive(serde::Serialize)]
    struct JobsFile<'a> {
        jobs: &'a [Job],
    }
    let text = serde_json::to_string_pretty(&JobsFile { jobs }).unwrap();
    atomic_write(&paths::jobs_path(), &text)
}

// ---------- runs ----------

const MAX_RUNS: usize = 400;

pub fn load_runs() -> Vec<RunRecord> {
    let Ok(text) = fs::read_to_string(paths::runs_path()) else {
        return Vec::new();
    };
    let mut runs: Vec<RunRecord> = text
        .lines()
        .filter(|line| !line.trim().is_empty())
        .filter_map(|line| match serde_json::from_str(line) {
            Ok(run) => Some(run),
            Err(err) => {
                tracing::warn!("skipping malformed run record: {err}");
                None
            }
        })
        .collect();
    runs.sort_by(|a, b| b.started_at.cmp(&a.started_at));
    runs
}

pub fn save_runs(runs: &[RunRecord]) -> AppResult<()> {
    let mut sorted: Vec<&RunRecord> = runs.iter().collect();
    sorted.sort_by(|a, b| b.started_at.cmp(&a.started_at));
    let keep: Vec<&RunRecord> = sorted.into_iter().take(MAX_RUNS).collect();
    let mut text = String::new();
    for run in keep {
        text.push_str(&serde_json::to_string(run).unwrap());
        text.push('\n');
    }
    atomic_write(&paths::runs_path(), &text)
}

pub fn upsert_run(run: &RunRecord) -> AppResult<()> {
    let mut runs = load_runs();
    match runs.iter_mut().find(|r| r.id == run.id) {
        Some(slot) => *slot = run.clone(),
        None => runs.push(run.clone()),
    }
    save_runs(&runs)
}

// ---------- scheduler state ----------

pub fn load_scheduler_state() -> std::collections::HashMap<String, String> {
    read_json(&paths::scheduler_state_path(), std::collections::HashMap::new())
}

pub fn save_scheduler_state(state: &std::collections::HashMap<String, String>) -> AppResult<()> {
    let text = serde_json::to_string_pretty(state).unwrap();
    atomic_write(&paths::scheduler_state_path(), &text)
}

// ---------- target-dir run history ----------

pub fn append_target_run_history(target_dir: &std::path::Path, run: &RunRecord) -> AppResult<()> {
    let path = paths::target_run_history_path(target_dir);
    let mut runs: Vec<RunRecord> = match std::fs::read_to_string(&path) {
        Ok(text) => serde_json::from_str(&text).unwrap_or_default(),
        Err(_) => Vec::new(),
    };
    runs.push(run.clone());
    if runs.len() > 100 {
        let start = runs.len() - 100;
        runs.drain(..start);
    }
    let text = serde_json::to_string_pretty(&runs).unwrap();
    atomic_write(&path, &text)
}

// ---------- v1 migration ----------

pub fn load_v1_settings() -> Option<serde_json::Value> {
    let path = paths::v1_app_data_dir().join("settings.json");
    let text = fs::read_to_string(path).ok()?;
    serde_json::from_str(&text).ok()
}

pub fn load_v1_jobs() -> Option<serde_json::Value> {
    let path = paths::v1_app_data_dir().join("jobs.json");
    let text = fs::read_to_string(path).ok()?;
    serde_json::from_str(&text).ok()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::models::ExportOptions;

    #[test]
    fn job_json_roundtrip_with_v1_aliases() {
        let v1_style = r##"{
            "id": "j1",
            "name": "Docs",
            "confluence_url": "https://x.atlassian.net/wiki/spaces/PROD",
            "target_dir": "/tmp/out",
            "include_children": true,
            "enabled": true,
            "export_options": {
                "cme_scope": "spaces",
                "cme_urls": "https://x.atlassian.net/wiki/spaces/PROD",
                "page_href": "wiki",
                "attachment_href": "relative",
                "timeout": 45,
                "max_workers": 12
            },
            "schedule": {"enabled": true, "kind": "weekly", "times": ["09:30","18:00"]}
        }"##;
        let job: Job = serde_json::from_str(v1_style).expect("v1 job should deserialize");
        assert_eq!(job.export_options.scope, "spaces");
        assert_eq!(job.export_options.page_link, "wiki");
        assert_eq!(job.export_options.timeout_seconds, 45);
        assert_eq!(job.export_options.max_requests, 12);
        assert_eq!(job.schedule.times, vec!["09:30".to_string(), "18:00".to_string()]);

        let round: Job = serde_json::from_str(&serde_json::to_string(&job).unwrap()).unwrap();
        assert_eq!(round, job);
        assert_eq!(ExportOptions::default().attachment_export_all, true);
    }

    #[test]
    fn settings_roundtrip() {
        let mut s = AppSettings::default();
        s.base_url = "https://team.atlassian.net".into();
        s.email = "a@b.c".into();
        let text = serde_json::to_string(&s).unwrap();
        let back: AppSettings = serde_json::from_str(&text).unwrap();
        assert_eq!(back, s);
    }
}
