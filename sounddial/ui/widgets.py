"""Custom widgets: themed slider with 100 % notch + VU meter, app row, icons."""

from __future__ import annotations

import os
import sys
from typing import Optional

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import (QColor, QFont, QIcon, QImage, QPainter, QPainterPath, QPen,
                           QPixmap)
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget)


# --------------------------------------------------------------------------- icons
def speaker_icon(color: str, level: float = 1.0, muted: bool = False, size: int = 18) -> QIcon:
    """A crisp vector speaker glyph drawn in the theme colour (works for mono tray too)."""
    pm = QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color)
    pen = QPen(c, 1.6)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(c)
    s = size
    path = QPainterPath()
    path.moveTo(s * 0.14, s * 0.38)
    path.lineTo(s * 0.32, s * 0.38)
    path.lineTo(s * 0.52, s * 0.20)
    path.lineTo(s * 0.52, s * 0.80)
    path.lineTo(s * 0.32, s * 0.62)
    path.lineTo(s * 0.14, s * 0.62)
    path.closeSubpath()
    p.drawPath(path)
    p.setBrush(Qt.NoBrush)
    if muted or level <= 0.0:
        p.drawLine(int(s * 0.62), int(s * 0.38), int(s * 0.86), int(s * 0.62))
        p.drawLine(int(s * 0.86), int(s * 0.38), int(s * 0.62), int(s * 0.62))
    else:
        if level > 0.0:
            p.drawArc(QRectF(s * 0.46, s * 0.36, s * 0.28, s * 0.28), -45 * 16, 90 * 16)
        if level > 0.5:
            p.drawArc(QRectF(s * 0.40, s * 0.22, s * 0.56, s * 0.56), -45 * 16, 90 * 16)
        if level > 1.0:
            p.drawArc(QRectF(s * 0.34, s * 0.08, s * 0.84, s * 0.84), -40 * 16, 80 * 16)
    p.end()
    return QIcon(pm)


def dial_icon(color: str, size: int = 18, bg: Optional[str] = None) -> QIcon:
    """The SoundDial mark: a dial with a tick, plus three level bars."""
    pm = QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color)
    s = size
    if bg:
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(bg))
        p.drawRoundedRect(QRectF(0, 0, s, s), s * 0.22, s * 0.22)
    pen = QPen(c, max(1.2, s * 0.085))
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    r = QRectF(s * 0.14, s * 0.14, s * 0.56, s * 0.56)
    p.drawArc(r, 225 * 16, -270 * 16)
    cx, cy = s * 0.42, s * 0.42
    p.drawLine(int(cx), int(cy), int(cx + s * 0.16), int(cy - s * 0.14))
    p.setBrush(c)
    p.setPen(Qt.NoPen)
    for i, h in enumerate((0.18, 0.30, 0.42)):
        x = s * (0.74 + i * 0.09)
        p.drawRoundedRect(QRectF(x, s * 0.80 - s * h, s * 0.055, s * h), 1, 1)
    p.end()
    return QIcon(pm)


def app_icon(path: Optional[str], fallback_color: str, size: int = 22) -> Optional[QIcon]:
    """Best-effort app icon: file icons from the OS where possible, else none."""
    if not path:
        return None
    try:
        if sys.platform.startswith("win") and path.lower().endswith(".exe") and os.path.exists(path):
            from PySide6.QtWidgets import QFileIconProvider
            from PySide6.QtCore import QFileInfo
            ic = QFileIconProvider().icon(QFileInfo(path))
            if not ic.isNull():
                return ic
        if os.path.exists(path) and path.lower().endswith((".png", ".icns", ".ico", ".svg")):
            ic = QIcon(path)
            if not ic.isNull():
                return ic
        if sys.platform.startswith("linux"):
            ic = QIcon.fromTheme(path)
            if not ic.isNull():
                return ic
    except Exception:
        pass
    return None


