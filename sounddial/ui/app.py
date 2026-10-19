"""Qt application: tray icon, popover, settings, global wiring."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from .. import __app_name__, __version__
from ..mixer import Mixer
from ..settings import Settings
from .popover import Popover
from .settings_dialog import SettingsDialog
from .themes import theme
from .widgets import dial_icon

log = logging.getLogger("sounddial.app")

ASSETS = Path(__file__).resolve().parent.parent.parent / "assets" / "icons"


def _app_icon() -> QIcon:
    for name in ("sounddial.png", "sounddial-256.png", "sounddial.ico", "sounddial.icns"):
        p = ASSETS / name
        if p.exists():
            ic = QIcon(str(p))
            if not ic.isNull():
                return ic
    return dial_icon("#FFFFFF", 128, bg="#111111")


def _tray_icon(t: dict, muted: bool = False) -> QIcon:
    """Tray glyphs are drawn live in the theme colour. On macOS a template-style
    (black) icon lets the menu bar invert it automatically for light/dark bars."""
    if sys.platform == "darwin":
        ic = dial_icon("#000000", 18)
        ic.setIsMask(True)
        return ic
    p = ASSETS / ("tray-mono-muted.png" if muted else "tray-mono.png")
    if p.exists():
        return QIcon(str(p))
    return dial_icon(t.get("fg", "#FFFFFF"), 20)


class SoundDialApp:
    def __init__(self, demo: bool = False, start_minimized: bool = False) -> None:
        self.qapp = QApplication.instance() or QApplication(sys.argv)
        self.qapp.setApplicationName(__app_name__)
        self.qapp.setApplicationVersion(__version__)
        self.qapp.setQuitOnLastWindowClosed(False)
        self.qapp.setWindowIcon(_app_icon())
        if sys.platform == "darwin":
            # Menu-bar app: hide the Dock icon
            try:
                from AppKit import NSApp, NSApplicationActivationPolicyAccessory  # type: ignore
                NSApp.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
            except Exception:
                pass

        self.settings = Settings()
        self.mixer = Mixer(self.settings, demo=demo)
        self.popover = Popover(self.mixer)
        self.popover.settingsRequested.connect(self.open_settings)
        self.popover.quitRequested.connect(self.quit)
        self._settings_dlg: SettingsDialog | None = None

        self.tray = QSystemTrayIcon()
        self._update_tray_icon()
        self.tray.setToolTip("SoundDial — per-app volume")
        self.tray.activated.connect(self._tray_activated)
        self.tray.setContextMenu(self._context_menu())
        self.tray.show()
        self.mixer.on_change(lambda: QTimer.singleShot(0, self._update_tray_icon))
        self.mixer.start()

        if not QSystemTrayIcon.isSystemTrayAvailable():
            log.warning("no system tray — opening popover as a window")
            self.popover.toggle_at(None)
        elif not start_minimized:
            QTimer.singleShot(400, lambda: self.popover.toggle_at(self.tray.geometry()))

    # ------------------------------------------------------------------ tray
    def _context_menu(self) -> QMenu:
        m = QMenu()
        a = QAction("Open SoundDial", m)
        a.triggered.connect(lambda: self.popover.toggle_at(self.tray.geometry()))
        m.addAction(a)
        s = QAction("Settings…", m)
        s.triggered.connect(self.open_settings)
        m.addAction(s)
        m.addSeparator()
        q = QAction("Quit", m)
        q.triggered.connect(self.quit)
        m.addAction(q)
        return m

    def _tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick, QSystemTrayIcon.MiddleClick):
            self.popover.toggle_at(self.tray.geometry())

    def _update_tray_icon(self) -> None:
        t = theme(self.settings.get("theme", "mono"), self.settings.get("accent"))
        self.tray.setIcon(_tray_icon(t, self.mixer.master_muted))

    # ------------------------------------------------------------------ settings
    def open_settings(self) -> None:
        self.popover.hide()
        if self._settings_dlg is None:
            self._settings_dlg = SettingsDialog(self.mixer, self._on_theme_change)
            self._settings_dlg.setWindowIcon(_app_icon())
        self._settings_dlg.show()
        self._settings_dlg.raise_()
        self._settings_dlg.activateWindow()

    def _on_theme_change(self) -> None:
        self.popover.apply_theme()
        # rebuild rows so compact/VU options take effect
        for key, row in list(self.popover.rows.items()):
            self.popover.apps_lay.removeWidget(row)
            row.deleteLater()
        self.popover.rows.clear()
        self.popover.refresh()
        self._update_tray_icon()

    def quit(self) -> None:
        try:
            self.mixer.stop()
        finally:
            self.qapp.quit()

    def run(self) -> int:
        return self.qapp.exec()
