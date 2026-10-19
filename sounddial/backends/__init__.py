"""Backend factory — picks the right implementation for this OS."""

from __future__ import annotations

import logging
import sys

from .base import AudioApp, AudioBackend, OutputDevice  # noqa: F401
from .demo import DemoBackend

log = logging.getLogger("sounddial.backends")


def create_backend(force_demo: bool = False) -> AudioBackend:
    if force_demo:
        b = DemoBackend()
        b.start()
        return b

    backend: AudioBackend | None = None
    try:
        if sys.platform == "darwin":
            from .macos import MacOSBackend
            backend = MacOSBackend()
        elif sys.platform.startswith("win"):
            from .windows import WindowsBackend, available
            if available():
                backend = WindowsBackend()
        elif sys.platform.startswith("linux"):
            from .linux import LinuxBackend, available
            if available():
                backend = LinuxBackend()
    except Exception:
        log.exception("backend import failed")

    if backend is None:
        log.warning("no native backend available — using demo backend")
        backend = DemoBackend()
    backend.start()
    if backend.last_error:
        log.warning("backend %s: %s", backend.name, backend.last_error)
    return backend
