from __future__ import annotations

from ctypes import byref, c_float, c_uint8
from datetime import datetime
import json
import os
from pathlib import Path
import platform
import time
from typing import Any

import sdl2

from .config import APP_NAME, ConfigStore
from .controllers import AXES, BUTTONS, ControllerBackend, ControllerDevice


ROLES = ("left", "center", "right")
ROLE_LABELS = {
    "left": "LEFT · FCU SPD / HDG",
    "center": "CENTER · EFIS / RADIO",
    "right": "RIGHT · FCU ALT / V/S",
}

PASSIVE_SIMVARS: tuple[tuple[str, str | None], ...] = (
    ("TITLE", None),
    ("ATC MODEL", None),
    ("AUTOPILOT AIRSPEED HOLD VAR", "Knots"),
    ("AUTOPILOT HEADING LOCK DIR", "Degrees"),
    ("AUTOPILOT ALTITUDE LOCK VAR", "Feet"),
    ("AUTOPILOT VERTICAL HOLD VAR", "Feet per minute"),
    ("KOHLSMAN SETTING HG", "inHg"),
)

ACTIVE_PROBES: tuple[dict[str, Any], ...] = (
    {
        "name": "FCU speed increment",
        "event": "AP_SPD_VAR_INC",
        "restore_event": "AP_SPD_VAR_DEC",
        "simvar": "AUTOPILOT AIRSPEED HOLD VAR",
        "units": "Knots",
        "expected": "FCU selected speed increases by one normal simulator step",
    },
    {
        "name": "FCU heading increment",
        "event": "HEADING_BUG_INC",
        "restore_event": "HEADING_BUG_DEC",
        "simvar": "AUTOPILOT HEADING LOCK DIR",
        "units": "Degrees",
        "expected": "FCU heading increases by one normal simulator step",
    },
    {
        "name": "FCU altitude increment",
        "event": "AP_ALT_VAR_INC",
        "restore_event": "AP_ALT_VAR_DEC",
        "simvar": "AUTOPILOT ALTITUDE LOCK VAR",
        "units": "Feet",
        "expected": "FCU selected altitude increases by one normal simulator step",
    },
    {
        "name": "FCU vertical-speed increment",
        "event": "AP_VS_VAR_INC",
        "restore_event": "AP_VS_VAR_DEC",
        "simvar": "AUTOPILOT VERTICAL HOLD VAR",
        "units": "Feet per minute",
        "expected": "FCU V/S target increases by one normal simulator step",
    },
)


