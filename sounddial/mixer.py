"""Mixer controller: polls the backend, applies remembered volumes, profiles
and auto-ducking. Framework-agnostic — the Qt layer only calls into this."""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Dict, List, Optional

from .backends import AudioApp, AudioBackend, OutputDevice, create_backend
from .settings import Settings

log = logging.getLogger("sounddial.mixer")


class Mixer:
    def __init__(self, settings: Settings, backend: Optional[AudioBackend] = None, demo: bool = False) -> None:
        self.settings = settings
        self.backend = backend or create_backend(force_demo=demo)
        self.apps: Dict[str, AudioApp] = {}
        self.master_volume = 1.0
        self.master_muted = False
        self.outputs: List[OutputDevice] = []
        self.ducking_active = False
        self._pre_duck: Dict[str, float] = {}
        self._seen: set[str] = set()
        self._listeners: List[Callable[[], None]] = []
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        self.refresh()
        self._thread = threading.Thread(target=self._loop, name="SoundDial-poll", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self.ducking_active:
            self._unduck()
        self.backend.stop()

    def on_change(self, fn: Callable[[], None]) -> None:
        self._listeners.append(fn)

    def _emit(self) -> None:
        for fn in list(self._listeners):
            try:
                fn()
            except Exception:
                log.exception("listener")

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.refresh()
            except Exception:
                log.exception("refresh")
            self._stop.wait(max(0.2, self.settings.get("poll_ms", 800) / 1000.0))

    # ------------------------------------------------------------------ polling
    def refresh(self) -> None:
        with self._lock:
            apps = self.backend.list_apps()
            new: Dict[str, AudioApp] = {}
            remembered = self.settings.get("remembered", {}) if self.settings.get("remember_volumes") else {}
            for a in apps:
                new[a.key] = a
                if a.key not in self._seen:
                    self._seen.add(a.key)
                    mem = remembered.get(a.key)
                    if mem and not self.ducking_active:
                        # First time we see this app this session: restore its remembered level
                        self.backend.set_app_volume(a.key, float(mem.get("volume", a.volume)))
                        self.backend.set_app_mute(a.key, bool(mem.get("muted", a.muted)))
                        a.volume = float(mem.get("volume", a.volume))
                        a.muted = bool(mem.get("muted", a.muted))
            self.apps = new
            self.master_volume, self.master_muted = self.backend.get_master()
            if self.backend.supports_output_switch:
                self.outputs = self.backend.list_outputs()
            self._tick_ducking()
        self._emit()

    # ------------------------------------------------------------------ control
    def set_volume(self, key: str, volume: float) -> None:
        with self._lock:
            volume = max(0.0, min(self.backend.max_gain, volume))
            if self.backend.set_app_volume(key, volume) and key in self.apps:
                self.apps[key].volume = volume
            if self.ducking_active and key in self._pre_duck and self._is_duckable(key):
                # user adjusted a ducked app: remember the un-ducked intent instead
                lvl = self.settings.get("ducking", {}).get("level", 0.25) or 1e-6
                self._pre_duck[key] = min(self.backend.max_gain, volume / lvl)
            self._remember(key)

    def set_mute(self, key: str, muted: bool) -> None:
        with self._lock:
            if self.backend.set_app_mute(key, muted) and key in self.apps:
                self.apps[key].muted = muted
            self._remember(key)

    def set_master(self, volume: float, muted: Optional[bool] = None) -> None:
        with self._lock:
            if self.backend.set_master(volume, muted):
                self.master_volume = volume
                if muted is not None:
                    self.master_muted = muted

    def set_output(self, device_id: str) -> None:
        with self._lock:
            self.backend.set_default_output(device_id)
            self.outputs = self.backend.list_outputs()

    def _remember(self, key: str) -> None:
        if not self.settings.get("remember_volumes"):
            return
        a = self.apps.get(key)
        if a is None:
            return
        vol = self._pre_duck.get(key, a.volume) if self.ducking_active else a.volume
        mem = dict(self.settings.get("remembered", {}))
        mem[key] = {"volume": round(vol, 3), "muted": a.muted}
        self.settings.set("remembered", mem)

    # ------------------------------------------------------------------ profiles
    def profile_names(self) -> List[str]:
        return list(self.settings.get("profiles", {}).keys())

    def apply_profile(self, name: str) -> None:
        prof = self.settings.get("profiles", {}).get(name)
        if prof is None:
            return
        with self._lock:
            for key, vol in prof.items():
                if key in self.apps:
                    self.set_volume(key, float(vol))
        self.settings.set("active_profile", name)
        self._emit()

    def save_profile(self, name: str) -> None:
        with self._lock:
            snapshot = {k: round(self._pre_duck.get(k, a.volume) if self.ducking_active else a.volume, 3)
                        for k, a in self.apps.items()}
        profs = dict(self.settings.get("profiles", {}))
        profs[name] = snapshot
        self.settings.set("profiles", profs)
        self.settings.set("active_profile", name)
        self._emit()

    def delete_profile(self, name: str) -> None:
        profs = dict(self.settings.get("profiles", {}))
        profs.pop(name, None)
        self.settings.set("profiles", profs)
        if self.settings.get("active_profile") == name:
            self.settings.set("active_profile", "")
        self._emit()

    # ------------------------------------------------------------------ ducking
    def _duck_cfg(self) -> dict:
        return self.settings.get("ducking", {})

    def _is_call(self, key: str) -> bool:
        k = key.lower()
        return any(c in k for c in self._duck_cfg().get("call_apps", []))

    def _is_duckable(self, key: str) -> bool:
        if self._is_call(key):
            return False
        if self._duck_cfg().get("duck_all"):
            return key != "system"
        k = key.lower()
        return any(m in k for m in self._duck_cfg().get("media_apps", []))

    def _tick_ducking(self) -> None:
        cfg = self._duck_cfg()
        if not cfg.get("enabled"):
            if self.ducking_active:
                self._unduck()
            return
        # A call is "active" when a call app has a live audio session that is actually producing sound
        # (peak > 0) if the backend reports peaks; otherwise merely having a session counts.
        call_live = False
        for key, a in self.apps.items():
            if self._is_call(key) and a.active:
                if self.backend.supports_peak:
                    if a.peak > 0.01:
                        call_live = True
                        break
                else:
                    call_live = True
                    break
        if call_live and not self.ducking_active:
            self._duck()
        elif not call_live and self.ducking_active:
            # small hysteresis so a brief silence in the call does not bounce volumes
            self._silence_since = getattr(self, "_silence_since", None) or time.time()
            if time.time() - self._silence_since > 4.0:
                self._unduck()
        elif call_live:
            self._silence_since = None
        if self.ducking_active:
            # catch media apps that appeared mid-call
            lvl = cfg.get("level", 0.25)
            for key, a in self.apps.items():
                if self._is_duckable(key) and key not in self._pre_duck:
                    self._pre_duck[key] = a.volume
                    target = a.volume * lvl
                    self.backend.set_app_volume(key, target)
                    a.volume = target

    def _duck(self) -> None:
        lvl = self._duck_cfg().get("level", 0.25)
        self._pre_duck = {}
        for key, a in self.apps.items():
            if self._is_duckable(key):
                self._pre_duck[key] = a.volume
                target = a.volume * lvl
                self.backend.set_app_volume(key, target)
                a.volume = target
        self.ducking_active = True
        self._silence_since = None
        log.info("ducking ON (%d apps)", len(self._pre_duck))

    def _unduck(self) -> None:
        for key, vol in self._pre_duck.items():
            if key in self.apps:
                self.backend.set_app_volume(key, vol)
                self.apps[key].volume = vol
        self._pre_duck = {}
        self.ducking_active = False
        log.info("ducking OFF")

    def force_duck(self, on: bool) -> None:
        with self._lock:
            if on and not self.ducking_active:
                self._duck()
            elif not on and self.ducking_active:
                self._unduck()
        self._emit()
