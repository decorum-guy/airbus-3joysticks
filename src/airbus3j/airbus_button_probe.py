from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import time
from typing import Any

from .aircraft_identity import classify_aircraft, identify_from_disk
from .config import APP_NAME
from .mobiflight import MobiFlightTransport


# Legacy/default Asobo A320neo interaction definitions are based on the Asobo
# ModelBehavior AUTOPILOT templates, not on FlyByWire-style FCU H-events.
# B: events reproduce the model-behavior input event; fallback H: events are
# the documented external code used by that same legacy template.
LEGACY_ASOBO_CANDIDATES: tuple[dict[str, Any], ...] = (
    {
        "id": "spd_push",
        "desired_trigger": "LEFT L3",
        "label": "SPD PUSH · managed speed",
        "method": "rpn",
        "command": "(>B:AUTOPILOT_Speed_Managed_Mode)",
        "fallback_command": "(>H:A320_Neo_CDU_MODE_MANAGED_SPEED)",
        "expected": "Push the SPD knob into managed speed exactly like the virtual cockpit control.",
    },
    {
        "id": "spd_pull",
        "desired_trigger": "LEFT L1+L3",
        "label": "SPD PULL · selected speed",
        "method": "rpn",
        "command": "(>B:AUTOPILOT_Speed_Selected_Mode)",
        "fallback_command": "(>H:A320_Neo_CDU_MODE_SELECTED_SPEED)",
        "expected": "Pull the SPD knob into selected speed exactly like the virtual cockpit control.",
    },
    {
        "id": "hdg_push",
        "desired_trigger": "LEFT R3",
        "label": "HDG PUSH · managed heading/NAV",
        "method": "rpn",
        "command": "(>B:AUTOPILOT_Heading_Managed_Select)",
        "fallback_command": "(>H:A320_Neo_CDU_MODE_MANAGED_HEADING)",
        "expected": "Push the HDG knob into the managed heading/NAV behavior available in the current flight state.",
    },
    {
        "id": "hdg_pull",
        "desired_trigger": "LEFT L1+R3",
        "label": "HDG PULL · selected heading",
        "method": "rpn",
        "command": "(>B:AUTOPILOT_Heading_Selected_Select)",
        "fallback_command": "(>H:A320_Neo_CDU_MODE_SELECTED_HEADING)",
        "expected": "Pull the HDG knob into selected heading exactly like the virtual cockpit control.",
    },
    {
        "id": "alt_push",
        "desired_trigger": "RIGHT L3",
        "label": "ALT PUSH · managed altitude",
        "method": "rpn",
        "command": "(>B:AUTOPILOT_Altitude_Managed_Mode)",
        "fallback_command": "(>H:A320_Neo_CDU_MODE_MANAGED_ALTITUDE)",
        "expected": "Push the ALT knob into managed climb/descent behavior when the aircraft state permits it.",
    },
    {
        "id": "alt_pull",
        "desired_trigger": "RIGHT L1+L3",
        "label": "ALT PULL · selected/open climb-descent",
        "method": "rpn",
        "command": "(>B:AUTOPILOT_Altitude_Selected_Mode)",
        "fallback_command": "(>H:A320_Neo_CDU_MODE_SELECTED_ALTITUDE)",
        "expected": "Pull the ALT knob into selected/open climb-descent behavior.",
    },
    {
        "id": "vs_push",
        "desired_trigger": "RIGHT R3",
        "label": "V/S PUSH · ZERO / level off",
        "method": "rpn",
        "command": "(>B:AUTOPILOT_VerticalSpeed_Zero_Push)",
        "fallback_command": "(>H:A320_Neo_FCU_VS_ZERO)",
        "expected": "Push the V/S knob to the legacy Asobo ZERO/level-off action.",
    },
    {
        "id": "vs_pull",
        "desired_trigger": "RIGHT L1+R3",
        "label": "V/S PULL · HOLD / selected V/S",
        "method": "rpn",
        "command": "(>B:AUTOPILOT_VerticalSpeed_Hold_Pull)",
        "fallback_command": "(>H:A320_Neo_FCU_VS_HOLD)",
        "expected": "Pull the V/S knob to the legacy Asobo HOLD/selected-V/S action.",
    },
    {
        "id": "loc_generic",
        "desired_trigger": "LEFT D-pad left",
        "label": "LOC · generic SimConnect validation",
        "method": "sim_event",
        "command": "AP_LOC_HOLD",
        "expected": "Arm/toggle LOC through the standard simulator event. Test with a valid localizer/navigation setup so the result is meaningful.",
    },
    {
        "id": "appr_generic",
        "desired_trigger": "LEFT triangle / Y",
        "label": "APPR · generic SimConnect validation",
        "method": "sim_event",
        "command": "AP_APR_HOLD",
        "expected": "Arm/toggle approach through the standard simulator event. Test with a valid approach/navigation setup so the result is meaningful.",
    },
)


