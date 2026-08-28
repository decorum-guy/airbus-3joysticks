from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import time
from typing import Any

from .config import APP_NAME
from .mobiflight import MobiFlightTransport


# Only candidates with evidence in the Asobo/MobiFlight preset ecosystem are
# included here. This is a validation list, not a production binding list.
CANDIDATES: tuple[dict[str, str], ...] = (
    {
        "id": "spd_push",
        "desired_trigger": "LEFT L3",
        "label": "SPD PUSH · managed speed",
        "rpn": "(>H:A320_Neo_FCU_SPEED_PUSH)",
        "expected": "FCU speed enters managed mode / managed indication changes as when physically pushing the SPD knob.",
    },
    {
        "id": "spd_pull",
        "desired_trigger": "LEFT L1+L3",
        "label": "SPD PULL · selected speed",
        "rpn": "(>H:A320_Neo_FCU_SPEED_PULL)",
        "expected": "FCU speed enters selected mode as when physically pulling the SPD knob.",
    },
    {
        "id": "alt_push",
        "desired_trigger": "RIGHT L3",
        "label": "ALT PUSH · managed altitude",
        "rpn": "(>H:A320_Neo_FCU_ALT_PUSH)",
        "expected": "Altitude knob push behavior / managed climb-descent mode changes exactly like a cockpit push.",
    },
    {
        "id": "alt_pull",
        "desired_trigger": "RIGHT L1+L3",
        "label": "ALT PULL · selected/open climb-descent",
        "rpn": "(>H:A320_Neo_FCU_ALT_PULL)",
        "expected": "Altitude knob pull behavior changes exactly like a cockpit pull.",
    },
    {
        "id": "vs_push",
        "desired_trigger": "RIGHT R3",
        "label": "V/S PUSH · level off",
        "rpn": "(>H:A320_Neo_FCU_VS_PUSH)",
        "expected": "V/S knob push behavior occurs, normally commanding/arming the Airbus level-off behavior.",
    },
    {
        "id": "vs_pull",
        "desired_trigger": "RIGHT L1+R3",
        "label": "V/S PULL · selected V/S",
        "rpn": "(>H:A320_Neo_FCU_VS_PULL)",
        "expected": "V/S knob pull behavior occurs exactly like a cockpit pull.",
    },
    {
        "id": "spd_mach",
        "desired_trigger": "LEFT D-pad up",
        "label": "SPD / MACH",
        "rpn": "(>H:A320_Neo_FCU_SPEED_TOGGLE_SPEED_MACH)",
        "expected": "FCU speed display toggles between SPD and MACH presentation.",
    },
    {
        "id": "loc",
        "desired_trigger": "LEFT D-pad left",
        "label": "LOC",
        "rpn": "(>H:A320_Neo_FCU_LOC_PUSH)",
        "expected": "LOC pushbutton state changes exactly as clicking LOC in the virtual cockpit.",
    },
    {
        "id": "appr",
        "desired_trigger": "LEFT triangle / Y",
        "label": "APPR",
        "rpn": "(>H:A320_Neo_FCU_APPR_PUSH)",
        "expected": "APPR pushbutton state changes exactly as clicking APPR in the virtual cockpit.",
    },
)


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


def main() -> None:
    print("Airbus 3 Joysticks · Airbus-specific button probe")
    print("====================================================")
    print("This is a guided VALIDATION tool. It does not edit production bindings.")
    print("Use it only with MSFS 2020 loaded into the tested A320 cockpit and the")
    print("aircraft safely stationary. Every candidate waits for your confirmation")
    print("before sending exactly one gauge/H-event through MobiFlight WASM.\n")

    report: dict[str, Any] = {
        "schema_version": 1,
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

        transport = MobiFlightTransport(sc)
        print("Checking MobiFlight WASM with MF.Ping...")
        available = transport.initialize(timeout_seconds=1.8)
        report["mobiflight"] = transport.state()
        if not available:
            print("\nMobiFlight WASM did not answer MF.Ping.")
            print("No aircraft-specific event was sent.")
            print("Install/enable the MobiFlight WASM module, restart MSFS, then run this probe again.")
            print(f"Detail: {transport.last_error}")
            return

        print("MobiFlight WASM: ONLINE\n")
        print("For each item: put the cockpit in a state where the action will be visible,")
        print("press Enter to send it, then LOOK AT THE COCKPIT before answering y/n/u.")
        print("You may skip any item. No candidate is promoted to production by this script.\n")

        for candidate in CANDIDATES:
            print(f"--- {candidate['label']} · desired {candidate['desired_trigger']} ---")
            print(f"Expected: {candidate['expected']}")
            item: dict[str, Any] = {"definition": candidate}
            if not _yes_no("Test this candidate?", default=True):
                item["skipped"] = True
                report["candidates"].append(item)
                print("skipped\n")
                continue
            input("When you are watching the relevant FCU control, press Enter to send ONE event...")
            item["send_ok"] = transport.execute_rpn(candidate["rpn"])
            item["transport_state_after_send"] = transport.state()
            if not item["send_ok"]:
                print(f"Transport send FAILED: {transport.last_error}\n")
                item["observation"] = {"worked": None, "raw": "transport-failed"}
                report["candidates"].append(item)
                continue
            time.sleep(0.2)
            print("Event sent. NOW inspect the A320 cockpit.")
            item["observation"] = _answer("Did it perform the exact intended Airbus action?")
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
