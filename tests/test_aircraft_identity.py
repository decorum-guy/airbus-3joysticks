from airbus3j.aircraft_identity import (
    classify_aircraft,
    parse_aircraft_cfg,
    parse_usercfg_installed_path,
)


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


def test_global_livery_title_classifies_as_legacy_asobo_when_disk_metadata_is_absent():
    result = classify_aircraft("A320neo Global Livery")
    assert result["family"] == "asobo_legacy_a320neo"
    assert result["confidence"] == "high"


def test_explicit_asobo_package_confirms_legacy_family():
    result = classify_aircraft(
        "Custom paint",
        package_name="asobo-aircraft-a320-neo",
        cfg_block={"base_container": "..\\Asobo_A320_NEO"},
    )
    assert result["family"] == "asobo_legacy_a320neo"


def test_explicit_flybywire_package_wins_over_reused_legacy_title():
    result = classify_aircraft(
        "A320neo Global Livery",
        package_name="flybywire-aircraft-a320-neo",
        manifest={"creator": "FlyByWire Simulations"},
        cfg_block={"base_container": "A32NX"},
    )
    assert result["family"] == "flybywire_a32nx"


def test_explicit_inibuilds_package_wins_over_reused_legacy_title():
    result = classify_aircraft(
        "A320neo Global Livery",
        package_name="microsoft-aircraft-a320neo-inibuilds",
        manifest={"creator": "iniBuilds", "title": "Airbus A320neo"},
    )
    assert result["family"] == "inibuilds_a320neo"


def test_unknown_a320_is_not_guessed():
    result = classify_aircraft("Some custom A320 title")
    assert result["family"] == "unknown_a320"
    assert result["confidence"] == "low"
