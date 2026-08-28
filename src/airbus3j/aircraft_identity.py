from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import re
from typing import Any, Iterable

from .config import APP_NAME


LEGACY_ASOBO_TITLES = {
    "a320neo white livery",
    "a320neo airbus house livery",
    "a320neo aviators club livery",
    "a320neo xbox aviators club livery",
    "a320neo global livery",
    "a320neo orbit livery",
    "a320neo pacific livery",
    "a320neo world travel livery",
    "a320neo easyjet livery",
    "a320neo wizz air livery",
}
PACKAGE_HINTS = ("a320", "a32n", "airbus", "asobo-aircraft-a320", "inibuilds", "flybywire")


def _strip_value(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
    return value.strip()


def parse_usercfg_installed_path(text: str) -> str | None:
    match = re.search(r'^\s*InstalledPackagesPath\s+["\'](.+?)["\']\s*$', text, re.I | re.M)
    if match:
        return match.group(1)
    match = re.search(r'^\s*InstalledPackagesPath\s+(.+?)\s*$', text, re.I | re.M)
    return match.group(1).strip() if match else None


def parse_aircraft_cfg(text: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    section = ""
    for original in text.splitlines():
        line = original.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("[") and "]" in line:
            section = line[1:line.index("]")].strip()
            if section.lower().startswith("fltsim."):
                current = {"section": section}
                blocks.append(current)
            else:
                current = None
            continue
        if current is None or "=" not in line:
            continue
        key, value = line.split("=", 1)
        # MSFS cfg comments normally use ';'. None of the identity fields we
        # inspect legitimately require a semicolon, so stripping it is safe.
        value = value.split(";", 1)[0]
        current[key.strip().lower()] = _strip_value(value)
    return blocks


def classify_aircraft(
    title: str | None,
    package_name: str | None = None,
    manifest: dict[str, Any] | None = None,
    cfg_block: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = manifest or {}
    cfg_block = cfg_block or {}
    title_norm = (title or "").strip().lower()
    haystack = " ".join(
        str(value or "").lower()
        for value in (
            package_name,
            manifest.get("title"),
            manifest.get("creator"),
            cfg_block.get("base_container"),
            cfg_block.get("ui_createdby"),
            cfg_block.get("ui_type"),
            title,
        )
    )

    evidence: list[str] = []
    if title_norm in LEGACY_ASOBO_TITLES:
        evidence.append(f"SimConnect TITLE matches a known legacy Asobo A320neo livery title: {title}")
    if "asobo-aircraft-a320-neo" in haystack or "asobo_a320_neo" in haystack:
        evidence.append("package/base-container identifies Asobo A320neo")
    if evidence:
        return {"family": "asobo_legacy_a320neo", "confidence": "high", "evidence": evidence}

    if "flybywire" in haystack or "a32nx" in haystack:
        return {
            "family": "flybywire_a32nx",
            "confidence": "high",
            "evidence": ["package/creator/base-container contains FlyByWire/A32NX identity"],
        }
    if "inibuilds" in haystack and ("a320" in haystack or "a32n" in haystack):
        return {
            "family": "inibuilds_a320neo",
            "confidence": "high",
            "evidence": ["package/creator identity contains iniBuilds and A320"],
        }
    return {"family": "unknown_a320", "confidence": "low", "evidence": []}


def usercfg_candidates(env: dict[str, str] | None = None) -> list[Path]:
    env = env or os.environ
    candidates: list[Path] = []
    local = env.get("LOCALAPPDATA")
    roaming = env.get("APPDATA")
    if local:
        candidates.append(
            Path(local)
            / "Packages"
            / "Microsoft.FlightSimulator_8wekyb3d8bbwe"
            / "LocalCache"
            / "UserCfg.opt"
        )
    if roaming:
        candidates.append(Path(roaming) / "Microsoft Flight Simulator" / "UserCfg.opt")
    # Keep order while de-duplicating custom redirected AppData layouts.
    seen: set[str] = set()
    result: list[Path] = []
    for path in candidates:
        key = str(path).lower()
        if key not in seen:
            seen.add(key)
            result.append(path)
    return result


def find_usercfg(env: dict[str, str] | None = None) -> Path | None:
    return next((path for path in usercfg_candidates(env) if path.is_file()), None)


def package_roots(installed_packages: Path) -> list[Path]:
    roots = [
        installed_packages / "Official" / "OneStore",
        installed_packages / "Official" / "Steam",
        installed_packages / "Community",
    ]
    return [path for path in roots if path.is_dir()]


def _candidate_package_dirs(roots: Iterable[Path]) -> list[Path]:
    preferred: list[Path] = []
    other: list[Path] = []
    for root in roots:
        try:
            children = [p for p in root.iterdir() if p.is_dir()]
        except OSError:
            continue
        for child in children:
            name = child.name.lower()
            if any(hint in name for hint in PACKAGE_HINTS):
                preferred.append(child)
            else:
                other.append(child)
    # We only scan generic packages if no likely A320 package matched. This
    # keeps the diagnostic fast on installations with hundreds of add-ons.
    return preferred + other


def _manifest_for(cfg_path: Path, package_dir: Path) -> tuple[Path | None, dict[str, Any] | None]:
    for parent in [cfg_path.parent, *cfg_path.parents]:
        if parent == package_dir.parent:
            break
        manifest_path = parent / "manifest.json"
        if manifest_path.is_file():
            try:
                return manifest_path, json.loads(manifest_path.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                return manifest_path, None
        if parent == package_dir:
            break
    return None, None


def scan_aircraft_packages(installed_packages: Path, title: str | None) -> dict[str, Any]:
    roots = package_roots(installed_packages)
    wanted = (title or "").strip().casefold()
    matches: list[dict[str, Any]] = []
    scanned_packages = 0
    preferred_found = False

    for package_dir in _candidate_package_dirs(roots):
        is_preferred = any(hint in package_dir.name.lower() for hint in PACKAGE_HINTS)
        if preferred_found and not is_preferred:
            break
        scanned_packages += 1
        try:
            cfg_paths = list(package_dir.rglob("aircraft.cfg"))
        except OSError:
            continue
        for cfg_path in cfg_paths:
            try:
                blocks = parse_aircraft_cfg(cfg_path.read_text(encoding="utf-8-sig", errors="replace"))
            except OSError:
                continue
            for block in blocks:
                block_title = str(block.get("title", "")).strip()
                exact = bool(wanted and block_title.casefold() == wanted)
                a320ish = "a320" in block_title.lower() or "a32n" in block_title.lower()
                if not exact and wanted and not a320ish:
                    continue
                if not wanted and not a320ish:
                    continue
                manifest_path, manifest = _manifest_for(cfg_path, package_dir)
                classification = classify_aircraft(title or block_title, package_dir.name, manifest, block)
                matches.append(
                    {
                        "exact_title_match": exact,
                        "package_directory": str(package_dir),
                        "package_name": package_dir.name,
                        "aircraft_cfg": str(cfg_path),
                        "fltsim": block,
                        "manifest_path": str(manifest_path) if manifest_path else None,
                        "manifest": manifest,
                        "classification": classification,
                    }
                )
                if exact:
                    preferred_found = True
        if preferred_found and is_preferred:
            # Continue preferred packages only; generic package scan is skipped.
            continue

    matches.sort(
        key=lambda item: (
            bool(item.get("exact_title_match")),
            item.get("classification", {}).get("confidence") == "high",
        ),
        reverse=True,
    )
    return {
        "installed_packages_path": str(installed_packages),
        "roots": [str(path) for path in roots],
        "scanned_packages": scanned_packages,
        "matches": matches[:20],
        "best_match": matches[0] if matches else None,
    }


def identify_from_disk(title: str | None, env: dict[str, str] | None = None) -> dict[str, Any]:
    cfg = find_usercfg(env)
    result: dict[str, Any] = {"usercfg": str(cfg) if cfg else None}
    if cfg is None:
        result["error"] = "MSFS UserCfg.opt was not found in the standard Microsoft Store or Steam locations"
        result["classification"] = classify_aircraft(title)
        return result
    try:
        text = cfg.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        result["error"] = f"cannot read UserCfg.opt: {exc}"
        result["classification"] = classify_aircraft(title)
        return result
    installed_raw = parse_usercfg_installed_path(text)
    if not installed_raw:
        result["error"] = "InstalledPackagesPath was not present in UserCfg.opt"
        result["classification"] = classify_aircraft(title)
        return result
    installed = Path(os.path.expandvars(installed_raw)).expanduser()
    result["scan"] = scan_aircraft_packages(installed, title)
    best = result["scan"].get("best_match")
    result["classification"] = (
        best.get("classification") if best else classify_aircraft(title)
    )
    return result


def _save(report: dict[str, Any]) -> list[str]:
    payload = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    local = Path.cwd() / "aircraft-identity-report.json"
    local.write_text(payload, encoding="utf-8")
    target_dir = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME / "diagnostics"
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    archived = target_dir / f"aircraft-identity-{stamp}.json"
    archived.write_text(payload, encoding="utf-8")
    return [str(local.resolve()), str(archived.resolve())]


def main() -> None:
    print("Airbus 3 Joysticks · aircraft identity")
    print("======================================")
    print("Read-only diagnostic: SimConnect identity + local MSFS package metadata.\n")
    report: dict[str, Any] = {
        "schema_version": 1,
        "created_at": datetime.now().astimezone().isoformat(),
    }
    title: str | None = None
    sc = None
    if os.name == "nt":
        try:
            from simconnect import SimConnect

            sc = SimConnect(name="Airbus3JoysticksAircraftIdentity")
            title = sc.get_simdatum("TITLE", timeout_seconds=1.5)
            report["simconnect"] = {
                "connected": True,
                "title": title,
                "atc_model": sc.get_simdatum("ATC MODEL", timeout_seconds=1.5),
                "atc_type": sc.get_simdatum("ATC TYPE", timeout_seconds=1.5),
            }
        except Exception as exc:
            report["simconnect"] = {
                "connected": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
        finally:
            if sc is not None:
                try:
                    sc.Close()
                except Exception:
                    pass
    else:
        report["simconnect"] = {"connected": False, "error": "Windows required for live SimConnect identity"}

    report["disk"] = identify_from_disk(title)
    classification = report["disk"].get("classification", classify_aircraft(title))
    report["classification"] = classification

    print(f"TITLE: {title or 'unavailable'}")
    print(f"Detected family: {classification.get('family')} ({classification.get('confidence')} confidence)")
    for evidence in classification.get("evidence", []):
        print(f"  - {evidence}")
    best = report["disk"].get("scan", {}).get("best_match")
    if best:
        print(f"Package: {best.get('package_name')}")
        print(f"aircraft.cfg: {best.get('aircraft_cfg')}")
        manifest = best.get("manifest") or {}
        if manifest:
            print(f"Creator: {manifest.get('creator', 'unknown')}")
            print(f"Version: {manifest.get('package_version', 'unknown')}")
    elif report["disk"].get("error"):
        print(f"Package scan note: {report['disk']['error']}")

    paths = _save(report)
    print("\nReport saved:")
    for path in paths:
        print(f"  {path}")


if __name__ == "__main__":
    main()
