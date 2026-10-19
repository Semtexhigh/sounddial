"""Logic tests — run with:  python -m pytest tests  (or python tests/test_mixer.py)"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sounddial.mixer import Mixer  # noqa: E402
from sounddial.settings import Settings  # noqa: E402


def make() -> Mixer:
    s = Settings(path=Path(tempfile.mkdtemp()) / "settings.json")
    m = Mixer(s, demo=True)
    m.refresh()
    return m


def test_ducking_applies_once_and_restores():
    m = make()
    assert m.ducking_active                       # demo Zoom is "live"
    assert abs(m.apps["spotify"].volume - 0.8 * 0.25) < 1e-6
    assert abs(m.apps["chrome"].volume - 0.25) < 1e-6
    assert m.apps["zoom"].volume == 1.0           # call app untouched
    m.force_duck(False)
    assert abs(m.apps["spotify"].volume - 0.8) < 1e-6


def test_volume_clamped_to_backend_gain():
    m = make()
    m.force_duck(False)
    m.set_volume("spotify", 5.0)
    assert m.apps["spotify"].volume == m.backend.max_gain
    m.set_volume("spotify", -1)
    assert m.apps["spotify"].volume == 0.0


def test_profiles_roundtrip():
    m = make()
    m.force_duck(False)
    m.set_volume("spotify", 0.33)
    m.save_profile("Test")
    assert m.settings.get("profiles")["Test"]["spotify"] == 0.33
    m.set_volume("spotify", 1.0)
    m.apply_profile("Test")
    assert abs(m.apps["spotify"].volume - 0.33) < 1e-6
    m.delete_profile("Test")
    assert "Test" not in m.profile_names()


def test_remembered_volumes_persist():
    m = make()
    m.force_duck(False)
    m.set_volume("music", 0.42)
    m.set_mute("music", True)
    mem = m.settings.get("remembered")["music"]
    assert mem["volume"] == 0.42 and mem["muted"] is True


def test_master():
    m = make()
    m.set_master(0.5, True)
    assert m.master_volume == 0.5 and m.master_muted


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
