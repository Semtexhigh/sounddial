"""Settings window — Appearance, Ducking, Profiles, General, About."""

from __future__ import annotations

import platform
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout,
                               QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
                               QMessageBox, QPushButton, QSlider, QSpinBox, QTabWidget,
                               QTextEdit, QVBoxLayout, QWidget)

from .. import __version__
from .. import autostart
from ..mixer import Mixer
from .themes import ACCENTS, THEMES, build_qss, theme


class SettingsDialog(QDialog):
    def __init__(self, mixer: Mixer, on_theme_change, parent=None) -> None:
        super().__init__(parent)
        self.mixer = mixer
        self.s = mixer.settings
        self.on_theme_change = on_theme_change
        self.setWindowTitle("SoundDial Settings")
        self.setMinimumSize(520, 460)
        self._build()
        self.apply_theme()

    def apply_theme(self) -> None:
        t = theme(self.s.get("theme", "mono"), self.s.get("accent"))
        self.setStyleSheet(build_qss(t) + f"QDialog {{ background: {t['bg']}; }} QWidget#Root {{ border: none; }}")

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        lay.addWidget(tabs)
        tabs.addTab(self._appearance_tab(), "Appearance")
        tabs.addTab(self._ducking_tab(), "Auto-Ducking")
        tabs.addTab(self._profiles_tab(), "Profiles")
        tabs.addTab(self._general_tab(), "General")
        tabs.addTab(self._about_tab(), "About")
        btns = QHBoxLayout()
        btns.addStretch(1)
        close = QPushButton("Close")
        close.setObjectName("Primary")
        close.clicked.connect(self.accept)
        btns.addWidget(close)
        lay.addLayout(btns)

    # ------------------------------------------------------------------ appearance
    def _appearance_tab(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        f.setLabelAlignment(Qt.AlignRight)
        self.theme_combo = QComboBox()
        for key, t in THEMES.items():
            self.theme_combo.addItem(t["label"], key)
        self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData(self.s.get("theme", "mono"))))
        self.theme_combo.currentIndexChanged.connect(self._theme_changed)
        f.addRow("Theme", self.theme_combo)

        self.accent_combo = QComboBox()
        for name, hexv in ACCENTS.items():
            self.accent_combo.addItem(name, hexv)
        idx = self.accent_combo.findData(self.s.get("accent"))
        self.accent_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.accent_combo.currentIndexChanged.connect(self._accent_changed)
        f.addRow("Accent (colour themes)", self.accent_combo)

        self.compact_cb = QCheckBox("Compact rows")
        self.compact_cb.setChecked(bool(self.s.get("compact")))
        self.compact_cb.toggled.connect(lambda v: self._set_and_refresh("compact", v))
        f.addRow("", self.compact_cb)
        self.vu_cb = QCheckBox("Show live level meters under sliders")
        self.vu_cb.setChecked(bool(self.s.get("show_vu", True)))
        self.vu_cb.toggled.connect(lambda v: self._set_and_refresh("show_vu", v))
        f.addRow("", self.vu_cb)

        self.width_spin = QSpinBox()
        self.width_spin.setRange(300, 640)
        self.width_spin.setSingleStep(10)
        self.width_spin.setValue(int(self.s.get("popover_width", 380)))
        self.width_spin.valueChanged.connect(lambda v: self._set_and_refresh("popover_width", v))
        f.addRow("Popover width (px)", self.width_spin)

        hint = QLabel("Mono is the default: pure greyscale, no colour. Colour themes use the accent above. "
                      "Terminal uses a monospace face.")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        f.addRow("", hint)
        return w

    def _theme_changed(self, idx: int) -> None:
        self.s.set("theme", self.theme_combo.itemData(idx))
        self.apply_theme()
        self.on_theme_change()

    def _accent_changed(self, idx: int) -> None:
        self.s.set("accent", self.accent_combo.itemData(idx))
        self.apply_theme()
        self.on_theme_change()

    def _set_and_refresh(self, key: str, v) -> None:
        self.s.set(key, v)
        self.on_theme_change()

    # ------------------------------------------------------------------ ducking
    def _ducking_tab(self) -> QWidget:
        w = QWidget()
        d = self.s.get("ducking", {})
        f = QFormLayout(w)
        self.duck_cb = QCheckBox("Lower media automatically when a call starts")
        self.duck_cb.setChecked(bool(d.get("enabled")))
        self.duck_cb.toggled.connect(lambda v: self._duck_set("enabled", v))
        f.addRow("", self.duck_cb)

        row = QHBoxLayout()
        self.duck_slider = QSlider(Qt.Horizontal)
        self.duck_slider.setRange(0, 100)
        self.duck_slider.setValue(int(round(float(d.get("level", 0.25)) * 100)))
        self.duck_lbl = QLabel(f"{self.duck_slider.value()}%")
        self.duck_lbl.setObjectName("Pct")
        self.duck_slider.valueChanged.connect(lambda v: (self.duck_lbl.setText(f"{v}%"), self._duck_set("level", v / 100.0)))
        row.addWidget(self.duck_slider, 1)
        row.addWidget(self.duck_lbl)
        f.addRow("Duck media to", row)

        self.duck_all_cb = QCheckBox("Duck every other app, not only media apps")
        self.duck_all_cb.setChecked(bool(d.get("duck_all")))
        self.duck_all_cb.toggled.connect(lambda v: self._duck_set("duck_all", v))
        f.addRow("", self.duck_all_cb)

        self.call_apps = QLineEdit(", ".join(d.get("call_apps", [])))
        self.call_apps.editingFinished.connect(lambda: self._duck_set("call_apps", self._split(self.call_apps.text())))
        f.addRow("Call apps", self.call_apps)
        self.media_apps = QLineEdit(", ".join(d.get("media_apps", [])))
        self.media_apps.editingFinished.connect(lambda: self._duck_set("media_apps", self._split(self.media_apps.text())))
        f.addRow("Media apps", self.media_apps)
        hint = QLabel("Match is case-insensitive on the app's process/bundle name. Ducking restores the original "
                      "volumes about 4 s after the call goes silent, so brief pauses don't bounce the music.")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        f.addRow("", hint)
        return w

    @staticmethod
    def _split(txt: str) -> list[str]:
        return [x.strip().lower() for x in txt.split(",") if x.strip()]

    def _duck_set(self, key: str, v) -> None:
        d = dict(self.s.get("ducking", {}))
        d[key] = v
        self.s.set("ducking", d)

    # ------------------------------------------------------------------ profiles
    def _profiles_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        self.prof_list = QListWidget()
        lay.addWidget(self.prof_list, 1)
        self.prof_detail = QTextEdit()
        self.prof_detail.setReadOnly(True)
        self.prof_detail.setMaximumHeight(110)
        lay.addWidget(self.prof_detail)
        row = QHBoxLayout()
        b_apply = QPushButton("Apply")
        b_apply.setObjectName("Primary")
        b_apply.clicked.connect(self._prof_apply)
        b_save = QPushButton("Save current as…")
        b_save.clicked.connect(self._prof_save)
        b_upd = QPushButton("Update selected")
        b_upd.clicked.connect(self._prof_update)
        b_ren = QPushButton("Rename")
        b_ren.clicked.connect(self._prof_rename)
        b_del = QPushButton("Delete")
        b_del.setObjectName("Danger")
        b_del.clicked.connect(self._prof_delete)
        for b in (b_apply, b_save, b_upd, b_ren, b_del):
            row.addWidget(b)
        lay.addLayout(row)
        self.prof_list.currentTextChanged.connect(self._prof_show)
        self._prof_reload()
        return w

    def _prof_reload(self) -> None:
        self.prof_list.clear()
        for n in self.mixer.profile_names():
            self.prof_list.addItem(n)
        if self.prof_list.count():
            self.prof_list.setCurrentRow(0)

    def _prof_show(self, name: str) -> None:
        prof = self.s.get("profiles", {}).get(name, {})
        self.prof_detail.setPlainText("\n".join(f"{k:<24} {int(round(v * 100))}%" for k, v in prof.items()) or "(empty)")

    def _sel(self) -> str:
        it = self.prof_list.currentItem()
        return it.text() if it else ""

    def _prof_apply(self) -> None:
        if self._sel():
            self.mixer.apply_profile(self._sel())

    def _prof_save(self) -> None:
        name, ok = QInputDialog.getText(self, "Save profile", "Profile name:")
        if ok and name.strip():
            self.mixer.save_profile(name.strip())
            self._prof_reload()

    def _prof_update(self) -> None:
        if self._sel():
            self.mixer.save_profile(self._sel())
            self._prof_show(self._sel())

    def _prof_rename(self) -> None:
        old = self._sel()
        if not old:
            return
        new, ok = QInputDialog.getText(self, "Rename profile", "New name:", text=old)
        if ok and new.strip() and new.strip() != old:
            profs = dict(self.s.get("profiles", {}))
            profs[new.strip()] = profs.pop(old)
            self.s.set("profiles", profs)
            if self.s.get("active_profile") == old:
                self.s.set("active_profile", new.strip())
            self._prof_reload()

    def _prof_delete(self) -> None:
        if self._sel() and QMessageBox.question(self, "Delete", f"Delete profile “{self._sel()}”?") == QMessageBox.Yes:
            self.mixer.delete_profile(self._sel())
            self._prof_reload()

    # ------------------------------------------------------------------ general
    def _general_tab(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self.login_cb = QCheckBox("Launch SoundDial at login")
        self.login_cb.setChecked(autostart.is_enabled())
        self.login_cb.toggled.connect(self._login_toggled)
        f.addRow("", self.login_cb)
        self.remember_cb = QCheckBox("Remember each app's volume across restarts")
        self.remember_cb.setChecked(bool(self.s.get("remember_volumes", True)))
        self.remember_cb.toggled.connect(lambda v: self.s.set("remember_volumes", v))
        f.addRow("", self.remember_cb)
        self.poll_spin = QSpinBox()
        self.poll_spin.setRange(200, 5000)
        self.poll_spin.setSingleStep(100)
        self.poll_spin.setSuffix(" ms")
        self.poll_spin.setValue(int(self.s.get("poll_ms", 800)))
        self.poll_spin.valueChanged.connect(lambda v: self.s.set("poll_ms", v))
        f.addRow("App list refresh", self.poll_spin)
        b = QPushButton("Forget remembered volumes")
        b.clicked.connect(lambda: self.s.set("remembered", {}))
        f.addRow("", b)
        b2 = QPushButton("Reset all settings")
        b2.setObjectName("Danger")
        b2.clicked.connect(self._reset_all)
        f.addRow("", b2)
        lbl = QLabel(f"Settings file: {self.s.path}")
        lbl.setObjectName("Hint")
        lbl.setWordWrap(True)
        f.addRow("", lbl)
        return w

    def _login_toggled(self, v: bool) -> None:
        if not autostart.set_enabled(v):
            QMessageBox.warning(self, "Launch at login", "Could not change the launch-at-login setting.")
            self.login_cb.blockSignals(True)
            self.login_cb.setChecked(autostart.is_enabled())
            self.login_cb.blockSignals(False)
        self.s.set("launch_at_login", autostart.is_enabled())

    def _reset_all(self) -> None:
        if QMessageBox.question(self, "Reset", "Reset every setting, profile and remembered volume?") == QMessageBox.Yes:
            self.s.reset()
            self.apply_theme()
            self.on_theme_change()
            self._prof_reload()

    # ------------------------------------------------------------------ about
    def _about_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        b = self.mixer.backend
        caps = []
        caps.append(f"Backend: {b.name}")
        caps.append(f"Max per-app gain: {int(b.max_gain * 100)}%")
        caps.append(f"Output switching: {'yes' if b.supports_output_switch else 'no'}")
        caps.append(f"Level meters: {'yes' if b.supports_peak else 'no'}")
        if b.last_error:
            caps.append(f"Note: {b.last_error}")
        txt = QTextEdit()
        txt.setReadOnly(True)
        txt.setPlainText(
            f"SoundDial {__version__}\nPer-app volume mixer for macOS, Windows and Linux.\n\n"
            f"Platform: {platform.system()} {platform.release()} · Python {sys.version.split()[0]}\n"
            + "\n".join(caps)
            + "\n\nHow it works\n"
              "• macOS: Core Audio process taps (macOS 14.2+) via the bundled SoundDialHelper. "
              "The helper captures each app's audio, mutes the original and re-renders it at your chosen gain (0–200%).\n"
              "• Windows: WASAPI audio sessions (ISimpleAudioVolume). Windows caps a session at 100%.\n"
              "• Linux: PulseAudio / PipeWire sink-inputs (0–200%).\n\n"
              "Shortcuts: double-click or right-click a slider to reset to 100% · scroll to nudge 5% "
              "(Shift = 1%) · Esc closes the popover.\n\nAll processing is local. Nothing leaves your machine."
        )
        lay.addWidget(txt)
        return w
