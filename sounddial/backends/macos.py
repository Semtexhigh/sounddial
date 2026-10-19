"""macOS backend — talks to the native Swift helper (``SoundDialHelper``).

macOS has no public per-app volume API in Python. Since macOS 14.2, Core Audio
exposes *process taps* (CATapDescription / AudioHardwareCreateProcessTap): a
tap captures the audio of one process, the original output is muted, and we
re-render the tapped audio to the output device at the gain we want. That has
to run on a realtime thread, so it lives in a small Swift helper
(``macos_helper/SoundDialHelper.swift``) that speaks JSON lines over stdio.

This Python class:
  * locates the helper (bundled binary, or compiles it on first run with swiftc),
  * keeps it running, restarts it if it dies,
  * mirrors its last reported state so the UI can read without blocking.

If the helper cannot be started (older macOS, no Xcode CLT, permission denied),
the backend degrades to master-volume-only through ``osascript``.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import List, Optional

from .base import AudioApp, AudioBackend, OutputDevice, pretty_name

log = logging.getLogger("sounddial.macos")

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent.parent
HELPER_DIR = PROJECT_ROOT / "macos_helper"
HELPER_SRC = HELPER_DIR / "SoundDialHelper.swift"
HELPER_NAME = "SoundDialHelper"


def available() -> bool:
    return sys.platform == "darwin"


def _candidate_binaries() -> List[Path]:
    cands = []
    env = os.environ.get("SOUNDDIAL_HELPER")
    if env:
        cands.append(Path(env))
    cands += [
        HELPER_DIR / HELPER_NAME,
        Path(sys.executable).resolve().parent / HELPER_NAME,
        Path.home() / "Library" / "Application Support" / "SoundDial" / HELPER_NAME,
    ]
    if getattr(sys, "frozen", False):  # PyInstaller bundle
        cands.insert(0, Path(sys._MEIPASS) / "macos_helper" / HELPER_NAME)  # type: ignore[attr-defined]
        cands.insert(0, Path(sys.executable).resolve().parent / ".." / "Resources" / "macos_helper" / HELPER_NAME)
    return cands


def _macos_version() -> tuple[int, int]:
    try:
        out = subprocess.check_output(["sw_vers", "-productVersion"], text=True).strip()
        parts = [int(x) for x in out.split(".")[:2]]
        while len(parts) < 2:
            parts.append(0)
        return (parts[0], parts[1])
    except Exception:
        return (0, 0)


def build_helper(dest: Optional[Path] = None) -> Optional[Path]:
    """Compile the Swift helper with swiftc. Returns the binary path or None."""
    if not HELPER_SRC.exists():
        log.error("helper source missing: %s", HELPER_SRC)
        return None
    swiftc = shutil.which("swiftc")
    if not swiftc:
        log.error("swiftc not found — install Xcode Command Line Tools: xcode-select --install")
        return None
    dest = dest or (Path.home() / "Library" / "Application Support" / "SoundDial" / HELPER_NAME)
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [swiftc, "-O", "-framework", "CoreAudio", "-framework", "AudioToolbox",
           "-framework", "AppKit", "-o", str(dest), str(HELPER_SRC)]
    log.info("compiling helper: %s", " ".join(cmd))
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)
    except subprocess.CalledProcessError as exc:
        log.error("swiftc failed:\n%s", exc.stderr)
        return None
    except Exception as exc:
        log.error("swiftc failed: %s", exc)
        return None
    os.chmod(dest, 0o755)
    return dest


class MacOSBackend(AudioBackend):
    name = "macos"
    max_gain = 2.0
    supports_output_switch = True
    supports_peak = True

    def __init__(self) -> None:
        super().__init__()
        self._proc: Optional[subprocess.Popen] = None
        self._reader: Optional[threading.Thread] = None
        self._state: dict = {"apps": [], "master": {"volume": 1.0, "muted": False}, "outputs": []}
        self._state_lock = threading.Lock()
        self._alive = False
        self.degraded = False
        self._helper_path: Optional[Path] = None
        self._last_restart = 0.0

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        if not available():
            self.last_error = "not macOS"
            return
        major, minor = _macos_version()
        if (major, minor) < (14, 2):
            self.last_error = f"macOS {major}.{minor}: per-app volume needs macOS 14.2+ (Core Audio process taps). Master volume only."
            self.degraded = True
            return
        for c in _candidate_binaries():
            if c.exists() and os.access(c, os.X_OK):
                self._helper_path = c
                break
        if self._helper_path is None:
            self._helper_path = build_helper()
        if self._helper_path is None:
            self.last_error = "SoundDialHelper could not be found or built. Master volume only."
            self.degraded = True
            return
        self._spawn()

    def _spawn(self) -> None:
        try:
            self._proc = subprocess.Popen(
                [str(self._helper_path)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1,
            )
        except Exception as exc:
            self.last_error = f"helper launch failed: {exc}"
            self.degraded = True
            return
        self._alive = True
        self.degraded = False
        self._reader = threading.Thread(target=self._read_loop, name="SoundDialHelper-reader", daemon=True)
        self._reader.start()
        threading.Thread(target=self._stderr_loop, daemon=True).start()
        self._send({"cmd": "list"})

    def stop(self) -> None:
        self._alive = False
        if self._proc is not None:
            try:
                self._send({"cmd": "quit"})
                self._proc.wait(timeout=3)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
        self._proc = None

    def _send(self, msg: dict) -> bool:
        p = self._proc
        if p is None or p.stdin is None or p.poll() is not None:
            self._maybe_restart()
            return False
        try:
            p.stdin.write(json.dumps(msg) + "\n")
            p.stdin.flush()
            return True
        except Exception as exc:
            log.warning("helper write failed: %s", exc)
            self._maybe_restart()
            return False

    def _maybe_restart(self) -> None:
        if not self._alive or self._helper_path is None:
            return
        now = time.time()
        if now - self._last_restart < 5:
            return
        self._last_restart = now
        log.warning("helper died — restarting")
        self._spawn()

    def _read_loop(self) -> None:
        p = self._proc
        if p is None or p.stdout is None:
            return
        for line in p.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except Exception:
                log.debug("helper noise: %s", line[:200])
                continue
            t = msg.get("type")
            if t == "state":
                with self._state_lock:
                    self._state = msg
                self._notify()
            elif t == "error":
                self.last_error = msg.get("message", "helper error")
                log.error("helper: %s", self.last_error)
            elif t == "log":
                log.info("helper: %s", msg.get("message"))
        self._alive_check()

    def _alive_check(self) -> None:
        if self._alive:
            self._maybe_restart()

    def _stderr_loop(self) -> None:
        p = self._proc
        if p is None or p.stderr is None:
            return
        for line in p.stderr:
            log.debug("helper stderr: %s", line.rstrip())

    # ------------------------------------------------------------------ apps
    def _impl_list_apps(self) -> List[AudioApp]:
        if self.degraded:
            return []
        self._send({"cmd": "list"})
        with self._state_lock:
            apps = list(self._state.get("apps", []))
        out: List[AudioApp] = []
        for a in apps:
            key = a.get("bundle") or f"pid:{a.get('pid')}"
            out.append(AudioApp(
                key=key, name=a.get("name") or pretty_name(key), pid=int(a.get("pid", 0)),
                volume=float(a.get("volume", 1.0)), muted=bool(a.get("muted", False)),
                peak=float(a.get("peak", 0.0)), icon_path=a.get("icon"), active=bool(a.get("active", True)),
            ))
        return out

    def _impl_set_app_volume(self, key: str, volume: float) -> bool:
        return self._send({"cmd": "set_volume", "key": key, "volume": volume})

    def _impl_set_app_mute(self, key: str, muted: bool) -> bool:
        return self._send({"cmd": "set_mute", "key": key, "muted": muted})

    # ------------------------------------------------------------------ master
    def _impl_get_master(self) -> tuple[float, bool]:
        if self.degraded:
            return self._osa_get_master()
        with self._state_lock:
            m = self._state.get("master", {})
        return (float(m.get("volume", 1.0)), bool(m.get("muted", False)))

    def _impl_set_master(self, volume: float, muted: Optional[bool]) -> bool:
        if self.degraded:
            return self._osa_set_master(volume, muted)
        msg = {"cmd": "set_master", "volume": volume}
        if muted is not None:
            msg["muted"] = muted
        return self._send(msg)

    def _impl_list_outputs(self) -> List[OutputDevice]:
        with self._state_lock:
            outs = list(self._state.get("outputs", []))
        return [OutputDevice(id=str(o.get("id")), name=o.get("name", "?"), is_default=bool(o.get("default")))
                for o in outs]

    def _impl_set_default_output(self, device_id: str) -> bool:
        return self._send({"cmd": "set_output", "id": device_id})

    # ------------------------------------------------------------------ degraded fallbacks
    @staticmethod
    def _osa(script: str) -> str:
        try:
            return subprocess.check_output(["osascript", "-e", script], text=True, timeout=5).strip()
        except Exception:
            return ""

    def _osa_get_master(self) -> tuple[float, bool]:
        out = self._osa("output volume of (get volume settings)")
        mute = self._osa("output muted of (get volume settings)")
        try:
            return (int(out) / 100.0, mute == "true")
        except Exception:
            return (1.0, False)

    def _osa_set_master(self, volume: float, muted: Optional[bool]) -> bool:
        self._osa(f"set volume output volume {int(round(volume * 100))}")
        if muted is not None:
            self._osa(f"set volume output muted {'true' if muted else 'false'}")
        return True
