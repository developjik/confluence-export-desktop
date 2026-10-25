//! Tauri IPC commands: a thin layer over the core modules.

use std::collections::HashMap;
use std::sync::Mutex;

use serde::Serialize;
use tauri::ipc::Channel;
use tauri::{AppHandle, Emitter, Manager};

use crate::credentials;
use crate::error::{AppError, AppResult, CancelFlag};
use crate::exporter::{self, ProgressEvent};
use crate::models::{AppSettings, Job, RunRecord, RunStatus};
use crate::storage;
use crate::{confluence, scheduler as sched};

pub struct AppState {
    /// job_id → active run
    pub running: Mutex<HashMap<String, RunningJob>>,
}

#[derive(Debug, Clone)]
pub struct RunningJob {
    pub run_id: String,
    pub cancel: CancelFlag,
}

impl AppState {
    pub fn new() -> Self {
        Self { running: Mutex::new(HashMap::new()) }
    }
}

impl Default for AppState {
    fn default() -> Self {
        Self::new()
    }
}

#[derive(Serialize)]
pub struct StateSnapshot {
    pub settings: AppSettings,
    pub has_token: bool,
    pub jobs: Vec<Job>,
    pub runs: Vec<RunRecord>,
    pub app_version: String,
}

#[tauri::command]
pub fn get_state() -> StateSnapshot {
    let settings = storage::load_settings();
    let has_token = credentials::read_token(&settings.base_url, &settings.email).is_some();
    StateSnapshot {
        has_token,
        settings,
        jobs: storage::load_jobs(),
        runs: storage::load_runs(),
        app_version: env!("CARGO_PKG_VERSION").to_string(),
    }
}

#[derive(Serialize)]
pub struct ConnectionTestResult {
    pub display_name: String,
    pub email: Option<String>,
}

#[tauri::command]
pub async fn test_connection(
    base_url: String,
    email: String,
    token: String,
) -> AppResult<ConnectionTestResult> {
    if base_url.trim().is_empty() || email.trim().is_empty() || token.trim().is_empty() {
        return Err(AppError::auth("AUTH_REQUIRED", "Base URL, 이메일, API 토큰을 모두 입력하세요.", ""));
    }
    let client = confluence::client::ConfluenceClient::new(
        &base_url,
        &email,
        &token,
        confluence::client::ClientConfig::default(),
    )?;
    let user = client.current_user().await?;
    Ok(ConnectionTestResult { display_name: user.display_name, email: user.email })
}

#[tauri::command]
pub async fn save_connection(base_url: String, email: String, token: String) -> AppResult<()> {
    let normalized = confluence::urls::normalize_base_url(&base_url)?;
    if email.trim().is_empty() {
        return Err(AppError::auth("EMAIL_REQUIRED", "이메일을 입력하세요.", ""));
    }
    if token.trim().is_empty() {
        return Err(AppError::auth("TOKEN_REQUIRED", "API 토큰을 입력하세요.", ""));
    }
    credentials::save_token(&normalized, &email, &token)?;
    let mut settings = storage::load_settings();
    settings.base_url = normalized;
    settings.email = email.trim().to_string();
    storage::save_settings(&settings)?;
    Ok(())
}

#[tauri::command]
pub fn clear_token() -> AppResult<()> {
    let settings = storage::load_settings();
    if settings.base_url.is_empty() || settings.email.is_empty() {
        return Ok(());
    }
    credentials::delete_token(&settings.base_url, &settings.email)
}

#[tauri::command]
pub fn save_job(job: Job) -> AppResult<Job> {
    if job.name.trim().is_empty() {
        return Err(AppError::config("NAME_REQUIRED", "작업 이름을 입력하세요.", ""));
    }
    if job.target_dir.trim().is_empty() {
        return Err(AppError::config("TARGET_DIR_REQUIRED", "대상 폴더를 지정하세요.", ""));
    }
    let mut job = job;
    job.name = job.name.trim().to_string();
    job.target_dir = job.target_dir.trim().to_string();
    if !job.export_options.config_json.trim().is_empty() {
        serde_json::from_str::<serde_json::Value>(job.export_options.config_json.trim()).map_err(
            |err| AppError::config("CONFIG_JSON_INVALID", "고급 JSON 형식을 확인하세요.", format!("{err}")),
        )?;
    }
    let _ = job.resolve_scope()?;
    let _ = job.export_urls()?;

    let mut jobs = storage::load_jobs();
    let now = chrono::Utc::now().to_rfc3339();
    match jobs.iter_mut().find(|j| j.id == job.id) {
        Some(existing) => {
            job.created_at = existing.created_at.clone();
            *existing = job.clone();
        }
        None => {
            job.created_at = now.clone();
            jobs.push(job.clone());
        }
    }
    job.updated_at = now;
    // persist with updated timestamps
    if let Some(existing) = jobs.iter_mut().find(|j| j.id == job.id) {
        *existing = job.clone();
    }
    storage::save_jobs(&jobs)?;
    Ok(job)
}

