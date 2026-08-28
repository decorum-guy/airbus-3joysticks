# Stock A320neo button backend notes

Status: validation in progress for the MSFS 2020 aircraft reported by SimConnect as `A320neo Global Livery`.

## Aircraft identity gate

Aircraft implementation matters: legacy Asobo, FlyByWire A32NX and iniBuilds A320neo do not share one universal cockpit-event namespace.

`powershell -ExecutionPolicy Bypass -File .\scripts\aircraft-identify.ps1` is a read-only diagnostic that combines the live SimConnect `TITLE` / ATC identity with local MSFS package metadata. It finds `UserCfg.opt`, resolves `InstalledPackagesPath`, scans likely A320 `aircraft.cfg` files and records package `manifest.json` creator/version/base-container evidence.

The normal `stock-airbus-button-probe.ps1` now runs the same identity check first. It only starts the stock Asobo event probe when the loaded aircraft is classified as `asobo_legacy_a320neo`; otherwise it stops before sending a cockpit event. Explicit package metadata overrides a reused human-readable livery title.

`A320neo Global Livery` is also recognized as a high-confidence legacy/default Asobo title when package files cannot be inspected, but package metadata remains stronger evidence when available.

## What probe v1 established

The MobiFlight WASM transport is healthy (`MF.Ping` -> `MF.Pong`), but the first guessed FCU H-events were not valid production evidence. In particular the user observed no effect from the v1 SPD/MACH, LOC, or APPR H-event candidates. Do not promote these v1 guesses:

- `A320_Neo_FCU_SPEED_PUSH/PULL`
- `A320_Neo_FCU_ALT_PUSH/PULL`
- `A320_Neo_FCU_VS_PUSH/PULL`
- `A320_Neo_FCU_SPEED_TOGGLE_SPEED_MACH`
- `A320_Neo_FCU_LOC_PUSH`
- `A320_Neo_FCU_APPR_PUSH`

## Official Asobo stock model-behavior candidates

The MSFS SDK Template Explorer shows the AIRBUS branches of the stock Asobo autopilot templates using the following cockpit InputEvents. These are the preferred v2 candidates and still require physical validation on the loaded aircraft before becoming production bindings.

| Cockpit action | B: InputEvent calculator code | Template's underlying H: action |
| --- | --- | --- |
| SPD PUSH / managed | `(>B:AUTOPILOT_Speed_Managed_Mode)` | `(>H:A320_Neo_CDU_MODE_MANAGED_SPEED)` |
| SPD PULL / selected | `(>B:AUTOPILOT_Speed_Selected_Mode)` | `(>H:A320_Neo_CDU_MODE_SELECTED_SPEED)` |
| HDG PUSH / managed | `(>B:AUTOPILOT_Heading_Managed_Select)` | `(>H:A320_Neo_CDU_MODE_MANAGED_HEADING)` |
| HDG PULL / selected | `(>B:AUTOPILOT_Heading_Selected_Select)` | `(>H:A320_Neo_CDU_MODE_SELECTED_HEADING)` |
| ALT PUSH / managed | `(>B:AUTOPILOT_Altitude_Managed_Mode)` | `(>H:A320_Neo_CDU_MODE_MANAGED_ALTITUDE)` |
| ALT PULL / selected | `(>B:AUTOPILOT_Altitude_Selected_Mode)` | `(>H:A320_Neo_CDU_MODE_SELECTED_ALTITUDE)` |
| V/S PUSH / zero | `(>B:AUTOPILOT_VerticalSpeed_Zero_Push)` | `(>H:A320_Neo_FCU_VS_ZERO)` |
| V/S PULL / hold | `(>B:AUTOPILOT_VerticalSpeed_Hold_Pull)` | `(>H:A320_Neo_FCU_VS_HOLD)` |

Official source:
- https://docs.flightsimulator.com/html/Content_Configuration/Models/ModelBehaviors/TemplateExplorer/Asobo/Common/Autopilot.html
- https://docs.flightsimulator.com/html/Content_Configuration/Models/ModelBehaviors/TemplateExplorer/Asobo/Common/Subtemplates/Autopilot_Subtemplates.html

## Generic stock-template events

The same stock templates show:

- SPD/MACH: `AP_MANAGED_SPEED_IN_MACH_TOGGLE`, observable through `AUTOPILOT MANAGED SPEED IN MACH`.
- LOC: `AP_LOC_HOLD`. This is navigation-state dependent.
- APPR: `AP_APR_HOLD`. This is approach/navigation-state dependent.
- A/THR generic candidate: `AUTO_THROTTLE_ARM`, observable through `AUTOPILOT THROTTLE ARM`.

Official event documentation:
- https://docs.flightsimulator.com/html/Programming_Tools/Event_IDs/Aircraft_Autopilot_Flight_Assist_Events.htm

Relevant machine-readable slot SimVars:
- `AUTOPILOT SPEED SLOT INDEX`
- `AUTOPILOT HEADING SLOT INDEX`
- `AUTOPILOT ALTITUDE SLOT INDEX`
- `AUTOPILOT VS SLOT INDEX`

Slot index changes are evidence, not by themselves a universal selected-vs-managed semantic mapping. The v2 probe records them before/after instead of assuming a forum-derived mapping.

## Not yet solved

- AP1 and AP2 must remain separate pending actions. Generic `AP_MASTER` cannot represent the two independent Airbus channels.
- TRK/FPA remains pending exact stock behavior validation.
- Production PUSH/PULL bindings remain pending until the v2 probe confirms them on the user's stock A320.
