from pathlib import Path

import pytest

from airbus3j.config import ConfigStore
from airbus3j.runtime import Runtime, enabled_roles


class FakeBridge:
    def __init__(self):
        self.events = []

    def send_event(self, event, data=None):
        self.events.append((event, data))
        return True

    def state(self):
        return {"connected": True, "last_error": None, "sent_events": len(self.events), "dropped_events": 0}


class RecordingRuntime(Runtime):
    def __init__(self, store):
        super().__init__(store)
        self.dispatched = []
        self.bridge = FakeBridge()

    def _dispatch_action(self, role, trigger, label, action):
        self.dispatched.append((role, trigger, label, action))
        return super()._dispatch_action(role, trigger, label, action)


def make_snapshot(**pressed):
    names = {
        "a", "b", "x", "y", "back", "guide", "start",
        "leftstick", "rightstick", "leftshoulder", "rightshoulder",
        "dpad_up", "dpad_down", "dpad_left", "dpad_right",
    }
    return {
        "identity": {"device_key": "pad", "name": "Pad"},
        "axes": {},
        "buttons": {name: bool(pressed.get(name, False)) for name in names},
    }


def test_default_active_roles_are_left_and_right(tmp_path: Path):
    store = ConfigStore(tmp_path / "config.json")
    cfg = store.snapshot()
    assert cfg["features"]["center_controller_enabled"] is False
    assert enabled_roles(cfg) == ("left", "right")


def test_center_role_can_be_enabled_without_losing_profile(tmp_path: Path):
    store = ConfigStore(tmp_path / "config.json")
    cfg = store.snapshot()
    cfg["features"]["center_controller_enabled"] = True
    assert enabled_roles(cfg) == ("left", "center", "right")
    assert cfg["bindings"]["center"]


def test_disabled_center_is_not_resolved_to_a_device(tmp_path: Path):
    store = ConfigStore(tmp_path / "config.json")
    store.assign_device("center", {
        "device_key": "center-pad",
        "name": "Center Pad",
        "serial": "CENTER",
        "path": None,
        "guid": "g",
        "vendor_id": 1,
        "product_id": 2,
    })
    runtime = RecordingRuntime(store)
    snapshots = {
        "center-pad": {"identity": {
            "device_key": "center-pad",
            "name": "Center Pad",
            "serial": "CENTER",
            "path": None,
            "guid": "g",
            "vendor_id": 1,
            "product_id": 2,
        }}
    }
    assert runtime._role_devices(snapshots)["center"] is None


def test_default_haptics_have_independent_intensities(tmp_path: Path):
    cfg = ConfigStore(tmp_path / "config.json").snapshot()
    assert cfg["haptics"]["changing_values"]["intensity"] != cfg["haptics"]["warnings"]["intensity"]
    assert cfg["haptics"]["ps4_bluetooth_extended_reports"] is True


def test_haptic_settings_persist_and_validate_range(tmp_path: Path):
    path = tmp_path / "config.json"
    store = ConfigStore(path)
    updated = store.update_haptics({
        "changing_values": {"intensity": 0.22},
        "warnings": {"intensity": 0.81},
    })
    assert updated["changing_values"]["intensity"] == 0.22
    assert updated["warnings"]["intensity"] == 0.81
    reloaded = ConfigStore(path).snapshot()
    assert reloaded["haptics"]["changing_values"]["intensity"] == 0.22
    assert reloaded["haptics"]["warnings"]["intensity"] == 0.81
    with pytest.raises(ValueError):
        store.update_haptics({"warnings": {"intensity": 1.5}})


def test_combo_precedence_does_not_also_fire_base_button(tmp_path: Path):
    store = ConfigStore(tmp_path / "config.json")
    runtime = RecordingRuntime(store)
    bindings = [
        {"trigger": "leftstick", "label": "base", "action": {"type": "noop"}},
        {"trigger": "leftshoulder+leftstick", "label": "combo", "action": {"type": "noop"}},
    ]
    runtime._route_buttons("left", "pad", make_snapshot(leftshoulder=True, leftstick=True), bindings)
    triggers = [entry[1] for entry in runtime.dispatched]
    assert triggers == ["leftshoulder+leftstick"]


def test_pending_action_never_emits_simconnect_event(tmp_path: Path):
    store = ConfigStore(tmp_path / "config.json")
    runtime = RecordingRuntime(store)
    result = runtime._dispatch_action("left", "leftstick", "SPD PUSH", {"type": "pending", "reason": "not verified"})
    assert result.startswith("pending:")
    assert runtime.bridge.events == []


def test_sim_event_is_forwarded_to_bridge(tmp_path: Path):
    store = ConfigStore(tmp_path / "config.json")
    runtime = RecordingRuntime(store)
    result = runtime._dispatch_action("right", "dpad_down", "FLAPS DOWN", {"type": "sim_event", "event": "FLAPS_INCR"})
    assert result == "sent"
    assert runtime.bridge.events == [("FLAPS_INCR", None)]


def test_ambiguous_identical_fallback_is_not_silently_selected(tmp_path: Path):
    store = ConfigStore(tmp_path / "config.json")
    runtime = RecordingRuntime(store)
    saved = {
        "device_key": "old-fallback-key", "name": "Wireless Controller", "serial": None,
        "path": None, "guid": "same-guid", "vendor_id": 1356, "product_id": 3302,
    }
    snapshots = {
        "pad-a": {"identity": {**saved, "device_key": "pad-a"}},
        "pad-b": {"identity": {**saved, "device_key": "pad-b"}},
    }
    assert runtime._find_device_for_saved_identity(saved, snapshots, already_used=set()) is None


def test_unique_fallback_can_be_recovered(tmp_path: Path):
    store = ConfigStore(tmp_path / "config.json")
    runtime = RecordingRuntime(store)
    saved = {
        "device_key": "old-fallback-key", "name": "Xbox Controller", "serial": None,
        "path": None, "guid": "xbox-guid", "vendor_id": 1118, "product_id": 654,
    }
    snapshots = {"new-key": {"identity": {**saved, "device_key": "new-key"}}}
    assert runtime._find_device_for_saved_identity(saved, snapshots, already_used=set()) == "new-key"


def test_config_role_assignment_and_binding_edit_survive_reload(tmp_path: Path):
    path = tmp_path / "config.json"
    store = ConfigStore(path)
    identity = {
        "device_key": "serial:abc", "name": "DualSense", "serial": "REAL-SERIAL",
        "path": None, "guid": "guid", "vendor_id": 1, "product_id": 2,
        "identity_source": "serial",
    }
    edited = [{"trigger": "a", "label": "TEST", "action": {"type": "noop"}}]
    store.assign_device("left", identity)
    store.replace_bindings("left", edited)
    reloaded = ConfigStore(path).snapshot()
    assert reloaded["roles"]["left"]["device"] == identity
    assert reloaded["bindings"]["left"] == edited
