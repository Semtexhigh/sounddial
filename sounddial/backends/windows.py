"""Windows backend — WASAPI audio sessions through pycaw / comtypes.

* Per-app volume : ISimpleAudioVolume on each audio session (0 .. 100 %)
* Per-app mute   : ISimpleAudioVolume.SetMute
* Peak meter     : IAudioMeterInformation on the session
* Master volume  : IAudioEndpointVolume on the default render endpoint
* Output switch  : undocumented but widely used IPolicyConfig.SetDefaultEndpoint

Windows session volume is a multiplier of the master, capped at 100 %, so
max_gain is 1.0 here. (Boosting above 100 % on Windows would require an APO
or a loopback re-render, which SoundDial deliberately does not do.)
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional

from .base import AudioApp, AudioBackend, OutputDevice, pretty_name

log = logging.getLogger("sounddial.windows")

try:  # pragma: no cover - only importable on Windows
    import comtypes
    from comtypes import CLSCTX_ALL, GUID, COMMETHOD, HRESULT, IUnknown
    from ctypes import POINTER, c_wchar_p, c_int
    from pycaw.pycaw import (
        AudioUtilities,
        IAudioEndpointVolume,
        IAudioMeterInformation,
        ISimpleAudioVolume,
    )
    from pycaw.constants import EDataFlow, ERole
    _AVAILABLE = True
except Exception as exc:  # pragma: no cover
    _AVAILABLE = False
    _IMPORT_ERROR = exc


def available() -> bool:
    return os.name == "nt" and _AVAILABLE


if _AVAILABLE:  # pragma: no cover - Windows only
    # ---- IPolicyConfig (used by every "set default audio device" utility on Windows)
    class IPolicyConfig(IUnknown):
        _iid_ = GUID("{f8679f50-850a-41e1-9c0a-7a2e9f3c3a7d}")
        _methods_ = [
            COMMETHOD([], HRESULT, "GetMixFormat", (["in"], c_wchar_p), (["out"], POINTER(c_int))),
            COMMETHOD([], HRESULT, "GetDeviceFormat", (["in"], c_wchar_p), (["in"], c_int), (["out"], POINTER(c_int))),
            COMMETHOD([], HRESULT, "ResetDeviceFormat", (["in"], c_wchar_p)),
            COMMETHOD([], HRESULT, "SetDeviceFormat", (["in"], c_wchar_p), (["in"], c_int), (["in"], c_int)),
            COMMETHOD([], HRESULT, "GetProcessingPeriod", (["in"], c_wchar_p), (["in"], c_int), (["out"], POINTER(c_int)), (["out"], POINTER(c_int))),
            COMMETHOD([], HRESULT, "SetProcessingPeriod", (["in"], c_wchar_p), (["in"], c_int)),
            COMMETHOD([], HRESULT, "GetShareMode", (["in"], c_wchar_p), (["out"], POINTER(c_int))),
            COMMETHOD([], HRESULT, "SetShareMode", (["in"], c_wchar_p), (["in"], c_int)),
            COMMETHOD([], HRESULT, "GetPropertyValue", (["in"], c_wchar_p), (["in"], c_int), (["out"], POINTER(c_int))),
            COMMETHOD([], HRESULT, "SetPropertyValue", (["in"], c_wchar_p), (["in"], c_int), (["in"], c_int)),
            COMMETHOD([], HRESULT, "SetDefaultEndpoint", (["in"], c_wchar_p, "wszDeviceId"), (["in"], c_int, "eRole")),
            COMMETHOD([], HRESULT, "SetEndpointVisibility", (["in"], c_wchar_p), (["in"], c_int)),
        ]

    CLSID_PolicyConfigClient = GUID("{870af99c-171d-4f9e-af0d-e63df40c2bc9}")


class WindowsBackend(AudioBackend):
    name = "windows"
    max_gain = 1.0
    supports_output_switch = True
    supports_peak = True

    def __init__(self) -> None:
        super().__init__()
        self._sessions: dict[str, list] = {}   # key -> [session, ...] (one app may have several)
        self._endpoint = None

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        if not available():
            self.last_error = "pycaw/comtypes not available"
            return
        try:
            comtypes.CoInitialize()
        except Exception:
            pass
        try:
            dev = AudioUtilities.GetSpeakers()
            iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            self._endpoint = iface.QueryInterface(IAudioEndpointVolume)
        except Exception as exc:
            self.last_error = f"endpoint: {exc}"
            log.exception("endpoint volume unavailable")

    def stop(self) -> None:
        self._sessions.clear()
        self._endpoint = None

    # ------------------------------------------------------------------ apps
    def _impl_list_apps(self) -> List[AudioApp]:
        self._sessions = {}
        result: dict[str, AudioApp] = {}
        for s in AudioUtilities.GetAllSessions():
            proc = s.Process
            if proc is None:
                # System sounds session — show it, people like to mute it
                key, nm, pid = "system", "System Sounds", 0
            else:
                try:
                    exe = proc.name()
                except Exception:
                    continue
                key, nm, pid = exe.lower(), pretty_name(exe), proc.pid
            sv = s._ctl.QueryInterface(ISimpleAudioVolume)
            vol = float(sv.GetMasterVolume())
            muted = bool(sv.GetMute())
            peak = 0.0
            try:
                meter = s._ctl.QueryInterface(IAudioMeterInformation)
                peak = float(meter.GetPeakValue())
            except Exception:
                pass
            self._sessions.setdefault(key, []).append(sv)
            if key in result:
                result[key].peak = max(result[key].peak, peak)
                continue
            icon = None
            try:
                icon = proc.exe() if proc is not None else None
            except Exception:
                pass
            result[key] = AudioApp(key=key, name=nm, pid=pid, volume=vol, muted=muted,
                                   peak=peak, icon_path=icon, active=True)
        return list(result.values())

    def _impl_set_app_volume(self, key: str, volume: float) -> bool:
        ok = False
        for sv in self._sessions.get(key, []):
            sv.SetMasterVolume(min(1.0, volume), None)
            ok = True
        return ok

    def _impl_set_app_mute(self, key: str, muted: bool) -> bool:
        ok = False
        for sv in self._sessions.get(key, []):
            sv.SetMute(1 if muted else 0, None)
            ok = True
        return ok

    # ------------------------------------------------------------------ master
    def _impl_get_master(self) -> tuple[float, bool]:
        if self._endpoint is None:
            return (1.0, False)
        return (float(self._endpoint.GetMasterVolumeLevelScalar()), bool(self._endpoint.GetMute()))

    def _impl_set_master(self, volume: float, muted: Optional[bool]) -> bool:
        if self._endpoint is None:
            return False
        self._endpoint.SetMasterVolumeLevelScalar(volume, None)
        if muted is not None:
            self._endpoint.SetMute(1 if muted else 0, None)
        return True

    def _impl_list_outputs(self) -> List[OutputDevice]:
        out: List[OutputDevice] = []
        try:
            default_id = AudioUtilities.GetSpeakers().GetId()
        except Exception:
            default_id = ""
        for d in AudioUtilities.GetAllDevices():
            try:
                if d.state != 1:          # DEVICE_STATE_ACTIVE
                    continue
                # pycaw returns both capture and render devices; keep render only
                if getattr(d, "DataFlow", None) not in (None, 0) and str(d.DataFlow) not in ("0", "EDataFlow.eRender"):
                    continue
                out.append(OutputDevice(id=d.id, name=d.FriendlyName, is_default=(d.id == default_id)))
            except Exception:
                continue
        return out

    def _impl_set_default_output(self, device_id: str) -> bool:
        pc = comtypes.CoCreateInstance(CLSID_PolicyConfigClient, IPolicyConfig, CLSCTX_ALL)
        for role in (0, 1, 2):   # eConsole, eMultimedia, eCommunications
            pc.SetDefaultEndpoint(device_id, role)
        self.start()             # re-bind endpoint volume to the new default
        return True
