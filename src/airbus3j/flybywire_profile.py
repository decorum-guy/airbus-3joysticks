from __future__ import annotations

import copy
from typing import Any

from .config import ConfigStore


FLYBYWIRE_FAMILY = "flybywire_a32nx"

# Production button layer for the two-controller A32NX profile. Rotary INC/DEC,
# flaps, spoilers and autobrake remain on their already-validated generic
# SimConnect events; only the Airbus-specific FCU/pushbutton layer lives here.
PRODUCTION_ACTIONS: dict[str, dict[str, tuple[str, str]]] = {
    "left": {
        "leftstick": ("SPD PUSH · managed", "A32NX.FCU_SPD_PUSH"),
        "leftshoulder+leftstick": ("SPD PULL · selected", "A32NX.FCU_SPD_PULL"),
        "rightstick": ("HDG PUSH · managed NAV", "A32NX.FCU_HDG_PUSH"),
        "leftshoulder+rightstick": ("HDG PULL · selected", "A32NX.FCU_HDG_PULL"),
        "x": ("AP1", "A32NX.FCU_AP_1_PUSH"),
        "b": ("AP2", "A32NX.FCU_AP_2_PUSH"),
        "a": ("A/THR", "A32NX.FCU_ATHR_PUSH"),
        "y": ("APPR", "A32NX.FCU_APPR_PUSH"),
        "dpad_left": ("LOC", "A32NX.FCU_LOC_PUSH"),
        "dpad_up": ("SPD / MACH", "A32NX.FCU_SPD_MACH_TOGGLE_PUSH"),
        "dpad_down": ("HDG-V/S ↔ TRK-FPA", "A32NX.FCU_TRK_FPA_TOGGLE_PUSH"),
    },
    "right": {
        "leftstick": ("ALT PUSH · managed", "A32NX.FCU_ALT_PUSH"),
        "leftshoulder+leftstick": ("ALT PULL · open climb/descent", "A32NX.FCU_ALT_PULL"),
        "rightstick": ("V/S PUSH · level off", "A32NX.FCU_VS_PUSH"),
        "leftshoulder+rightstick": ("V/S PULL · selected", "A32NX.FCU_VS_PULL"),
    },
}

# These were the only non-pending legacy actions occupying a slot now promoted
# to the aircraft-specific A32NX API. They are safe to migrate automatically.
LEGACY_REPLACEABLE_EVENTS = {
    "AP_APR_HOLD",
    "AP_LOC_HOLD",
}


def _production_action(event: str) -> dict[str, Any]:
    return {
        "type": "sim_event",
        "event": event,
        "requires_aircraft": FLYBYWIRE_FAMILY,
    }


def _can_promote(binding: dict[str, Any], expected_event: str) -> bool:
    action = binding.get("action") or {}
    action_type = action.get("type")
    if action_type == "pending":
        return True
    if action_type == "sim_event":
        current_event = str(action.get("event", ""))
        if current_event in LEGACY_REPLACEABLE_EVENTS:
            return True
        # Idempotent startup migration and future event-name corrections in
        # this built-in profile are allowed only for our own A32NX namespace.
        if current_event.startswith("A32NX."):
            return True
        if current_event == expected_event:
            return True
    return False


def promote_flybywire_profile(store: ConfigStore) -> dict[str, Any]:
    """Promote verified/published A32NX actions without clobbering user edits.

    Existing pending bindings and the two legacy generic LOC/APPR bindings are
    upgraded. A user-created noop, generic/custom SimConnect event, or a removed
    binding is deliberately preserved.
    """

    snapshot = store.snapshot()
    changed_roles: list[str] = []
    promoted: list[dict[str, str]] = []

    for role, actions in PRODUCTION_ACTIONS.items():
        bindings = copy.deepcopy(snapshot.get("bindings", {}).get(role, []))
        changed = False
        for binding in bindings:
            trigger = str(binding.get("trigger", ""))
            target = actions.get(trigger)
            if target is None:
                continue
            label, event = target
            if not _can_promote(binding, event):
                continue
            new_action = _production_action(event)
            if binding.get("label") != label or binding.get("action") != new_action:
                binding["label"] = label
                binding["action"] = new_action
                changed = True
                promoted.append({"role": role, "trigger": trigger, "event": event})
        if changed:
            store.replace_bindings(role, bindings)
            changed_roles.append(role)

    return {
        "family": FLYBYWIRE_FAMILY,
        "changed_roles": changed_roles,
        "promoted": promoted,
    }
