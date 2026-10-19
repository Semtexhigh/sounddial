#!/usr/bin/env python3
"""SoundDial Engine — the small local service behind the HTML app.

A web page cannot touch other apps' audio, so this engine does the native work
(WASAPI / PulseAudio / Core Audio taps via the Swift helper) and exposes it to
``sounddial.html`` on 127.0.0.1 only:

    GET  /                 the HTML app itself (so http://127.0.0.1:47800 just works)
    GET  /state            current JSON state (apps, master, outputs, ducking)
    GET  /events           Server-Sent Events stream of the same state (push, ~8 Hz)
    GET  /icon/<key>       app icon as PNG (or 404)
    POST /cmd              {"cmd": "set_volume", "key": "...", "volume": 1.25} etc.

Usage:
    python engine.py            start engine (binds 127.0.0.1:47800)
    python engine.py --open     start and open the app in the default browser
    python engine.py --demo     simulated apps
    python engine.py --port N

No third-party packages are needed for the engine itself (stdlib HTTP server).
The platform backend packages install themselves on first run (pycaw / pulsectl).
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import logging
import os
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from sounddial.mixer import Mixer  # noqa: E402
from sounddial.settings import Settings  # noqa: E402
from sounddial import __version__  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
log = logging.getLogger("sounddial.engine")

def _html_file() -> Path:
    cands = [ROOT / "sounddial.html"]
    if getattr(sys, "frozen", False):
        cands.insert(0, Path(getattr(sys, "_MEIPASS", ROOT)) / "sounddial.html")
    for c in cands:
        if c.exists():
            return c
    return cands[0]


HTML_FILE = _html_file()
DEFAULT_PORT = 47800


# ----------------------------------------------------------------------------- icons
class IconService:
    """Best-effort app icons as PNG bytes. Falls back to None (the page draws a monogram)."""

    def __init__(self) -> None:
        self.cache: dict[str, Optional[bytes]] = {}
        self._lock = threading.Lock()

    def get(self, key: str, icon_path: Optional[str]) -> Optional[bytes]:
        with self._lock:
            if key in self.cache:
                return self.cache[key]
        data = None
        try:
            data = self._load(icon_path)
        except Exception as exc:
            log.debug("icon %s: %s", key, exc)
        with self._lock:
            self.cache[key] = data
        return data

    def _load(self, path: Optional[str]) -> Optional[bytes]:
        if not path:
            return None
        p = Path(path)
        low = path.lower()
        if p.exists() and low.endswith(".png"):
            return p.read_bytes()
        if p.exists() and low.endswith((".ico", ".icns", ".jpg", ".jpeg", ".bmp")):
            from PIL import Image  # pillow is optional; only needed for conversion
            im = Image.open(p)
            if low.endswith(".ico") and getattr(im, "info", {}).get("sizes"):
                im.size = max(im.info["sizes"], key=lambda s: s[0])  # pick the largest frame
            im = im.convert("RGBA").resize((64, 64))
            buf = io.BytesIO()
            im.save(buf, "PNG")
            return buf.getvalue()
        if sys.platform.startswith("win") and low.endswith(".exe") and p.exists():
            return self._windows_exe_icon(p)
        if sys.platform.startswith("linux"):
            return self._linux_theme_icon(path)
        return None

    @staticmethod
    def _windows_exe_icon(p: Path) -> Optional[bytes]:
        """Extract the large icon from an .exe using win32 APIs (ctypes) and encode as PNG via Pillow."""
        import ctypes
        from ctypes import wintypes
        from PIL import Image
        shell32, user32, gdi32 = ctypes.windll.shell32, ctypes.windll.user32, ctypes.windll.gdi32
        large = (wintypes.HICON * 1)()
        n = shell32.ExtractIconExW(str(p), 0, large, None, 1)
        if n < 1 or not large[0]:
            return None
        hicon = large[0]
        try:
            class ICONINFO(ctypes.Structure):
                _fields_ = [("fIcon", wintypes.BOOL), ("xHotspot", wintypes.DWORD), ("yHotspot", wintypes.DWORD),
                            ("hbmMask", wintypes.HBITMAP), ("hbmColor", wintypes.HBITMAP)]
            info = ICONINFO()
            if not user32.GetIconInfo(hicon, ctypes.byref(info)):
                return None

            class BITMAP(ctypes.Structure):
                _fields_ = [("bmType", wintypes.LONG), ("bmWidth", wintypes.LONG), ("bmHeight", wintypes.LONG),
                            ("bmWidthBytes", wintypes.LONG), ("bmPlanes", wintypes.WORD), ("bmBitsPixel", wintypes.WORD),
                            ("bmBits", ctypes.c_void_p)]
            bm = BITMAP()
            gdi32.GetObjectW(info.hbmColor, ctypes.sizeof(BITMAP), ctypes.byref(bm))
            w, h = bm.bmWidth, bm.bmHeight
            size = w * h * 4
            buf = ctypes.create_string_buffer(size)

            class BITMAPINFOHEADER(ctypes.Structure):
                _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                            ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                            ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                            ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]
            bih = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, size, 0, 0, 0, 0)
            hdc = user32.GetDC(None)
            gdi32.GetDIBits(hdc, info.hbmColor, 0, h, buf, ctypes.byref(bih), 0)
            user32.ReleaseDC(None, hdc)
            gdi32.DeleteObject(info.hbmColor)
            gdi32.DeleteObject(info.hbmMask)
            im = Image.frombuffer("RGBA", (w, h), buf.raw, "raw", "BGRA", 0, 1)
            if not any(px[3] for px in list(im.getdata())[:: max(1, (w * h) // 64)]):
                im.putalpha(255)
            out = io.BytesIO()
            im.resize((64, 64)).save(out, "PNG")
            return out.getvalue()
        finally:
            user32.DestroyIcon(hicon)

    @staticmethod
    def _linux_theme_icon(name: str) -> Optional[bytes]:
        roots = [Path.home() / ".local/share/icons", Path("/usr/share/icons"), Path("/usr/share/pixmaps"),
                 Path("/var/lib/flatpak/exports/share/icons"), Path.home() / ".local/share/flatpak/exports/share/icons"]
        for root in roots:
            if not root.exists():
                continue
            for size in ("64x64", "128x128", "48x48", "256x256", "scalable"):
                for cand in root.glob(f"*/{size}/apps/{name}.png"):
                    return cand.read_bytes()
            for cand in root.glob(f"{name}.png"):
                return cand.read_bytes()
        return None


# ----------------------------------------------------------------------------- engine
class Engine:
    def __init__(self, demo: bool) -> None:
        self.settings = Settings()
        self.mixer = Mixer(self.settings, demo=demo)
        self.icons = IconService()
        self._subs: list[threading.Event] = []
        self._subs_lock = threading.Lock()
        self.mixer.on_change(self._wake)
        self.mixer.start()

    def _wake(self) -> None:
        with self._subs_lock:
            for ev in self._subs:
                ev.set()

    def subscribe(self) -> threading.Event:
        ev = threading.Event()
        with self._subs_lock:
            self._subs.append(ev)
        return ev

    def unsubscribe(self, ev: threading.Event) -> None:
        with self._subs_lock:
            if ev in self._subs:
                self._subs.remove(ev)

    def state(self) -> dict:
        m = self.mixer
        apps = []
        for a in sorted(m.apps.values(), key=lambda a: (a.key == "system", a.name.lower())):
            apps.append({
                "key": a.key, "name": a.name, "pid": a.pid, "volume": round(a.volume, 4), "muted": a.muted,
                "peak": round(a.peak, 3), "active": a.active, "hasIcon": bool(a.icon_path),
                "call": m._is_call(a.key), "ducked": m.ducking_active and a.key in m._pre_duck,
            })
        return {
            "version": __version__, "backend": m.backend.name, "maxGain": m.backend.max_gain,
            "outputSwitch": m.backend.supports_output_switch, "peaks": m.backend.supports_peak,
            "degraded": bool(getattr(m.backend, "degraded", False)), "error": m.backend.last_error or "",
            "apps": apps,
            "master": {"volume": round(m.master_volume, 4), "muted": m.master_muted},
            "outputs": [{"id": o.id, "name": o.name, "default": o.is_default} for o in m.outputs],
            "ducking": {"active": m.ducking_active, **self.settings.get("ducking", {})},
            "profiles": self.settings.get("profiles", {}), "activeProfile": self.settings.get("active_profile", ""),
            "uiDoc": self.settings.get("ui_doc"),
            "ts": time.time(),
        }

    def command(self, msg: dict) -> dict:
        m = self.mixer
        c = msg.get("cmd")
        try:
            if c == "set_volume":
                m.set_volume(str(msg["key"]), float(msg["volume"]))
            elif c == "set_mute":
                m.set_mute(str(msg["key"]), bool(msg["muted"]))
            elif c == "set_master":
                m.set_master(float(msg.get("volume", m.master_volume)), msg.get("muted"))
            elif c == "set_output":
                m.set_output(str(msg["id"]))
            elif c == "apply_profile":
                m.apply_profile(str(msg["name"]))
            elif c == "save_profile":
                m.save_profile(str(msg["name"]))
            elif c == "delete_profile":
                m.delete_profile(str(msg["name"]))
            elif c == "set_ducking":
                d = dict(self.settings.get("ducking", {}))
                for k in ("enabled", "level", "duck_all", "call_apps", "media_apps"):
                    if k in msg:
                        d[k] = msg[k]
                self.settings.set("ducking", d)
            elif c == "force_duck":
                m.force_duck(bool(msg.get("on")))
            elif c == "reset_all":
                for k in list(m.apps):
                    m.set_volume(k, 1.0)
            elif c == "unmute_all":
                for k in list(m.apps):
                    m.set_mute(k, False)
            elif c == "set_setting":
                self.settings.set(str(msg["key"]), msg.get("value"))
            elif c == "refresh":
                m.refresh()
            elif c == "ping":
                return {"ok": True, "pong": True}
            else:
                return {"ok": False, "error": f"unknown cmd {c}"}
            m.refresh()
            return {"ok": True}
        except Exception as exc:
            log.exception("command failed")
            return {"ok": False, "error": str(exc)}

    def icon_png(self, key: str) -> Optional[bytes]:
        a = self.mixer.apps.get(key)
        return self.icons.get(key, a.icon_path if a else None)


# ----------------------------------------------------------------------------- HTTP
def make_handler(engine: Engine):
    class H(BaseHTTPRequestHandler):
        server_version = "SoundDialEngine/" + __version__

        def log_message(self, fmt, *args):  # quiet
            log.debug(fmt, *args)

        def _cors(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

        def _json(self, obj, code=200):
            data = json.dumps(obj).encode()
            self.send_response(code)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_OPTIONS(self):
            self.send_response(204)
            self._cors()
            self.end_headers()

        def do_GET(self):
            path = urlparse(self.path).path
            if path in ("/", "/index.html", "/sounddial.html"):
                if HTML_FILE.exists():
                    data = HTML_FILE.read_bytes()
                    self.send_response(200)
                    self._cors()
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                else:
                    self._json({"error": "sounddial.html not found next to engine.py"}, 404)
            elif path == "/state":
                self._json(engine.state())
            elif path == "/events":
                self.send_response(200)
                self._cors()
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                ev = engine.subscribe()
                try:
                    last = 0.0
                    while True:
                        ev.wait(0.12)
                        ev.clear()
                        now = time.time()
                        if now - last < 0.1:
                            continue
                        last = now
                        payload = json.dumps(engine.state())
                        self.wfile.write(f"data: {payload}\n\n".encode())
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
                finally:
                    engine.unsubscribe(ev)
            elif path.startswith("/icon/"):
                key = unquote(path[6:])
                png = engine.icon_png(key)
                if png:
                    self.send_response(200)
                    self._cors()
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Cache-Control", "max-age=600")
                    self.send_header("Content-Length", str(len(png)))
                    self.end_headers()
                    self.wfile.write(png)
                else:
                    self._json({"error": "no icon"}, 404)
            elif path == "/health":
                self._json({"ok": True, "version": __version__, "backend": engine.mixer.backend.name})
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self):
            path = urlparse(self.path).path
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b"{}"
            try:
                msg = json.loads(raw.decode("utf-8") or "{}")
            except Exception:
                return self._json({"ok": False, "error": "bad json"}, 400)
            if path == "/cmd":
                return self._json(engine.command(msg))
            if path == "/quit":
                threading.Thread(target=lambda: (time.sleep(0.2), os._exit(0)), daemon=True).start()
                return self._json({"ok": True})
            self._json({"error": "not found"}, 404)

    return H


def _pid_alive(pid: int) -> bool:
    try:
        if sys.platform.startswith("win"):
            import ctypes
            h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if not h:
                return False
            code = ctypes.c_ulong()
            ok = ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
            ctypes.windll.kernel32.CloseHandle(h)
            return bool(ok) and code.value == 259  # STILL_ACTIVE
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _watch_parent(pid: int) -> None:
    while True:
        time.sleep(2)
        if not _pid_alive(pid):
            log.info("parent %s gone — exiting", pid)
            os._exit(0)


def ensure_backend_deps() -> None:
    need = []
    if sys.platform.startswith("win"):
        for mod, pipn in (("pycaw", "pycaw"), ("comtypes", "comtypes"), ("psutil", "psutil"), ("PIL", "pillow")):
            try:
                __import__(mod)
            except Exception:
                need.append(pipn)
    elif sys.platform.startswith("linux"):
        try:
            import pulsectl  # noqa: F401
        except Exception:
            need.append("pulsectl")
    if need:
        log.info("installing %s", " ".join(need))
        for flags in (["--user", "--quiet", "--break-system-packages"], ["--user", "--quiet"], ["--quiet"]):
            try:
                subprocess.run([sys.executable, "-m", "pip", "install", *flags, *need], check=True)
                break
            except Exception:
                continue


def main() -> int:
    ap = argparse.ArgumentParser(description="SoundDial engine")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--open", action="store_true", help="open the app in the browser")
    ap.add_argument("--no-install", action="store_true")
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--parent-pid", type=int, default=0, help="exit when this process disappears (used by the desktop app)")
    args = ap.parse_args()
    if args.parent_pid:
        threading.Thread(target=_watch_parent, args=(args.parent_pid,), daemon=True).start()
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    if not args.no_install and not args.demo:
        ensure_backend_deps()
    engine = Engine(demo=args.demo)
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(engine))
    srv.daemon_threads = True
    url = f"http://127.0.0.1:{args.port}/"
    log.info("SoundDial engine %s · backend=%s · %s", __version__, engine.mixer.backend.name, url)
    if args.open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        engine.mixer.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
