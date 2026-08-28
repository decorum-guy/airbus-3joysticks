from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import time
from typing import Any

from .config import APP_NAME
from .mobiflight import MobiFlightTransport


# These candidates are derived from the official Asobo stock autopilot model-
# behavior templates. They intentionally target the B: InputEvent names used by
# the cockpit interaction layer, rather than the older H: guesses from probe v1.
KNOB_ACTIONS: tuple[dict[str, Any], ...] = (
    {
        "id": "spd_push",
        "label": "SPD PUSH · managed speed",
        "desired_trigger": "LEFT L3",
        "rpn": "(>B:AUTOPILOT_Speed_Managed_Mode)",
        "fallback_rpn": "(>H:A320_Neo_CDU_MODE_MANAGED_SPEED)",
        "watch": ("speed_slot",),
    },
    {
        "id": "spd_pull",
        "label": "SPD PULL · selected speed",
        "desired_trigger": "LEFT L1+L3",
        "rpn": "(>B:AUTOPILOT_Speed_Selected_Mode)",
        "fallback_rpn": "(>H:A320_Neo_CDU_MODE_SELECTED_SPEED)",
        "watch": ("speed_slot",),
    },
    {
        "id": "hdg_push",
        "label": "HDG PUSH · managed heading",
        "desired_trigger": "LEFT R3",
        "rpn": "(>B:AUTOPILOT_Heading_Managed_Select)",
        "fallback_rpn": "(>H:A320_Neo_CDU_MODE_MANAGED_HEADING)",
        "watch": ("heading_slot",),
    },
    {
        "id": "hdg_pull",
        "label": "HDG PULL · selected heading",
        "desired_trigger": "LEFT L1+R3",
        "rpn": "(>B:AUTOPILOT_Heading_Selected_Select)",
        "fallback_rpn": "(>H:A320_Neo_CDU_MODE_SELECTED_HEADING)",
        "watch": ("heading_slot",),
    },
    {
        "id": "alt_push",
        "label": "ALT PUSH · managed altitude",
        "desired_trigger": "RIGHT L3",
        "rpn": "(>B:AUTOPILOT_Altitude_Managed_Mode)",
        "fallback_rpn": "(>H:A320_Neo_CDU_MODE_MANAGED_ALTITUDE)",
        "watch": ("altitude_slot",),
    },
    {
        "id": "alt_pull",
        "label": "ALT PULL · selected altitude",
        "desired_trigger": "RIGHT L1+L3",
        "rpn": "(>B:AUTOPILOT_Altitude_Selected_Mode)",
        "fallback_rpn": "(>H:A320_Neo_CDU_MODE_SELECTED_ALTITUDE)",
        "watch": ("altitude_slot",),
    },
    {
        "id": "vs_push",
        "label": "V/S PUSH · zero / level-off",
        "desired_trigger": "RIGHT R3",
        "rpn": "(>B:AUTOPILOT_VerticalSpeed_Zero_Push)",
        "fallback_rpn": "(>H:A320_Neo_FCU_VS_ZERO)",
        "watch": ("vs_slot", "vertical_speed_target"),
    },
    {
        "id": "vs_pull",
        "label": "V/S PULL · hold / selected V/S",
        "desired_trigger": "RIGHT L1+R3",
        "rpn": "(>B:AUTOPILOT_VerticalSpeed_Hold_Pull)",
        "fallback_rpn": "(>H:A320_Neo_FCU_VS_HOLD)",
        "watch": ("vs_slot", "vertical_speed_target"),
    },
)

# Generic events used by the official stock Asobo templates. Unlike the v1 H:
# candidates, these have directly readable simulator state that the probe can
# compare before/after without relying solely on visual judgement.
GENERIC_ACTIONS: tuple[dict[str, Any], ...] = (
    {
        "id": "spd_mach",
        "label": "SPD / MACH",
        "desired_trigger": "LEFT D-pad up",
        "event": "AP_MANAGED_SPEED_IN_MACH_TOGGLE",
        "watch": ("managed_speed_in_mach",),
        "safe_restore": True,
    },
    {
        "id": "loc",
        "label": "LOC",
        "desired_trigger": "LEFT D-pad left",
        "event": "AP_LOC_HOLD",
        "watch": ("approach_hold", "glideslope_hold", "nav1_lock"),
        "safe_restore": False,
        "state_dependent": True,
    },
    {
        "id": "appr",
        "label": "APPR",
        "desired_trigger": "LEFT triangle / Y",
        "event": "AP_APR_HOLD",
        "watch": ("approach_hold", "approach_arm", "glideslope_hold", "glideslope_arm"),
        "safe_restore": False,
        "state_dependent": True,
    },
    {
        "id": "athr",
        "label": "A/THR",
        "desired_trigger": "LEFT cross / A",
        "event": "AUTO_THROTTLE_ARM",
        "watch": ("autothrottle_arm",),
        "safe_restore": True,
        "optional": True,
    },
)

