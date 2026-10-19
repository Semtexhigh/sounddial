# PyInstaller spec — builds SoundDial for the current OS.
#   pip install pyinstaller
#   pyinstaller packaging/sounddial.spec
# Output: dist/SoundDial.app (macOS) · dist/SoundDial/SoundDial.exe (Windows) · dist/SoundDial/SoundDial (Linux)

import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
block_cipher = None

datas = [(str(ROOT / "assets" / "icons"), "assets/icons")]
binaries = []
if sys.platform == "darwin":
    helper = ROOT / "macos_helper" / "SoundDialHelper"
    if helper.exists():
        datas.append((str(helper), "macos_helper"))
    datas.append((str(ROOT / "macos_helper" / "SoundDialHelper.swift"), "macos_helper"))

hidden = ["sounddial.backends.windows", "sounddial.backends.linux", "sounddial.backends.macos", "sounddial.backends.demo"]
if sys.platform.startswith("win"):
    hidden += ["pycaw", "pycaw.pycaw", "comtypes", "psutil"]
elif sys.platform.startswith("linux"):
    hidden += ["pulsectl"]
elif sys.platform == "darwin":
    hidden += ["AppKit", "Foundation", "objc"]

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
              "PySide6.QtCharts", "PySide6.QtMultimedia", "PySide6.QtQml", "PySide6.QtQuick"],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

icon = None
if sys.platform == "darwin":
    icon = str(ROOT / "assets" / "icons" / "sounddial.icns")
elif sys.platform.startswith("win"):
    icon = str(ROOT / "assets" / "icons" / "sounddial.ico")

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="SoundDial",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=icon,
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, strip=False, upx=False, name="SoundDial")

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="SoundDial.app",
        icon=icon,
        bundle_identifier="com.sounddial.app",
        info_plist={
            "CFBundleName": "SoundDial",
            "CFBundleDisplayName": "SoundDial",
            "CFBundleShortVersionString": "1.0.0",
            "LSUIElement": True,                 # menu-bar only, no Dock icon
            "LSMinimumSystemVersion": "14.2",
            "NSHighResolutionCapable": True,
            "NSAudioCaptureUsageDescription": "SoundDial taps each app's audio to control its volume independently. Audio never leaves your Mac.",
        },
    )
