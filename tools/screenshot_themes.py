"""Render the popover in every theme (offscreen) — used for testing and the README gallery.

    python tools/screenshot_themes.py            -> assets/screenshots/<theme>.png
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

from sounddial.mixer import Mixer  # noqa: E402
from sounddial.settings import Settings  # noqa: E402
from sounddial.ui.popover import Popover  # noqa: E402
from sounddial.ui.settings_dialog import SettingsDialog  # noqa: E402
from sounddial.ui.themes import THEMES  # noqa: E402


def main() -> None:
    out = ROOT / "assets" / "screenshots"
    out.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv)
    s = Settings(path=Path("/tmp/sounddial_shot_settings.json"))
    mixer = Mixer(s, demo=True)
    mixer.refresh()
    mixer.force_duck(True)   # show the DUCKED badge in the gallery
    pop = Popover(mixer)
    for name in THEMES:
        s.set("theme", name)
        pop.apply_theme()
        pop.refresh()
        pop.show()
        app.processEvents()
        pop.grab().save(str(out / f"{name}.png"))
        print("wrote", name)
    s.set("theme", "mono")
    dlg = SettingsDialog(mixer, lambda: None)
    dlg.resize(560, 480)
    dlg.show()
    app.processEvents()
    dlg.grab().save(str(out / "settings.png"))
    print("wrote settings")
    mixer.stop()


if __name__ == "__main__":
    main()
