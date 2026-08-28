from airbus3j.stock_airbus_probe import GENERIC_ACTIONS, KNOB_ACTIONS, changed


def by_id(items):
    return {item["id"]: item for item in items}


def test_stock_knob_probe_uses_asobo_inputevent_names():
    actions = by_id(KNOB_ACTIONS)
    assert actions["spd_push"]["rpn"] == "(>B:AUTOPILOT_Speed_Managed_Mode)"
    assert actions["spd_pull"]["rpn"] == "(>B:AUTOPILOT_Speed_Selected_Mode)"
    assert actions["hdg_push"]["rpn"] == "(>B:AUTOPILOT_Heading_Managed_Select)"
    assert actions["hdg_pull"]["rpn"] == "(>B:AUTOPILOT_Heading_Selected_Select)"
    assert actions["alt_push"]["rpn"] == "(>B:AUTOPILOT_Altitude_Managed_Mode)"
    assert actions["alt_pull"]["rpn"] == "(>B:AUTOPILOT_Altitude_Selected_Mode)"
    assert actions["vs_push"]["rpn"] == "(>B:AUTOPILOT_VerticalSpeed_Zero_Push)"
    assert actions["vs_pull"]["rpn"] == "(>B:AUTOPILOT_VerticalSpeed_Hold_Pull)"


def test_stock_knob_probe_has_exact_asobo_h_fallbacks_not_v1_guesses():
    actions = by_id(KNOB_ACTIONS)
    assert actions["spd_push"]["fallback_rpn"] == "(>H:A320_Neo_CDU_MODE_MANAGED_SPEED)"
    assert actions["hdg_push"]["fallback_rpn"] == "(>H:A320_Neo_CDU_MODE_MANAGED_HEADING)"
    assert actions["alt_push"]["fallback_rpn"] == "(>H:A320_Neo_CDU_MODE_MANAGED_ALTITUDE)"
    assert actions["vs_push"]["fallback_rpn"] == "(>H:A320_Neo_FCU_VS_ZERO)"
    assert all("A320_Neo_FCU_SPEED_PUSH" not in item["fallback_rpn"] for item in KNOB_ACTIONS)


def test_generic_probe_uses_stock_template_events():
    actions = by_id(GENERIC_ACTIONS)
    assert actions["spd_mach"]["event"] == "AP_MANAGED_SPEED_IN_MACH_TOGGLE"
    assert actions["loc"]["event"] == "AP_LOC_HOLD"
    assert actions["appr"]["event"] == "AP_APR_HOLD"
    assert actions["athr"]["event"] == "AUTO_THROTTLE_ARM"
    assert actions["loc"]["state_dependent"] is True
    assert actions["appr"]["state_dependent"] is True


def test_changed_only_reports_successfully_read_differences():
    before = {
        "a": {"ok": True, "value": 1},
        "b": {"ok": True, "value": 2},
        "c": {"ok": False, "error": "nope"},
    }
    after = {
        "a": {"ok": True, "value": 1},
        "b": {"ok": True, "value": 3},
        "c": {"ok": True, "value": 9},
    }
    assert changed(before, after) == ["b"]