SIMVARS: dict[str, tuple[str, str | None]] = {
    "aircraft_title": ("TITLE", None),
    "speed_slot": ("AUTOPILOT SPEED SLOT INDEX", "Number"),
    "heading_slot": ("AUTOPILOT HEADING SLOT INDEX", "Number"),
    "altitude_slot": ("AUTOPILOT ALTITUDE SLOT INDEX", "Number"),
    "vs_slot": ("AUTOPILOT VS SLOT INDEX", "Number"),
    "vertical_speed_target": ("AUTOPILOT VERTICAL HOLD VAR", "Feet per minute"),
    "managed_speed_in_mach": ("AUTOPILOT MANAGED SPEED IN MACH", "Bool"),
    "approach_hold": ("AUTOPILOT APPROACH HOLD", "Bool"),
    "approach_arm": ("AUTOPILOT APPROACH ARM", "Bool"),
    "glideslope_hold": ("AUTOPILOT GLIDESLOPE HOLD", "Bool"),
    "glideslope_arm": ("AUTOPILOT GLIDESLOPE ARM", "Bool"),
    "nav1_lock": ("AUTOPILOT NAV1 LOCK", "Bool"),
    "autothrottle_arm": ("AUTOPILOT THROTTLE ARM", "Bool"),
}


def _read(sc: Any, key: str) -> dict[str, Any]:
    name, units = SIMVARS[key]
    try:
        value = sc.get_simdatum(name, units=units, timeout_seconds=1.2)
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        return {"ok": True, "value": value, "name": name, "units": units}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "name": name, "units": units}


def snapshot(sc: Any, keys: tuple[str, ...] | list[str]) -> dict[str, Any]:
    return {key: _read(sc, key) for key in keys}


