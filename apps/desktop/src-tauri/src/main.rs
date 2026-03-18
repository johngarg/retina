#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{
    fs,
    fs::OpenOptions,
    io::ErrorKind,
    net::TcpListener,
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

fn prepare_backend_logs(data_dir: &PathBuf) -> Result<(PathBuf, PathBuf), String> {
    let logs_dir = data_dir.join("logs");
    fs::create_dir_all(&logs_dir)
        .map_err(|error| format!("Failed to create backend logs directory: {error}"))?;

    let stdout_log = logs_dir.join("backend.stdout.log");
    let stderr_log = logs_dir.join("backend.stderr.log");

    OpenOptions::new()
        .create(true)
        .write(true)
        .truncate(true)
        .open(&stdout_log)
        .map_err(|error| format!("Failed to create backend stdout log: {error}"))?;
    OpenOptions::new()
        .create(true)
        .write(true)
        .truncate(true)
        .open(&stderr_log)
        .map_err(|error| format!("Failed to create backend stderr log: {error}"))?;

    Ok((stdout_log, stderr_log))
}

fn ensure_backend_port_available() -> Result<(), String> {
    match TcpListener::bind("127.0.0.1:8000") {
        Ok(listener) => {
            drop(listener);
            Ok(())
        }
        Err(error) if error.kind() == ErrorKind::AddrInUse => Err(
            "Port 8000 is already in use. Close any other Retina instance or local service using 127.0.0.1:8000, then retry.".into(),
        ),
        Err(error) => Err(format!(
            "Failed to check whether 127.0.0.1:8000 is available: {error}"
        )),
    }
}

fn shutdown_backend(state: &BackendState) {
    let mut child_guard = state.child.lock().expect("backend state mutex poisoned");
    if let Some(mut child) = child_guard.take() {
        let _ = child.kill();
        let _ = child.wait();
    }
}

#[cfg(unix)]
fn ensure_executable(path: &PathBuf) -> Result<(), String> {
    use std::os::unix::fs::PermissionsExt;

    let mut permissions = fs::metadata(path)
        .map_err(|error| format!("Failed to read backend executable metadata: {error}"))?
        .permissions();
    permissions.set_mode(0o755);
    fs::set_permissions(path, permissions)
        .map_err(|error| format!("Failed to set backend executable permissions: {error}"))?;
    Ok(())
}

#[cfg(not(unix))]
fn ensure_executable(_path: &PathBuf) -> Result<(), String> {
    Ok(())
}

#[cfg(debug_assertions)]
fn resolve_dev_backend_runtime() -> Result<(PathBuf, PathBuf, PathBuf), String> {
    let api_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../api");
    let executable_path = if cfg!(target_os = "windows") {
        api_dir.join(".venv/Scripts/python.exe")
    } else {
        api_dir.join(".venv/bin/python")
    };
    let data_dir = api_dir.join("data");

    if !executable_path.exists() {
        return Err(format!(
            "Expected backend runtime at {}. Run `uv sync --extra dev` in apps/api first.",
            executable_path.display()
        ));
    }

    Ok((executable_path, api_dir, data_dir))
}

#[cfg(not(debug_assertions))]
fn resolve_packaged_backend_runtime(
    app: &tauri::AppHandle,
) -> Result<(PathBuf, PathBuf, PathBuf), String> {
    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|error| format!("Failed to resolve resource directory: {error}"))?;
    let backend_dir = resource_dir.join("backend");
    let executable_name = if cfg!(target_os = "windows") {
        "retina-api.exe"
    } else {
        "retina-api"
    };
    let executable_path = backend_dir.join(executable_name);
    let data_dir = app
        .path()
        .app_local_data_dir()
        .map_err(|error| format!("Failed to resolve app data directory: {error}"))?
        .join("backend-data");

    if !executable_path.exists() {
        return Err(format!(
            "Bundled backend executable is missing at {}.",
            executable_path.display()
        ));
    }

    fs::create_dir_all(&data_dir)
        .map_err(|error| format!("Failed to create backend data directory: {error}"))?;
    ensure_executable(&executable_path)?;

    Ok((executable_path, backend_dir, data_dir))
}

fn resolve_backend_runtime(app: &tauri::AppHandle) -> Result<(PathBuf, PathBuf, PathBuf), String> {
    #[cfg(debug_assertions)]
    {
        let _ = app;
        return resolve_dev_backend_runtime();
    }

    #[cfg(not(debug_assertions))]
    {
        resolve_packaged_backend_runtime(app)
    }
}

#[tauri::command]
fn ensure_backend_started(
    app: tauri::AppHandle,
    state: State<'_, BackendState>,
) -> Result<BackendStartResult, String> {
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

    let (backend_executable, backend_workdir, data_dir) = resolve_backend_runtime(&app)?;
    ensure_backend_port_available()?;
    #[cfg(debug_assertions)]
    let mut command = {
        let mut command = Command::new(&backend_executable);
        command.arg("-m").arg("uvicorn").arg("app.main:app");
        command
    };

    #[cfg(not(debug_assertions))]
    let mut command = Command::new(&backend_executable);

    let (stdout_log_path, stderr_log_path) = prepare_backend_logs(&data_dir)?;
    let stdout_log = OpenOptions::new()
        .create(true)
        .write(true)
        .truncate(true)
        .open(&stdout_log_path)
        .map_err(|error| format!("Failed to open backend stdout log: {error}"))?;
    let stderr_log = OpenOptions::new()
        .create(true)
        .write(true)
        .truncate(true)
        .open(&stderr_log_path)
        .map_err(|error| format!("Failed to open backend stderr log: {error}"))?;

    let child = command
        .current_dir(backend_workdir)
        .env("RETINA_DATA_DIR", data_dir)
        .env("PYTHONUNBUFFERED", "1")
        .arg("--host")
        .arg("127.0.0.1")
        .arg("--port")
        .arg("8000")
        .stdout(Stdio::from(stdout_log))
        .stderr(Stdio::from(stderr_log))
        .spawn()
        .map_err(|error| format!("Failed to launch backend process: {error}"))?;

    child_guard.replace(child);

    Ok(BackendStartResult {
        status: "started".into(),
        detail: format!(
            "Started the local API process. Logs: stdout={}, stderr={}",
            stdout_log_path.display(),
            stderr_log_path.display()
        ),
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
