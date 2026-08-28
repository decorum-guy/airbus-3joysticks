from __future__ import annotations

import asyncio
import copy
import math
import time
from typing import Any

from .config import ConfigStore
from .controllers import ControllerBackend
from .rotary import RotaryEngine
from .simconnect_bridge import SimConnectBridge


ROLES = ("left", "center", "right")


def enabled_roles(cfg: dict[str, Any]) -> tuple[str, ...]:
    center_enabled = bool(cfg.get("features", {}).get("center_controller_enabled", False))
    return tuple(role for role in ROLES if role != "center" or center_enabled)


def _stick_live(axes: dict[str, Any], stick: str) -> dict[str, float]:
    x = float(axes.get(f"{stick}_x", 0.0))
    y = float(axes.get(f"{stick}_y", 0.0))
    return {
        "x": x,
        "y": y,
        "radius": min(1.5, math.hypot(x, y)),
        "angle_degrees": math.degrees(math.atan2(-y, x)),
    }


class Runtime:
    def __init__(self, config: ConfigStore):
        self.config_store = config
        cfg = config.snapshot()
        rotary = cfg["rotary"]
        self.rotary = RotaryEngine(
            outer_radius=float(rotary["outer_radius"]),
            inner_radius=float(rotary["inner_radius"]),
            detent_degrees=float(rotary["detent_degrees"]),
        )
        self.controllers: ControllerBackend | None = None
        self.bridge = SimConnectBridge()
        self.assignment_target: str | None = None
        self.last_input: dict[str, Any] | None = None
        self.last_action: dict[str, Any] | None = None
        self.last_haptic_test: dict[str, Any] | None = None
        self._previous_buttons: dict[str, set[str]] = {}
        self._task: asyncio.Task | None = None
        self._stopping = False

    async def start(self) -> None:
        cfg = self.config_store.snapshot()
        haptics = cfg.get("haptics", {})
        self.controllers = ControllerBackend(
            enable_ps4_bt_rumble=bool(haptics.get("ps4_bluetooth_extended_reports", False))
        )
        self.bridge.start()
        self._stopping = False
        self._task = asyncio.create_task(self._loop(), name="controller-runtime")

    async def stop(self) -> None:
        self._stopping = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self.bridge.stop()
        if self.controllers:
            self.controllers.close()
            self.controllers = None

    def arm_assignment(self, role: str) -> None:
        if role not in ROLES:
            raise KeyError(role)
        cfg = self.config_store.snapshot()
        if role not in enabled_roles(cfg):
            self.assignment_target = None
            return
        self.assignment_target = role

    def cancel_assignment(self) -> None:
        self.assignment_target = None

    def clear_assignment(self, role: str) -> None:
        self.config_store.assign_device(role, None)
        self.rotary.reset()

    def replace_bindings(self, role: str, bindings: list[dict[str, Any]]) -> None:
        self.config_store.replace_bindings(role, bindings)

    def update_haptics(self, haptics: dict[str, Any]) -> dict[str, Any]:
        previous = self.config_store.snapshot().get("haptics", {})
        updated = self.config_store.update_haptics(haptics)
        restart_required = bool(
            previous.get("ps4_bluetooth_extended_reports")
            != updated.get("ps4_bluetooth_extended_reports")
        )
        return {"haptics": updated, "restart_required": restart_required}

    def _find_device_for_saved_identity(
        self,
        saved: dict[str, Any] | None,
        snapshots: dict[str, dict[str, Any]],
        already_used: set[str],
    ) -> str | None:
        if not saved:
            return None

        exact_key = saved.get("device_key")
        if exact_key in snapshots and exact_key not in already_used:
            return exact_key

        serial = saved.get("serial")
        if serial:
            matches = [
                key for key, snap in snapshots.items()
                if key not in already_used and snap["identity"].get("serial") == serial
            ]
            if len(matches) == 1:
                return matches[0]

        path = saved.get("path")
        if path:
            matches = [
                key for key, snap in snapshots.items()
                if key not in already_used and snap["identity"].get("path") == path
            ]
            if len(matches) == 1:
                return matches[0]

        fields = ("guid", "vendor_id", "product_id", "name")
        matches = []
        for key, snap in snapshots.items():
            if key in already_used:
                continue
            identity = snap["identity"]
            if all(identity.get(field) == saved.get(field) for field in fields):
                matches.append(key)
        return matches[0] if len(matches) == 1 else None

    def _role_devices(self, snapshots: dict[str, dict[str, Any]]) -> dict[str, str | None]:
        cfg = self.config_store.snapshot()
        active = set(enabled_roles(cfg))
        used: set[str] = set()
        result: dict[str, str | None] = {}
        for role in ROLES:
            if role not in active:
                result[role] = None
                continue
            key = self._find_device_for_saved_identity(cfg["roles"][role].get("device"), snapshots, used)
            result[role] = key
            if key:
                used.add(key)
        return result

    def _haptic_channels(self, kind: str, intensity: float) -> tuple[float, float]:
        strength = min(1.0, max(0.0, float(intensity)))
        if kind == "changing_values":
            # A short, crisp detent: mostly the lighter/faster motor.
            return strength * 0.08, strength
        # Warning channel: deliberately heavier and physically distinct.
        return strength, strength * 0.55

    def _rumble_profile(
        self,
        device_key: str,
        kind: str,
        intensity: float,
        duration_ms: int,
    ) -> dict[str, Any]:
        if self.controllers is None:
            return {"ok": False, "selected_method": None, "attempts": [], "error": "backend offline"}
        low, high = self._haptic_channels(kind, intensity)
        attempts: list[dict[str, Any]] = []
        for method in ("gamecontroller", "joystick", "haptic"):
            attempt = self.controllers.rumble_method(device_key, method, low, high, duration_ms)
            attempts.append(attempt)
            if attempt.get("ok"):
                return {
                    "ok": True,
                    "selected_method": method,
                    "low_strength": low,
                    "high_strength": high,
                    "attempts": attempts,
                }
        return {
            "ok": False,
            "selected_method": None,
            "low_strength": low,
            "high_strength": high,
            "attempts": attempts,
        }

    def test_haptic(self, kind: str, role: str | None = None) -> dict[str, Any]:
        if kind not in {"changing_values", "warnings"}:
            raise ValueError("kind must be changing_values or warnings")
        if role is not None and role not in ROLES:
            raise ValueError("unknown role")
        if self.controllers is None:
            raise RuntimeError("controller backend is not running")

        cfg = self.config_store.snapshot()
        haptics = cfg.get("haptics", {})
        section = haptics.get(kind, {})
        strength = float(section.get("intensity", 0.0))
        duration_ms = int(section.get("duration_ms", 100))
        snapshots = self.controllers.poll()
        role_devices = self._role_devices(snapshots)

        target_roles = [role] if role else list(enabled_roles(cfg))
        results: dict[str, Any] = {}
        for target_role in target_roles:
            device_key = role_devices.get(target_role)
            if not device_key:
                results[target_role] = {"ok": False, "error": "role is not online"}
                continue
            results[target_role] = self._rumble_profile(
                device_key, kind, strength, duration_ms
            )

        low, high = self._haptic_channels(kind, strength)
        payload = {
            "kind": kind,
            "role": role,
            "intensity": strength,
            "low_strength": low,
            "high_strength": high,
            "duration_ms": duration_ms,
            "results": results,
            "at": time.time(),
        }
        self.last_haptic_test = copy.deepcopy(payload)
        return payload

    def _record_input(self, role: str, trigger: str, label: str, result: str) -> None:
        self.last_input = {
            "role": role,
            "trigger": trigger,
            "label": label,
            "result": result,
            "at": time.time(),
        }

    def _dispatch_action(self, role: str, trigger: str, label: str, action: dict[str, Any] | None) -> str:
        action = action or {"type": "pending", "reason": "No action configured"}
        action_type = action.get("type")
        if action_type == "sim_event":
            event = str(action.get("event", ""))
            queued = self.bridge.send_event(event, action.get("data"))
            result = "sent" if queued else "dropped: SimConnect offline"
        elif action_type == "pending":
            result = f"pending: {action.get('reason', 'not implemented')}"
        elif action_type == "noop":
            result = "noop"
        else:
            result = f"unsupported action type: {action_type}"

        self.last_action = {
            "role": role,
            "trigger": trigger,
            "label": label,
            "action": copy.deepcopy(action),
            "result": result,
            "at": time.time(),
        }
        self._record_input(role, trigger, label, result)
        return result

    def _route_buttons(
        self,
        role: str,
        device_key: str,
        snapshot: dict[str, Any],
        bindings: list[dict[str, Any]],
    ) -> None:
        pressed = {name for name, is_pressed in snapshot["buttons"].items() if is_pressed}
        previous = self._previous_buttons.get(device_key, set())
        rising = pressed - previous
        self._previous_buttons[device_key] = pressed
        if not rising:
            return

        candidates: list[tuple[int, set[str], dict[str, Any]]] = []
        for binding in bindings:
            trigger = str(binding.get("trigger", ""))
            if trigger.startswith("rotary:"):
                continue
            components = {part for part in trigger.split("+") if part}
            if components and components.issubset(pressed) and components.intersection(rising):
                candidates.append((len(components), components, binding))

        candidates.sort(key=lambda item: item[0], reverse=True)
        consumed_rising: set[str] = set()
        for _, components, binding in candidates:
            relevant_rising = components.intersection(rising)
            if relevant_rising and relevant_rising.issubset(consumed_rising):
                continue
            self._dispatch_action(
                role,
                binding["trigger"],
                binding.get("label", binding["trigger"]),
                binding.get("action"),
            )
            consumed_rising.update(relevant_rising)

    def _route_rotaries(
        self,
        role: str,
        device_key: str,
        snapshot: dict[str, Any],
        bindings: list[dict[str, Any]],
        cfg: dict[str, Any],
    ) -> None:
        axes = snapshot["axes"]
        for stick in ("left", "right"):
            binding = next((b for b in bindings if b.get("trigger") == f"rotary:{stick}"), None)
            if not binding:
                continue
            detents = self.rotary.update(
                device_key,
                stick,
                float(axes[f"{stick}_x"]),
                float(axes[f"{stick}_y"]),
            )
            if not detents:
                continue

            direction = "clockwise" if detents > 0 else "counter_clockwise"
            action = binding.get(direction)
            count = min(abs(detents), 12)
            for _ in range(count):
                self._dispatch_action(
                    role,
                    f"rotary:{stick}:{direction}",
                    binding.get("label", f"{stick} rotary"),
                    action,
                )

            haptics = cfg.get("haptics", {})
            change = haptics.get("changing_values", {})
            if (
                haptics.get("enabled", True)
                and change.get("enabled", True)
                and self.controllers
            ):
                self._rumble_profile(
                    device_key,
                    "changing_values",
                    float(change.get("intensity", 0.12)),
                    int(change.get("duration_ms", 24)),
                )

    def _maybe_assign(self, snapshots: dict[str, dict[str, Any]]) -> bool:
        target = self.assignment_target
        if not target:
            return False
        cfg = self.config_store.snapshot()
        if target not in enabled_roles(cfg):
            self.assignment_target = None
            return False
        for device_key, snapshot in snapshots.items():
            pressed = {name for name, value in snapshot["buttons"].items() if value}
            previous = self._previous_buttons.get(device_key, set())
            rising = pressed - previous
            self._previous_buttons[device_key] = pressed
            if rising:
                self.config_store.assign_device(target, snapshot["identity"])
                self.assignment_target = None
                self.rotary.reset()
                self.last_input = {
                    "role": target,
                    "trigger": sorted(rising)[0],
                    "label": "Controller assigned",
                    "result": snapshot["identity"]["name"],
                    "at": time.time(),
                }
                return True
        return False

    async def _loop(self) -> None:
        assert self.controllers is not None
        while not self._stopping:
            snapshots = self.controllers.poll()

            if self._maybe_assign(snapshots):
                await asyncio.sleep(0.02)
                continue

            cfg = self.config_store.snapshot()
            role_devices = self._role_devices(snapshots)
            for role, device_key in role_devices.items():
                if not device_key:
                    continue
                snapshot = snapshots[device_key]
                bindings = cfg["bindings"].get(role, [])
                self._route_buttons(role, device_key, snapshot, bindings)
                self._route_rotaries(role, device_key, snapshot, bindings, cfg)

            for key in list(self._previous_buttons):
                if key not in snapshots:
                    self._previous_buttons.pop(key, None)
                    self.rotary.reset(key)
            await asyncio.sleep(1 / 60)

    def _readiness(
        self,
        cfg: dict[str, Any],
        role_devices: dict[str, str | None],
        simconnect: dict[str, Any],
    ) -> dict[str, Any]:
        active = list(enabled_roles(cfg))
        missing = [role for role in active if not role_devices.get(role)]
        sim_ok = bool(simconnect.get("connected"))
        return {
            "ready": not missing and sim_ok,
            "controllers_ready": not missing,
            "simconnect_ready": sim_ok,
            "missing_roles": missing,
            "active_roles": active,
        }

    def public_state(self) -> dict[str, Any]:
        cfg = self.config_store.snapshot()
        active = set(enabled_roles(cfg))
        snapshots = self.controllers.poll() if self.controllers else {}
        role_devices = self._role_devices(snapshots) if self.controllers else {role: None for role in ROLES}
        simconnect = self.bridge.state()

        roles: dict[str, Any] = {}
        for role in ROLES:
            key = role_devices.get(role)
            live = snapshots.get(key) if key else None
            axes = copy.deepcopy(live.get("axes", {})) if live else {}
            buttons = copy.deepcopy(live.get("buttons", {})) if live else {}
            roles[role] = {
                **copy.deepcopy(cfg["roles"][role]),
                "enabled": role in active,
                "online": bool(key),
                "runtime_device_key": key,
                "runtime_device": copy.deepcopy(live["identity"]) if live else None,
                "bindings": copy.deepcopy(cfg["bindings"].get(role, [])),
                "input": {
                    "axes": axes,
                    "buttons": buttons,
                    "pressed_buttons": sorted(name for name, value in buttons.items() if value),
                    "left_stick": _stick_live(axes, "left"),
                    "right_stick": _stick_live(axes, "right"),
                } if live else None,
            }

        return {
            "roles": roles,
            "enabled_roles": list(enabled_roles(cfg)),
            "features": copy.deepcopy(cfg.get("features", {})),
            "available_devices": [copy.deepcopy(s["identity"]) for s in snapshots.values()],
            "assignment_target": self.assignment_target,
            "simconnect": simconnect,
            "readiness": self._readiness(cfg, role_devices, simconnect),
            "rotary": copy.deepcopy(cfg["rotary"]),
            "haptics": copy.deepcopy(cfg.get("haptics", {})),
            "last_haptic_test": copy.deepcopy(self.last_haptic_test),
            "last_input": copy.deepcopy(self.last_input),
            "last_action": copy.deepcopy(self.last_action),
            "config_path": str(self.config_store.path),
        }
