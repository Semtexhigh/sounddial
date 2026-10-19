"""The menu-bar / tray popover: master output, app sliders, profiles, ducking."""

from __future__ import annotations

import sys
from typing import Dict

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QInputDialog, QLabel, QMenu,
                               QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from ..mixer import Mixer
from .themes import build_qss, theme
from .widgets import AppRow, VolumeSlider, dial_icon, speaker_icon


class Popover(QWidget):
    settingsRequested = Signal()
    quitRequested = Signal()

    def __init__(self, mixer: Mixer) -> None:
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.mixer = mixer
        self.settings = mixer.settings
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, False)
        self.rows: Dict[str, AppRow] = {}
        self.t = theme(self.settings.get("theme", "mono"), self.settings.get("accent"))
        self._build()
        self.apply_theme()
        self._peak_timer = QTimer(self)
        self._peak_timer.setInterval(int(self.settings.get("peak_ms", 90)))
        self._peak_timer.timeout.connect(self._tick_peaks)
        mixer.on_change(self._schedule_refresh)
        self._refresh_pending = False

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.root = QWidget()
        self.root.setObjectName("Root")
        outer.addWidget(self.root)
        lay = QVBoxLayout(self.root)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)

        # header
        head = QHBoxLayout()
        self.logo = QLabel()
        head.addWidget(self.logo)
        title = QLabel("SoundDial")
        title.setObjectName("Title")
        head.addWidget(title)
        head.addStretch(1)
        self.duck_badge = QLabel("DUCKING")
        self.duck_badge.setObjectName("BadgeOn")
        self.duck_badge.hide()
        head.addWidget(self.duck_badge)
        self.profile_btn = QPushButton("Profiles")
        self.profile_btn.setObjectName("Chip")
        self.profile_btn.clicked.connect(self._profiles_menu)
        head.addWidget(self.profile_btn)
        self.more_btn = QPushButton("⋯")
        self.more_btn.setObjectName("Chip")
        self.more_btn.setFixedWidth(34)
        self.more_btn.clicked.connect(self._more_menu)
        head.addWidget(self.more_btn)
        lay.addLayout(head)

        # master card
        self.master_card = QFrame()
        self.master_card.setObjectName("Card")
        mc = QVBoxLayout(self.master_card)
        mc.setContentsMargins(10, 8, 10, 8)
        mc.setSpacing(6)
        top = QHBoxLayout()
        sec = QLabel("OUTPUT")
        sec.setObjectName("Section")
        top.addWidget(sec)
        top.addStretch(1)
        self.master_pct = QLabel("100%")
        self.master_pct.setObjectName("Pct")
        top.addWidget(self.master_pct)
        mc.addLayout(top)
        row = QHBoxLayout()
        row.setSpacing(10)
        self.master_mute = QPushButton()
        self.master_mute.setObjectName("Icon")
        self.master_mute.setCheckable(True)
        self.master_mute.setToolTip("Mute output")
        self.master_mute.setIconSize(QSize(16, 16))
        self.master_mute.clicked.connect(self._on_master_mute)
        row.addWidget(self.master_mute)
        self.master_slider = VolumeSlider(1.0)
        self.master_slider.valueChanged.connect(self._on_master_slide)
        row.addWidget(self.master_slider, 1)
        mc.addLayout(row)
        self.output_combo = QComboBox()
        self.output_combo.currentIndexChanged.connect(self._on_output_changed)
        mc.addWidget(self.output_combo)
        lay.addWidget(self.master_card)

        # apps
        apps_head = QHBoxLayout()
        sec2 = QLabel("APPLICATIONS")
        sec2.setObjectName("Section")
        apps_head.addWidget(sec2)
        apps_head.addStretch(1)
        self.count_lbl = QLabel("")
        self.count_lbl.setObjectName("Hint")
        apps_head.addWidget(self.count_lbl)
        lay.addLayout(apps_head)

        self.apps_card = QFrame()
        self.apps_card.setObjectName("Card")
        ac = QVBoxLayout(self.apps_card)
        ac.setContentsMargins(0, 0, 0, 0)
        ac.setSpacing(0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.apps_box = QWidget()
        self.apps_lay = QVBoxLayout(self.apps_box)
        self.apps_lay.setContentsMargins(0, 0, 0, 0)
        self.apps_lay.setSpacing(0)
        self.empty = QLabel("Nothing is playing audio right now.")
        self.empty.setObjectName("Hint")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setContentsMargins(10, 18, 10, 18)
        self.apps_lay.addWidget(self.empty)
        self.apps_lay.addStretch(1)
        self.scroll.setWidget(self.apps_box)
        ac.addWidget(self.scroll)
        lay.addWidget(self.apps_card, 1)

        # footer
        foot = QHBoxLayout()
        self.status = QLabel("")
        self.status.setObjectName("Hint")
        foot.addWidget(self.status, 1)
        self.settings_btn = QPushButton("Settings")
        self.settings_btn.setObjectName("Flat")
        self.settings_btn.clicked.connect(self.settingsRequested.emit)
        foot.addWidget(self.settings_btn)
        self.quit_btn = QPushButton("Quit")
        self.quit_btn.setObjectName("Flat")
        self.quit_btn.clicked.connect(self.quitRequested.emit)
        foot.addWidget(self.quit_btn)
        lay.addLayout(foot)

    # ------------------------------------------------------------------ theme
    def apply_theme(self) -> None:
        self.t = theme(self.settings.get("theme", "mono"), self.settings.get("accent"))
        self.setStyleSheet(build_qss(self.t))
        self.master_slider.t = self.t
        self.master_slider.show_vu = False
        for r in self.rows.values():
            r.t = self.t
            r.slider.t = self.t
            r.slider.show_vu = bool(self.settings.get("show_vu", True))
            r.refresh_icon()
        self.logo.setPixmap(dial_icon(self.t["accent"], 20).pixmap(20, 20))
        self._update_master_icon()
        w = int(self.settings.get("popover_width", 380))
        self.setFixedWidth(max(300, w))
        self.update()

    def _update_master_icon(self) -> None:
        col = self.t.get("fg2") if not self.mixer.master_muted else self.t.get("fg3")
        self.master_mute.setIcon(speaker_icon(col, self.mixer.master_volume, self.mixer.master_muted))

    # ------------------------------------------------------------------ refresh
    def _schedule_refresh(self) -> None:
        if not self._refresh_pending:
            self._refresh_pending = True
            QTimer.singleShot(0, self.refresh)

    def refresh(self) -> None:
        self._refresh_pending = False
        m = self.mixer
        if not self.master_slider._dragging:
            self.master_slider.setValue(m.master_volume)
        self.master_slider.setMuted(m.master_muted)
        self.master_mute.setChecked(m.master_muted)
        self.master_pct.setText("Muted" if m.master_muted else f"{int(round(m.master_volume * 100))}%")
        self._update_master_icon()

        # outputs
        self.output_combo.blockSignals(True)
        self.output_combo.clear()
        cur = 0
        if m.backend.supports_output_switch and m.outputs:
            for i, o in enumerate(m.outputs):
                self.output_combo.addItem(o.name, o.id)
                if o.is_default:
                    cur = i
            self.output_combo.setCurrentIndex(cur)
            self.output_combo.show()
        else:
            self.output_combo.hide()
        self.output_combo.blockSignals(False)

        # apps
        compact = bool(self.settings.get("compact", False))
        seen = set()
        apps = sorted(m.apps.values(), key=lambda a: (a.key == "system", a.name.lower()))
        for a in apps:
            seen.add(a.key)
            row = self.rows.get(a.key)
            if row is None:
                row = AppRow(a.key, a.name, m.backend.max_gain, self.t, compact)
                row.slider.show_vu = bool(self.settings.get("show_vu", True))
                row.volumeChanged.connect(self._on_app_volume)
                row.muteToggled.connect(self._on_app_mute)
                self.rows[a.key] = row
                self.apps_lay.insertWidget(self.apps_lay.count() - 1, row)
            badge = ""
            if m.ducking_active and a.key in m._pre_duck:
                badge = "DUCKED"
            elif m._is_call(a.key):
                badge = "CALL"
            elif a.volume > 1.0:
                badge = "BOOST"
            row.set_state(a.volume, a.muted, a.peak, badge)
        for key in list(self.rows):
            if key not in seen:
                row = self.rows.pop(key)
                self.apps_lay.removeWidget(row)
                row.deleteLater()
        self.empty.setVisible(not self.rows)
        self.count_lbl.setText(f"{len(self.rows)} active" if self.rows else "")
        self.duck_badge.setVisible(m.ducking_active)
        ap = self.settings.get("active_profile") or ""
        self.profile_btn.setText(ap if ap else "Profiles")
        err = m.backend.last_error
        if m.backend.name == "demo":
            self.status.setText("Demo mode — simulated apps")
        elif getattr(m.backend, "degraded", False):
            self.status.setText("Master volume only — see Settings › About")
        elif err:
            self.status.setText(err[:60])
        else:
            self.status.setText("")

        rows_h = sum(r.sizeHint().height() for r in self.rows.values()) or self.empty.sizeHint().height()
        target = min(int(QGuiApplication.primaryScreen().availableGeometry().height() * 0.75), rows_h + 215)
        self.setFixedHeight(max(220, target))

    def _tick_peaks(self) -> None:
        # Fast-path: only update meters without rebuilding rows.
        for key, row in self.rows.items():
            a = self.mixer.apps.get(key)
            if a is not None:
                row.slider.setPeak(a.peak if not a.muted else 0.0)

    # ------------------------------------------------------------------ handlers
    def _on_app_volume(self, key: str, v: float) -> None:
        self.mixer.set_volume(key, v)

    def _on_app_mute(self, key: str, muted: bool) -> None:
        self.mixer.set_mute(key, muted)

    def _on_master_slide(self, v: float) -> None:
        self.master_pct.setText(f"{int(round(v * 100))}%")
        self.mixer.set_master(v)

    def _on_master_mute(self) -> None:
        self.mixer.set_master(self.mixer.master_volume, self.master_mute.isChecked())
        self._update_master_icon()

    def _on_output_changed(self, idx: int) -> None:
        dev = self.output_combo.itemData(idx)
        if dev:
            self.mixer.set_output(dev)

    def _profiles_menu(self) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(self.styleSheet())
        active = self.settings.get("active_profile") or ""
        for name in self.mixer.profile_names():
            act = menu.addAction(("● " if name == active else "   ") + name)
            act.triggered.connect(lambda _=False, n=name: self.mixer.apply_profile(n))
        menu.addSeparator()
        menu.addAction("Save current as…").triggered.connect(self._save_profile)
        if active:
            menu.addAction(f"Update “{active}”").triggered.connect(lambda: self.mixer.save_profile(active))
            menu.addAction(f"Delete “{active}”").triggered.connect(lambda: self.mixer.delete_profile(active))
        menu.exec(self.profile_btn.mapToGlobal(QPoint(0, self.profile_btn.height() + 4)))

    def _save_profile(self) -> None:
        name, ok = QInputDialog.getText(self, "Save profile", "Profile name:")
        if ok and name.strip():
            self.mixer.save_profile(name.strip())

    def _more_menu(self) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(self.styleSheet())
        d = menu.addAction("Auto-ducking")
        d.setCheckable(True)
        d.setChecked(bool(self.settings.get("ducking", {}).get("enabled")))
        d.triggered.connect(self._toggle_ducking)
        f = menu.addAction("Duck now (manual)")
        f.setCheckable(True)
        f.setChecked(self.mixer.ducking_active)
        f.triggered.connect(lambda on: self.mixer.force_duck(on))
        menu.addSeparator()
        menu.addAction("Reset all apps to 100%").triggered.connect(self._reset_all)
        menu.addAction("Unmute all").triggered.connect(self._unmute_all)
        menu.addSeparator()
        th = menu.addMenu("Theme")
        from .themes import THEMES
        cur = self.settings.get("theme", "mono")
        for key, t in THEMES.items():
            a = th.addAction(("● " if key == cur else "   ") + t["label"])
            a.triggered.connect(lambda _=False, k=key: self._set_theme(k))
        menu.addSeparator()
        menu.addAction("Settings…").triggered.connect(self.settingsRequested.emit)
        menu.addAction("Quit SoundDial").triggered.connect(self.quitRequested.emit)
        menu.exec(self.more_btn.mapToGlobal(QPoint(0, self.more_btn.height() + 4)))

    def _toggle_ducking(self, on: bool) -> None:
        d = dict(self.settings.get("ducking", {}))
        d["enabled"] = bool(on)
        self.settings.set("ducking", d)
        self.mixer.refresh()

    def _set_theme(self, key: str) -> None:
        self.settings.set("theme", key)
        self.apply_theme()
        self.refresh()

    def _reset_all(self) -> None:
        for key in list(self.mixer.apps):
            self.mixer.set_volume(key, 1.0)
        self.mixer.refresh()

    def _unmute_all(self) -> None:
        for key in list(self.mixer.apps):
            self.mixer.set_mute(key, False)
        self.mixer.refresh()

    # ------------------------------------------------------------------ show/hide
    def toggle_at(self, anchor: QRect | None) -> None:
        if self.isVisible():
            self.hide()
            return
        self.refresh()
        screen = QGuiApplication.screenAt(anchor.center()) if anchor and not anchor.isNull() else QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        w, h = self.width(), self.height()
        if anchor and not anchor.isNull():
            x = anchor.center().x() - w // 2
            top_bar = anchor.center().y() < geo.center().y()
            y = anchor.bottom() + 6 if top_bar else anchor.top() - h - 6
        else:  # no tray geometry (e.g. Wayland/GNOME): bottom-right corner
            x, y = geo.right() - w - 12, geo.bottom() - h - 12
        x = max(geo.left() + 6, min(x, geo.right() - w - 6))
        y = max(geo.top() + 6, min(y, geo.bottom() - h - 6))
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        self._peak_timer.start()

    def hideEvent(self, e) -> None:
        self._peak_timer.stop()
        super().hideEvent(e)

    def event(self, e) -> bool:
        if e.type() == QEvent.WindowDeactivate and self.isVisible():
            # close when clicking away, like a real menu-bar popover
            QTimer.singleShot(80, self._hide_if_inactive)
        return super().event(e)

    def _hide_if_inactive(self) -> None:
        if not self.isActiveWindow() and self.isVisible():
            self.hide()

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(e)
