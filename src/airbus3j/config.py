from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from threading import RLock
from typing import Any


APP_NAME = "Airbus3Joysticks"


def _sim_event(event: str, data: int | None = None) -> dict[str, Any]:
    action: dict[str, Any] = {"type": "sim_event", "event": event}
    if data is not None:
        action["data"] = data
    return action


def _pending(reason: str) -> dict[str, Any]:
    return {"type": "pending", "reason": reason}


def default_config() -> dict[str, Any]:
    pending_push_pull = (
        "Needs verified stock A320neo managed/selected PUSH/PULL implementation; "
        "do not guess this event."
    )
    pending_efis = "Needs verified A320neo EFIS/InputEvent or MobiFlight WASM action."

    return {
        "version": 1,
        "server": {"host": "0.0.0.0", "port": 8765},
        "roles": {
            "left": {"display_name": "LEFT · FCU SPD / HDG", "device": None},
            "center": {"display_name": "CENTER · EFIS / RADIO", "device": None},
            "right": {"display_name": "RIGHT · FCU ALT / V/S", "device": None},
        },
        "rotary": {
            "outer_radius": 0.58,
            "inner_radius": 0.32,
            "detent_degrees": 22.5,
            "clockwise_is_increment": True,
            "rumble": True,
            "rumble_strength": 0.12,
            "rumble_ms": 18,
        },
        "bindings": {
            "left": [
                {
                    "trigger": "rotary:left",
                    "label": "FCU SPEED",
                    "clockwise": _sim_event("AP_SPD_VAR_INC"),
                    "counter_clockwise": _sim_event("AP_SPD_VAR_DEC"),
                },
                {
                    "trigger": "rotary:right",
                    "label": "FCU HEADING",
                    "clockwise": _sim_event("HEADING_BUG_INC"),
                    "counter_clockwise": _sim_event("HEADING_BUG_DEC"),
                },
                {"trigger": "leftstick", "label": "SPD PUSH · managed", "action": _pending(pending_push_pull)},
                {"trigger": "leftshoulder+leftstick", "label": "SPD PULL · selected", "action": _pending(pending_push_pull)},
                {"trigger": "rightstick", "label": "HDG PUSH · managed NAV", "action": _pending(pending_push_pull)},
                {"trigger": "leftshoulder+rightstick", "label": "HDG PULL · selected", "action": _pending(pending_push_pull)},
                {"trigger": "x", "label": "AP1", "action": _pending("Need exact A320neo AP1 input event; AP_MASTER is not equivalent to AP1.")},
                {"trigger": "b", "label": "AP2", "action": _pending("Need exact A320neo AP2 input event; AP_MASTER is not equivalent to AP2.")},
                {"trigger": "a", "label": "A/THR", "action": _pending("Need exact A320neo A/THR pushbutton action.")},
                {"trigger": "y", "label": "APPR", "action": _sim_event("AP_APR_HOLD")},
                {"trigger": "dpad_left", "label": "LOC", "action": _sim_event("AP_LOC_HOLD")},
                {"trigger": "dpad_up", "label": "SPD / MACH", "action": _pending("Needs verified A320neo SPD/MACH pushbutton action.")},
                {"trigger": "dpad_down", "label": "HDG-V/S ↔ TRK-FPA", "action": _pending("Needs verified A320neo TRK/FPA pushbutton action.")},
            ],
            "center": [
                {
                    "trigger": "rotary:left",
                    "label": "BARO / QNH",
                    "clockwise": _sim_event("KOHLSMAN_INC"),
                    "counter_clockwise": _sim_event("KOHLSMAN_DEC"),
                },
                {
                    "trigger": "rotary:right",
                    "label": "COM1 / RADIO",
                    "clockwise": _pending("Radio rotary policy and 8.33 kHz stepping still need implementation."),
                    "counter_clockwise": _pending("Radio rotary policy and 8.33 kHz stepping still need implementation."),
                },
                {"trigger": "leftstick", "label": "BARO STD", "action": _sim_event("BAROMETRIC_STD_PRESSURE", 1)},
                {"trigger": "rightstick", "label": "COM1 SWAP", "action": _sim_event("COM_STBY_RADIO_SWAP")},
                {"trigger": "dpad_up", "label": "ND RANGE +", "action": _pending(pending_efis)},
                {"trigger": "dpad_down", "label": "ND RANGE −", "action": _pending(pending_efis)},
                {"trigger": "dpad_left", "label": "ND MODE ←", "action": _pending(pending_efis)},
                {"trigger": "dpad_right", "label": "ND MODE →", "action": _pending(pending_efis)},
                {"trigger": "x", "label": "CSTR", "action": _pending(pending_efis)},
                {"trigger": "a", "label": "WPT", "action": _pending(pending_efis)},
                {"trigger": "b", "label": "VOR D", "action": _pending(pending_efis)},
                {"trigger": "y", "label": "ARPT", "action": _pending(pending_efis)},
            ],
            "right": [
                {
                    "trigger": "rotary:left",
                    "label": "FCU ALTITUDE",
                    "clockwise": _sim_event("AP_ALT_VAR_INC"),
                    "counter_clockwise": _sim_event("AP_ALT_VAR_DEC"),
                },
                {
                    "trigger": "rotary:right",
                    "label": "FCU V/S",
                    "clockwise": _sim_event("AP_VS_VAR_INC"),
                    "counter_clockwise": _sim_event("AP_VS_VAR_DEC"),
                },
                {"trigger": "leftstick", "label": "ALT PUSH · managed", "action": _pending(pending_push_pull)},
                {"trigger": "leftshoulder+leftstick", "label": "ALT PULL · open climb/descent", "action": _pending(pending_push_pull)},
                {"trigger": "rightstick", "label": "V/S PUSH · level off", "action": _pending(pending_push_pull)},
                {"trigger": "leftshoulder+rightstick", "label": "V/S PULL · selected", "action": _pending(pending_push_pull)},
                {"trigger": "dpad_up", "label": "FLAPS one detent UP", "action": _sim_event("FLAPS_DECR")},
                {"trigger": "dpad_down", "label": "FLAPS one detent DOWN", "action": _sim_event("FLAPS_INCR")},
                {"trigger": "dpad_left", "label": "SPEEDBRAKE −", "action": _sim_event("SPOILERS_DEC")},
                {"trigger": "dpad_right", "label": "SPEEDBRAKE +", "action": _sim_event("SPOILERS_INC")},
                {"trigger": "x", "label": "SPOILERS ARM", "action": _sim_event("SPOILERS_ARM_TOGGLE")},
                {"trigger": "a", "label": "AUTOBRAKE LOW", "action": _sim_event("AUTOBRAKE_LO_SET")},
                {"trigger": "b", "label": "AUTOBRAKE MED", "action": _sim_event("AUTOBRAKE_MED_SET")},
                {"trigger": "y", "label": "AUTOBRAKE MAX · pending", "action": _pending("No generic event is assumed for the A320 MAX position.")},
            ],
        },
    }


