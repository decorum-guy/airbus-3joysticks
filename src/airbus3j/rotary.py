from __future__ import annotations

from dataclasses import dataclass
import math
import time


ANGLE_EPSILON_DEGREES = 1e-6


@dataclass
class RotaryState:
    armed: bool = False
    last_angle: float | None = None
    accumulated_degrees: float = 0.0
    last_update_at: float | None = None
    smoothed_speed_dps: float = 0.0
    last_detent_at: float = 0.0
    active_detent_degrees: float = 45.0


class RotaryEngine:
    """Convert a 2D analog stick moving around a circle into encoder detents.

    The production profile is deliberately precision-first. Slow rotation uses
    a large angular detent so a pilot can dial an exact value. As angular speed
    rises, the detent becomes smaller, allowing faster coarse changes.

    A hard event-rate limiter is also applied. Excess detents are *dropped*,
    never queued, so a fast spin cannot keep changing the FCU after the stick
    has stopped. This also avoids feeding MSFS large bursts of INC/DEC events,
    which can feel much more sensitive than individually spaced inputs.

    SDL uses positive Y downward. We invert Y before atan2 so geometric angle
    behaves in the conventional mathematical direction. ``update`` returns a
    signed number of detents: positive means clockwise, negative means
    counter-clockwise.
    """

    def __init__(
        self,
        outer_radius: float,
        inner_radius: float,
        detent_degrees: float,
        *,
        slow_detent_degrees: float = 45.0,
        fast_detent_degrees: float = 15.0,
        acceleration_start_dps: float = 180.0,
        acceleration_full_dps: float = 720.0,
        max_events_per_second: float = 30.0,
    ):
        if not 0 <= inner_radius < outer_radius <= 1.5:
            raise ValueError("Expected 0 <= inner_radius < outer_radius")
        if detent_degrees <= 0:
            raise ValueError("detent_degrees must be positive")
        if slow_detent_degrees <= 0 or fast_detent_degrees <= 0:
            raise ValueError("adaptive detent sizes must be positive")
        if fast_detent_degrees > slow_detent_degrees:
            raise ValueError("fast_detent_degrees must be <= slow_detent_degrees")
        if acceleration_start_dps < 0 or acceleration_full_dps <= acceleration_start_dps:
            raise ValueError("invalid acceleration speed range")
        if max_events_per_second <= 0:
            raise ValueError("max_events_per_second must be positive")

        self.outer_radius = float(outer_radius)
        self.inner_radius = float(inner_radius)
        # Kept for compatibility/diagnostics. Adaptive production behavior uses
        # slow/fast detent sizes below instead of blindly trusting an old saved
        # detent_degrees value from a pre-tuning config.
        self.detent_degrees = float(detent_degrees)
        self.slow_detent_degrees = float(slow_detent_degrees)
        self.fast_detent_degrees = float(fast_detent_degrees)
        self.acceleration_start_dps = float(acceleration_start_dps)
        self.acceleration_full_dps = float(acceleration_full_dps)
        self.max_events_per_second = float(max_events_per_second)
        self._states: dict[tuple[str, str], RotaryState] = {}

    @property
    def min_emit_interval(self) -> float:
        return 1.0 / self.max_events_per_second

    def reset(self, device_key: str | None = None) -> None:
        if device_key is None:
            self._states.clear()
            return
        for key in list(self._states):
            if key[0] == device_key:
                del self._states[key]

    def _adaptive_detent(self, speed_dps: float) -> float:
        if speed_dps <= self.acceleration_start_dps:
            return self.slow_detent_degrees
        if speed_dps >= self.acceleration_full_dps:
            return self.fast_detent_degrees
        progress = (speed_dps - self.acceleration_start_dps) / (
            self.acceleration_full_dps - self.acceleration_start_dps
        )
        return self.slow_detent_degrees + (
            self.fast_detent_degrees - self.slow_detent_degrees
        ) * progress

    def debug_state(self, device_key: str, stick: str) -> dict[str, float | bool | None]:
        state = self._states.get((device_key, stick))
        if state is None:
            return {
                "armed": False,
                "speed_dps": 0.0,
                "detent_degrees": self.slow_detent_degrees,
                "accumulated_degrees": 0.0,
            }
        return {
            "armed": state.armed,
            "speed_dps": state.smoothed_speed_dps,
            "detent_degrees": state.active_detent_degrees,
            "accumulated_degrees": state.accumulated_degrees,
        }

    def update(self, device_key: str, stick: str, x: float, y: float, now: float | None = None) -> int:
        now = now if now is not None else time.monotonic()
        key = (device_key, stick)
        state = self._states.setdefault(key, RotaryState(active_detent_degrees=self.slow_detent_degrees))
        radius = math.hypot(x, y)

        if radius <= self.inner_radius:
            state.armed = False
            state.last_angle = None
            state.accumulated_degrees = 0.0
            state.last_update_at = None
            state.smoothed_speed_dps = 0.0
            state.active_detent_degrees = self.slow_detent_degrees
            # Re-centering intentionally clears the limiter too: the next
            # deliberate turn should feel immediately responsive.
            state.last_detent_at = 0.0
            return 0

        if not state.armed:
            if radius < self.outer_radius:
                return 0
            state.armed = True
            state.last_angle = math.atan2(-y, x)
            state.accumulated_degrees = 0.0
            state.last_update_at = now
            state.smoothed_speed_dps = 0.0
            state.active_detent_degrees = self.slow_detent_degrees
            return 0

        current_angle = math.atan2(-y, x)
        if state.last_angle is None:
            state.last_angle = current_angle
            state.last_update_at = now
            return 0

        delta = current_angle - state.last_angle
        # Unwrap to [-pi, pi] so crossing 359 -> 0 is a small movement.
        while delta > math.pi:
            delta -= 2 * math.pi
        while delta < -math.pi:
            delta += 2 * math.pi
        state.last_angle = current_angle

        previous_update = state.last_update_at
        state.last_update_at = now
        dt = max(1 / 240.0, now - previous_update) if previous_update is not None else 1 / 60.0

        # Positive mathematical delta is CCW; public contract uses + for CW.
        clockwise_degrees = -math.degrees(delta)
        instant_speed = abs(clockwise_degrees) / dt
        if state.smoothed_speed_dps <= 0.0:
            state.smoothed_speed_dps = instant_speed
        else:
            # Enough smoothing to ignore single-frame stick noise, while still
            # reaching the fast profile within a fraction of a revolution.
            state.smoothed_speed_dps = 0.72 * state.smoothed_speed_dps + 0.28 * instant_speed

        threshold = self._adaptive_detent(state.smoothed_speed_dps)
        state.active_detent_degrees = threshold
        state.accumulated_degrees += clockwise_degrees

        raw_detents = 0
        while state.accumulated_degrees + ANGLE_EPSILON_DEGREES >= threshold:
            raw_detents += 1
            state.accumulated_degrees -= threshold
        while state.accumulated_degrees - ANGLE_EPSILON_DEGREES <= -threshold:
            raw_detents -= 1
            state.accumulated_degrees += threshold

        if abs(state.accumulated_degrees) < ANGLE_EPSILON_DEGREES:
            state.accumulated_degrees = 0.0

        if raw_detents == 0:
            return 0

        # Consume all angular detents above, but emit at most one and never more
        # often than the configured rate. Deliberately dropping excess detents
        # prevents a post-spin backlog and tames simulator-side key acceleration.
        if state.last_detent_at and now - state.last_detent_at < self.min_emit_interval:
            return 0

        state.last_detent_at = now
        return 1 if raw_detents > 0 else -1
