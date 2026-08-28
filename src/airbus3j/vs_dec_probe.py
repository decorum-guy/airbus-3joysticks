from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import time
from typing import Any

from .config import APP_NAME


SIMVAR = "AUTOPILOT VERTICAL HOLD VAR"
UNITS = "Feet per minute"
EVENT = "AP_VS_VAR_DEC"
RESTORE_EVENT = "AP_VS_VAR_INC"
STEPS = 5


def _read(sc: Any) -> dict[str, Any]:
    try:
        return {
            "ok": True,
            "value": sc.get_simdatum(SIMVAR, units=UNITS, timeout_seconds=1.5),
            "units": UNITS,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "units": UNITS}


def _send(sc: Any, event: str, count: int) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for step in range(1, count + 1):
        item: dict[str, Any] = {"step": step, "event": event}
        try:
            sc.send_event(event)
            item["send_ok"] = True
        except Exception as exc:
            item["send_ok"] = False
            item["send_error"] = str(exc)
            samples.append(item)
            break
        time.sleep(0.35)
        item["simvar"] = _read(sc)
        samples.append(item)
    return samples


def _save(report: dict[str, Any]) -> list[str]:
    payload = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    local = Path.cwd() / "vs-dec-probe-report.json"
    local.write_text(payload, encoding="utf-8")
    target = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME / "diagnostics"
    target.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    archive = target / f"vs-dec-probe-{stamp}.json"
    archive.write_text(payload, encoding="utf-8")
    return [str(local.resolve()), str(archive.resolve())]


def main() -> None:
    print("Airbus 3 Joysticks · V/S decrement probe")
    print("========================================")
    print("MSFS 2020 must already be loaded into the tested A320 cockpit.")
    print("This sends five AP_VS_VAR_DEC events only after you explicitly continue.\n")

    report: dict[str, Any] = {
        "schema_version": 1,
        "created_at": datetime.now().astimezone().isoformat(),
        "definition": {
            "event": EVENT,
            "restore_event": RESTORE_EVENT,
            "simvar": SIMVAR,
            "units": UNITS,
            "steps": STEPS,
        },
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
        sc = SimConnect(name="Airbus3JoysticksVSDecProbe")
        report["connect_ok"] = True
        try:
            report["aircraft_title"] = sc.get_simdatum("TITLE", units=None, timeout_seconds=1.5)
        except Exception as exc:
            report["aircraft_title_error"] = str(exc)

        print("Using the mouse in the cockpit, set a clear positive V/S target, ideally +1500 fpm.")
        input("When that visible value is set, press Enter here...")
        report["before"] = _read(sc)
        report["visible_before"] = input("Type the visible starting V/S value: ").strip()

        print(f"\nSending {STEPS} decrement events one by one...")
        report["decrements"] = _send(sc, EVENT, STEPS)
        report["after"] = _read(sc)
        print("Switch to the cockpit and inspect V/S now.")
        report["visible_after"] = input("Type the visible V/S value after the five decrements: ").strip()

        restore = input("Restore with five AP_VS_VAR_INC events? [Y/n]: ").strip().lower()
        if restore not in {"n", "no", "нет", "н"}:
            report["restore_samples"] = _send(sc, RESTORE_EVENT, STEPS)
            report["after_restore"] = _read(sc)
            report["restored"] = True
        else:
            report["restored"] = False

    except KeyboardInterrupt:
        report["aborted_reason"] = "KeyboardInterrupt"
        print("\nProbe interrupted.")
    except Exception as exc:
        report["fatal_error"] = {"type": type(exc).__name__, "message": str(exc)}
        print(f"\nProbe failed: {type(exc).__name__}: {exc}")
    finally:
        if sc is not None:
            try:
                sc.Close()
            except Exception:
                pass

    print("\nSaved:")
    for path in _save(report):
        print(f"  {path}")
    print("Send vs-dec-probe-report.json back in the chat.")


if __name__ == "__main__":
    main()
