"""Persistent settings (JSON) — themes, profiles, remembered volumes, ducking."""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Any, Dict

log = logging.getLogger("sounddial.settings")


def config_dir() -> Path:
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    d = base / "SoundDial"
    d.mkdir(parents=True, exist_ok=True)
    return d


CALL_APPS_DEFAULT = ["zoom", "zoom.us", "teams", "ms-teams", "msteams", "facetime", "discord",
                     "slack", "webex", "skype", "google meet", "whatsapp", "telegram", "signal"]
MEDIA_APPS_DEFAULT = ["spotify", "music", "chrome", "google chrome", "safari", "firefox", "msedge",
                      "arc", "brave", "vlc", "mpv", "tidal", "apple music", "youtube music", "iina"]

DEFAULTS: Dict[str, Any] = {
    "theme": "mono",                 # mono | graphite | paper | midnight | terminal | system
    "accent": "#4F8CFF",             # used by themes that take an accent
    "compact": False,
    "show_vu": True,
    "show_percent": True,
    "popover_width": 380,
    "launch_at_login": False,
    "remember_volumes": True,
    "remembered": {},                # key -> {"volume": f, "muted": b}
    "profiles": {
        "Work":  {"spotify": 0.35, "music": 0.35, "chrome": 0.8, "zoom": 1.0, "teams": 1.0, "discord": 0.5},
        "Focus": {"spotify": 0.6, "music": 0.6, "chrome": 0.4, "discord": 0.0, "slack": 0.0},
        "Chill": {"spotify": 1.0, "music": 1.0, "chrome": 1.0, "discord": 0.7},
    },
    "active_profile": "",
    "ducking": {
        "enabled": True,
        "level": 0.25,               # media volume multiplier while a call is active
        "call_apps": CALL_APPS_DEFAULT,
        "media_apps": MEDIA_APPS_DEFAULT,
        "duck_all": False,           # duck every non-call app instead of just media apps
    },
    "hotkey": "",                    # reserved
    "poll_ms": 800,
    "peak_ms": 90,
}


class Settings:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (config_dir() / "settings.json")
        self._lock = threading.RLock()
        self.data: Dict[str, Any] = json.loads(json.dumps(DEFAULTS))
        self.load()

    def load(self) -> None:
        try:
            if self.path.exists():
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                self._merge(self.data, raw)
        except Exception as exc:
            log.warning("settings load failed (%s) — using defaults", exc)

    @staticmethod
    def _merge(dst: dict, src: dict) -> None:
        for k, v in src.items():
            if isinstance(v, dict) and isinstance(dst.get(k), dict) and k not in ("profiles", "remembered"):
                Settings._merge(dst[k], v)
            else:
                dst[k] = v

    def save(self) -> None:
        with self._lock:
            tmp = self.path.with_suffix(".tmp")
            try:
                tmp.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
                os.replace(tmp, self.path)
            except Exception as exc:
                log.warning("settings save failed: %s", exc)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any, save: bool = True) -> None:
        with self._lock:
            self.data[key] = value
        if save:
            self.save()

    def reset(self) -> None:
        with self._lock:
            self.data = json.loads(json.dumps(DEFAULTS))
        self.save()
