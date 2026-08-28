from __future__ import annotations

import asyncio
import copy
import time
from typing import Any

from .config import ConfigStore
from .controllers import ControllerBackend
from .rotary import RotaryEngine
from .simconnect_bridge import SimConnectBridge


ROLES = ("left", "center", "right")


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
        self._previous_buttons: dict[str, set[str]] = {}
        self._task: asyncio.Task | None = None
        self._stopping = False

    async def start(self) -> None:
        self.controllers = ControllerBackend()
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
        self.assignment_target = role

    def cancel_assignment(self) -> None:
        self.assignment_target = None

    def clear_assignment(self, role: str) -> None:
        self.config_store.assign_device(role, None)
        self.rotary.reset()

    def replace_bindings(self, role: str, bindings: list[dict[str, Any]]) -> None:
        self.config_store.replace_bindings(role, bindings)

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

        # Last-resort matching is allowed only when unambiguous. With two
        # identical controllers and no serial/path, silently guessing would be
        # worse than asking for re-assignment.
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
        used: set[str] = set()
        result: dict[str, str | None] = {}
        for role in ROLES:
            key = self._find_device_for_saved_identity(cfg["roles"][role].get("device"), snapshots, used)
            result[role] = key
            if key:
                used.add(key)
        return result

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
            count = min(abs(detents), 12)  # guard against pathological input spikes
            for _ in range(count):
                self._dispatch_action(
                    role,
                    f"rotary:{stick}:{direction}",
                    binding.get("label", f"{stick} rotary"),
                    action,
                )

            rotary_cfg = cfg["rotary"]
            if rotary_cfg.get("rumble") and self.controllers:
                self.controllers.rumble(
                    device_key,
                    float(rotary_cfg.get("rumble_strength", 0.12)),
                    int(rotary_cfg.get("rumble_ms", 18)),
                )

    def _maybe_assign(self, snapshots: dict[str, dict[str, Any]]) -> bool:
        target = self.assignment_target
        if not target:
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

            # Prune stale edge state after disconnects.
            for key in list(self._previous_buttons):
                if key not in snapshots:
                    self._previous_buttons.pop(key, None)
                    self.rotary.reset(key)
            await asyncio.sleep(1 / 60)

    def public_state(self) -> dict[str, Any]:
        cfg = self.config_store.snapshot()
        snapshots = self.controllers.poll() if self.controllers else {}
        role_devices = self._role_devices(snapshots) if self.controllers else {role: None for role in ROLES}

        roles: dict[str, Any] = {}
        for role in ROLES:
            key = role_devices.get(role)
            roles[role] = {
                **copy.deepcopy(cfg["roles"][role]),
                "online": bool(key),
                "runtime_device_key": key,
                "runtime_device": copy.deepcopy(snapshots[key]["identity"]) if key else None,
                "bindings": copy.deepcopy(cfg["bindings"].get(role, [])),
            }

        return {
            "roles": roles,
            "available_devices": [copy.deepcopy(s["identity"]) for s in snapshots.values()],
            "assignment_target": self.assignment_target,
            "simconnect": self.bridge.state(),
            "rotary": copy.deepcopy(cfg["rotary"]),
            "last_input": copy.deepcopy(self.last_input),
            "last_action": copy.deepcopy(self.last_action),
            "config_path": str(self.config_store.path),
        }
