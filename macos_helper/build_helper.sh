#!/usr/bin/env bash
# Builds SoundDialHelper (macOS 14.2+). Needs Xcode Command Line Tools: xcode-select --install
set -euo pipefail
cd "$(dirname "$0")"
echo "Compiling SoundDialHelper…"
swiftc -O -target arm64-apple-macos14.2 -framework CoreAudio -framework AudioToolbox -framework AppKit \
       -o SoundDialHelper-arm64 SoundDialHelper.swift
swiftc -O -target x86_64-apple-macos14.2 -framework CoreAudio -framework AudioToolbox -framework AppKit \
       -o SoundDialHelper-x86_64 SoundDialHelper.swift
lipo -create SoundDialHelper-arm64 SoundDialHelper-x86_64 -output SoundDialHelper
rm -f SoundDialHelper-arm64 SoundDialHelper-x86_64
chmod +x SoundDialHelper
# ad-hoc sign so TCC keeps the audio-capture grant stable between runs
codesign --force --sign - --identifier com.sounddial.helper SoundDialHelper
echo "OK → $(pwd)/SoundDialHelper (universal)"
