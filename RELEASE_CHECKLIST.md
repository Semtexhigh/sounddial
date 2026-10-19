# SoundDial — release checklist

1. Code lives at `github.com/Semtexhigh/sounddial` (nothing in the tree carries a real name; LICENSE credits the Semtexhigh account).
2. Tag a version (`git tag v1.0.0 && git push --tags`, or GitHub → Releases → Draft a new release → tag `v1.0.0` → Publish) → the **release** workflow builds:
   - macOS Apple Silicon `.dmg` (macos-14 runner)
   - macOS Intel `.dmg` (macos-13 runner)
   - Windows `-setup.exe` (NSIS)
   - Linux `.AppImage` + `.deb`
   and attaches them to the Release. Unsigned macOS by design.
3. Settings → Pages → deploy from `main`, folder `/site` → the download page auto-picks the right installer.
4. To bump: edit `version` in `src-tauri/tauri.conf.json`, `src-tauri/Cargo.toml`, `package.json`, `sounddial/__init__.py`; tag again.

Download-only: the site never links to source. If the source must be hidden too, make the repo private and host the
installers on Pages (`site/dl/`) instead — a private repo hides its Releases from the public.
