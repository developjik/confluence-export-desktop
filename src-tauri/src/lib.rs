pub mod commands;
pub mod confluence;
pub mod converter;
pub mod credentials;
pub mod error;
pub mod exporter;
pub mod models;
pub mod paths;
pub mod scheduler;
pub mod storage;

use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{Emitter, Manager, WindowEvent};

use crate::commands::AppState;

fn init_logging() {
    use tracing_subscriber::EnvFilter;
    let settings = storage::load_settings();
    let level = match settings.log_level.to_lowercase().as_str() {
        "trace" => "trace",
        "debug" => "debug",
        "warn" | "warning" => "warn",
        "error" => "error",
        _ => "info",
    };
    let log_dir = paths::logs_dir();
    let _ = std::fs::create_dir_all(&log_dir);
    let appender = tracing_appender::rolling::daily(&log_dir, "app.log");
    tracing_subscriber::fmt()
        .with_env_filter(EnvFilter::new(format!("{level},reqwest=warn,rustls=warn")))
        .with_writer(appender)
        .with_ansi(false)
        .init();
}

fn show_main_window(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

fn run_scheduler_loop(app: tauri::AppHandle) {
    tauri::async_runtime::spawn(async move {
        let mut interval = tokio::time::interval(std::time::Duration::from_secs(20));
        interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
        loop {
            interval.tick().await;
            let now = chrono::Utc::now();
            let mut fired_any = false;
            let mut state = storage::load_scheduler_state();
            for job in storage::load_jobs() {
                if !job.enabled || !job.schedule.enabled || job.schedule.paused {
                    continue;
                }
                let last_fired = state
                    .get(&job.id)
                    .and_then(|value| chrono::DateTime::parse_from_rfc3339(value).ok())
                    .map(|dt| dt.with_timezone(&chrono::Utc))
                    .unwrap_or_else(|| now - chrono::Duration::hours(24));
                let Some(next) = scheduler::next_occurrence(&job.schedule, last_fired) else {
                    continue;
                };
                if next <= now {
                    // misfire policy: skip — record the missed slot and fire at most once
                    state.insert(job.id.clone(), now.to_rfc3339());
                    fired_any = true;
                    tracing::info!("scheduler firing job {} ({})", job.id, job.name);
                    commands::spawn_scheduled_run(app.clone(), job.clone());
                }
            }
            if fired_any {
                let _ = storage::save_scheduler_state(&state);
                let _ = app.emit("runs://changed", ());
            }
        }
    });
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    init_logging();
    tracing::info!("starting Confluence Export Desktop v{}", env!("CARGO_PKG_VERSION"));

    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .manage(AppState::new())
        .invoke_handler(tauri::generate_handler![
            commands::get_state,
            commands::test_connection,
            commands::save_connection,
            commands::clear_token,
            commands::save_job,
            commands::delete_job,
            commands::duplicate_job,
            commands::save_settings,
            commands::get_runs,
            commands::get_next_runs,
            commands::is_job_running,
            commands::cancel_run,
            commands::run_job,
            commands::open_folder,
            commands::import_v1
        ])
        .setup(|app| {
            let open = MenuItem::with_id(app, "open", "열기", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "종료", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&open, &quit])?;
            let mut tray = TrayIconBuilder::with_id("main-tray")
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "open" => show_main_window(app),
                    "quit" => app.exit(0),
                    _ => {}
                });
            if let Some(icon) = app.default_window_icon() {
                tray = tray.icon(icon.clone());
            }
            tray = tray.on_tray_icon_event(|tray, event| {
                if let TrayIconEvent::Click {
                    button: MouseButton::Left,
                    button_state: MouseButtonState::Up,
                    ..
                } = event
                {
                    show_main_window(tray.app_handle());
                }
            });
            tray.build(app)?;

            run_scheduler_loop(app.handle().clone());
            Ok(())
        })
        .on_window_event(|window, event| {
            // closing the window keeps the scheduler alive in the tray
            if let WindowEvent::CloseRequested { api, .. } = event {
                let _ = window.hide();
                api.prevent_close();
            }
        })
        .run(tauri::generate_context!())
        .expect("tauri application failed to start");
}
