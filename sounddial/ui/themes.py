"""Themes for SoundDial.

Each theme is a palette dict; `build_qss()` turns it into a Qt stylesheet.
"Mono" is the signature look: pure greyscale, no colour anywhere, thin lines.
"""

from __future__ import annotations

from typing import Dict

THEMES: Dict[str, dict] = {
    "mono": {
        "label": "Mono",
        "bg": "#0E0E0E", "panel": "#161616", "panel2": "#1E1E1E",
        "border": "#2A2A2A", "border2": "#3A3A3A",
        "fg": "#F2F2F2", "fg2": "#9A9A9A", "fg3": "#5C5C5C",
        "accent": "#FFFFFF", "accent_fg": "#000000",
        "track": "#2A2A2A", "fill": "#E6E6E6", "boost": "#8A8A8A",
        "vu": "#B5B5B5", "vu_hot": "#FFFFFF", "danger": "#CFCFCF",
        "font": "'Inter','SF Pro Text','Segoe UI','Helvetica Neue',Arial,sans-serif",
        "mono": False, "radius": "4px", "accent_takes_user": False,
    },
    "mono-light": {
        "label": "Mono Light",
        "bg": "#FAFAFA", "panel": "#FFFFFF", "panel2": "#F1F1F1",
        "border": "#E2E2E2", "border2": "#CFCFCF",
        "fg": "#111111", "fg2": "#5E5E5E", "fg3": "#A3A3A3",
        "accent": "#111111", "accent_fg": "#FFFFFF",
        "track": "#E6E6E6", "fill": "#1A1A1A", "boost": "#7A7A7A",
        "vu": "#5A5A5A", "vu_hot": "#000000", "danger": "#333333",
        "font": "'Inter','SF Pro Text','Segoe UI','Helvetica Neue',Arial,sans-serif",
        "mono": False, "radius": "4px", "accent_takes_user": False,
    },
    "graphite": {
        "label": "Graphite",
        "bg": "#1C1C1E", "panel": "#242426", "panel2": "#2C2C2E",
        "border": "#3A3A3C", "border2": "#48484A",
        "fg": "#F5F5F7", "fg2": "#A1A1A6", "fg3": "#636366",
        "accent": "#4F8CFF", "accent_fg": "#FFFFFF",
        "track": "#3A3A3C", "fill": "#4F8CFF", "boost": "#FF9F0A",
        "vu": "#30D158", "vu_hot": "#FF453A", "danger": "#FF453A",
        "font": "'Inter','SF Pro Text','Segoe UI','Helvetica Neue',Arial,sans-serif",
        "mono": False, "radius": "8px", "accent_takes_user": True,
    },
    "paper": {
        "label": "Paper",
        "bg": "#F4F4F6", "panel": "#FFFFFF", "panel2": "#EDEDF0",
        "border": "#DCDCE1", "border2": "#C9C9D0",
        "fg": "#1D1D1F", "fg2": "#6E6E73", "fg3": "#AEAEB2",
        "accent": "#0A66FF", "accent_fg": "#FFFFFF",
        "track": "#DCDCE1", "fill": "#0A66FF", "boost": "#F59E0B",
        "vu": "#1DB954", "vu_hot": "#E5484D", "danger": "#E5484D",
        "font": "'Inter','SF Pro Text','Segoe UI','Helvetica Neue',Arial,sans-serif",
        "mono": False, "radius": "8px", "accent_takes_user": True,
    },
    "midnight": {
        "label": "Midnight",
        "bg": "#0B1020", "panel": "#111833", "panel2": "#172044",
        "border": "#223060", "border2": "#2E3F78",
        "fg": "#E8ECFF", "fg2": "#9AA6D6", "fg3": "#5C6896",
        "accent": "#7C9CFF", "accent_fg": "#0B1020",
        "track": "#223060", "fill": "#7C9CFF", "boost": "#FFB86B",
        "vu": "#5FE0B2", "vu_hot": "#FF6B8A", "danger": "#FF6B8A",
        "font": "'Inter','SF Pro Text','Segoe UI','Helvetica Neue',Arial,sans-serif",
        "mono": False, "radius": "10px", "accent_takes_user": True,
    },
    "terminal": {
        "label": "Terminal",
        "bg": "#050806", "panel": "#0A100B", "panel2": "#0F170F",
        "border": "#1E3A22", "border2": "#2F5A35",
        "fg": "#9CFF9C", "fg2": "#4FC95A", "fg3": "#2A6B33",
        "accent": "#39FF14", "accent_fg": "#000000",
        "track": "#1E3A22", "fill": "#39FF14", "boost": "#FFD700",
        "vu": "#39FF14", "vu_hot": "#FF4444", "danger": "#FF4444",
        "font": "'JetBrains Mono','SF Mono','Cascadia Mono','Consolas','DejaVu Sans Mono',monospace",
        "mono": True, "radius": "0px", "accent_takes_user": False,
    },
    "sunset": {
        "label": "Sunset",
        "bg": "#1A1214", "panel": "#241A1D", "panel2": "#2E2226",
        "border": "#44323A", "border2": "#5A4249",
        "fg": "#FFF1EA", "fg2": "#D1A99E", "fg3": "#80656A",
        "accent": "#FF7A59", "accent_fg": "#1A1214",
        "track": "#44323A", "fill": "#FF7A59", "boost": "#FFD166",
        "vu": "#FFB46B", "vu_hot": "#FF4D6D", "danger": "#FF4D6D",
        "font": "'Inter','SF Pro Text','Segoe UI','Helvetica Neue',Arial,sans-serif",
        "mono": False, "radius": "12px", "accent_takes_user": True,
    },
}

