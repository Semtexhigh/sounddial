//! SoundDial desktop shell (Tauri 2).
//!
//! * Starts the bundled `sounddial-engine` sidecar (the Python engine, frozen with
//!   PyInstaller) on 127.0.0.1:47800 and kills it when the app quits.
//! * On macOS passes the bundled Core Audio helper's path to the engine.
//! * Lives in the tray / menu bar: clicking the icon toggles the window, closing the
//!   window hides it instead of quitting.
//! * The window loads `sounddial.html`; the page finds the engine on its default address.

use std::sync::Mutex;

use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Manager, RunEvent, WindowEvent,
};
use tauri_plugin_shell::{process::CommandChild, ShellExt};

const ENGINE_PORT: &str = "47800";

struct EngineChild(Mutex<Option<CommandChild>>);

fn start_engine(app: &AppHandle) -> tauri::Result<()> {
    let mut cmd = app
        .shell()
        .sidecar("sounddial-engine")
        .map_err(|e| tauri::Error::Anyhow(e.into()))?
        .args(["--port", ENGINE_PORT, "--no-install", "--parent-pid", &std::process::id().to_string()]);

    // macOS: the Swift Core Audio helper ships as a resource next to the binary.
    #[cfg(target_os = "macos")]
    {
        if let Ok(dir) = app.path().resource_dir() {
            let helper = dir.join("resources").join("SoundDialHelper");
            if helper.exists() {
                cmd = cmd.env("SOUNDDIAL_HELPER", helper.to_string_lossy().to_string());
            }
        }
    }
    #[cfg(not(target_os = "macos"))]
    {
        cmd = cmd.env("SOUNDDIAL_DESKTOP", "1");
    }

    match cmd.spawn() {
        Ok((_rx, child)) => {
            if let Some(state) = app.try_state::<EngineChild>() {
                *state.0.lock().unwrap() = Some(child);
            }
            Ok(())
        }
        Err(e) => {
            eprintln!("SoundDial: engine failed to start: {e}");
            Ok(()) // the page falls back to demo mode and says so
        }
    }
}

fn stop_engine(app: &AppHandle) {
    if let Some(state) = app.try_state::<EngineChild>() {
        if let Some(child) = state.0.lock().unwrap().take() {
            let _ = child.kill();
        }
    }
}

fn toggle_window(app: &AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        if w.is_visible().unwrap_or(false) && w.is_focused().unwrap_or(false) {
            let _ = w.hide();
        } else {
            let _ = w.show();
            let _ = w.unminimize();
            let _ = w.set_focus();
        }
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .manage(EngineChild(Mutex::new(None)))
        .setup(|app| {
            // tray / menu bar
            let open = MenuItem::with_id(app, "open", "Open SoundDial", true, None::<&str>)?;
            let restart = MenuItem::with_id(app, "restart", "Restart audio engine", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "Quit SoundDial", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&open, &restart, &quit])?;
            let mut tray = TrayIconBuilder::with_id("main")
                .menu(&menu)
                .show_menu_on_left_click(false)
                .tooltip("SoundDial — per-app volume")
                .on_menu_event(|app, ev| match ev.id().as_ref() {
                    "open" => toggle_window(app),
                    "restart" => {
                        stop_engine(app);
                        let _ = start_engine(app);
                    }
                    "quit" => {
                        stop_engine(app);
                        app.exit(0);
                    }
                    _ => {}
                })
                .on_tray_icon_event(|tray, ev| {
                    if let TrayIconEvent::Click { button: MouseButton::Left, button_state: MouseButtonState::Up, .. } = ev {
                        toggle_window(tray.app_handle());
                    }
                });
            if let Some(icon) = app.default_window_icon().cloned() {
                tray = tray.icon(icon);
            }
            #[cfg(target_os = "macos")]
            {
                // template icon follows light/dark menu bars
                if let Ok(img) = tauri::image::Image::from_bytes(include_bytes!("../icons/trayTemplate@2x.png")) {
                    tray = tray.icon(img).icon_as_template(true);
                }
                let _ = app.set_activation_policy(tauri::ActivationPolicy::Accessory);
            }
            tray.build(app)?;

            start_engine(app.handle())?;
            Ok(())
        })
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                // hide instead of quit; the tray keeps the app alive
                let _ = window.hide();
                api.prevent_close();
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building SoundDial")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                stop_engine(app);
            }
            #[cfg(target_os = "macos")]
            if let RunEvent::Reopen { .. } = event {
                toggle_window(app);
            }
        });
}
