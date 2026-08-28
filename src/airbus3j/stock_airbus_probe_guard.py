from __future__ import annotations

import os
from typing import Any

from .aircraft_identity import classify_aircraft, identify_from_disk


REQUIRED_FAMILY = "asobo_legacy_a320neo"


def resolve_family(title: str | None) -> dict[str, Any]:
    identity = identify_from_disk(title)
    classification = identity.get("classification") or classify_aircraft(title)
    return {"identity": identity, "classification": classification}


def main() -> None:
    print("Airbus 3 Joysticks · stock A320 probe preflight")
    print("===============================================")
    print("This safety preflight identifies the loaded A320 before any stock-Asobo")
    print("button event is allowed to run. No cockpit command is sent here.\n")

    if os.name != "nt":
        print("Windows is required for MSFS SimConnect.")
        return

    sc = None
    title: str | None = None
    try:
        from simconnect import SimConnect

        sc = SimConnect(name="Airbus3JoysticksStockProbeIdentity")
        title = sc.get_simdatum("TITLE", timeout_seconds=1.5)
    except Exception as exc:
        print(f"Cannot identify the loaded aircraft through SimConnect: {type(exc).__name__}: {exc}")
        print("Stock probe NOT started.")
        return
    finally:
        if sc is not None:
            try:
                sc.Close()
            except Exception:
                pass

    resolved = resolve_family(str(title) if title is not None else None)
    classification = resolved["classification"]
    family = classification.get("family", "unknown_a320")
    confidence = classification.get("confidence", "unknown")

    print(f"Loaded TITLE: {title}")
    print(f"Detected family: {family} ({confidence} confidence)")
    for evidence in classification.get("evidence", []):
        print(f"  - {evidence}")

    best = resolved["identity"].get("scan", {}).get("best_match")
    if best:
        print(f"Package: {best.get('package_name')}")
        manifest = best.get("manifest") or {}
        if manifest:
            print(f"Creator: {manifest.get('creator', 'unknown')}")
            print(f"Package version: {manifest.get('package_version', 'unknown')}")

    if family != REQUIRED_FAMILY:
        print("\nSTOP: the loaded aircraft is not confirmed as the legacy/default Asobo A320neo.")
        print("The stock-Asobo candidate set will NOT be sent to this aircraft.")
        print("Run scripts\\aircraft-identify.ps1 and use that report to build/select the correct backend.")
        return

    print("\nLegacy/default Asobo A320neo confirmed strongly enough for the stock probe.")
    print("Starting machine-assisted stock A320 probe v2...\n")
    from .stock_airbus_probe import main as stock_probe_main

    stock_probe_main()


if __name__ == "__main__":
    main()