class ConfigStore:
    def __init__(self, path: Path | None = None):
        base = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
        self.path = path or (base / "config.json")
        self._lock = RLock()
        self._config = self._load()

    def _load(self) -> dict[str, Any]:
        defaults = default_config()
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._write(defaults)
            return defaults

        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            backup = self.path.with_suffix(".broken.json")
            try:
                self.path.replace(backup)
            except OSError:
                pass
            self._write(defaults)
            return defaults

        # Keep this intentionally conservative for v1: only fill missing top-level
        # sections. Do not overwrite user-edited bindings during upgrades.
        for key, value in defaults.items():
            loaded.setdefault(key, copy.deepcopy(value))
        for role, role_defaults in defaults["roles"].items():
            loaded["roles"].setdefault(role, copy.deepcopy(role_defaults))
        for role, role_bindings in defaults["bindings"].items():
            loaded["bindings"].setdefault(role, copy.deepcopy(role_bindings))
        return loaded

    def _write(self, config: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._config)

    def save(self) -> None:
        with self._lock:
            self._write(self._config)

    def assign_device(self, role: str, identity: dict[str, Any] | None) -> None:
        with self._lock:
            if role not in self._config["roles"]:
                raise KeyError(role)
            self._config["roles"][role]["device"] = copy.deepcopy(identity)
            self._write(self._config)

    def replace_bindings(self, role: str, bindings: list[dict[str, Any]]) -> None:
        if role not in self._config["bindings"]:
            raise KeyError(role)
        if not isinstance(bindings, list):
            raise TypeError("bindings must be a list")
        for binding in bindings:
            if not isinstance(binding, dict) or not isinstance(binding.get("trigger"), str):
                raise ValueError("every binding must be an object with a string trigger")
            if not isinstance(binding.get("label"), str):
                raise ValueError("every binding must have a string label")
        with self._lock:
            self._config["bindings"][role] = copy.deepcopy(bindings)
            self._write(self._config)