# The first probe used these FCU H-events. The user's A320neo Global Livery
# accepted the MobiFlight transport but showed definite no-ops for V/S push,
# SPD/MACH, LOC and APPR. They are intentionally not reused for legacy Asobo.
FLYBYWIRE_STYLE_CANDIDATES: tuple[dict[str, Any], ...] = (
    {
        "id": "spd_push",
        "desired_trigger": "LEFT L3",
        "label": "SPD PUSH · experimental non-legacy candidate",
        "method": "rpn",
        "command": "(>H:A320_Neo_FCU_SPEED_PUSH)",
        "expected": "Aircraft-specific SPD push behavior.",
    },
    {
        "id": "spd_pull",
        "desired_trigger": "LEFT L1+L3",
        "label": "SPD PULL · experimental non-legacy candidate",
        "method": "rpn",
        "command": "(>H:A320_Neo_FCU_SPEED_PULL)",
        "expected": "Aircraft-specific SPD pull behavior.",
    },
)


def candidates_for_family(family: str) -> tuple[dict[str, Any], ...]:
    if family == "asobo_legacy_a320neo":
        return LEGACY_ASOBO_CANDIDATES
    if family == "flybywire_a32nx":
        return FLYBYWIRE_STYLE_CANDIDATES
    return ()


def _answer(prompt: str) -> dict[str, Any]:
    raw = input(f"{prompt} [y/n/u=unclear]: ").strip().lower()
    if raw in {"y", "yes", "д", "да"}:
        value: bool | None = True
    elif raw in {"n", "no", "н", "нет"}:
        value = False
    else:
        value = None
    return {"worked": value, "raw": raw}


