# SoundDial

**Per-app volume mixer for macOS, Windows and Linux.** Lives in your menu bar / system tray, opens instantly, closes when you click away.

Control every app's volume independently — lower Spotify during a Zoom call, boost a quiet browser tab, mute Discord — without touching the system volume.

**Download:** https://semtexhigh.github.io/sounddial/ (picks the right installer for your OS) · [all releases](https://github.com/Semtexhigh/sounddial/releases)

## Features

| Feature | macOS | Windows | Linux |
|---|---|---|---|
| Per-app volume sliders | 0–200 % | 0–100 % | 0–200 % |
| Per-app mute | ✓ | ✓ | ✓ |
| Live level meters (VU) under each slider | ✓ | ✓ | — |
| Auto-ducking (lower media when a call starts, restore after) | ✓ | ✓ | ✓ |
| Volume profiles (Work / Focus / Chill, your own) | ✓ | ✓ | ✓ |
| Master output volume + mute | ✓ | ✓ | ✓ |
| Switch output device from the popover | ✓ | ✓ | ✓ |
| Remember each app's volume across restarts | ✓ | ✓ | ✓ |
| App icons in the list | ✓ | ✓ | theme icons |

All processing is local. Nothing leaves your machine.

---

## Desktop app (Tauri) — downloads for macOS Silicon / Intel, Windows, Linux

The shipped product is a Tauri 2 desktop app: a native window + tray icon around `sounddial.html`, with the
Python engine frozen into a sidecar binary and (on macOS) the Core Audio helper bundled as a resource.
Nothing is installed on the user's machine except the app.

| Download | Built on | File |
|---|---|---|
| macOS Apple Silicon | `macos-14` runner | `SoundDial_1.0.0_aarch64.dmg` |
| macOS Intel | `macos-13` runner | `SoundDial_1.0.0_x64.dmg` |
| Windows 10/11 | `windows-latest` | `SoundDial_1.0.0_x64-setup.exe` (NSIS, per-user) |
| Linux | `ubuntu-22.04` | `SoundDial_1.0.0_amd64.AppImage` + `.deb` |

**Release procedure (GitHub Actions does all four):** tag a version (`v1.0.0`) or run the *release* workflow by hand.
~15 minutes later the Release page has all installers; `site/index.html` (GitHub Pages) detects the visitor's OS and offers the right one.

macOS builds are unsigned by design. The workflow signs automatically only if `APPLE_*` secrets exist; nothing else changes.
First launch on macOS: right-click the app → Open → Open, or `xattr -dr com.apple.quarantine /Applications/SoundDial.app`.

**Local build** (any OS, needs Rust + Node + Python):

```
pip install pyinstaller pillow     # plus pycaw (Windows) / pulsectl (Linux)
python tools/make_icons.py         # icon set → assets/icons + src-tauri/icons
python tools/build_engine.py       # sidecar → src-tauri/binaries/sounddial-engine-<triple>
bash macos_helper/build_helper.sh && cp macos_helper/SoundDialHelper src-tauri/resources/   # macOS only
npm install && npm run build       # → src-tauri/target/release/bundle/…
```

Layout: `src-tauri/` (Rust shell: tray, window, sidecar lifecycle, `tauri.conf.json`, entitlements),
`dist/index.html` (copy of `sounddial.html` made by `npm run dist`), `.github/workflows/release.yml`, `site/` (download page).

## The HTML app — `sounddial.html`

The UI is a **single-file HTML app**. A web page cannot reach other apps' audio, so the real work is done by a small local service, `engine.py`, which the page talks to on `127.0.0.1:47800`:

```
python3 engine.py --open        # starts the engine and opens the app (Windows: run_engine.bat)
```

* With the engine running: real apps, real icons (pulled from each app and served at `/icon/<app>`), real volume.
* Without it: the page still opens and runs in **demo mode** with simulated apps.
* API: `GET /state`, `GET /events` (Server-Sent Events), `GET /icon/<key>`, `POST /cmd` — see the top of `engine.py`.

Pages: **Mixer** (output + per-app rows with icon · mute · slider · VU · badges, filter, quick actions, undo) · **Profiles** · **Ducking** · **Options** (5 greyscale themes, density, behaviour, engine) · **Data** (10 storage places with health lamps, backup / import with preview / delete-all).

## macOS — the native helper

Per-app volume on macOS uses **Core Audio process taps**, which need **macOS 14.2 (Sonoma) or newer**. The tap engine is a small Swift program, `macos_helper/SoundDialHelper.swift`, compiled by the release workflow and bundled into the app.
The first time an app is tapped, macOS asks for **System Audio Recording** permission (System Settings › Privacy & Security › Screen & System Audio Recording) — this is the OS gate for reading another app's audio.
On macOS older than 14.2 only the master output slider works.

## Windows notes

* WASAPI audio sessions through `pycaw` — the same mechanism as the Windows Volume Mixer. No driver, no admin rights.
* Windows caps a session at 100 %, so the slider's boost zone is absent there.
* Output switching uses the standard `IPolicyConfig` interface.

## Linux notes

* Works with PulseAudio and with PipeWire (through `pipewire-pulse`).
* Sink-inputs can go above 100 %, so boost works.
* On GNOME/Wayland the tray needs the *AppIndicator and KStatusNotifierItem* extension.

## Auto-ducking — how it decides

1. A **call app** (Zoom, Teams, FaceTime, Discord, Slack, Webex, Skype, Meet, WhatsApp, Telegram, Signal — editable) has a live audio stream that is actually producing sound.
2. Every **media app** (Spotify, Music, browsers, VLC, mpv… — editable; or *every* other app with *Duck all*) is lowered to the duck level (default 25 % of its own volume).
3. When the call goes silent for ~4 s, every ducked app is restored to exactly where it was.

## Project layout

```
sounddial.html               the app (single file)
engine.py                    local service: HTTP + SSE + icons, drives the backends
sounddial/backends/          base.py · windows.py (pycaw) · linux.py (pulsectl) · macos.py (Swift helper) · demo.py
sounddial/mixer.py           polling, remembered volumes, profiles, ducking engine
sounddial/settings.py        JSON settings in the OS config dir
macos_helper/                SoundDialHelper.swift (Core Audio process taps, macOS 14.2+)
src-tauri/                   Tauri 2 desktop shell
tools/make_icons.py          icon generator (app, tray, Tauri set)
tools/build_engine.py        PyInstaller sidecar build
site/                        download page (GitHub Pages)
tests/test_mixer.py          logic tests
main.py + sounddial/ui/      alternative Qt tray front-end on the same backends
```

## Testing

```
python tests/test_mixer.py           # logic tests, no audio needed
python engine.py --demo --open       # the app with fake apps
python main.py --selftest            # real backend on this machine
```

License: MIT.
