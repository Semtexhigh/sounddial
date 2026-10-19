#!/usr/bin/env python3
"""SoundDial launcher.

    python main.py              start the tray app
    python main.py --demo       simulated apps (works anywhere, no audio needed)
    python main.py --minimized  start hidden in the tray (used by launch-at-login)
    python main.py --selftest   check backend + dependencies and exit
    python main.py --cli        tiny command-line mixer (no Qt)

Dependencies are installed automatically on first run (PySide6 everywhere,
pycaw on Windows, pulsectl on Linux). Use --no-install to disable that.
"""

from __future__ import annotations

import argparse
import importlib
import logging
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

if sys.version_info < (3, 9):
    sys.exit("SoundDial needs Python 3.9 or newer.")

LOG_FILE = Path.home() / ".sounddial.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stderr), logging.FileHandler(LOG_FILE, encoding="utf-8")],
)
log = logging.getLogger("sounddial.main")


def _required() -> list[tuple[str, str]]:
    """(import name, pip name)"""
    req = [("PySide6", "PySide6")]
    if sys.platform.startswith("win"):
        req += [("pycaw", "pycaw"), ("comtypes", "comtypes"), ("psutil", "psutil")]
    elif sys.platform.startswith("linux"):
        req += [("pulsectl", "pulsectl")]
    elif sys.platform == "darwin":
        req += [("AppKit", "pyobjc-framework-Cocoa")]
    return req


def ensure_dependencies(auto_install: bool = True) -> bool:
    missing = []
    for mod, pip_name in _required():
        try:
            importlib.import_module(mod)
        except Exception:
            missing.append(pip_name)
    if not missing:
        return True
    if not auto_install:
        print("Missing packages: " + " ".join(missing))
        print(f"Install with:  {sys.executable} -m pip install " + " ".join(missing))
        # Only the UI toolkit is mandatory; without a platform package we fall back to demo mode.
        return "PySide6" not in missing
    print("SoundDial: installing " + ", ".join(missing) + " …")
    cmd = [sys.executable, "-m", "pip", "install", "--user", "--quiet"] + missing
    if sys.platform.startswith("linux") or sys.platform == "darwin":
        cmd.insert(5, "--break-system-packages")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError:
        # retry without the flags some pips reject
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "--quiet"] + missing, check=True)
        except subprocess.CalledProcessError as exc:
            print(f"pip failed ({exc}). Install manually:\n  {sys.executable} -m pip install " + " ".join(missing))
            return "PySide6" not in missing
    importlib.invalidate_caches()
    return True


def selftest() -> int:
    print(f"Python {sys.version.split()[0]} on {sys.platform}")
    ok = ensure_dependencies(auto_install=False)
    print("Dependencies:", "OK" if ok else "MISSING")
    from sounddial.backends import create_backend
    b = create_backend()
    print(f"Backend: {b.name}  max_gain={b.max_gain}  output_switch={b.supports_output_switch}  peak={b.supports_peak}")
    if b.last_error:
        print("Backend note:", b.last_error)
    apps = b.list_apps()
    print(f"Audio apps now: {len(apps)}")
    for a in apps:
        print(f"  - {a.name:<28} {int(a.volume*100):>4}%  {'muted' if a.muted else ''}")
    vol, muted = b.get_master()
    print(f"Master: {int(vol*100)}% {'muted' if muted else ''}")
    outs = b.list_outputs()
    for o in outs:
        print(f"  output: {'*' if o.is_default else ' '} {o.name}")
    b.stop()
    return 0 if ok else 1


def cli() -> int:
    from sounddial.backends import create_backend
    b = create_backend()
    print("SoundDial CLI — commands: list | set <app> <percent> | mute <app> | unmute <app> | master <percent> | quit")
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue
        parts = line.split()
        c = parts[0].lower()
        if c in ("q", "quit", "exit"):
            break
        if c == "list":
            for a in b.list_apps():
                print(f"  {a.key:<22} {a.name:<24} {int(a.volume*100):>4}% {'muted' if a.muted else ''}")
        elif c == "set" and len(parts) == 3:
            b.list_apps()
            print("ok" if b.set_app_volume(parts[1], float(parts[2]) / 100) else "no such app")
        elif c in ("mute", "unmute") and len(parts) == 2:
            b.list_apps()
            print("ok" if b.set_app_mute(parts[1], c == "mute") else "no such app")
        elif c == "master" and len(parts) == 2:
            print("ok" if b.set_master(float(parts[1]) / 100) else "failed")
        else:
            print("?")
    b.stop()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="SoundDial — per-app volume mixer")
    ap.add_argument("--demo", action="store_true", help="simulated apps (no real audio)")
    ap.add_argument("--minimized", action="store_true", help="start hidden in the tray")
    ap.add_argument("--selftest", action="store_true", help="check backend and exit")
    ap.add_argument("--cli", action="store_true", help="command-line mixer, no GUI")
    ap.add_argument("--no-install", action="store_true", help="never pip install missing packages")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.selftest:
        return selftest()
    if args.cli:
        return cli()
    if not ensure_dependencies(auto_install=not args.no_install):
        return 1

    # single instance guard
    from PySide6.QtCore import QLockFile, QDir
    lock = QLockFile(os.path.join(QDir.tempPath(), "sounddial.lock"))
    if not lock.tryLock(100):
        print("SoundDial is already running.")
        return 0

    from sounddial.ui.app import SoundDialApp
    app = SoundDialApp(demo=args.demo, start_minimized=args.minimized)
    return app.run()


if __name__ == "__main__":
    sys.exit(main())