def _yes(prompt: str, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    value = input(f"{prompt} {suffix} ").strip().lower()
    if not value:
        return default
    return value in {"y", "yes", "д", "да"}


def _sdl_version() -> str | None:
    try:
        version = sdl2.SDL_version()
        sdl2.SDL_GetVersion(byref(version))
        return f"{version.major}.{version.minor}.{version.patch}"
    except Exception:
        return None


def _device_record(device: ControllerDevice) -> dict[str, Any]:
    identity = device.public_identity()
    identity["instance_id"] = device.instance_id

    capabilities: dict[str, Any] = {}
    try:
        joystick = sdl2.SDL_GameControllerGetJoystick(device.controller)
        if hasattr(sdl2, "SDL_JoystickCurrentPowerLevel"):
            capabilities["power_level_raw"] = int(sdl2.SDL_JoystickCurrentPowerLevel(joystick))
        if hasattr(sdl2, "SDL_JoystickGetType"):
            capabilities["joystick_type_raw"] = int(sdl2.SDL_JoystickGetType(joystick))
    except Exception as exc:
        capabilities["joystick_metadata_error"] = str(exc)

    try:
        if hasattr(sdl2, "SDL_GameControllerGetNumTouchpads"):
            touchpads = int(sdl2.SDL_GameControllerGetNumTouchpads(device.controller))
            capabilities["touchpads"] = touchpads
            if touchpads > 0 and hasattr(sdl2, "SDL_GameControllerGetNumTouchpadFingers"):
                capabilities["touchpad_fingers"] = [
                    int(sdl2.SDL_GameControllerGetNumTouchpadFingers(device.controller, index))
                    for index in range(touchpads)
                ]
        else:
            capabilities["touchpads"] = None
    except Exception as exc:
        capabilities["touchpad_error"] = str(exc)

    sensor_result: dict[str, Any] = {}
    if hasattr(sdl2, "SDL_GameControllerHasSensor"):
        for label, symbol in (("gyro", "SDL_SENSOR_GYRO"), ("accelerometer", "SDL_SENSOR_ACCEL")):
            if hasattr(sdl2, symbol):
                try:
                    sensor_result[label] = bool(
                        sdl2.SDL_GameControllerHasSensor(device.controller, getattr(sdl2, symbol))
                    )
                except Exception as exc:
                    sensor_result[label] = f"error: {exc}"
    if sensor_result:
        capabilities["sensors"] = sensor_result

    capabilities["rumble_api_available"] = hasattr(sdl2, "SDL_GameControllerRumble")
    capabilities["standard_axes"] = list(AXES)
    capabilities["standard_buttons"] = list(BUTTONS)
    identity["capabilities"] = capabilities
    return identity


def _all_device_records(backend: ControllerBackend) -> list[dict[str, Any]]:
    return [_device_record(device) for device in backend.devices.values()]


def _wait_for_button_press(backend: ControllerBackend, used_keys: set[str]) -> tuple[str, str]:
    previous: dict[str, dict[str, bool]] = {}
    while True:
        snapshots = backend.poll()
        for key, snapshot in snapshots.items():
            buttons = snapshot["buttons"]
            old = previous.get(key, {})
            if key not in used_keys:
                for name, pressed in buttons.items():
                    if pressed and not old.get(name, False):
                        return key, name
            previous[key] = dict(buttons)
        time.sleep(0.04)


def _assign_roles(backend: ControllerBackend) -> dict[str, dict[str, Any]]:
    print("\n=== ROLE ASSIGNMENT ===")
    print("For each role, press one normal button on the requested physical controller.")
    print("Do not hold a button before the prompt appears. Ctrl+C aborts diagnostics.\n")
    assigned: dict[str, dict[str, Any]] = {}
    used_keys: set[str] = set()

    for role in ROLES:
        print(f"{ROLE_LABELS[role]}: press any button now...")
        key, button = _wait_for_button_press(backend, used_keys)
        used_keys.add(key)
        device = backend.devices[key]
        assigned[role] = {
            "device_key": key,
            "identity": _device_record(device),
            "assignment_button": button,
        }
        source = "serial" if device.serial else ("path" if device.path else "fallback")
        print(f"  -> {device.name} · {source} · {key}\n")
    return assigned


def _identity_comparison(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    serial_same = bool(before.get("serial") and before.get("serial") == after.get("serial"))
    path_same = bool(before.get("path") and before.get("path") == after.get("path"))
    key_same = before.get("device_key") == after.get("device_key")
    guid_same = before.get("guid") == after.get("guid")
    same_model = (
        before.get("vendor_id") == after.get("vendor_id")
        and before.get("product_id") == after.get("product_id")
        and before.get("name") == after.get("name")
    )

    if serial_same:
        verdict = "stable_serial"
    elif path_same:
        verdict = "stable_path"
    elif key_same:
        verdict = "same_generated_key_without_serial_or_path"
    else:
        verdict = "identity_changed_or_unresolved"

    return {
        "verdict": verdict,
        "serial_same": serial_same,
        "path_same": path_same,
        "device_key_same": key_same,
        "guid_same": guid_same,
        "same_model": same_model,
    }


def _reconnect_tests(
    backend: ControllerBackend,
    assigned: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    results: dict[str, Any] = {}
    print("\n=== RECONNECT IDENTITY TEST ===")
    print("This checks whether LEFT/CENTER/RIGHT can be remembered after USB/Bluetooth reconnects.")

    for role in ROLES:
        current_key = assigned[role]["device_key"]
        current = backend.devices.get(current_key)
        if not current:
            results[role] = {"error": "assigned device is no longer connected"}
            continue

        print(f"\n{ROLE_LABELS[role]} · {current.name}")
        before = _device_record(current)
        input("Unplug/disconnect THIS controller, wait for Windows to notice, then press Enter...")
        time.sleep(1.1)
        backend.scan()
        unplug_keys = set(backend.devices)
        removed = current_key not in unplug_keys
        unplug_snapshot = _all_device_records(backend)
        print("  disconnect observed" if removed else "  WARNING: assigned key still present after disconnect")

        input("Reconnect the same controller, wait until Windows sees it, then press Enter...")
        # Do not force-reopen every remaining controller: that could itself alter
        # last-resort instance-ID identities and contaminate the reconnect test.
        for _ in range(6):
            time.sleep(1.05)
            backend.scan()
            if len(backend.devices) >= len(unplug_keys) + 1:
                break

        added_keys = [key for key in backend.devices if key not in unplug_keys]
        after_device: ControllerDevice | None = None
        if len(added_keys) == 1:
            after_device = backend.devices[added_keys[0]]
        elif current_key in backend.devices:
            after_device = backend.devices[current_key]
        else:
            # Last-resort diagnostic selection only. We do not silently use this
            # for persisted runtime assignment when multiple identical pads match.
            candidates = [
                device
                for device in backend.devices.values()
                if device.name == before.get("name")
                and device.vendor_id == before.get("vendor_id")
                and device.product_id == before.get("product_id")
            ]
            if len(candidates) == 1:
                after_device = candidates[0]

        if after_device is None:
            results[role] = {
                "before": before,
                "disconnect_observed": removed,
                "devices_while_disconnected": unplug_snapshot,
                "devices_after_reconnect": _all_device_records(backend),
                "verdict": "could_not_uniquely_identify_reconnected_device",
            }
            print("  -> could not uniquely identify the reconnected device")
            continue

        after = _device_record(after_device)
        comparison = _identity_comparison(before, after)
        results[role] = {
            "before": before,
            "disconnect_observed": removed,
            "after": after,
            "comparison": comparison,
        }
        assigned[role]["device_key"] = after_device.key
        assigned[role]["identity"] = after
        print(f"  -> {comparison['verdict']}")

    return results


def _read_touch_contacts(device: ControllerDevice) -> dict[str, Any]:
    result = {"active_contacts": 0, "samples": []}
    if not (
        hasattr(sdl2, "SDL_GameControllerGetNumTouchpads")
        and hasattr(sdl2, "SDL_GameControllerGetNumTouchpadFingers")
        and hasattr(sdl2, "SDL_GameControllerGetTouchpadFinger")
    ):
        return result
    try:
        touchpads = int(sdl2.SDL_GameControllerGetNumTouchpads(device.controller))
        for touchpad in range(touchpads):
            fingers = int(sdl2.SDL_GameControllerGetNumTouchpadFingers(device.controller, touchpad))
            for finger in range(fingers):
                state = c_uint8()
                x = c_float()
                y = c_float()
                pressure = c_float()
                rc = sdl2.SDL_GameControllerGetTouchpadFinger(
                    device.controller,
                    touchpad,
                    finger,
                    byref(state),
                    byref(x),
                    byref(y),
                    byref(pressure),
                )
                if rc == 0 and state.value:
                    result["active_contacts"] += 1
                    result["samples"].append(
                        {
                            "touchpad": touchpad,
                            "finger": finger,
                            "x": round(float(x.value), 4),
                            "y": round(float(y.value), 4),
                            "pressure": round(float(pressure.value), 4),
                        }
                    )
    except Exception as exc:
        result["error"] = str(exc)
    return result


def _exercise_controller(
    backend: ControllerBackend,
    key: str,
    seconds: float,
) -> dict[str, Any]:
    axis_ranges = {name: {"min": 1.0, "max": -1.0} for name in AXES}
    buttons_seen: set[str] = set()
    prior_buttons: dict[str, bool] = {}
    touch = {"max_active_contacts": 0, "sample_count": 0, "examples": []}
    samples = 0
    deadline = time.monotonic() + seconds

    while time.monotonic() < deadline:
        snapshots = backend.poll()
        snapshot = snapshots.get(key)
        device = backend.devices.get(key)
        if snapshot is None or device is None:
            return {
                "error": "controller disconnected during exercise",
                "axis_ranges": axis_ranges,
                "buttons_seen": sorted(buttons_seen),
            }
        samples += 1
        for name, value in snapshot["axes"].items():
            axis_ranges[name]["min"] = round(min(axis_ranges[name]["min"], float(value)), 4)
            axis_ranges[name]["max"] = round(max(axis_ranges[name]["max"], float(value)), 4)
        for name, pressed in snapshot["buttons"].items():
            if pressed and not prior_buttons.get(name, False):
                buttons_seen.add(name)
        prior_buttons = dict(snapshot["buttons"])

        touch_now = _read_touch_contacts(device)
        active = int(touch_now.get("active_contacts", 0))
        touch["max_active_contacts"] = max(touch["max_active_contacts"], active)
        if active:
            touch["sample_count"] += 1
            if len(touch["examples"]) < 8:
                touch["examples"].extend(touch_now.get("samples", [])[:2])
        if touch_now.get("error"):
            touch["error"] = touch_now["error"]
        time.sleep(0.015)

    return {
        "duration_seconds": seconds,
        "poll_samples": samples,
        "axis_ranges": axis_ranges,
        "buttons_seen": sorted(buttons_seen),
        "touchpad_activity": touch,
    }


def _input_exercises(
    backend: ControllerBackend,
    assigned: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    print("\n=== INPUT EXERCISE ===")
    print("For each controller: move BOTH sticks through full circles and edges;")
    print("press L1/R1, L3/R3, D-pad, all four face buttons, touchpad click/touch if present.")
    print("L2/R2 are optional but moving them once helps identify trigger axis ranges.\n")
    try:
        raw = input("Seconds per controller [10]: ").strip()
        seconds = max(5.0, min(30.0, float(raw))) if raw else 10.0
    except ValueError:
        seconds = 10.0

    result: dict[str, Any] = {}
    for role in ROLES:
        key = assigned[role]["device_key"]
        device = backend.devices.get(key)
        if device is None:
            result[role] = {"error": "assigned device unavailable"}
            continue
        input(f"\nReady for {ROLE_LABELS[role]} · {device.name}. Press Enter, then operate its controls...")
        result[role] = _exercise_controller(backend, key, seconds)
        seen = ", ".join(result[role].get("buttons_seen", [])) or "none"
        print(f"  buttons observed: {seen}")
    return result


def _rumble_tests(backend: ControllerBackend, assigned: dict[str, dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    print("\n=== RUMBLE TEST ===")
    for role in ROLES:
        key = assigned[role]["device_key"]
        device = backend.devices.get(key)
        if device is None:
            result[role] = {"api_call_ok": False, "user_felt": None, "error": "device unavailable"}
            continue
        print(f"{ROLE_LABELS[role]} · sending a short low-strength pulse...")
        ok = backend.rumble(key, 0.18, 120)
        felt: bool | None = None
        if ok:
            felt = _yes("Did you feel the vibration?", default=True)
        result[role] = {"api_call_ok": ok, "user_felt": felt}
    return result


def _safe_simvar(sc: Any, name: str, units: str | None) -> dict[str, Any]:
    try:
        value = sc.get_simdatum(name, units=units, timeout_seconds=1.5)
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        return {"ok": True, "value": value, "units": units}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "units": units}


def _read_simvars(sc: Any) -> dict[str, Any]:
    return {name: _safe_simvar(sc, name, units) for name, units in PASSIVE_SIMVARS}


def _simconnect_diagnostics() -> dict[str, Any]:
    report: dict[str, Any] = {"platform_supported": os.name == "nt"}
    if os.name != "nt":
        report["error"] = "SimConnect diagnostics require Windows"
        return report

    try:
        from simconnect import SimConnect
    except Exception as exc:
        report["import_ok"] = False
        report["error"] = f"pysimconnect import failed: {exc}"
        return report

    report["import_ok"] = True
    sc = None
    try:
        sc = SimConnect(name="Airbus3JoysticksDiagnostics")
        report["connect_ok"] = True
    except Exception as exc:
        report["connect_ok"] = False
        report["error"] = str(exc)
        return report

    try:
        report["initial_snapshot"] = _read_simvars(sc)
        print("\n=== MSFS PASSIVE READ TEST ===")
        title = report["initial_snapshot"].get("TITLE", {})
        print(f"SimConnect connected. Aircraft TITLE: {title.get('value') if title.get('ok') else 'unreadable'}")
        print("Using the MOUSE in the A320 cockpit, change SPD, HDG, ALT and V/S to visibly different values.")
        print("Do not use these three diagnostic gamepads for this step.")
        input("When the FCU values are changed, press Enter...")
        report["after_manual_fcu_change"] = _read_simvars(sc)

        print("\nOptional ACTIVE probe: this sends exactly ONE standard increment event at a time,")
        print("asks you what the stock A320neo visibly did, then sends the matching decrement to restore it.")
        print("Do this only when a small FCU target change is safe. It does NOT test push/pull modes.")
        consent = input("Type ACTIVE to run it, or press Enter to skip: ").strip()
        report["active_probe_requested"] = consent == "ACTIVE"
        if consent == "ACTIVE":
            active: list[dict[str, Any]] = []
            for probe in ACTIVE_PROBES:
                print(f"\nProbe: {probe['name']}")
                print(f"Expected visible behavior: {probe['expected']}")
                before = _safe_simvar(sc, probe["simvar"], probe["units"])
                item: dict[str, Any] = {"definition": probe, "before": before}
                try:
                    sc.send_event(probe["event"])
                    item["send_ok"] = True
                except Exception as exc:
                    item["send_ok"] = False
                    item["send_error"] = str(exc)
                    active.append(item)
                    continue
                time.sleep(0.45)
                item["after_increment"] = _safe_simvar(sc, probe["simvar"], probe["units"])
                observation = input("Did the visible FCU target increase? [y/n/u=unclear]: ").strip().lower()
                item["user_observation"] = {
                    "visible_increase": True if observation in {"y", "yes", "д", "да"} else (
                        False if observation in {"n", "no", "н", "нет"} else None
                    ),
                    "raw": observation,
                }
                try:
                    sc.send_event(probe["restore_event"])
                    item["restore_send_ok"] = True
                    time.sleep(0.35)
                    item["after_restore"] = _safe_simvar(sc, probe["simvar"], probe["units"])
                except Exception as exc:
                    item["restore_send_ok"] = False
                    item["restore_error"] = str(exc)
                active.append(item)
            report["active_probes"] = active
    finally:
        try:
            if sc is not None:
                sc.Close()
        except Exception:
            pass

    return report


def _save_report(report: dict[str, Any]) -> list[str]:
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    appdata = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME / "diagnostics"
    appdata.mkdir(parents=True, exist_ok=True)
    canonical = appdata / f"diagnostics-{stamp}.json"
    local = Path.cwd() / "diagnostics-report.json"
    payload = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    canonical.write_text(payload, encoding="utf-8")
    local.write_text(payload, encoding="utf-8")
    return [str(local.resolve()), str(canonical.resolve())]


def main() -> None:
    print("Airbus 3 Joysticks · guided diagnostics")
    print("========================================")
    print("This mode does not require the normal web app to be running.")
    print("It records controller serial/path identity, reconnect stability, input ranges,")
    print("touchpad/rumble capability and a passive MSFS SimConnect snapshot.")
    print("The optional ACTIVE SimConnect probe runs only if you type ACTIVE explicitly.\n")

    report: dict[str, Any] = {
        "schema_version": 1,
        "created_at": datetime.now().astimezone().isoformat(),
        "environment": {
            "python": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "os": platform.system(),
            "os_release": platform.release(),
            "architecture": platform.machine(),
            "sdl_runtime": _sdl_version(),
        },
    }

    backend: ControllerBackend | None = None
    try:
        backend = ControllerBackend()
        report["devices_initial"] = _all_device_records(backend)
        print(f"Detected SDL game controllers: {len(backend.devices)}")
        for index, device in enumerate(backend.devices.values(), 1):
            source = "serial" if device.serial else ("path" if device.path else "fallback")
            print(f"  {index}. {device.name} · {source} · {device.key}")
            print(f"     serial={device.serial!r}")
            print(f"     path={device.path!r}")

        if len(backend.devices) < 3:
            print("\nWARNING: fewer than three SDL game controllers are visible.")
            print("You can continue, but LEFT/CENTER/RIGHT assignment will require three devices.")
            if not _yes("Continue diagnostics anyway?", default=False):
                report["aborted_reason"] = "fewer than three controllers"
                paths = _save_report(report)
                print("\nPartial report saved:")
                for path in paths:
                    print(f"  {path}")
                return

        assigned = _assign_roles(backend)
        report["role_assignment_initial"] = assigned

        if _yes("Run unplug/replug identity stability test for all three roles?", default=True):
            report["reconnect_tests"] = _reconnect_tests(backend, assigned)
        else:
            report["reconnect_tests"] = {"skipped": True}

        report["input_exercises"] = _input_exercises(backend, assigned)

        if _yes("Run short rumble test on each controller?", default=True):
            report["rumble_tests"] = _rumble_tests(backend, assigned)
        else:
            report["rumble_tests"] = {"skipped": True}

        report["role_assignment_final"] = assigned
        if _yes("Save the final LEFT/CENTER/RIGHT identities into the normal app config?", default=True):
            store = ConfigStore()
            saved: dict[str, Any] = {}
            for role in ROLES:
                identity = assigned[role]["identity"]
                # Persist only the fields the normal runtime understands.
                clean_identity = {
                    key: identity.get(key)
                    for key in (
                        "device_key",
                        "name",
                        "serial",
                        "path",
                        "guid",
                        "vendor_id",
                        "product_id",
                        "identity_source",
                    )
                }
                store.assign_device(role, clean_identity)
                saved[role] = clean_identity
            report["normal_config_roles_saved"] = saved
            report["normal_config_path"] = str(store.path)
        else:
            report["normal_config_roles_saved"] = False

        if _yes("Run MSFS SimConnect diagnostics now? Start/load MSFS 2020 first.", default=True):
            report["simconnect"] = _simconnect_diagnostics()
        else:
            report["simconnect"] = {"skipped": True}

    except KeyboardInterrupt:
        report["aborted_reason"] = "KeyboardInterrupt"
        print("\nDiagnostics interrupted by user.")
    except Exception as exc:
        report["fatal_error"] = {"type": type(exc).__name__, "message": str(exc)}
        print(f"\nDiagnostics failed: {type(exc).__name__}: {exc}")
    finally:
        if backend is not None:
            backend.close()

    paths = _save_report(report)
    print("\n=== REPORT READY ===")
    print("Send diagnostics-report.json back in this chat. It contains controller serial/path data by design.")
    print("Saved to:")
    for path in paths:
        print(f"  {path}")
    print("\nYou can also paste the console output if something looked wrong.")


if __name__ == "__main__":
    main()