# --------------------------------------------------------------------------- slider
class VolumeSlider(QWidget):
    """0 .. max_gain slider with a notch at 100 %, boost region shading and a VU bar."""

    valueChanged = Signal(float)
    released = Signal()

    def __init__(self, max_gain: float = 2.0, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.max_gain = max_gain
        self._value = 1.0
        self._peak = 0.0
        self._muted = False
        self._dragging = False
        self.show_vu = True
        self.t: dict = {}
        self.setMinimumHeight(24)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.WheelFocus)

    def sizeHint(self) -> QSize:
        return QSize(200, 24)

    def value(self) -> float:
        return self._value

    def setValue(self, v: float, emit: bool = False) -> None:
        v = max(0.0, min(self.max_gain, float(v)))
        if abs(v - self._value) < 1e-4:
            return
        self._value = v
        self.update()
        if emit:
            self.valueChanged.emit(v)

    def setPeak(self, p: float) -> None:
        p = max(0.0, min(1.0, p))
        if abs(p - self._peak) > 0.005:
            self._peak = p
            self.update()

    def setMuted(self, m: bool) -> None:
        self._muted = m
        self.update()

    # geometry helpers
    def _track(self) -> QRectF:
        return QRectF(10, self.height() / 2 - 2, self.width() - 20, 4)

    def _x_for(self, v: float) -> float:
        tr = self._track()
        return tr.left() + tr.width() * (v / self.max_gain)

    def _v_for(self, x: float) -> float:
        tr = self._track()
        return max(0.0, min(self.max_gain, (x - tr.left()) / tr.width() * self.max_gain))

    def paintEvent(self, _e) -> None:
        t = self.t
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        tr = self._track()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(t.get("track", "#333")))
        p.drawRoundedRect(tr, 2, 2)
        if self.max_gain > 1.0:  # boost zone shading above 100 %
            x1 = self._x_for(1.0)
            zone = QRectF(x1, tr.top(), tr.right() - x1, tr.height())
            c = QColor(t.get("boost", "#888"))
            c.setAlpha(60)
            p.setBrush(c)
            p.drawRoundedRect(zone, 2, 2)
        # fill
        x = self._x_for(self._value)
        fill = QColor(t.get("fill", "#ddd"))
        if self._muted:
            fill.setAlpha(70)
        elif self._value > 1.0:
            fill = QColor(t.get("boost", "#888"))
        p.setBrush(fill)
        p.drawRoundedRect(QRectF(tr.left(), tr.top(), x - tr.left(), tr.height()), 2, 2)
        # VU
        if self.show_vu and not self._muted and self._peak > 0:
            vu = QColor(t.get("vu_hot" if self._peak > 0.92 else "vu", "#aaa"))
            vu.setAlpha(170)
            p.setBrush(vu)
            p.drawRoundedRect(QRectF(tr.left(), tr.bottom() + 4, tr.width() * self._peak * min(1.0, self._value), 2), 1, 1)
        # notch at 100 %
        if self.max_gain > 1.0:
            nx = self._x_for(1.0)
            p.setPen(QPen(QColor(t.get("fg3", "#666")), 1))
            p.drawLine(int(nx), int(tr.top() - 5), int(nx), int(tr.bottom() + 5))
        # knob
        knob = QRectF(x - 7, tr.center().y() - 7, 14, 14)
        p.setPen(QPen(QColor(t.get("border2", "#555")), 1))
        p.setBrush(QColor(t.get("fg", "#fff")) if not self._muted else QColor(t.get("fg3", "#666")))
        p.drawEllipse(knob)
        p.end()

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self._dragging = True
            self.setValue(self._v_for(e.position().x()), emit=True)
        elif e.button() == Qt.RightButton:
            self.setValue(1.0, emit=True)  # right click resets to 100 %
            self.released.emit()

    def mouseMoveEvent(self, e) -> None:
        if self._dragging:
            v = self._v_for(e.position().x())
            if abs(v - 1.0) < 0.03:   # snap to 100 %
                v = 1.0
            self.setValue(v, emit=True)

    def mouseReleaseEvent(self, e) -> None:
        if self._dragging:
            self._dragging = False
            self.released.emit()

    def mouseDoubleClickEvent(self, e) -> None:
        self.setValue(1.0, emit=True)
        self.released.emit()

    def wheelEvent(self, e) -> None:
        step = 0.05 if not (e.modifiers() & Qt.ShiftModifier) else 0.01
        d = 1 if e.angleDelta().y() > 0 else -1
        self.setValue(round(self._value + d * step, 2), emit=True)
        self.released.emit()
        e.accept()

    def keyPressEvent(self, e) -> None:
        if e.key() in (Qt.Key_Left, Qt.Key_Down):
            self.setValue(round(self._value - 0.05, 2), emit=True)
        elif e.key() in (Qt.Key_Right, Qt.Key_Up):
            self.setValue(round(self._value + 0.05, 2), emit=True)
        elif e.key() == Qt.Key_Home:
            self.setValue(0.0, emit=True)
        elif e.key() == Qt.Key_End:
            self.setValue(self.max_gain, emit=True)
        elif e.key() in (Qt.Key_0, Qt.Key_Space):
            self.setValue(1.0, emit=True)
        else:
            return super().keyPressEvent(e)
        self.released.emit()


