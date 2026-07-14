use serde::Deserialize;
use std::fs;
use std::sync::Mutex;
use tauri::{Manager, RunEvent, Url};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

struct SidecarProcess {
    child: Option<CommandChild>,
    shutdown_file: std::path::PathBuf,
}

struct SidecarState(Mutex<SidecarProcess>);

#[derive(Deserialize)]
struct ReadyEvent {
    event: String,
    host: String,
    port: u16,
}

fn start_sidecar(app: &tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    let data_dir = app.path().app_data_dir()?;
    fs::create_dir_all(&data_dir)?;
    let ready_file = data_dir.join("desktop-ready.json");
    let shutdown_file = data_dir.join("desktop-shutdown");
    let _ = fs::remove_file(&ready_file);
    let _ = fs::remove_file(&shutdown_file);
    let data_dir_arg = data_dir.to_string_lossy().into_owned();
    let ready_file_arg = ready_file.to_string_lossy().into_owned();
    let shutdown_file_arg = shutdown_file.to_string_lossy().into_owned();

    let command = app
        .shell()
        .sidecar("proofline-sidecar")?
        .args([
            "serve",
            "--host",
            "127.0.0.1",
            "--port",
            "0",
            "--data-dir",
            data_dir_arg.as_str(),
            "--ready-file",
            ready_file_arg.as_str(),
            "--shutdown-file",
            shutdown_file_arg.as_str(),
        ])
        .env("PROOFLINE_SECRET_STORE", "os_keyring");
    let (mut receiver, child) = command.spawn()?;
    app.manage(SidecarState(Mutex::new(SidecarProcess {
        child: Some(child),
        shutdown_file,
    })));

    let handle = app.handle().clone();
    tauri::async_runtime::spawn(async move {
        while let Some(event) = receiver.recv().await {
            match event {
                CommandEvent::Stdout(bytes) => {
                    let Ok(line) = String::from_utf8(bytes) else {
                        continue;
                    };
                    let Ok(ready) = serde_json::from_str::<ReadyEvent>(line.trim()) else {
                        continue;
                    };
                    if ready.event != "ready" || ready.host != "127.0.0.1" {
                        continue;
                    }
                    let Ok(url) = Url::parse(&format!("http://127.0.0.1:{}/", ready.port)) else {
                        continue;
                    };
                    if let Some(window) = handle.get_webview_window("main") {
                        let _ = window.navigate(url);
                    }
                }
                CommandEvent::Terminated(_) => break,
                _ => {}
            }
        }
    });
    Ok(())
}

fn stop_sidecar(app: &tauri::AppHandle) {
    let Some(state) = app.try_state::<SidecarState>() else {
        return;
    };
    if let Ok(guard) = state.0.lock() {
        // The Python sidecar watches this private app-data file and asks Uvicorn
        // to drain requests before exiting. Keep the child handle alive until
        // the application process is torn down instead of force-killing it.
        let _ = fs::write(&guard.shutdown_file, b"shutdown\n");
        let _ = guard.child.as_ref();
    };
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| start_sidecar(app).map_err(|error| error.to_string().into()))
        .build(tauri::generate_context!())
        .expect("failed to build Proofline desktop shell");

    app.run(|handle, event| {
        if matches!(event, RunEvent::Exit | RunEvent::ExitRequested { .. }) {
            stop_sidecar(handle);
        }
    });
}

#[cfg(test)]
mod tests {
    use super::ReadyEvent;

    #[test]
    fn readiness_event_is_bounded_to_loopback() {
        let ready: ReadyEvent =
            serde_json::from_str(r#"{"event":"ready","host":"127.0.0.1","port":49152}"#)
                .expect("valid readiness event");
        assert_eq!(ready.event, "ready");
        assert_eq!(ready.host, "127.0.0.1");
        assert_eq!(ready.port, 49152);
    }
}
