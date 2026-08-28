from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import platform
import time
from typing import Any

from .config import APP_NAME, ConfigStore
from .controllers import ControllerBackend
from .runtime import enabled_roles


def _felt(prompt: str) -> dict[str, Any]:
    raw = input(f"{prompt} [y/n/u=unclear]: ").strip().lower()
    if raw in {"y", "yes", "д", "да"}:
        value: bool | None = True
    elif raw in {"n", "no", "н", "нет"}:
        value = False
    else:
        value = None
    return {"felt": value, "raw": raw}


def _match_role(backend: ControllerBackend, saved: dict[str, Any] | None, used: set[str]) -> str | None:
    if not saved:
        return None
    key = saved.get("device_key")
    if key in backend.devices and key not in used:
        return key
    serial = saved.get("serial")
    if serial:
        matches = [k for k, d in backend.devices.items() if k not in used and d.serial == serial]
        if len(matches) == 1:
            return matches[0]
    path = saved.get("path")
    if path:
        matches = [k for k, d in backend.devices.items() if k not in used and d.path == path]
        if len(matches) == 1:
            return matches[0]
    return None


def _save(report: dict[str, Any]) -> list[str]:
    payload = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    local = Path.cwd() / "rumble-probe-report.json"
    local.write_text(payload, encoding="utf-8")
    target_dir = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME / "diagnostics"
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    archived = target_dir / f"rumble-probe-{stamp}.json"
    archived.write_text(payload, encoding="utf-8")
    return [str(local.resolve()), str(archived.resolve())]


def main() -> None:
    print("Airbus 3 Joysticks · focused rumble probe")
    print("==========================================")
    print("Hold each controller in your hands during its tests.")
    print("This probe enables SDL PS4 Bluetooth extended reports BEFORE opening controllers.")
    print("SDL warns that extended reports can affect DirectInput handling in other apps")
    print("until the controller is power-cycled. The probe itself does not send MSFS events.\n")

    report: dict[str, Any] = {
        "schema_version": 1,
        "created_at": datetime.now().astimezone().isoformat(),
        "environment": {
            "python": platform.python_version(),
            "os": platform.system(),
            "os_release": platform.release(),
        },
        "ps4_bluetooth_extended_reports_requested": True,
    }

    backend: ControllerBackend | None = None
    try:
        store = ConfigStore()
        cfg = store.snapshot()
        backend = ControllerBackend(enable_ps4_bt_rumble=True)
        report["detected_devices"] = [d.public_identity() for d in backend.devices.values()]

        used: set[str] = set()
        role_keys: dict[str, str | None] = {}
        for role in enabled_roles(cfg):
            key = _match_role(backend, cfg.get("roles", {}).get(role, {}).get("device"), used)
            role_keys[role] = key
            if key:
                used.add(key)
        report["role_device_keys"] = role_keys

        tests = (
            ("gamecontroller_both", "gamecontroller", 0.35, 0.35, 900),
            ("gamecontroller_low_motor", "gamecontroller", 0.50, 0.0, 900),
            ("gamecontroller_high_motor", "gamecontroller", 0.0, 0.50, 900),
            ("joystick_both", "joystick", 0.40, 0.40, 900),
            ("haptic_simple", "haptic", 0.45, 0.45, 900),
        )

        role_reports: dict[str, Any] = {}
        for role in enabled_roles(cfg):
            key = role_keys.get(role)
            if not key:
                role_reports[role] = {"error": "saved role is not online / could not be matched"}
                print(f"\n{role.upper()}: saved controller is not online; skipping.")
                continue
            device = backend.devices[key]
            print(f"\n=== {role.upper()} · {device.name} ===")
            print(f"serial={device.serial!r}")
            capabilities = backend.rumble_capabilities(key)
            print(f"capabilities={capabilities}")
            items: list[dict[str, Any]] = []
            for label, method, low, high, duration in tests:
                input(f"\nHold {role.upper()} now. Press Enter for {label}...")
                result = backend.rumble_method(key, method, low, high, duration)
                print(f"  SDL result: {'OK' if result.get('ok') else 'FAILED'}")
                if result.get("error") or result.get("sdl_error"):
                    print(f"  error: {result.get('error') or result.get('sdl_error')}")
                time.sleep((duration / 1000.0) + 0.15)
                observation = _felt("Did you physically feel vibration?")
                items.append({"label": label, "call": result, "observation": observation})
            role_reports[role] = {"identity": device.public_identity(), "capabilities": capabilities, "tests": items}
        report["roles"] = role_reports

    except KeyboardInterrupt:
        report["aborted_reason"] = "KeyboardInterrupt"
        print("\nProbe interrupted by user.")
    except Exception as exc:
        report["fatal_error"] = {"type": type(exc).__name__, "message": str(exc)}
        print(f"\nProbe failed: {type(exc).__name__}: {exc}")
    finally:
        if backend is not None:
            backend.close()

    paths = _save(report)
    print("\n=== RUMBLE REPORT READY ===")
    print("Send rumble-probe-report.json back in the chat.")
    for path in paths:
        print(f"  {path}")


if __name__ == "__main__":
    main()