def _yes_no(prompt: str, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    raw = input(f"{prompt} {suffix}: ").strip().lower()
    if not raw:
        return default
    return raw in {"y", "yes", "д", "да"}


def _save(report: dict[str, Any]) -> list[str]:
    payload = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    local = Path.cwd() / "airbus-button-probe-report.json"
    local.write_text(payload, encoding="utf-8")
    target_dir = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME / "diagnostics"
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    archived = target_dir / f"airbus-button-probe-{stamp}.json"
    archived.write_text(payload, encoding="utf-8")
    return [str(local.resolve()), str(archived.resolve())]


def _read_title(sc: Any) -> Any:
    try:
        return sc.get_simdatum("TITLE", timeout_seconds=1.5)
    except Exception as exc:
        return f"unreadable: {exc}"


def _send_candidate(sc: Any, transport: MobiFlightTransport, candidate: dict[str, Any]) -> bool:
    method = candidate["method"]
    command = candidate["command"]
    if method == "rpn":
        return transport.execute_rpn(command)
    if method == "sim_event":
        try:
            sc.send_event(command)
            return True
        except Exception as exc:
            transport.last_error = f"SimConnect event failed: {type(exc).__name__}: {exc}"
            return False
    raise ValueError(f"unknown candidate method: {method}")


def main() -> None:
    print("Airbus 3 Joysticks · aircraft-aware button probe")
    print("=================================================")
    print("Guided VALIDATION only. Production bindings are not changed by this tool.")
    print("The probe identifies the loaded aircraft family before choosing events.\n")

    report: dict[str, Any] = {
        "schema_version": 2,
        "created_at": datetime.now().astimezone().isoformat(),
        "candidates": [],
    }

    if os.name != "nt":
        report["fatal_error"] = "Windows is required for MSFS SimConnect"
        _save(report)
        print(report["fatal_error"])
        return

    sc = None
    try:
        from simconnect import SimConnect

        sc = SimConnect(name="Airbus3JoysticksButtonProbe")
        report["simconnect_connected"] = True
        report["aircraft_title"] = _read_title(sc)
        print(f"SimConnect connected. Aircraft: {report['aircraft_title']}")

        identity = identify_from_disk(str(report["aircraft_title"]))
        report["aircraft_identity"] = identity
        classification = identity.get("classification") or classify_aircraft(str(report["aircraft_title"]))
        report["aircraft_family"] = classification
        family = str(classification.get("family", "unknown_a320"))
        print(f"Detected aircraft family: {family} ({classification.get('confidence', 'unknown')} confidence)")
        for evidence in classification.get("evidence", []):
            print(f"  - {evidence}")

        candidates = candidates_for_family(family)
        if not candidates:
            report["fatal_error"] = (
                f"No validated candidate set exists for aircraft family {family}. "
                "No cockpit event was sent."
            )
            print("\n" + report["fatal_error"])
            print("Run scripts\\aircraft-identify.ps1 and use its report to add the correct backend first.")
            return

        transport = MobiFlightTransport(sc)
        needs_mobiflight = any(item["method"] == "rpn" for item in candidates)
        if needs_mobiflight:
            print("Checking MobiFlight WASM with MF.Ping...")
            available = transport.initialize(timeout_seconds=1.8)
            report["mobiflight"] = transport.state()
            if not available:
                print("\nMobiFlight WASM did not answer MF.Ping.")
                print("No aircraft-specific calculator event was sent.")
                print(f"Detail: {transport.last_error}")
                return
            print("MobiFlight WASM: ONLINE\n")

        if family == "asobo_legacy_a320neo":
            print("LEGACY ASOBO profile selected.")
            print("This intentionally does NOT reuse the previous FCU_PUSH/PULL H-events.")
            print("The new candidates follow the legacy Asobo AUTOPILOT ModelBehavior interactions.\n")

        print("For each item, first put the cockpit in a state where the action is meaningful.")
        print("Press Enter to send ONE event, inspect the cockpit, then answer y/n/u.")
        print("You can skip any item.\n")

        for candidate in candidates:
            print(f"--- {candidate['label']} · desired {candidate['desired_trigger']} ---")
            print(f"Method: {candidate['method']} · {candidate['command']}")
            print(f"Expected: {candidate['expected']}")
            item: dict[str, Any] = {"definition": candidate}
            if not _yes_no("Test this candidate?", default=True):
                item["skipped"] = True
                report["candidates"].append(item)
                print("skipped\n")
                continue

            input("When you are looking at the relevant cockpit control, press Enter to send ONE event...")
            item["send_ok"] = _send_candidate(sc, transport, candidate)
            item["transport_state_after_send"] = transport.state()
            if not item["send_ok"]:
                print(f"Send FAILED: {transport.last_error}\n")
                item["observation"] = {"worked": None, "raw": "transport-failed"}
                report["candidates"].append(item)
                continue

            time.sleep(0.2)
            print("Event sent. NOW inspect the A320 cockpit.")
            observation = _answer("Did it perform the exact intended action?")
            item["observation"] = observation

            fallback = candidate.get("fallback_command")
            if fallback and observation.get("worked") is False:
                print(f"Primary B-event was a definite no-op. Documented legacy H-event fallback: {fallback}")
                if _yes_no("Try the fallback once?", default=True):
                    input("Look at the same cockpit control and press Enter to send the fallback...")
                    fallback_ok = transport.execute_rpn(str(fallback))
                    item["fallback"] = {
                        "command": fallback,
                        "send_ok": fallback_ok,
                        "transport_state_after_send": transport.state(),
                    }
                    if fallback_ok:
                        time.sleep(0.2)
                        item["fallback"]["observation"] = _answer(
                            "Did the fallback perform the exact intended action?"
                        )
                    else:
                        item["fallback"]["observation"] = {
                            "worked": None,
                            "raw": "transport-failed",
                        }

            item["notes"] = input("Optional short note / visible indication (Enter to leave blank): ").strip()
            report["candidates"].append(item)
            print()

    except KeyboardInterrupt:
        report["aborted_reason"] = "KeyboardInterrupt"
        print("\nProbe interrupted by user.")
    except Exception as exc:
        report["fatal_error"] = {"type": type(exc).__name__, "message": str(exc)}
        print(f"\nProbe failed: {type(exc).__name__}: {exc}")
    finally:
        if sc is not None:
            try:
                sc.Close()
            except Exception:
                pass
        paths = _save(report)
        print("\nReport saved:")
        for path in paths:
            print(f"  {path}")


if __name__ == "__main__":
    main()
