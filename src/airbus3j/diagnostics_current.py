from __future__ import annotations

from datetime import datetime
import platform
from typing import Any

from .config import ConfigStore
from . import diagnostics as diag


def _active_roles(store: ConfigStore) -> tuple[str, ...]:
    cfg = store.snapshot()
    center_enabled = bool(cfg.get("features", {}).get("center_controller_enabled", False))
    return ("left", "center", "right") if center_enabled else ("left", "right")


def main() -> None:
    store = ConfigStore()
    roles = _active_roles(store)
    diag.ROLES = roles

    print("Airbus 3 Joysticks · guided diagnostics")
    print("========================================")
    print(f"Active controller roles: {', '.join(role.upper() for role in roles)}")
    if "center" not in roles:
        print("CENTER is preserved in the project but temporarily disabled by feature flag.")
        print("Current diagnostics require only two working controllers: LEFT and RIGHT.")
    print("This mode records controller identity, reconnect stability, input ranges,")
    print("touchpad/rumble capability and optional MSFS SimConnect behavior.\n")

    report: dict[str, Any] = {
        "schema_version": 2,
        "created_at": datetime.now().astimezone().isoformat(),
        "active_roles": list(roles),
        "features": store.snapshot().get("features", {}),
        "environment": {
            "python": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "os": platform.system(),
            "os_release": platform.release(),
            "architecture": platform.machine(),
            "sdl_runtime": diag._sdl_version(),
        },
    }

    backend = None
    try:
        backend = diag.ControllerBackend()
        report["devices_initial"] = diag._all_device_records(backend)
        print(f"Detected SDL game controllers: {len(backend.devices)}")
        for index, device in enumerate(backend.devices.values(), 1):
            source = "serial" if device.serial else ("path" if device.path else "fallback")
            print(f"  {index}. {device.name} · {source} · {device.key}")
            print(f"     serial={device.serial!r}")
            print(f"     path={device.path!r}")

        required = len(roles)
        if len(backend.devices) < required:
            print(f"\nWARNING: diagnostics need {required} active controller(s), but SDL sees {len(backend.devices)}.")
            if not diag._yes("Continue diagnostics anyway?", default=False):
                report["aborted_reason"] = f"fewer than {required} active controllers"
                paths = diag._save_report(report)
                print("\nPartial report saved:")
                for path in paths:
                    print(f"  {path}")
                return

        assigned = diag._assign_roles(backend)
        report["role_assignment_initial"] = assigned

        if diag._yes(f"Run unplug/replug identity stability test for {required} active roles?", default=True):
            report["reconnect_tests"] = diag._reconnect_tests(backend, assigned)
        else:
            report["reconnect_tests"] = {"skipped": True}

        report["input_exercises"] = diag._input_exercises(backend, assigned)

        if diag._yes("Run short rumble test on each active controller?", default=True):
            report["rumble_tests"] = diag._rumble_tests(backend, assigned)
        else:
            report["rumble_tests"] = {"skipped": True}

        report["role_assignment_final"] = assigned
        if diag._yes(f"Save the final {'/'.join(role.upper() for role in roles)} identities into the normal app config?", default=True):
            saved: dict[str, Any] = {}
            for role in roles:
                identity = assigned[role]["identity"]
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

        if diag._yes("Run MSFS SimConnect diagnostics now? Start/load MSFS 2020 first.", default=True):
            report["simconnect"] = diag._simconnect_diagnostics()
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

    paths = diag._save_report(report)
    print("\n=== REPORT READY ===")
    print("Send diagnostics-report.json back in this chat.")
    print("Saved to:")
    for path in paths:
        print(f"  {path}")


if __name__ == "__main__":
    main()
