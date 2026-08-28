from airbus3j.rotary import RotaryEngine


def engine(detent=30.0):
    return RotaryEngine(outer_radius=0.5, inner_radius=0.2, detent_degrees=detent)


def test_first_outer_position_arms_without_detent():
    r = engine()
    assert r.update("pad", "left", 1.0, 0.0) == 0


def test_clockwise_is_positive():
    r = engine()
    assert r.update("pad", "left", 1.0, 0.0) == 0
    assert r.update("pad", "left", 0.0, 1.0) == 3


def test_counter_clockwise_is_negative():
    r = engine()
    assert r.update("pad", "left", 1.0, 0.0) == 0
    assert r.update("pad", "left", 0.0, -1.0) == -3


def test_center_resets_tracking_and_next_outer_position_only_rearms():
    r = engine()
    r.update("pad", "left", 1.0, 0.0)
    assert r.update("pad", "left", 0.0, 1.0) == 3
    assert r.update("pad", "left", 0.0, 0.0) == 0
    assert r.update("pad", "left", -1.0, 0.0) == 0


def test_middle_hysteresis_zone_does_not_arm_from_center():
    r = engine()
    assert r.update("pad", "left", 0.35, 0.0) == 0
    assert r.update("pad", "left", 0.40, 0.0) == 0
    assert r.update("pad", "left", 0.60, 0.0) == 0


def test_angle_wrap_ccw_does_not_create_full_circle_jump():
    # On screen coordinates, upper-left -> lower-left along the left edge is
    # counter-clockwise. Crossing +/-pi must remain a small ~20-degree move.
    r = engine(detent=5.0)
    r.update("pad", "left", -0.985, -0.174)
    detents = r.update("pad", "left", -0.985, 0.174)
    assert -10 < detents < 0


def test_angle_wrap_clockwise_does_not_create_full_circle_jump():
    r = engine(detent=5.0)
    r.update("pad", "left", -0.985, 0.174)
    detents = r.update("pad", "left", -0.985, -0.174)
    assert 0 < detents < 10
