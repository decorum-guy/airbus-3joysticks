import math

from airbus3j.rotary import RotaryEngine


def engine(**kwargs):
    return RotaryEngine(
        outer_radius=0.5,
        inner_radius=0.2,
        detent_degrees=22.5,
        **kwargs,
    )


def point_for_clockwise_degrees(degrees: float) -> tuple[float, float]:
    # Screen coordinates: +Y is down. Increasing screen-space angle here gives
    # clockwise motion under the production atan2(-y, x) convention.
    radians = math.radians(degrees)
    return math.cos(radians), math.sin(radians)


def test_first_outer_position_arms_without_detent():
    r = engine()
    assert r.update("pad", "left", 1.0, 0.0, now=0.0) == 0


def test_slow_rotation_is_precision_first_about_seven_steps_per_circle():
    r = engine(max_events_per_second=100.0)
    assert r.update("pad", "left", *point_for_clockwise_degrees(0), now=0.0) == 0
    emitted = 0
    # 45-degree samples every 0.3 s stay in the slow profile. The production
    # slow threshold is 50 degrees, giving roughly seven changes per circle.
    for index, angle in enumerate(range(45, 361, 45), start=1):
        emitted += r.update(
            "pad",
            "left",
            *point_for_clockwise_degrees(angle % 360),
            now=index * 0.3,
        )
    assert emitted == 7


def test_fast_rotation_changes_faster_per_second_than_slow_rotation():
    slow = engine(max_events_per_second=100.0)
    fast = engine(max_events_per_second=100.0)

    slow.update("pad", "left", *point_for_clockwise_degrees(0), now=0.0)
    slow_events = 0
    for index, angle in enumerate(range(45, 361, 45), start=1):
        slow_events += abs(
            slow.update(
                "pad", "left", *point_for_clockwise_degrees(angle % 360), now=index * 0.3
            )
        )

    fast.update("pad", "left", *point_for_clockwise_degrees(0), now=0.0)
    fast_events = 0
    # 15-degree samples every 10 ms are firmly in the fast profile.
    for index, angle in enumerate(range(15, 361, 15), start=1):
        fast_events += abs(
            fast.update(
                "pad", "left", *point_for_clockwise_degrees(angle % 360), now=index * 0.01
            )
        )

    assert slow_events == 7
    assert fast_events > slow_events
    assert fast_events <= 24


def test_per_control_scale_makes_slow_and_fast_rotation_more_precise():
    normal_slow = engine(max_events_per_second=100.0)
    vs_slow = engine(max_events_per_second=100.0)
    normal_fast = engine(max_events_per_second=100.0)
    vs_fast = engine(max_events_per_second=100.0)

    normal_slow.update("normal", "right", *point_for_clockwise_degrees(0), now=0.0)
    vs_slow.update("vs", "right", *point_for_clockwise_degrees(0), now=0.0, slow_scale=1.5, fast_scale=1.5)
    normal_slow_events = 0
    vs_slow_events = 0
    for index, angle in enumerate(range(45, 361, 45), start=1):
        point = point_for_clockwise_degrees(angle % 360)
        normal_slow_events += abs(normal_slow.update("normal", "right", *point, now=index * 0.3))
        vs_slow_events += abs(
            vs_slow.update(
                "vs", "right", *point, now=index * 0.3, slow_scale=1.5, fast_scale=1.5
            )
        )

    normal_fast.update("normal-fast", "right", *point_for_clockwise_degrees(0), now=0.0)
    vs_fast.update(
        "vs-fast", "right", *point_for_clockwise_degrees(0), now=0.0,
        slow_scale=1.5, fast_scale=1.5,
    )
    normal_fast_events = 0
    vs_fast_events = 0
    for index, angle in enumerate(range(15, 361, 15), start=1):
        point = point_for_clockwise_degrees(angle % 360)
        normal_fast_events += abs(normal_fast.update("normal-fast", "right", *point, now=index * 0.01))
        vs_fast_events += abs(
            vs_fast.update(
                "vs-fast", "right", *point, now=index * 0.01,
                slow_scale=1.5, fast_scale=1.5,
            )
        )

    assert vs_slow_events < normal_slow_events
    assert vs_fast_events < normal_fast_events


def test_rate_limiter_drops_excess_instead_of_building_backlog():
    r = engine(
        fast_detent_degrees=5.0,
        acceleration_start_dps=1.0,
        acceleration_full_dps=2.0,
        max_events_per_second=10.0,
    )
    r.update("pad", "left", *point_for_clockwise_degrees(0), now=0.0)

    emitted = 0
    for index, angle in enumerate(range(20, 361, 20), start=1):
        emitted += abs(
            r.update(
                "pad", "left", *point_for_clockwise_degrees(angle % 360), now=index * 0.02
            )
        )

    # 0.36 seconds at a 10 Hz cap can emit only a few events, despite enough
    # angular travel for dozens of raw detents.
    assert emitted <= 4

    # Stopping movement does not replay dropped detents later.
    x, y = point_for_clockwise_degrees(0)
    assert r.update("pad", "left", x, y, now=2.0) == 0


def test_counter_clockwise_is_negative():
    r = engine(max_events_per_second=100.0)
    assert r.update("pad", "left", 1.0, 0.0, now=0.0) == 0
    # Screen-space upward quarter-turn is counter-clockwise.
    assert r.update("pad", "left", 0.707, -0.707, now=0.3) == -1


def test_center_resets_tracking_and_next_outer_position_only_rearms():
    r = engine(max_events_per_second=100.0)
    r.update("pad", "left", 1.0, 0.0, now=0.0)
    assert r.update("pad", "left", 0.707, 0.707, now=0.3) == 0
    assert r.update("pad", "left", 0.0, 0.0, now=0.4) == 0
    assert r.update("pad", "left", -1.0, 0.0, now=0.5) == 0


def test_middle_hysteresis_zone_does_not_arm_from_center():
    r = engine()
    assert r.update("pad", "left", 0.35, 0.0, now=0.0) == 0
    assert r.update("pad", "left", 0.40, 0.0, now=0.1) == 0
    assert r.update("pad", "left", 0.49, 0.0, now=0.2) == 0


def test_angle_wrap_does_not_create_full_circle_jump():
    r = engine(
        slow_detent_degrees=5.0,
        fast_detent_degrees=5.0,
        max_events_per_second=100.0,
    )
    r.update("pad", "left", -0.985, 0.174, now=0.0)
    detent = r.update("pad", "left", -0.985, -0.174, now=0.2)
    assert 0 <= detent <= 1


def test_debug_state_exposes_current_speed_and_threshold():
    r = engine(max_events_per_second=100.0)
    r.update("pad", "left", 1.0, 0.0, now=0.0)
    r.update("pad", "left", 0.707, 0.707, now=0.05)
    state = r.debug_state("pad", "left")
    assert state["armed"] is True
    assert float(state["speed_dps"]) > 0
    assert 15.0 <= float(state["detent_degrees"]) <= 50.0
