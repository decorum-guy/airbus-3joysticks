from airbus3j.flybywire_probe import ACTIONS


def test_flybywire_probe_uses_documented_fcu_event_names():
    events = {item["id"]: item["event"] for item in ACTIONS}
    assert events["spd_push"] == "A32NX.FCU_SPD_PUSH"
    assert events["spd_pull"] == "A32NX.FCU_SPD_PULL"
    assert events["hdg_push"] == "A32NX.FCU_HDG_PUSH"
    assert events["hdg_pull"] == "A32NX.FCU_HDG_PULL"
    assert events["alt_push"] == "A32NX.FCU_ALT_PUSH"
    assert events["alt_pull"] == "A32NX.FCU_ALT_PULL"
    assert events["vs_push"] == "A32NX.FCU_VS_PUSH"
    assert events["vs_pull"] == "A32NX.FCU_VS_PULL"
    assert events["spd_mach"] == "A32NX.FCU_SPD_MACH_TOGGLE_PUSH"
    assert events["trk_fpa"] == "A32NX.FCU_TRK_FPA_TOGGLE_PUSH"
    assert events["loc"] == "A32NX.FCU_LOC_PUSH"
    assert events["appr"] == "A32NX.FCU_APPR_PUSH"
    assert events["ap1"] == "A32NX.FCU_AP_1_PUSH"
    assert events["ap2"] == "A32NX.FCU_AP_2_PUSH"
    assert events["athr"] == "A32NX.FCU_ATHR_PUSH"


def test_state_dependent_actions_default_to_explicit_validation():
    state_dependent = {item["id"] for item in ACTIONS if item.get("state_dependent")}
    assert {"loc", "appr", "ap1", "ap2", "athr"} <= state_dependent
