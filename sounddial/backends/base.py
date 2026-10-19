"""Abstract audio backend.

Every platform backend exposes the same small surface so the UI, profiles and
auto-ducking never need to know what operating system they are on.

Volumes are expressed as floats where 1.0 == 100 %. Backends report their own
maximum (`max_gain`) because not every platform can amplify beyond 100 %:

* macOS   (process tap)       -> 2.0  (we scale the samples ourselves)
* Linux   (PulseAudio/PipeWire)-> 2.0  (sink-input volume may exceed PA_VOLUME_NORM)
* Windows (WASAPI session)    -> 1.0  (ISimpleAudioVolume is capped at 100 %)
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

log = logging.getLogger("sounddial.backend")


@dataclass
class AudioApp:
    """One application (or audio session) that is producing sound."""

    key: str                      # stable identifier (bundle id, exe name, binary)
    name: str                     # human readable
    pid: int = 0
    volume: float = 1.0           # 0.0 .. max_gain
    muted: bool = False
    peak: float = 0.0             # 0..1 instantaneous level for VU meter (optional)
    icon_path: Optional[str] = None
    active: bool = True           # currently has an audio stream
    extra: dict = field(default_factory=dict)


@dataclass
class OutputDevice:
    id: str
    name: str
    is_default: bool = False


class AudioBackend:
    """Base class. Subclasses override the `_impl_*` methods."""

    name = "base"
    max_gain = 1.0
    supports_output_switch = False
    supports_peak = False

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._listeners: List[Callable[[], None]] = []
        self.last_error: Optional[str] = None

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        """Initialise platform resources. Must not raise; set last_error instead."""

    def stop(self) -> None:
        """Release platform resources."""

    # ------------------------------------------------------------------ events
    def add_listener(self, fn: Callable[[], None]) -> None:
        self._listeners.append(fn)

    def _notify(self) -> None:
        for fn in list(self._listeners):
            try:
                fn()
            except Exception:  # pragma: no cover - UI callbacks must never kill audio
                log.exception("listener failed")

    # ------------------------------------------------------------------ apps
    def list_apps(self) -> List[AudioApp]:
        with self._lock:
            try:
                return self._impl_list_apps()
            except Exception as exc:
                self.last_error = str(exc)
                log.exception("list_apps failed")
                return []

    def set_app_volume(self, key: str, volume: float) -> bool:
        volume = max(0.0, min(self.max_gain, float(volume)))
        with self._lock:
            try:
                return self._impl_set_app_volume(key, volume)
            except Exception as exc:
                self.last_error = str(exc)
                log.exception("set_app_volume failed")
                return False

    def set_app_mute(self, key: str, muted: bool) -> bool:
        with self._lock:
            try:
                return self._impl_set_app_mute(key, bool(muted))
            except Exception as exc:
                self.last_error = str(exc)
                log.exception("set_app_mute failed")
                return False

    # ------------------------------------------------------------------ master
    def get_master(self) -> tuple[float, bool]:
        with self._lock:
            try:
                return self._impl_get_master()
            except Exception as exc:
                self.last_error = str(exc)
                return (1.0, False)

    def set_master(self, volume: float, muted: Optional[bool] = None) -> bool:
        volume = max(0.0, min(1.0, float(volume)))
        with self._lock:
            try:
                return self._impl_set_master(volume, muted)
            except Exception as exc:
                self.last_error = str(exc)
                return False

    def list_outputs(self) -> List[OutputDevice]:
        with self._lock:
            try:
                return self._impl_list_outputs()
            except Exception as exc:
                self.last_error = str(exc)
                return []

    def set_default_output(self, device_id: str) -> bool:
        with self._lock:
            try:
                return self._impl_set_default_output(device_id)
            except Exception as exc:
                self.last_error = str(exc)
                return False

    # ------------------------------------------------------------------ to override
    def _impl_list_apps(self) -> List[AudioApp]:
        return []

    def _impl_set_app_volume(self, key: str, volume: float) -> bool:
        return False

    def _impl_set_app_mute(self, key: str, muted: bool) -> bool:
        return False

    def _impl_get_master(self) -> tuple[float, bool]:
        return (1.0, False)

    def _impl_set_master(self, volume: float, muted: Optional[bool]) -> bool:
        return False

    def _impl_list_outputs(self) -> List[OutputDevice]:
        return []

    def _impl_set_default_output(self, device_id: str) -> bool:
        return False


# ---------------------------------------------------------------------- helpers
PRETTY_NAMES: Dict[str, str] = {
    "chrome": "Google Chrome",
    "google chrome": "Google Chrome",
    "firefox": "Firefox",
    "msedge": "Microsoft Edge",
    "spotify": "Spotify",
    "zoom": "Zoom",
    "zoom.us": "Zoom",
    "teams": "Microsoft Teams",
    "ms-teams": "Microsoft Teams",
    "discord": "Discord",
    "slack": "Slack",
    "facetime": "FaceTime",
    "music": "Music",
    "vlc": "VLC",
    "safari": "Safari",
    "arc": "Arc",
    "brave": "Brave",
    "telegram": "Telegram",
    "whatsapp": "WhatsApp",
    "steam": "Steam",
    "obs": "OBS Studio",
    "obs64": "OBS Studio",
    "mpv": "mpv",
    "audacious": "Audacious",
    "rhythmbox": "Rhythmbox",
    "clementine": "Clementine",
    "webcord": "Discord",
    "code": "VS Code",
}


def pretty_name(raw: str) -> str:
    base = raw.strip()
    low = base.lower()
    for suffix in (".exe", ".app", ".bin", "-bin"):
        if low.endswith(suffix):
            base = base[: -len(suffix)]
            low = base.lower()
    return PRETTY_NAMES.get(low, base[:1].upper() + base[1:] if base else "Unknown")
