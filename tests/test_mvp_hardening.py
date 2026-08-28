from pathlib import Path

from airbus3j.config import ConfigStore
from airbus3j.runtime import Runtime, _stick_live
from airbus3j.simconnect_bridge import SimConnectBridge


def test_stick_live_exposes_radius_and_aircraft_style_angle():
    live = _stick_live({"left_x": 0.0, "left_y": -1.0}, "left")
    assert live["x"] == 0.0
    assert live["y"] == -1.0
    assert live["radius"] == 1.0
    assert live["angle_degrees"] == 90.0


def test_haptic_profiles_are_physically_distinct(tmp_path: Path):
    runtime = Runtime(ConfigStore(tmp_path / "config.json"))
    detent_low, detent_high = runtime._haptic_channels("changing_values", 0.5)
    warning_low, warning_high = runtime._haptic_channels("warnings", 0.5)
    assert detent_high > detent_low
    assert warning_low > warning_high
    assert detent_high == 0.5
    assert warning_low == 0.5


def test_readiness_requires_all_active_roles_and_simconnect(tmp_path: Path):
    runtime = Runtime(ConfigStore(tmp_path / "config.json"))
    cfg = runtime.config_store.snapshot()
    role_devices = {"left": "left-pad", "center": None, "right": "right-pad"}
    ready = runtime._readiness(cfg, role_devices, {"connected": True})
    assert ready["ready"] is True
    assert ready["missing_roles"] == []

    not_ready = runtime._readiness(cfg, {**role_devices, "right": None}, {"connected": True})
    assert not_ready["ready"] is False
    assert not_ready["missing_roles"] == ["right"]


def test_bridge_state_always_exposes_telemetry_shape():
    state = SimConnectBridge().state()
    assert state["connected"] is False
    assert state["telemetry"] == {}
    assert state["telemetry_errors"] == {}
    assert state["last_telemetry_at"] is None
