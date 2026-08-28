from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import time
from typing import Any

from .aircraft_identity import identify_from_disk
from .config import APP_NAME


ACTIONS: tuple[dict[str, Any], ...] = (
    {"id": "spd_push", "label": "SPD PUSH · managed speed", "event": "A32NX.FCU_SPD_PUSH", "desired": "LEFT L3"},
    {"id": "spd_pull", "label": "SPD PULL · selected speed", "event": "A32NX.FCU_SPD_PULL", "desired": "LEFT L1+L3"},
    {"id": "hdg_push", "label": "HDG PUSH · managed heading", "event": "A32NX.FCU_HDG_PUSH", "desired": "LEFT R3"},
    {"id": "hdg_pull", "label": "HDG PULL · selected heading", "event": "A32NX.FCU_HDG_PULL", "desired": "LEFT L1+R3"},
    {"id": "alt_push", "label": "ALT PUSH · managed altitude", "event": "A32NX.FCU_ALT_PUSH", "desired": "RIGHT L3"},
    {"id": "alt_pull", "label": "ALT PULL · selected altitude", "event": "A32NX.FCU_ALT_PULL", "desired": "RIGHT L1+L3"},
    {"id": "vs_push", "label": "V/S PUSH · immediate level-off", "event": "A32NX.FCU_VS_PUSH", "desired": "RIGHT R3"},
    {"id": "vs_pull", "label": "V/S PULL · selected V/S", "event": "A32NX.FCU_VS_PULL", "desired": "RIGHT L1+R3"},
    {"id": "spd_mach", "label": "SPD / MACH", "event": "A32NX.FCU_SPD_MACH_TOGGLE_PUSH", "desired": "LEFT D-pad up"},
    {"id": "trk_fpa", "label": "HDG/TRK · V/S/FPA", "event": "A32NX.FCU_TRK_FPA_TOGGLE_PUSH", "desired": "LEFT D-pad down"},
    {"id": "loc", "label": "LOC", "event": "A32NX.FCU_LOC_PUSH", "desired": "LEFT D-pad left", "state_dependent": True},
    {"id": "appr", "label": "APPR", "event": "A32NX.FCU_APPR_PUSH", "desired": "LEFT triangle / Y", "state_dependent": True},
    {"id": "ap1", "label": "AP1", "event": "A32NX.FCU_AP_1_PUSH", "desired": "LEFT square / X", "state_dependent": True},
    {"id": "ap2", "label": "AP2", "event": "A32NX.FCU_AP_2_PUSH", "desired": "LEFT circle / B", "state_dependent": True},
    {"id": "athr", "label": "A/THR", "event": "A32NX.FCU_ATHR_PUSH", "desired": "LEFT cross / A", "state_dependent": True},
)


def _answer(prompt: str) -> dict[str, Any]:
    raw = input(f"{prompt} [y/n/u=unclear]: ").strip().lower()
    if raw in {"y", "yes", "д", "да"}:
        worked: bool | None = True
    elif raw in {"n", "no", "н", "нет"}:
        worked = False
    else:
        worked = None
    return {"worked": worked, "raw": raw}


def _yes_no(prompt: str, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    raw = input(f"{prompt} {suffix}: ").strip().lower()
    if not raw:
        return default
    return raw in {"y", "yes", "д", "да"}


def _save(report: dict[str, Any]) -> list[str]:
    payload = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    local = Path.cwd() / "flybywire-button-probe-report.json"
    local.write_text(payload, encoding="utf-8")
    app_dir = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME / "diagnostics"
    app_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    archive = app_dir / f"flybywire-button-probe-{stamp}.json"
    archive.write_text(payload, encoding="utf-8")
    return [str(local.resolve()), str(archive.resolve())]


def main() -> None:
    print("Airbus 3 Joysticks · FlyByWire A32NX button probe")
    print("==================================================")
    print("Uses FlyByWire's documented custom SimConnect events.")
    print("It does NOT change production bindings.\n")
    print("For PUSH/PULL visibility, load the aircraft powered and with the FCU visible.")
    print("AP1/AP2/LOC/APPR/A-THR are flight/state dependent; skip them if the current")
    print("aircraft state cannot legitimately accept the command.\n")

    report: dict[str, Any] = {
        "schema_version": 1,
        "created_at": datetime.now().astimezone().isoformat(),
        "actions": [],
    }

    if os.name != "nt":
        report["fatal_error"] = "Windows is required for MSFS SimConnect"
        _save(report)
        return

    sc = None
    try:
        from simconnect import SimConnect

        sc = SimConnect(name="Airbus3JoysticksFlyByWireProbe")
        title = sc.get_simdatum("TITLE", timeout_seconds=1.5)
        report["title"] = title
        identity = identify_from_disk(title)
        report["identity"] = identity
        classification = identity.get("classification", {})
        family = classification.get("family")
        print(f"Connected: {title}")
        print(f"Detected family: {family} ({classification.get('confidence', 'unknown')} confidence)")

        if family != "flybywire_a32nx":
            report["fatal_error"] = f"Loaded aircraft is not identified as FlyByWire A32NX (got {family})"
            print("\nSTOP: no A32NX custom event was sent.")
            print("Load the FlyByWire A32NX in MSFS, wait until the cockpit is fully loaded, then rerun.")
            return

        print("FlyByWire identity: CONFIRMED\n")
        for action in ACTIONS:
            print(f"--- {action['label']} · desired {action['desired']} ---")
            if action.get("state_dependent"):
                print("NOTE: state-dependent; no visible effect can be legitimate in the wrong flight/nav state.")
            if not _yes_no("Test this action?", default=not action.get("state_dependent", False)):
                report["actions"].append({"definition": action, "skipped": True})
                print("skipped\n")
                continue
            input("Watch the relevant FCU control, then press Enter to send ONE documented A32NX event...")
            item: dict[str, Any] = {"definition": action}
            try:
                sc.send_event(action["event"])
                item["send_ok"] = True
                item["send_error"] = None
            except Exception as exc:
                item["send_ok"] = False
                item["send_error"] = f"{type(exc).__name__}: {exc}"
                report["actions"].append(item)
                print(f"Send failed: {item['send_error']}\n")
                continue
            time.sleep(0.35)
            item["observation"] = _answer("Did the exact intended cockpit action visibly occur?")
            item["notes"] = input("Optional short note / indication (Enter to leave blank): ").strip()
            report["actions"].append(item)
            print()

    except KeyboardInterrupt:
        report["aborted_reason"] = "KeyboardInterrupt"
        print("\nProbe interrupted by user.")
    except Exception as exc:
        report["fatal_error"] = f"{type(exc).__name__}: {exc}"
        print(f"\nProbe failed: {report['fatal_error']}")
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