#[tauri::command]
pub fn delete_job(job_id: String) -> AppResult<()> {
    let mut jobs = storage::load_jobs();
    let before = jobs.len();
    jobs.retain(|j| j.id != job_id);
    if jobs.len() == before {
        return Err(AppError::config("JOB_NOT_FOUND", "작업을 찾을 수 없습니다.", job_id));
    }
    storage::save_jobs(&jobs)?;
    Ok(())
}

#[tauri::command]
pub fn duplicate_job(job_id: String) -> AppResult<Job> {
    let mut jobs = storage::load_jobs();
    let source = jobs
        .iter()
        .find(|j| j.id == job_id)
        .cloned()
        .ok_or_else(|| AppError::config("JOB_NOT_FOUND", "작업을 찾을 수 없습니다.", job_id))?;
    let mut copy = source;
    copy.id = uuid::Uuid::new_v4().to_string();
    copy.name = format!("{} (복제본)", copy.name);
    copy.schedule.enabled = false;
    copy.created_at = chrono::Utc::now().to_rfc3339();
    copy.updated_at = copy.created_at.clone();
    jobs.push(copy.clone());
    storage::save_jobs(&jobs)?;
    Ok(copy)
}

#[tauri::command]
pub fn save_settings(settings: AppSettings) -> AppResult<()> {
    let mut current = storage::load_settings();
    // connection identity only changes through save_connection
    current.theme = settings.theme;
    current.log_level = settings.log_level;
    current.default_max_requests = settings.default_max_requests.max(1);
    storage::save_settings(&current)
}

#[tauri::command]
pub fn get_runs(job_id: Option<String>) -> Vec<RunRecord> {
    let mut runs = storage::load_runs();
    if let Some(job_id) = job_id {
        runs.retain(|r| r.job_id == job_id);
    }
    runs
}

#[tauri::command]
pub fn get_next_runs() -> HashMap<String, Option<String>> {
    let mut out = HashMap::new();
    let now = chrono::Utc::now();
    for job in storage::load_jobs() {
        let next = if job.enabled && job.schedule.enabled && !job.schedule.paused {
            sched::next_occurrence(&job.schedule, now).map(|dt| dt.to_rfc3339())
        } else {
            None
        };
        out.insert(job.id, next);
    }
    out
}

#[tauri::command]
pub fn is_job_running(state: tauri::State<'_, AppState>, job_id: String) -> bool {
    state.running.lock().unwrap().contains_key(&job_id)
}

#[tauri::command]
pub fn cancel_run(state: tauri::State<'_, AppState>, job_id: String) -> bool {
    let running = state.running.lock().unwrap();
    match running.get(&job_id) {
        Some(job) => {
            job.cancel.cancel();
            true
        }
        None => false,
    }
}

#[tauri::command]
pub async fn run_job(
    app: AppHandle,
    state: tauri::State<'_, AppState>,
    job_id: String,
    on_progress: Channel<ProgressEvent>,
) -> Result<RunRecord, AppError> {
    let job = load_job(&job_id)?;
    execute_run(app, state, job, "manual", Some(on_progress)).await
}

#[tauri::command]
pub async fn open_folder(path: String) -> AppResult<()> {
    tauri_plugin_opener::open_path(&path, None::<&str>)
        .map_err(|err| AppError::config("OPEN_FAILED", "폴더를 열 수 없습니다.", format!("{err}")))
}

#[derive(Serialize)]
pub struct V1ImportSummary {
    pub settings_imported: bool,
    pub jobs_imported: usize,
    pub jobs_skipped: usize,
    pub token_imported: bool,
}

#[tauri::command]
pub async fn import_v1() -> AppResult<V1ImportSummary> {
    let mut summary = V1ImportSummary { settings_imported: false, jobs_imported: 0, jobs_skipped: 0, token_imported: false };

    let mut settings = storage::load_settings();
    if let Some(v1) = storage::load_v1_settings() {
        let base_url = v1.get("base_url").and_then(|v| v.as_str()).unwrap_or_default().to_string();
        let email = v1.get("email").and_then(|v| v.as_str()).unwrap_or_default().to_string();
        if !base_url.is_empty() && !email.is_empty() {
            let normalized = confluence::urls::normalize_base_url(&base_url)?;
            if let Some(token) = credentials::read_v1_native_token(&normalized, &email) {
                credentials::save_token(&normalized, &email, &token)?;
                summary.token_imported = true;
            }
            settings.base_url = normalized;
            settings.email = email;
            storage::save_settings(&settings)?;
            summary.settings_imported = true;
        }
    }

    if let Some(v1_jobs) = storage::load_v1_jobs() {
        let raw_list = match v1_jobs.get("jobs").and_then(|v| v.as_array()) {
            Some(list) => list.clone(),
            None => Vec::new(),
        };
        let mut jobs = storage::load_jobs();
        let existing_ids: Vec<String> = jobs.iter().map(|j| j.id.clone()).collect();
        for raw in raw_list {
            match serde_json::from_value::<Job>(raw) {
                Ok(mut job) => {
                    job.id = uuid::Uuid::new_v4().to_string();
                    if existing_ids.iter().any(|name| name == &job.name) {
                        job.name = format!("{} (v1)", job.name);
                    }
                    jobs.push(job);
                    summary.jobs_imported += 1;
                }
                Err(_) => summary.jobs_skipped += 1,
            }
        }
        if summary.jobs_imported > 0 {
            storage::save_jobs(&jobs)?;
        }
    }
    Ok(summary)
}

