"""Demo backend — simulated apps so the UI can be previewed / tested anywhere.

Activated with ``--demo`` or automatically when no real backend works.
"""

from __future__ import annotations

import math
import time
from typing import List, Optional

import os
from .base import AudioApp, AudioBackend, OutputDevice

DEMO_ICON_DIR = os.environ.get("SOUNDDIAL_DEMO_ICONS", "")  # testing hook: dir of <key>.png


class DemoBackend(AudioBackend):
    name = "demo"
    max_gain = 2.0
    supports_output_switch = True
    supports_peak = True

    def __init__(self) -> None:
        super().__init__()
        self._apps = {
            "spotify": AudioApp("spotify", "Spotify", 4101, 0.8),
            "chrome": AudioApp("chrome", "Google Chrome", 4120, 1.0),
            "zoom": AudioApp("zoom", "Zoom", 4182, 1.0),
            "discord": AudioApp("discord", "Discord", 4210, 0.6, muted=True),
            "music": AudioApp("music", "Music", 4290, 1.25),
            "system": AudioApp("system", "System Sounds", 0, 0.5),
        }
        self._master = [0.72, False]
        self._outputs = [
            OutputDevice("built-in", "MacBook Pro Speakers", True),
            OutputDevice("airpods", "AirPods Pro", False),
            OutputDevice("hdmi", "LG UltraFine (HDMI)", False),
        ]
        self._t0 = time.time()
        if DEMO_ICON_DIR:
            for k, a in self._apps.items():
                cand = os.path.join(DEMO_ICON_DIR, k + ".png")
                if os.path.exists(cand):
                    a.icon_path = cand

    def _impl_list_apps(self) -> List[AudioApp]:
        t = time.time() - self._t0
        out = []
        for i, a in enumerate(self._apps.values()):
            if a.muted or a.volume == 0:
                a.peak = 0.0
            else:
                a.peak = max(0.0, min(1.0, (0.45 + 0.4 * math.sin(t * (1.3 + i * 0.37)) + 0.1 * math.sin(t * 7 + i)) * min(1.0, a.volume)))
            out.append(a)
        return out

    def _impl_set_app_volume(self, key: str, volume: float) -> bool:
        if key in self._apps:
            self._apps[key].volume = volume
            return True
        return False

    def _impl_set_app_mute(self, key: str, muted: bool) -> bool:
        if key in self._apps:
            self._apps[key].muted = muted
            return True
        return False

    def _impl_get_master(self) -> tuple[float, bool]:
        return (self._master[0], self._master[1])

    def _impl_set_master(self, volume: float, muted: Optional[bool]) -> bool:
        self._master[0] = volume
        if muted is not None:
            self._master[1] = muted
        return True

    def _impl_list_outputs(self) -> List[OutputDevice]:
        return list(self._outputs)

    def _impl_set_default_output(self, device_id: str) -> bool:
        for o in self._outputs:
            o.is_default = (o.id == device_id)
        return True
