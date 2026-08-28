from pathlib import Path

from airbus3j.aircraft_identity import (
    classify_aircraft,
    parse_aircraft_cfg,
    parse_usercfg_installed_path,
)
from airbus3j.airbus_button_probe import candidates_for_family


def test_usercfg_installed_packages_path_parses_quotes():
    text = 'InstalledPackagesPath "D:\\MSFS Packages"\n'
    assert parse_usercfg_installed_path(text) == "D:\\MSFS Packages"


def test_aircraft_cfg_extracts_fltsim_identity_fields():
    blocks = parse_aircraft_cfg(
        """
[VERSION]
major = 1
[FLTSIM.0]
title = "A320neo Global Livery"
ui_type = "A320neo"
ui_createdby = "Asobo Studio" ; comment
[FLTSIM.1]
title = "A320neo AI"
isUserSelectable = 0
"""
    )
    assert len(blocks) == 2
    assert blocks[0]["title"] == "A320neo Global Livery"
    assert blocks[0]["ui_createdby"] == "Asobo Studio"


def test_global_livery_title_classifies_as_legacy_asobo_without_disk_metadata():
    result = classify_aircraft("A320neo Global Livery")
    assert result["family"] == "asobo_legacy_a320neo"
    assert result["confidence"] == "high"


def test_asobo_package_name_classifies_as_legacy():
    result = classify_aircraft(
        "Custom paint",
        package_name="asobo-aircraft-a320-neo",
        cfg_block={"base_container": "..\\Asobo_A320_NEO"},
    )
    assert result["family"] == "asobo_legacy_a320neo"


def test_flybywire_identity_is_not_mixed_with_legacy_asobo():
    result = classify_aircraft(
        "Airbus A320neo",
        package_name="flybywire-aircraft-a320-neo",
        manifest={"creator": "FlyByWire Simulations"},
        cfg_block={"base_container": "A32NX"},
    )
    assert result["family"] == "flybywire_a32nx"


def test_legacy_candidate_set_uses_modelbehavior_input_events():
    candidates = candidates_for_family("asobo_legacy_a320neo")
    by_id = {item["id"]: item for item in candidates}
    assert by_id["spd_push"]["command"] == "(>B:AUTOPILOT_Speed_Managed_Mode)"
    assert by_id["hdg_pull"]["command"] == "(>B:AUTOPILOT_Heading_Selected_Select)"
    assert by_id["alt_push"]["command"] == "(>B:AUTOPILOT_Altitude_Managed_Mode)"
    assert by_id["vs_push"]["command"] == "(>B:AUTOPILOT_VerticalSpeed_Zero_Push)"
    assert by_id["vs_pull"]["fallback_command"] == "(>H:A320_Neo_FCU_VS_HOLD)"


def test_unknown_family_has_no_guessing_candidate_set():
    assert candidates_for_family("unknown_a320") == ()
