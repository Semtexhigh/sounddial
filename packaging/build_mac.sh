#!/usr/bin/env bash
# macOS: builds the Swift helper, then SoundDial.app with PyInstaller.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m pip install --quiet --upgrade pyinstaller PySide6 pyobjc-framework-Cocoa
bash macos_helper/build_helper.sh
python3 tools/make_icons.py
pyinstaller --noconfirm --clean packaging/sounddial.spec
codesign --force --deep --sign - dist/SoundDial.app
echo "Built: dist/SoundDial.app  (drag to /Applications)"
