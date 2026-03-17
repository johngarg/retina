#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::Mutex,
};

use serde::Serialize;
use tauri::{Manager, State};

struct BackendState {
    child: Mutex<Option<Child>>,
}

#[derive(Serialize)]
struct BackendStartResult {
    status: String,
    detail: String,
    mode: String,
}

fn shutdown_backend(state: &BackendState) {
    let mut child_guard = state.child.lock().expect("backend state mutex poisoned");
    if let Some(mut child) = child_guard.take() {
        let _ = child.kill();
        let _ = child.wait();
    }
}

#[cfg(debug_assertions)]
fn resolve_backend_runtime() -> Result<(PathBuf, PathBuf, PathBuf), String> {
    let api_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../api");
    let python_path = api_dir.join(".venv/bin/python");
    let data_dir = api_dir.join("data");

    if !python_path.exists() {
        return Err(format!(
            "Expected backend runtime at {}. Run `uv sync --extra dev` in apps/api first.",
            python_path.display()
        ));
    }

    Ok((python_path, api_dir, data_dir))
}

#[cfg(not(debug_assertions))]
fn resolve_backend_runtime() -> Result<(PathBuf, PathBuf, PathBuf), String> {
    Err(
        "Packaged backend runtime is not configured yet. Milestone 2 will bundle Python and backend assets."
            .to_string(),
    )
}

#[tauri::command]
fn ensure_backend_started(state: State<'_, BackendState>) -> Result<BackendStartResult, String> {
    let mut child_guard = state.child.lock().expect("backend state mutex poisoned");

    if let Some(child) = child_guard.as_mut() {
        match child.try_wait() {
            Ok(None) => {
                return Ok(BackendStartResult {
                    status: "already-running".into(),
                    detail: "Local API is already running.".into(),
                    mode: if cfg!(debug_assertions) {
                        "dev".into()
                    } else {
                        "packaged".into()
                    },
                });
            }
            Ok(Some(_)) => {
                child_guard.take();
            }
            Err(error) => {
                return Err(format!("Failed to inspect backend process state: {error}"));
            }
        }
    }

    let (python_path, api_dir, data_dir) = resolve_backend_runtime()?;
    let child = Command::new(python_path)
        .current_dir(api_dir)
        .env("RETINA_DATA_DIR", data_dir)
        .env("PYTHONUNBUFFERED", "1")
        .arg("-m")
        .arg("uvicorn")
        .arg("app.main:app")
        .arg("--host")
        .arg("127.0.0.1")
        .arg("--port")
        .arg("8000")
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|error| format!("Failed to launch backend process: {error}"))?;

    child_guard.replace(child);

    Ok(BackendStartResult {
        status: "started".into(),
        detail: "Started the local API process.".into(),
        mode: if cfg!(debug_assertions) {
            "dev".into()
        } else {
            "packaged".into()
        },
    })
}

fn main() {
    let app = tauri::Builder::default()
        .manage(BackendState {
            child: Mutex::new(None),
        })
        .invoke_handler(tauri::generate_handler![ensure_backend_started])
        .build(tauri::generate_context!())
        .expect("error while building retina desktop");

    app.run(|app_handle, event| {
        if matches!(
            event,
            tauri::RunEvent::Exit | tauri::RunEvent::ExitRequested { .. }
        ) {
            let state = app_handle.state::<BackendState>();
            shutdown_backend(&state);
        }
    });
}
