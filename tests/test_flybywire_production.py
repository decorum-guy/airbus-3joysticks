from pathlib import Path

from airbus3j.config import ConfigStore
from airbus3j.flybywire_profile import FLYBYWIRE_FAMILY, promote_flybywire_profile
from airbus3j.production_runtime import ProductionRuntime
from airbus3j.simconnect_bridge import SimConnectBridge, classify_live_aircraft


class FakeBridge:
    def __init__(self, family: str):
        self.family = family
        self.events: list[tuple[str, int | None]] = []

    def state(self):
        return {
            "connected": True,
            "aircraft_family": self.family,
            "aircraft_backend": {
                "family": self.family,
                "full_controls": self.family == FLYBYWIRE_FAMILY,
            },
        }

    def send_event(self, event: str, data=None):
        self.events.append((event, data))
        return True


def binding_for(store: ConfigStore, role: str, trigger: str):
    return next(
        binding
        for binding in store.snapshot()["bindings"][role]
        if binding["trigger"] == trigger
    )


def test_live_title_detects_flybywire():
    assert classify_live_aircraft("Airbus A320neo FlyByWire") == ("flybywire_a32nx", "high")


def test_profile_promotes_all_two_controller_airbus_buttons(tmp_path: Path):
    store = ConfigStore(tmp_path / "config.json")
    result = promote_flybywire_profile(store)
    assert len(result["promoted"]) == 15

    expected = {
        ("left", "leftstick"): "A32NX.FCU_SPD_PUSH",
        ("left", "leftshoulder+leftstick"): "A32NX.FCU_SPD_PULL",
        ("left", "rightstick"): "A32NX.FCU_HDG_PUSH",
        ("left", "leftshoulder+rightstick"): "A32NX.FCU_HDG_PULL",
        ("left", "x"): "A32NX.FCU_AP_1_PUSH",
        ("left", "b"): "A32NX.FCU_AP_2_PUSH",
        ("left", "a"): "A32NX.FCU_ATHR_PUSH",
        ("left", "y"): "A32NX.FCU_APPR_PUSH",
        ("left", "dpad_left"): "A32NX.FCU_LOC_PUSH",
        ("left", "dpad_up"): "A32NX.FCU_SPD_MACH_TOGGLE_PUSH",
        ("left", "dpad_down"): "A32NX.FCU_TRK_FPA_TOGGLE_PUSH",
        ("right", "leftstick"): "A32NX.FCU_ALT_PUSH",
        ("right", "leftshoulder+leftstick"): "A32NX.FCU_ALT_PULL",
        ("right", "rightstick"): "A32NX.FCU_VS_PUSH",
        ("right", "leftshoulder+rightstick"): "A32NX.FCU_VS_PULL",
    }
    for (role, trigger), event in expected.items():
        action = binding_for(store, role, trigger)["action"]
        assert action == {
            "type": "sim_event",
            "event": event,
            "requires_aircraft": FLYBYWIRE_FAMILY,
        }


def test_profile_does_not_clobber_user_custom_binding(tmp_path: Path):
    store = ConfigStore(tmp_path / "config.json")
    bindings = store.snapshot()["bindings"]["left"]
    for binding in bindings:
        if binding["trigger"] == "x":
            binding["label"] = "MY CUSTOM AP"
            binding["action"] = {"type": "noop"}
    store.replace_bindings("left", bindings)

    promote_flybywire_profile(store)
    custom = binding_for(store, "left", "x")
    assert custom["label"] == "MY CUSTOM AP"
    assert custom["action"] == {"type": "noop"}


def test_production_runtime_blocks_a32nx_action_on_wrong_aircraft(tmp_path: Path):
    store = ConfigStore(tmp_path / "config.json")
    promote_flybywire_profile(store)
    runtime = ProductionRuntime(store)
    runtime.bridge = FakeBridge("asobo_legacy_a320neo")
    action = binding_for(store, "left", "leftstick")["action"]

    result = runtime._dispatch_action("left", "leftstick", "SPD PUSH", action)
    assert result.startswith("blocked: requires flybywire_a32nx")
    assert runtime.bridge.events == []


def test_production_runtime_sends_a32nx_action_on_flybywire(tmp_path: Path):
    store = ConfigStore(tmp_path / "config.json")
    promote_flybywire_profile(store)
    runtime = ProductionRuntime(store)
    runtime.bridge = FakeBridge(FLYBYWIRE_FAMILY)
    action = binding_for(store, "left", "leftstick")["action"]

    result = runtime._dispatch_action("left", "leftstick", "SPD PUSH", action)
    assert result == "sent"
    assert runtime.bridge.events == [("A32NX.FCU_SPD_PUSH", None)]


def test_bridge_has_second_defense_in_depth_gate():
    bridge = SimConnectBridge()
    bridge._state.connected = True
    bridge._state.aircraft_family = "asobo_legacy_a320neo"
    assert bridge.send_event("A32NX.FCU_AP_1_PUSH") is False
    assert bridge.state()["blocked_events"] == 1
    assert bridge.state()["last_blocked_event"] == "A32NX.FCU_AP_1_PUSH"

    bridge._state.aircraft_family = FLYBYWIRE_FAMILY
    assert bridge.send_event("A32NX.FCU_AP_1_PUSH") is True
