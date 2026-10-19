"""Launch-at-login for macOS (LaunchAgent), Windows (Run key) and Linux (XDG autostart)."""

from __future__ import annotations

import logging
import os
import plistlib
import sys
from pathlib import Path

log = logging.getLogger("sounddial.autostart")

LABEL = "com.sounddial.app"


def _launch_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable]
    main = Path(__file__).resolve().parent.parent / "main.py"
    return [sys.executable, str(main), "--minimized"]


def is_enabled() -> bool:
    try:
        if sys.platform == "darwin":
            return (Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist").exists()
        if sys.platform.startswith("win"):
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
                try:
                    winreg.QueryValueEx(k, "SoundDial")
                    return True
                except FileNotFoundError:
                    return False
        return (Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "autostart" / "sounddial.desktop").exists()
    except Exception:
        return False


def set_enabled(enabled: bool) -> bool:
    try:
        cmd = _launch_command()
        if sys.platform == "darwin":
            p = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
            if enabled:
                p.parent.mkdir(parents=True, exist_ok=True)
                with open(p, "wb") as fh:
                    plistlib.dump({"Label": LABEL, "ProgramArguments": cmd, "RunAtLoad": True,
                                   "ProcessType": "Interactive"}, fh)
            elif p.exists():
                p.unlink()
            return True
        if sys.platform.startswith("win"):
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run",
                                0, winreg.KEY_SET_VALUE) as k:
                if enabled:
                    exe = cmd[0]
                    if not getattr(sys, "frozen", False):
                        exe = exe.replace("python.exe", "pythonw.exe")
                    value = " ".join(f'"{c}"' for c in [exe] + cmd[1:])
                    winreg.SetValueEx(k, "SoundDial", 0, winreg.REG_SZ, value)
                else:
                    try:
                        winreg.DeleteValue(k, "SoundDial")
                    except FileNotFoundError:
                        pass
            return True
        p = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "autostart" / "sounddial.desktop"
        if enabled:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("[Desktop Entry]\nType=Application\nName=SoundDial\n"
                         f"Exec={' '.join(cmd)}\nIcon=sounddial\nX-GNOME-Autostart-enabled=true\n"
                         "Comment=Per-app volume mixer\n", encoding="utf-8")
        elif p.exists():
            p.unlink()
        return True
    except Exception as exc:
        log.warning("autostart change failed: %s", exc)
        return False
