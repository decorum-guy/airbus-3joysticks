from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from threading import RLock
from typing import Any


APP_NAME = "Airbus3Joysticks"

# Precision multiplier: larger values require more physical stick travel per
# logical FCU change, so the control feels slower and easier to set exactly.
DEFAULT_ROTARY_PRECISION: dict[str, float] = {
    "speed": 1.00,
    "heading": 1.00,
    "altitude": 1.35,
    "vertical_speed": 2.00,
}

CONTROL_ROUTES: dict[str, tuple[str, str]] = {
    "speed": ("left", "left"),
    "heading": ("left", "right"),
    "altitude": ("right", "left"),
    "vertical_speed": ("right", "right"),
}

MIN_PRECISION = 0.50
MAX_PRECISION = 3.00


class RotarySensitivityStore:
    def __init__(self, path: Path | None = None):
        base = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
        self.path = path or (base / "rotary-sensitivity.json")
        self._lock = RLock()
        self._values = self._load()

    def _load(self) -> dict[str, float]:
        values = copy.deepcopy(DEFAULT_ROTARY_PRECISION)
        if not self.path.exists():
            self._write(values)
            return values
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._write(values)
            return values
        if not isinstance(raw, dict):
            self._write(values)
            return values
        for control in values:
            try:
                value = float(raw.get(control, values[control]))
            except (TypeError, ValueError):
                continue
            if MIN_PRECISION <= value <= MAX_PRECISION:
                values[control] = value
        # Persist newly introduced controls/defaults after migration.
        self._write(values)
        return values

    def _write(self, values: dict[str, float]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "values": copy.deepcopy(self._values),
                "defaults": copy.deepcopy(DEFAULT_ROTARY_PRECISION),
                "min": MIN_PRECISION,
                "max": MAX_PRECISION,
                "path": str(self.path),
            }

    def set(self, control: str, precision: float) -> dict[str, Any]:
        if control not in DEFAULT_ROTARY_PRECISION:
            raise KeyError(control)
        value = float(precision)
        if not MIN_PRECISION <= value <= MAX_PRECISION:
            raise ValueError(
                f"precision must be between {MIN_PRECISION:.2f} and {MAX_PRECISION:.2f}"
            )
        with self._lock:
            self._values[control] = value
            self._write(self._values)
        return self.snapshot()

    def reset(self, control: str | None = None) -> dict[str, Any]:
        if control is not None and control not in DEFAULT_ROTARY_PRECISION:
            raise KeyError(control)
        with self._lock:
            if control is None:
                self._values = copy.deepcopy(DEFAULT_ROTARY_PRECISION)
            else:
                self._values[control] = DEFAULT_ROTARY_PRECISION[control]
            self._write(self._values)
        return self.snapshot()
