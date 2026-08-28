from pathlib import Path

import pytest

from airbus3j.rotary_settings import (
    CONTROL_ROUTES,
    DEFAULT_ROTARY_PRECISION,
    RotarySensitivityStore,
)


def test_default_rotary_precision_matches_current_cockpit_tuning(tmp_path: Path):
    store = RotarySensitivityStore(tmp_path / "rotary-sensitivity.json")
    state = store.snapshot()
    assert state["values"] == {
        "speed": 1.00,
        "heading": 1.00,
        "altitude": 1.35,
        "vertical_speed": 2.00,
    }
    assert state["defaults"] == DEFAULT_ROTARY_PRECISION
    assert CONTROL_ROUTES["speed"] == ("left", "left")
    assert CONTROL_ROUTES["vertical_speed"] == ("right", "right")


def test_rotary_precision_persists_and_reset_restores_base(tmp_path: Path):
    path = tmp_path / "rotary-sensitivity.json"
    store = RotarySensitivityStore(path)
    store.set("altitude", 1.75)
    store.set("vertical_speed", 2.40)

    reloaded = RotarySensitivityStore(path)
    assert reloaded.snapshot()["values"]["altitude"] == 1.75
    assert reloaded.snapshot()["values"]["vertical_speed"] == 2.40

    state = reloaded.reset("altitude")
    assert state["values"]["altitude"] == DEFAULT_ROTARY_PRECISION["altitude"]
    assert state["values"]["vertical_speed"] == 2.40

    state = reloaded.reset()
    assert state["values"] == DEFAULT_ROTARY_PRECISION


def test_rotary_precision_validates_control_and_range(tmp_path: Path):
    store = RotarySensitivityStore(tmp_path / "rotary-sensitivity.json")
    with pytest.raises(KeyError):
        store.set("unknown", 1.0)
    with pytest.raises(ValueError):
        store.set("speed", 0.49)
    with pytest.raises(ValueError):
        store.set("speed", 3.01)
