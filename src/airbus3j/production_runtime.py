from __future__ import annotations

import copy
import time
from typing import Any

from .runtime import Runtime


class ProductionRuntime(Runtime):
    """Runtime with an explicit aircraft-family gate for custom events."""

    def _dispatch_action(
        self,
        role: str,
        trigger: str,
        label: str,
        action: dict[str, Any] | None,
    ) -> str:
        action = action or {"type": "pending", "reason": "No action configured"}
        required = action.get("requires_aircraft")
        if action.get("type") == "sim_event" and required:
            bridge_state = self.bridge.state()
            loaded = str(bridge_state.get("aircraft_family", "unknown"))
            if loaded != required:
                result = f"blocked: requires {required}; loaded {loaded}"
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
        return super()._dispatch_action(role, trigger, label, action)
