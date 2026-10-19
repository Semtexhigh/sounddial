"""Linux backend — PulseAudio / PipeWire (via pipewire-pulse) through pulsectl.

* Per-app volume : sink-input volume (can exceed 100 %, so max_gain = 2.0)
* Per-app mute   : sink-input mute
* Peak meter     : not polled (would need a monitor stream per input) — off
* Master volume  : default sink volume + mute
* Output switch  : set default sink and move every sink-input to it
"""

from __future__ import annotations

import logging
import sys
from typing import List, Optional

from .base import AudioApp, AudioBackend, OutputDevice, pretty_name

log = logging.getLogger("sounddial.linux")

try:
    import pulsectl  # type: ignore
    _AVAILABLE = True
except Exception:  # pragma: no cover
    _AVAILABLE = False


def available() -> bool:
    return sys.platform.startswith("linux") and _AVAILABLE


class LinuxBackend(AudioBackend):
    name = "linux"
    max_gain = 2.0
    supports_output_switch = True
    supports_peak = False

    def __init__(self) -> None:
        super().__init__()
        self._pulse = None
        self._inputs: dict[str, list] = {}

    def start(self) -> None:
        if not available():
            self.last_error = "pulsectl not available (needs PulseAudio or pipewire-pulse)"
            return
        try:
            self._pulse = pulsectl.Pulse("SoundDial")
        except Exception as exc:
            self.last_error = f"cannot connect to PulseAudio/PipeWire: {exc}"
            self._pulse = None

    def stop(self) -> None:
        if self._pulse is not None:
            try:
                self._pulse.close()
            except Exception:
                pass
        self._pulse = None

    def _ensure(self):
        if self._pulse is None:
            self.start()
        return self._pulse

    # ------------------------------------------------------------------ apps
    def _impl_list_apps(self) -> List[AudioApp]:
        p = self._ensure()
        if p is None:
            return []
        self._inputs = {}
        result: dict[str, AudioApp] = {}
        for si in p.sink_input_list():
            props = si.proplist or {}
            raw = (props.get("application.name") or props.get("application.process.binary")
                   or props.get("media.name") or si.name or "Unknown")
            binary = props.get("application.process.binary", raw)
            key = str(binary).lower()
            pid = int(props.get("application.process.id", 0) or 0)
            vol = float(si.volume.value_flat)
            self._inputs.setdefault(key, []).append(si)
            if key in result:
                continue
            icon = props.get("application.icon_name")
            result[key] = AudioApp(key=key, name=pretty_name(str(raw)), pid=pid, volume=vol,
                                   muted=bool(si.mute), icon_path=icon, active=True)
        return list(result.values())

    def _impl_set_app_volume(self, key: str, volume: float) -> bool:
        p = self._ensure()
        ok = False
        for si in self._inputs.get(key, []):
            p.volume_set_all_chans(si, volume)
            ok = True
        return ok

    def _impl_set_app_mute(self, key: str, muted: bool) -> bool:
        p = self._ensure()
        ok = False
        for si in self._inputs.get(key, []):
            p.mute(si, muted)
            ok = True
        return ok

    # ------------------------------------------------------------------ master
    def _default_sink(self):
        p = self._ensure()
        name = p.server_info().default_sink_name
        for s in p.sink_list():
            if s.name == name:
                return s
        sinks = p.sink_list()
        return sinks[0] if sinks else None

    def _impl_get_master(self) -> tuple[float, bool]:
        s = self._default_sink()
        if s is None:
            return (1.0, False)
        return (min(1.0, float(s.volume.value_flat)), bool(s.mute))

    def _impl_set_master(self, volume: float, muted: Optional[bool]) -> bool:
        p = self._ensure()
        s = self._default_sink()
        if s is None:
            return False
        p.volume_set_all_chans(s, volume)
        if muted is not None:
            p.mute(s, muted)
        return True

    def _impl_list_outputs(self) -> List[OutputDevice]:
        p = self._ensure()
        if p is None:
            return []
        default = p.server_info().default_sink_name
        return [OutputDevice(id=s.name, name=s.description or s.name, is_default=(s.name == default))
                for s in p.sink_list()]

    def _impl_set_default_output(self, device_id: str) -> bool:
        p = self._ensure()
        target = None
        for s in p.sink_list():
            if s.name == device_id:
                target = s
        if target is None:
            return False
        p.sink_default_set(target)
        for si in p.sink_input_list():
            try:
                p.sink_input_move(si.index, target.index)
            except Exception:
                pass
        return True
