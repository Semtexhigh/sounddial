#!/bin/bash
# SoundDial — macOS installer. Run with:
#   curl -fsSL https://semtexhigh.github.io/sounddial/install.sh | bash
# Downloads the latest build straight into /Applications. Files fetched this way carry no
# quarantine flag, so Gatekeeper never shows the "damaged" / "cannot verify" dialog.
set -u
REPO="Semtexhigh/sounddial"
APP="/Applications/SoundDial.app"
ARCH="$(uname -m)"
case "$ARCH" in arm64) ASSET="SoundDial_aarch64.app.tar.gz";; *) ASSET="SoundDial_x64.app.tar.gz";; esac
TMP="$(mktemp -d /tmp/sounddial.XXXXXX)"
echo "SoundDial installer ($ARCH)"
TAG="$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" 2>/dev/null | sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p' | head -1)"
[ -n "$TAG" ] || TAG="v1.0.1"
URL="https://github.com/$REPO/releases/download/$TAG/$ASSET"
echo "Downloading $TAG ..."
if ! curl -fL --progress-bar -o "$TMP/app.tgz" "$URL"; then echo "Download failed: $URL"; exit 1; fi
echo "Installing to /Applications ..."
pkill -x sounddial 2>/dev/null; pkill -f "SoundDial.app" 2>/dev/null; sleep 1
if [ -d "$APP" ]; then rm -rf "$APP" 2>/dev/null || sudo rm -rf "$APP"; fi
if ! tar -xzf "$TMP/app.tgz" -C /Applications 2>/dev/null; then sudo tar -xzf "$TMP/app.tgz" -C /Applications || { echo "Could not write to /Applications"; exit 1; }; fi
xattr -cr "$APP" 2>/dev/null || true
codesign --force --deep --sign - "$APP" 2>/dev/null || sudo codesign --force --deep --sign - "$APP" 2>/dev/null || true
rm -rf "$TMP"
echo "Signature: $(codesign --verify --deep --strict "$APP" 2>&1 && echo valid)"
echo "Quarantine: $(xattr -p com.apple.quarantine "$APP" 2>/dev/null || echo none)"
open "$APP"
sleep 4
if pgrep -x sounddial >/dev/null 2>&1; then
  echo "SoundDial is running — look for the dial icon in the menu bar."
else
  echo "SoundDial did not stay running. Diagnostics:"
  sw_vers 2>/dev/null
  CR="$(ls -t ~/Library/Logs/DiagnosticReports/sounddial* 2>/dev/null | head -1)"
  if [ -n "$CR" ]; then echo "--- crash report: $CR"; head -40 "$CR"; fi
  log show --last 2m --predicate 'process == "sounddial" OR process == "sounddial-engine"' --style compact 2>/dev/null | tail -30
fi