# --------------------------------------------------------------------------- app row
class AppRow(QFrame):
    volumeChanged = Signal(str, float)
    muteToggled = Signal(str, bool)

    def __init__(self, key: str, name: str, max_gain: float, t: dict, compact: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.key = key
        self.t = t
        self.setObjectName("Row")
        self._muted = False
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6 if compact else 9, 10, 6 if compact else 9)
        lay.setSpacing(10)

        self.icon_btn = QPushButton()
        self.icon_btn.setObjectName("Icon")
        self.icon_btn.setCheckable(True)
        self.icon_btn.setToolTip("Mute / unmute")
        self.icon_btn.setIconSize(QSize(16, 16))
        self.icon_btn.clicked.connect(self._on_mute)
        lay.addWidget(self.icon_btn)

        col = QVBoxLayout()
        col.setSpacing(2)
        top = QHBoxLayout()
        self.name_lbl = QLabel(name)
        self.name_lbl.setObjectName("AppName")
        top.addWidget(self.name_lbl)
        self.badge = QLabel("")
        self.badge.setObjectName("Badge")
        self.badge.hide()
        top.addWidget(self.badge)
        top.addStretch(1)
        self.pct = QLabel("100%")
        self.pct.setObjectName("Pct")
        self.pct.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        top.addWidget(self.pct)
        col.addLayout(top)
        self.slider = VolumeSlider(max_gain)
        self.slider.t = t
        self.slider.valueChanged.connect(self._on_slide)
        col.addWidget(self.slider)
        lay.addLayout(col, 1)
        self.refresh_icon()

    def refresh_icon(self) -> None:
        col = self.t.get("fg2", "#999") if not self._muted else self.t.get("fg3", "#666")
        self.icon_btn.setIcon(speaker_icon(col, self.slider.value(), self._muted))

    def set_state(self, volume: float, muted: bool, peak: float, badge: str = "") -> None:
        if not self.slider._dragging:
            self.slider.setValue(volume)
        self._muted = muted
        self.slider.setMuted(muted)
        self.slider.setPeak(peak)
        self.icon_btn.setChecked(muted)
        self.pct.setText("Muted" if muted else f"{int(round(volume * 100))}%")
        if badge:
            self.badge.setText(badge)
            self.badge.setObjectName("BadgeOn" if badge == "DUCKED" or badge == "CALL" else "Badge")
            self.badge.style().unpolish(self.badge)
            self.badge.style().polish(self.badge)
            self.badge.show()
        else:
            self.badge.hide()
        self.refresh_icon()

    def _on_slide(self, v: float) -> None:
        self.pct.setText(f"{int(round(v * 100))}%")
        self.refresh_icon()
        self.volumeChanged.emit(self.key, v)

    def _on_mute(self) -> None:
        self._muted = self.icon_btn.isChecked()
        self.slider.setMuted(self._muted)
        self.pct.setText("Muted" if self._muted else f"{int(round(self.slider.value() * 100))}%")
        self.refresh_icon()
        self.muteToggled.emit(self.key, self._muted)