def changed(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for key in before:
        b = before[key]
        a = after.get(key, {})
        if b.get("ok") and a.get("ok") and b.get("value") != a.get("value"):
            result.append(key)
    return result


def _yes_no(prompt: str, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    raw = input(f"{prompt} {suffix}: ").strip().lower()
    if not raw:
        return default
    return raw in {"y", "yes", "д", "да"}


def _observation(prompt: str) -> dict[str, Any]:
    raw = input(f"{prompt} [y/n/u]: ").strip().lower()
    if raw in {"y", "yes", "д", "да"}:
        worked: bool | None = True
    elif raw in {"n", "no", "н", "нет"}:
        worked = False
    else:
        worked = None
    return {"worked": worked, "raw": raw}


def _save(report: dict[str, Any]) -> list[str]:
    payload = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    local = Path.cwd() / "stock-airbus-button-probe-report.json"
    local.write_text(payload, encoding="utf-8")
    app_dir = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME / "diagnostics"
    app_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    archive = app_dir / f"stock-airbus-button-probe-{stamp}.json"
    archive.write_text(payload, encoding="utf-8")
    return [str(local.resolve()), str(archive.resolve())]


def _print_changes(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    keys = changed(before, after)
    if keys:
        print("Machine-observed change:")
        for key in keys:
            print(f"  {key}: {before[key].get('value')} -> {after[key].get('value')}")
    else:
        print("Machine-observed watched SimVars: no change detected.")
    return keys


def _send_generic(sc: Any, event: str) -> tuple[bool, str | None]:
    try:
        sc.send_event(event)
        return True, None
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def main() -> None:
    print("Airbus 3 Joysticks · STOCK A320 button probe v2")
    print("================================================")
    print("This replaces the first H-event guess probe. It uses official Asobo")
    print("stock-model InputEvents plus machine-readable SimVars where available.")
    print("It does NOT alter production bindings.\n")
    print("For the safest and clearest run, use the A320 parked/stationary. LOC/APPR")
    print("are state-dependent and may legitimately be ignored without a valid nav/approach state.\n")

    report: dict[str, Any] = {
        "schema_version": 2,
        "created_at": datetime.now().astimezone().isoformat(),
        "knob_actions": [],
        "generic_actions": [],
    }

    if os.name != "nt":
        report["fatal_error"] = "Windows is required for MSFS SimConnect"
        _save(report)
        return

    sc = None
    try:
        from simconnect import SimConnect

        sc = SimConnect(name="Airbus3JoysticksStockButtonProbeV2")
        report["simconnect_connected"] = True
        report["aircraft"] = _read(sc, "aircraft_title")
        report["initial_snapshot"] = snapshot(sc, list(SIMVARS.keys())[1:])
        print(f"Connected: {report['aircraft'].get('value', 'unreadable')}")

        transport = MobiFlightTransport(sc)
        print("Checking MobiFlight WASM...")
        if not transport.initialize(timeout_seconds=1.8):
            report["mobiflight"] = transport.state()
            report["fatal_error"] = "MobiFlight WASM did not answer MF.Ping"
            print("MobiFlight WASM offline; no aircraft-specific event sent.")
            return
        report["mobiflight"] = transport.state()
        print("MobiFlight WASM: ONLINE\n")

        print("PART 1 · Airbus knob PUSH/PULL InputEvents")
        print("The probe records slot/target SimVars around every action.")
        for action in KNOB_ACTIONS:
            print(f"\n--- {action['label']} · desired {action['desired_trigger']} ---")
            if not _yes_no("Test this action?", default=True):
                report["knob_actions"].append({"definition": action, "skipped": True})
                continue
            before = snapshot(sc, action["watch"])
            input("Put the FCU where you can see this control, then press Enter to send the stock B: InputEvent...")
            send_ok = transport.execute_rpn(action["rpn"])
            time.sleep(0.35)
            after = snapshot(sc, action["watch"])
            machine_changes = _print_changes(before, after)
            print("Now inspect the cockpit once. The machine result above is recorded even if the visual state is ambiguous.")
            obs = _observation("Did the intended Airbus action visibly occur?")
            item: dict[str, Any] = {
                "definition": action,
                "backend": "B: InputEvent via MobiFlight calculator code",
                "before": before,
                "send_ok": send_ok,
                "after": after,
                "machine_changed": machine_changes,
                "observation": obs,
            }

            # Only offer the exact H: fallback when the preferred B: path did
            # not visibly work. This keeps a successful run short.
            if send_ok and obs["worked"] is False and _yes_no(
                "B: action did not work. Test the exact H: action used by the Asobo template as fallback?",
                default=True,
            ):
                fallback_before = snapshot(sc, action["watch"])
                item["fallback_send_ok"] = transport.execute_rpn(action["fallback_rpn"])
                time.sleep(0.35)
                fallback_after = snapshot(sc, action["watch"])
                item["fallback_before"] = fallback_before
                item["fallback_after"] = fallback_after
                item["fallback_machine_changed"] = _print_changes(fallback_before, fallback_after)
                item["fallback_observation"] = _observation("Did the fallback perform the intended action?")
            report["knob_actions"].append(item)

        print("\nPART 2 · official generic stock events with SimVar verification")
        for action in GENERIC_ACTIONS:
            print(f"\n--- {action['label']} · desired {action['desired_trigger']} ---")
            if action.get("state_dependent"):
                print("NOTE: this action is flight/nav-state dependent. No change can mean 'not valid in this state', not a bad event.")
            if not _yes_no("Test this action?", default=not action.get("optional", False)):
                report["generic_actions"].append({"definition": action, "skipped": True})
                continue
            before = snapshot(sc, action["watch"])
            send_ok, send_error = _send_generic(sc, action["event"])
            time.sleep(0.4)
            after = snapshot(sc, action["watch"])
            machine_changes = _print_changes(before, after)
            item = {
                "definition": action,
                "backend": "SimConnect K: event",
                "before": before,
                "send_ok": send_ok,
                "send_error": send_error,
                "after": after,
                "machine_changed": machine_changes,
            }
            if action.get("state_dependent"):
                item["observation"] = _observation("Did the cockpit indication visibly change?")

            # Toggle-style probes with a single unambiguous watched bool are
            # restored only when the machine confirms that the state changed.
            if action.get("safe_restore") and machine_changes:
                restore_ok, restore_error = _send_generic(sc, action["event"])
                time.sleep(0.3)
                item["restore_send_ok"] = restore_ok
                item["restore_error"] = restore_error
                item["after_restore"] = snapshot(sc, action["watch"])
            report["generic_actions"].append(item)

        report["final_snapshot"] = snapshot(sc, list(SIMVARS.keys())[1:])

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
        print("\nReport saved:")
        for path in _save(report):
            print(f"  {path}")


if __name__ == "__main__":
    main()
