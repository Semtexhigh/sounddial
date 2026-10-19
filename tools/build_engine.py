#!/usr/bin/env python3
"""Freeze engine.py into a single sidecar binary for Tauri.

    python tools/build_engine.py            -> src-tauri/binaries/sounddial-engine-<target-triple>[.exe]

Tauri expects sidecars named with the Rust target triple. We ask rustc for it
(falls back to a platform guess). Needs: pip install pyinstaller plus the
platform package (pycaw on Windows, pulsectl on Linux, pyobjc-core on macOS is optional).
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src-tauri" / "binaries"
OUT.mkdir(parents=True, exist_ok=True)


def target_triple() -> str:
    try:
        out = subprocess.check_output(["rustc", "-vV"], text=True)
        for line in out.splitlines():
            if line.startswith("host:"):
                return line.split(":", 1)[1].strip()
    except Exception:
        pass
    m = platform.machine().lower()
    if sys.platform == "darwin":
        return ("aarch64" if m in ("arm64", "aarch64") else "x86_64") + "-apple-darwin"
    if sys.platform.startswith("win"):
        return ("aarch64" if m in ("arm64", "aarch64") else "x86_64") + "-pc-windows-msvc"
    return ("aarch64" if m in ("arm64", "aarch64") else "x86_64") + "-unknown-linux-gnu"


def main() -> int:
    triple = target_triple()
    name = f"sounddial-engine-{triple}"
    hidden = ["sounddial.backends.demo", "sounddial.backends.macos", "sounddial.backends.windows", "sounddial.backends.linux"]
    if sys.platform.startswith("win"):
        hidden += ["pycaw", "pycaw.pycaw", "pycaw.constants", "comtypes", "comtypes.client", "psutil", "PIL", "PIL.Image"]
    elif sys.platform.startswith("linux"):
        hidden += ["pulsectl"]
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--console",
           "--name", name, "--distpath", str(OUT), "--workpath", str(ROOT / "build" / "engine"),
           "--specpath", str(ROOT / "build"), "--paths", str(ROOT),
           "--add-data", f"{ROOT / 'sounddial.html'}{';' if sys.platform.startswith('win') else ':'}."]
    for h in hidden:
        cmd += ["--hidden-import", h]
    for ex in ("PySide6", "PyQt5", "PyQt6", "tkinter", "matplotlib", "numpy", "scipy", "pandas"):
        cmd += ["--exclude-module", ex]
    cmd.append(str(ROOT / "engine.py"))
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)
    produced = OUT / (name + (".exe" if sys.platform.startswith("win") else ""))
    if not produced.exists():
        print("build failed: no output at", produced)
        return 1
    print("OK ->", produced, f"({produced.stat().st_size // 1024} KB)")
    # keep the repo-relative HTML discoverable when frozen: engine.py already looks next to itself
    shutil.rmtree(ROOT / "build", ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