// ---------- shared run execution ----------

fn load_job(job_id: &str) -> AppResult<Job> {
    storage::load_jobs()
        .into_iter()
        .find(|j| j.id == job_id)
        .ok_or_else(|| AppError::config("JOB_NOT_FOUND", "작업을 찾을 수 없습니다.", job_id))
}

pub async fn execute_run(
    app: AppHandle,
    state: tauri::State<'_, AppState>,
    job: Job,
    trigger: &str,
    on_progress: Option<Channel<ProgressEvent>>,
) -> Result<RunRecord, AppError> {
    {
        let running = state.running.lock().unwrap();
        if running.contains_key(&job.id) {
            return Err(AppError::new("Run", "ALREADY_RUNNING", "이 작업은 이미 실행 중입니다.", job.id, false));
        }
    }

    let settings = storage::load_settings();
    if settings.base_url.is_empty() || settings.email.is_empty() {
        return Err(AppError::auth("AUTH_SETTINGS_REQUIRED", "연결 설정을 먼저 저장하세요.", ""));
    }
    let Some(token) = credentials::read_token(&settings.base_url, &settings.email) else {
        return Err(AppError::auth("TOKEN_NOT_FOUND", "저장된 API 토큰이 없습니다. 연결 화면에서 저장하세요.", ""));
    };

    let scope = job.resolve_scope()?;
    let urls = job.export_urls()?;
    let mut run = RunRecord {
        job_id: job.id.clone(),
        job_name: job.name.clone(),
        status: RunStatus::Running,
        trigger: trigger.to_string(),
        scope: scope.as_str().to_string(),
        urls: urls.clone(),
        target_dir: job.target_dir.clone(),
        ..Default::default()
    };
    storage::upsert_run(&run)?;
    let _ = app.emit("runs://changed", ());

    let cancel = CancelFlag::new();
    state
        .running
        .lock()
        .unwrap()
        .insert(job.id.clone(), RunningJob { run_id: run.id.clone(), cancel: cancel.clone() });

    let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<ProgressEvent>();
    let job_for_task = job.clone();
    let base_url = settings.base_url.clone();
    let email = settings.email.clone();
    let mut handle = tokio::spawn(async move {
        exporter::run_export(&job_for_task, &base_url, &email, &token, &tx, &cancel).await
    });

    let mut cancellation_requested = false;
    let outcome = loop {
        tokio::select! {
            maybe_event = rx.recv() => {
                if let Some(event) = maybe_event {
                    if let Some(channel) = &on_progress {
                        let _ = channel.send(event.clone());
                    }
                    if matches!(event, ProgressEvent::PageDone { .. }) {
                        let _ = app.emit("runs://progress", &event);
                    }
                }
            }
            result = &mut handle => {
                break match result {
                    Ok(Ok(outcome)) => Some(Ok(outcome)),
                    Ok(Err(err)) if err.code == "CANCELLED" => {
                        cancellation_requested = true;
                        None
                    }
                    Ok(Err(err)) => Some(Err(err)),
                    Err(join_err) => Some(Err(AppError::new("Internal", "TASK_FAILED", "실행 작업이 비정상 종료되었습니다.", format!("{join_err}"), false))),
                };
            }
        }
    };

    // drain any trailing progress events
    while let Ok(event) = rx.try_recv() {
        if let Some(channel) = &on_progress {
            let _ = channel.send(event);
        }
    }

    match outcome {
        Some(Ok(export_outcome)) => {
            run.status = RunStatus::Succeeded;
            run.stats = export_outcome.stats;
        }
        Some(Err(err)) => {
            run.status = RunStatus::Failed;
            run.error = Some(err.message.clone());
            tracing::error!("run {} failed: {} ({})", run.id, err.message, err.detail);
        }
        None => {
            run.status = RunStatus::Cancelled;
        }
    }
    if cancellation_requested {
        run.status = RunStatus::Cancelled;
    }
    run.finished_at = Some(chrono::Utc::now().to_rfc3339());
    storage::upsert_run(&run)?;
    storage::append_target_run_history(std::path::Path::new(&job.target_dir), &run).ok();
    state.running.lock().unwrap().remove(&job.id);
    let _ = app.emit("runs://changed", ());
    Ok(run)
}

/// Fire a scheduled run from the background scheduler loop.
pub fn spawn_scheduled_run(app: AppHandle, job: Job) {
    let job_id = job.id.clone();
    tauri::async_runtime::spawn(async move {
        let state = app.state::<AppState>();
        // A job already running manually is skipped (misfire policy: skip).
        {
            let running = state.running.lock().unwrap();
            if running.contains_key(&job_id) {
                tracing::info!("scheduled run skipped, job {job_id} already running");
                return;
            }
        }
        if let Err(err) = execute_run(app.clone(), state, job, "scheduled", None).await {
            tracing::warn!("scheduled run failed for {job_id}: {}", err.message);
        }
    });
}