ACCENTS = {
    "Blue": "#4F8CFF", "Purple": "#A78BFA", "Pink": "#F472B6", "Red": "#FF453A",
    "Orange": "#FF9F0A", "Yellow": "#FFD60A", "Green": "#30D158", "Teal": "#40C8E0",
    "Graphite": "#8E8E93",
}


def theme(name: str, accent: str | None = None) -> dict:
    t = dict(THEMES.get(name, THEMES["mono"]))
    if accent and t.get("accent_takes_user"):
        t["accent"] = accent
        t["fill"] = accent
    return t


def build_qss(t: dict) -> str:
    r = t["radius"]
    return f"""
    * {{ font-family: {t['font']}; font-size: 13px; }}
    QWidget#Root {{ background: {t['bg']}; color: {t['fg']}; border: 1px solid {t['border']}; border-radius: {r}; }}
    QWidget {{ color: {t['fg']}; background: transparent; }}
    QLabel {{ background: transparent; }}
    QLabel#Title {{ font-size: 15px; font-weight: 600; letter-spacing: 0.3px; }}
    QLabel#Section {{ font-size: 10px; font-weight: 600; color: {t['fg3']}; letter-spacing: 1.4px; }}
    QLabel#AppName {{ font-weight: 500; }}
    QLabel#Pct {{ color: {t['fg2']}; min-width: 40px; }}
    QLabel#Hint {{ color: {t['fg3']}; font-size: 11px; }}
    QLabel#Badge {{ background: {t['panel2']}; color: {t['fg2']}; border: 1px solid {t['border']}; border-radius: 9px; padding: 1px 7px; font-size: 10px; }}
    QLabel#BadgeOn {{ background: {t['accent']}; color: {t['accent_fg']}; border-radius: 9px; padding: 1px 7px; font-size: 10px; font-weight: 600; }}

    QFrame#Card {{ background: {t['panel']}; border: 1px solid {t['border']}; border-radius: {r}; }}
    QFrame#Row {{ background: transparent; border-bottom: 1px solid {t['border']}; }}
    QFrame#Row:last {{ border-bottom: none; }}
    QFrame#Sep {{ background: {t['border']}; max-height: 1px; min-height: 1px; border: none; }}

    QPushButton {{ background: {t['panel2']}; color: {t['fg']}; border: 1px solid {t['border2']}; border-radius: {r}; padding: 5px 10px; }}
    QPushButton:hover {{ border-color: {t['fg2']}; }}
    QPushButton:pressed {{ background: {t['border']}; }}
    QPushButton:checked {{ background: {t['accent']}; color: {t['accent_fg']}; border-color: {t['accent']}; }}
    QPushButton#Flat {{ background: transparent; border: none; padding: 2px 6px; color: {t['fg2']}; }}
    QPushButton#Flat:hover {{ color: {t['fg']}; }}
    QPushButton#Icon {{ background: transparent; border: 1px solid transparent; padding: 3px; min-width: 24px; max-width: 24px; min-height: 24px; max-height: 24px; border-radius: 12px; }}
    QPushButton#Icon:hover {{ background: {t['panel2']}; border-color: {t['border2']}; }}
    QPushButton#Icon:checked {{ background: {t['accent']}; color: {t['accent_fg']}; }}
    QPushButton#Chip {{ padding: 3px 10px; border-radius: 11px; font-size: 11px; }}
    QPushButton#Primary {{ background: {t['accent']}; color: {t['accent_fg']}; border-color: {t['accent']}; font-weight: 600; }}
    QPushButton#Danger {{ color: {t['danger']}; border-color: {t['danger']}; background: transparent; }}

    QComboBox {{ background: {t['panel2']}; border: 1px solid {t['border2']}; border-radius: {r}; padding: 4px 8px; color: {t['fg']}; }}
    QComboBox::drop-down {{ border: none; width: 18px; }}
    QComboBox QAbstractItemView {{ background: {t['panel']}; color: {t['fg']}; selection-background-color: {t['accent']}; selection-color: {t['accent_fg']}; border: 1px solid {t['border2']}; outline: none; }}
    QLineEdit, QSpinBox, QDoubleSpinBox {{ background: {t['panel2']}; border: 1px solid {t['border2']}; border-radius: {r}; padding: 4px 8px; color: {t['fg']}; selection-background-color: {t['accent']}; }}
    QCheckBox {{ spacing: 8px; }}
    QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {t['border2']}; border-radius: 4px; background: {t['panel2']}; }}
    QCheckBox::indicator:checked {{ background: {t['accent']}; border-color: {t['accent']}; }}
    QTabWidget::pane {{ border: 1px solid {t['border']}; border-radius: {r}; top: -1px; background: {t['panel']}; }}
    QTabBar::tab {{ background: transparent; color: {t['fg2']}; padding: 6px 12px; border: 1px solid transparent; border-bottom: none; }}
    QTabBar::tab:selected {{ color: {t['fg']}; background: {t['panel']}; border-color: {t['border']}; border-top-left-radius: {r}; border-top-right-radius: {r}; }}
    QScrollArea {{ border: none; }}
    QScrollBar:vertical {{ background: transparent; width: 6px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: {t['border2']}; border-radius: 3px; min-height: 24px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QToolTip {{ background: {t['panel']}; color: {t['fg']}; border: 1px solid {t['border2']}; padding: 4px 6px; }}
    QMenu {{ background: {t['panel']}; color: {t['fg']}; border: 1px solid {t['border2']}; padding: 4px; }}
    QMenu::item {{ padding: 5px 18px; border-radius: 4px; }}
    QMenu::item:selected {{ background: {t['accent']}; color: {t['accent_fg']}; }}
    QMenu::separator {{ height: 1px; background: {t['border']}; margin: 4px 6px; }}
    """
