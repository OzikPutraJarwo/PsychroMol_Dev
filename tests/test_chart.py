from __future__ import annotations

from psychromol.core.chart import (
    _target_zone_points,
    build_mollier_chart,
    build_psychrometric_chart,
)
from psychromol.core.constants import STANDARD_PRESSURE_PA


def test_the_zone_is_closed():
    points = _target_zone_points((18.0, 28.0, 60.0, 80.0), STANDARD_PRESSURE_PA, 0.05)
    assert points[0] == points[-1]


def test_the_zone_stays_within_the_crops_temperature_band():
    points = _target_zone_points((18.0, 28.0, 60.0, 80.0), STANDARD_PRESSURE_PA, 0.05)
    temperatures = [t for t, _ in points]
    assert min(temperatures) == 18.0
    assert max(temperatures) == 28.0


def test_a_degenerate_range_gives_no_zone():
    assert _target_zone_points((25.0, 25.0, 60.0, 80.0), STANDARD_PRESSURE_PA, 0.05) == []
    assert _target_zone_points((30.0, 20.0, 60.0, 80.0), STANDARD_PRESSURE_PA, 0.05) == []


def test_no_target_means_no_zone_curve():
    geometry = build_psychrometric_chart(t_min=-20, t_max=50, w_max=0.05)
    assert not [c for c in geometry.curves if c.family == "target_zone"]


def test_the_zone_sits_first_so_other_curves_draw_over_it():
    geometry = build_psychrometric_chart(
        t_min=-20, t_max=50, w_max=0.05, target=(18.0, 28.0, 60.0, 80.0)
    )
    assert geometry.curves[0].family == "target_zone"


def test_the_zone_is_bounded_by_the_relative_humidity_it_targets():
    """The top and bottom edges must be the same curve the RH family itself
    would draw at those same percentages -- not an independent approximation.
    """
    from psychromol.core import psychrometrics as psy

    points = _target_zone_points((18.0, 28.0, 60.0, 80.0), STANDARD_PRESSURE_PA, 0.05)
    top_left = points[0]
    expected = psy.humidity_ratio_from_relative_humidity(18.0, 80.0, STANDARD_PRESSURE_PA)
    assert top_left == (18.0, expected)


def test_the_mollier_zone_uses_mollier_coordinates():
    geometry = build_mollier_chart(
        t_min=-20, t_max=50, w_max=0.05, target=(18.0, 28.0, 60.0, 80.0)
    )
    zone = next(c for c in geometry.curves if c.family == "target_zone")
    xs = [x for x, _ in zone.points]
    assert min(xs) >= 0.0
    assert max(xs) <= 50.0
