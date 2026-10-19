#!/usr/bin/env bash
# Linux: builds dist/SoundDial/SoundDial and installs a .desktop launcher for the current user.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m pip install --quiet --upgrade --break-system-packages pyinstaller PySide6 pulsectl pillow || \
python3 -m pip install --quiet --upgrade pyinstaller PySide6 pulsectl pillow
python3 tools/make_icons.py
pyinstaller --noconfirm --clean packaging/sounddial.spec
mkdir -p ~/.local/share/applications ~/.local/share/icons/hicolor/256x256/apps
cp assets/icons/sounddial-256.png ~/.local/share/icons/hicolor/256x256/apps/sounddial.png
sed "s|__EXEC__|$(pwd)/dist/SoundDial/SoundDial|" packaging/sounddial.desktop > ~/.local/share/applications/sounddial.desktop
echo "Built: dist/SoundDial/SoundDial  (launcher installed in your app menu)"
