from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import time
from typing import Any

from .config import APP_NAME


PROBES: tuple[dict[str, Any], ...] = (
    {
        "name": "SPD",
        "event": "AP_SPD_VAR_INC",
        "restore_event": "AP_SPD_VAR_DEC",
        "simvar": "AUTOPILOT AIRSPEED HOLD VAR",
        "units": "Knots",
        "steps": 5,
    },
    {
        "name": "HDG",
        "event": "HEADING_BUG_INC",
        "restore_event": "HEADING_BUG_DEC",
        "simvar": "AUTOPILOT HEADING LOCK DIR",
        "units": "Degrees",
        "steps": 5,
    },
    {
        "name": "ALT",
        "event": "AP_ALT_VAR_INC",
        "restore_event": "AP_ALT_VAR_DEC",
        "simvar": "AUTOPILOT ALTITUDE LOCK VAR",
        "units": "Feet",
        "steps": 2,
    },
)

VS_PROBE = {
    "name": "V/S",
    "event": "AP_VS_VAR_INC",
    "simvar": "AUTOPILOT VERTICAL HOLD VAR",
    "units": "Feet per minute",
    "steps": 5,
}


def _read(sc: Any, name: str, units: str | None) -> dict[str, Any]:
    try:
        value = sc.get_simdatum(name, units=units, timeout_seconds=1.5)
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        return {"ok": True, "value": value, "units": units}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "units": units}


def _send_sequence(sc: Any, event: str, simvar: str, units: str, count: int) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for index in range(1, count + 1):
        item: dict[str, Any] = {"step": index, "event": event}
        try:
            sc.send_event(event)
            item["send_ok"] = True
        except Exception as exc:
            item["send_ok"] = False
            item["send_error"] = str(exc)
            samples.append(item)
            break
        time.sleep(0.35)
        item["simvar"] = _read(sc, simvar, units)
        samples.append(item)
    return samples


def _save(report: dict[str, Any]) -> list[str]:
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    app_dir = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME / "diagnostics"
    app_dir.mkdir(parents=True, exist_ok=True)
    local = Path.cwd() / "fcu-probe-report.json"
    archive = app_dir / f"fcu-probe-{stamp}.json"
    payload = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    local.write_text(payload, encoding="utf-8")
    archive.write_text(payload, encoding="utf-8")
    return [str(local.resolve()), str(archive.resolve())]


def main() -> None:
    print("Airbus 3 Joysticks · focused FCU probe")
    print("======================================")
    print("Use this only with MSFS 2020 already loaded into the A320 cockpit.")
    print("This does NOT repeat controller identity/input diagnostics.\n")

    report: dict[str, Any] = {
        "schema_version": 1,
        "created_at": datetime.now().astimezone().isoformat(),
        "standard_probes": [],
    }

    if os.name != "nt":
        report["fatal_error"] = "Windows is required for SimConnect"
        for path in _save(report):
            print(path)
        return

    try:
        from simconnect import SimConnect
    except Exception as exc:
        report["fatal_error"] = f"pysimconnect import failed: {exc}"
        for path in _save(report):
            print(path)
        return

    sc = None
    try:
        sc = SimConnect(name="Airbus3JoysticksFCUProbe")
        report["connect_ok"] = True
        report["aircraft_title"] = _read(sc, "TITLE", None)
        print(f"Connected. Aircraft: {report['aircraft_title'].get('value', 'unreadable')}\n")

        print("For SPD / HDG / ALT we deliberately send several increments so the change is obvious.")
        print("IMPORTANT: after each batch, switch to the cockpit BEFORE answering the prompt.")
        print("The script waits for you. It will restore the same number of steps only after you answer.\n")

        for probe in PROBES:
            name = probe["name"]
            print(f"--- {name} ---")
            before = _read(sc, probe["simvar"], probe["units"])
            print(f"SimConnect before: {before.get('value') if before.get('ok') else 'unreadable'}")
            input(
                f"Put the cockpit/FCU where you can inspect {name}, then press Enter here to send "
                f"{probe['steps']} increment events..."
            )
            increments = _send_sequence(
                sc,
                probe["event"],
                probe["simvar"],
                probe["units"],
                int(probe["steps"]),
            )
            after = _read(sc, probe["simvar"], probe["units"])
            print(f"SimConnect after increments: {after.get('value') if after.get('ok') else 'unreadable'}")
            print("NOW switch to the A320 cockpit and look at the visible FCU value.")
            visible = input(f"Return here and type the exact visible {name} value (or u if genuinely unclear): ").strip()

            restore_samples = _send_sequence(
                sc,
                probe["restore_event"],
                probe["simvar"],
                probe["units"],
                int(probe["steps"]),
            )
            after_restore = _read(sc, probe["simvar"], probe["units"])
            print(f"Restored SimConnect value: {after_restore.get('value') if after_restore.get('ok') else 'unreadable'}\n")
            report["standard_probes"].append(
                {
                    "definition": probe,
                    "before": before,
                    "increments": increments,
                    "after_increments": after,
                    "visible_value_reported_by_user": visible,
                    "restore_samples": restore_samples,
                    "after_restore": after_restore,
                }
            )

        print("--- V/S SPECIAL PROBE ---")
        print("The previous full diagnostic showed unusual V/S semantics, so this test does NOT assume")
        print("that the first AP_VS_VAR_INC means +100 fpm and it will NOT auto-restore V/S.")
        print("Using the MOUSE, set a clearly visible V/S target (for example +1000) in the A320.")
        input("When the cockpit shows the starting V/S you want to test, press Enter...")
        vs_before = _read(sc, VS_PROBE["simvar"], VS_PROBE["units"])
        visible_before = input("Type the V/S value/indication you can visibly see right now: ").strip()
        print("Five AP_VS_VAR_INC events will now be sent one at a time.")
        vs_samples = _send_sequence(
            sc,
            VS_PROBE["event"],
            VS_PROBE["simvar"],
            VS_PROBE["units"],
            int(VS_PROBE["steps"]),
        )
        print("NOW switch to the cockpit and inspect V/S before answering.")
        visible_after = input("Return here and type the visible V/S value/indication (or u): ").strip()
        vs_after = _read(sc, VS_PROBE["simvar"], VS_PROBE["units"])
        report["vs_probe"] = {
            "definition": VS_PROBE,
            "before": vs_before,
            "visible_before": visible_before,
            "increments": vs_samples,
            "after": vs_after,
            "visible_after": visible_after,
            "automatic_restore": False,
        }
        print("V/S was intentionally NOT restored automatically. Set it back with the cockpit controls if desired.\n")

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

    print("Saved:")
    for path in _save(report):
        print(f"  {path}")
    print("Send fcu-probe-report.json back in the chat.")


if __name__ == "__main__":
    main()
