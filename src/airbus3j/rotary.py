from __future__ import annotations

from dataclasses import dataclass
import math
import time


@dataclass
class RotaryState:
    armed: bool = False
    last_angle: float | None = None
    accumulated_degrees: float = 0.0
    last_detent_at: float = 0.0


class RotaryEngine:
    """Convert a 2D analog stick moving around a circle into encoder detents.

    SDL uses positive Y downward. We invert Y before atan2 so geometric angle
    behaves in the conventional mathematical direction. `update` returns a
    signed number of detents: positive means clockwise, negative means
    counter-clockwise.
    """

    def __init__(self, outer_radius: float, inner_radius: float, detent_degrees: float):
        if not 0 <= inner_radius < outer_radius <= 1.5:
            raise ValueError("Expected 0 <= inner_radius < outer_radius")
        if detent_degrees <= 0:
            raise ValueError("detent_degrees must be positive")
        self.outer_radius = outer_radius
        self.inner_radius = inner_radius
        self.detent_degrees = detent_degrees
        self._states: dict[tuple[str, str], RotaryState] = {}

    def reset(self, device_key: str | None = None) -> None:
        if device_key is None:
            self._states.clear()
            return
        for key in list(self._states):
            if key[0] == device_key:
                del self._states[key]

    def update(self, device_key: str, stick: str, x: float, y: float, now: float | None = None) -> int:
        now = now if now is not None else time.monotonic()
        key = (device_key, stick)
        state = self._states.setdefault(key, RotaryState())
        radius = math.hypot(x, y)

        if radius <= self.inner_radius:
            state.armed = False
            state.last_angle = None
            state.accumulated_degrees = 0.0
            return 0

        if not state.armed:
            if radius < self.outer_radius:
                return 0
            state.armed = True
            state.last_angle = math.atan2(-y, x)
            state.accumulated_degrees = 0.0
            return 0

        current_angle = math.atan2(-y, x)
        if state.last_angle is None:
            state.last_angle = current_angle
            return 0

        delta = current_angle - state.last_angle
        # unwrap to [-pi, pi] so crossing 359 -> 0 is a small movement
        while delta > math.pi:
            delta -= 2 * math.pi
        while delta < -math.pi:
            delta += 2 * math.pi
        state.last_angle = current_angle

        # Positive mathematical delta is CCW; public contract uses + for CW.
        clockwise_degrees = -math.degrees(delta)
        state.accumulated_degrees += clockwise_degrees

        detents = 0
        while state.accumulated_degrees >= self.detent_degrees:
            detents += 1
            state.accumulated_degrees -= self.detent_degrees
        while state.accumulated_degrees <= -self.detent_degrees:
            detents -= 1
            state.accumulated_degrees += self.detent_degrees

        if detents:
            state.last_detent_at = now
        return detents
