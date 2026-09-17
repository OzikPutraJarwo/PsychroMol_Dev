"""Numerical verification of the psychrometric engine.

The brief (SS10) is explicit: do not test whether the application runs, test
whether the numbers are right. The strategy below is ordered by decreasing
independence from the implementation, because a test that shares the
implementation's assumptions verifies nothing.

1. **Published absolute values.** Saturation pressures from the Hyland-Wexler
   correlation as tabulated in ASHRAE Fundamentals Ch. 1, and ASHRAE's own
   worked Example 1.
2. **A second, independent formulation.** ASHRAE Eq. (37)/(38) are separate
   curve fits for the dew point; the engine inverts Eq. (5)/(6) numerically
   instead, so agreement between them is a genuine cross-check.
3. **An independent implementation.** ``psychrolib`` is the ASHRAE-derived
   reference library, maintained separately from this project. Skipped rather
   than failed when absent -- it is a verification aid, never a runtime
   dependency.
4. **Internal consistency.** Every inverse must round-trip; every monotonic
   relation must actually be monotonic.
5. **Physical sanity** across the representative conditions the brief names:
   cold/humid, moderate, hot/dry, hot/humid, near-saturation.

Expected values, tolerances and their justification are recorded in
``docs/psychrometric-methodology.md``.
"""

from __future__ import annotations

import math

import pytest

from psychromol.core import psychrometrics as psy
from psychromol.core import state as st
from psychromol.core.constants import STANDARD_PRESSURE_PA

P_ATM = STANDARD_PRESSURE_PA

try:
    import psychrolib

    psychrolib.SetUnitSystem(psychrolib.SI)
    HAS_PSYCHROLIB = True
except ImportError:
    HAS_PSYCHROLIB = False

requires_psychrolib = pytest.mark.skipif(
    not HAS_PSYCHROLIB, reason="psychrolib not installed (verification aid only)"
)

# 1. Saturation vapour pressure -- ASHRAE Eq. (5) and (6)

# ASHRAE Fundamentals Ch. 1. Tolerance 5e-4 relative is the table's own
SATURATION_PRESSURE_TABLE = [
    (-60.0, 1.0817),
    (-40.0, 12.845),
    (-20.0, 103.26),
    (-10.0, 259.90),
    (-5.0, 401.76),
    (0.0, 611.21),
    (5.0, 872.49),
    (10.0, 1228.0),
    (15.0, 1705.4),
    (20.0, 2338.8),
    (25.0, 3169.2),
    (30.0, 4246.0),
    (35.0, 5627.8),
    (40.0, 7383.5),
    (45.0, 9593.1),
    (50.0, 12349.9),
    (60.0, 19943.8),
    (80.0, 47415.0),
    (100.0, 101418.0),
]

@pytest.mark.parametrize("t_db, expected_pa", SATURATION_PRESSURE_TABLE)
def test_saturation_vapour_pressure_matches_ashrae_table(t_db, expected_pa):
    assert psy.saturation_vapour_pressure(t_db) == pytest.approx(expected_pa, rel=5e-4)

def test_saturation_pressure_branch_switch_at_zero_celsius():
    assert psy.saturation_vapour_pressure(0.0) == pytest.approx(611.213, abs=0.01)
    assert psy.saturation_vapour_pressure_over_ice(0.0) == pytest.approx(611.154, abs=0.01)
    assert psy.saturation_vapour_pressure(-0.001) < 611.213

def test_saturation_pressure_is_strictly_increasing():
    previous = 0.0
    for step in range(-100, 201):
        current = psy.saturation_vapour_pressure(float(step))
        assert current > previous, f"not monotonic at {step} degC"
        previous = current

def test_saturation_temperature_inverts_saturation_pressure():
    for t_db in [-50.0, -10.0, 0.0, 12.5, 20.0, 37.3, 60.0, 120.0]:
        p_ws = psy.saturation_vapour_pressure(t_db)
        assert psy.saturation_temperature(p_ws) == pytest.approx(t_db, abs=1e-6)

def test_temperature_outside_correlation_range_is_rejected():
    with pytest.raises(psy.PsychrometricRangeError):
        psy.saturation_vapour_pressure(-100.001)
    with pytest.raises(psy.PsychrometricRangeError):
        psy.saturation_vapour_pressure(200.001)
    with pytest.raises(psy.PsychrometricRangeError):
        psy.saturation_vapour_pressure(float("nan"))

# 2. ASHRAE Fundamentals Ch. 1, worked Example 1

def test_ashrae_worked_example_1():
    """Moist air at 40 degC dry-bulb, 20 degC wet-bulb, 101.325 kPa.

    ASHRAE Fundamentals 2017, Ch. 1, Example 1 reports
    W = 0.0064 kg/kg_da, h = 56.7 kJ/kg_da, t_d = 7.4 degC,
    phi = 14 %, v = 0.896 m3/kg_da.

    Tolerances are the printed precision of the example, not an allowance for
    error: the engine agrees to far more digits than ASHRAE prints (see the
    psychrolib comparison below).
    """
    state = st.from_temperature_wet_bulb(40.0, 20.0, P_ATM)

    assert state.humidity_ratio == pytest.approx(0.0064, abs=5e-5)
    assert state.enthalpy == pytest.approx(56.7, abs=0.1)
    assert state.dew_point == pytest.approx(7.4, abs=0.1)
    assert state.relative_humidity == pytest.approx(14.0, abs=0.2)
    assert state.specific_volume == pytest.approx(0.896, abs=0.001)

# 3. Independent formulation -- ASHRAE Eq. (37)/(38) dew-point fits

def _ashrae_eq37_dew_point(p_w_pa: float) -> float:
    """ASHRAE Eq. (37)/(38): explicit dew-point curve fits, p_w in kPa.

    An entirely separate correlation from the Eq. (5)/(6) inverse the engine
    uses. ASHRAE quotes it as accurate to about +/-0.3 degC over 0..93 degC.
    """
    p_kpa = p_w_pa / 1000.0
    alpha = math.log(p_kpa)
    if p_kpa > 0.61121:
        return (
            6.54
            + 14.526 * alpha
            + 0.7389 * alpha**2
            + 0.09486 * alpha**3
            + 0.4569 * p_kpa**0.1984
        )
    return 6.09 + 12.608 * alpha + 0.4959 * alpha**2

@pytest.mark.parametrize("t_db", [0.0, 10.0, 20.0, 25.0, 30.0, 40.0, 50.0])
@pytest.mark.parametrize("relative_humidity", [20.0, 50.0, 80.0, 100.0])
def test_dew_point_agrees_with_ashrae_curve_fit(t_db, relative_humidity):
    w = psy.humidity_ratio_from_relative_humidity(t_db, relative_humidity, P_ATM)
    p_w = psy.vapour_pressure_from_humidity_ratio(w, P_ATM)

    engine = psy.dew_point_temperature(p_w)
    curve_fit = _ashrae_eq37_dew_point(p_w)

    assert engine == pytest.approx(curve_fit, abs=0.3)

GRID_TEMPERATURES = [-10.0, 0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 50.0]
GRID_HUMIDITIES = [5.0, 20.0, 40.0, 60.0, 80.0, 95.0, 100.0]

@requires_psychrolib
@pytest.mark.parametrize("t_db", GRID_TEMPERATURES)
@pytest.mark.parametrize("relative_humidity", GRID_HUMIDITIES)
def test_matches_psychrolib_across_a_grid(t_db, relative_humidity):
    """Cross-check every derived property against an independent library.

    Tolerances: 1e-3 relative on the humidity ratio and 5e-3 K on the two
    solved temperatures. The residual is the two libraries' differing solver
    tolerances, not a formulation difference -- both implement ASHRAE 2017.
    """
    state = st.from_temperature_relative_humidity(t_db, relative_humidity, P_ATM)
    reference_w = psychrolib.GetHumRatioFromRelHum(t_db, relative_humidity / 100.0, P_ATM)

    assert state.humidity_ratio == pytest.approx(reference_w, rel=1e-3)
    assert state.dew_point == pytest.approx(
        psychrolib.GetTDewPointFromRelHum(t_db, relative_humidity / 100.0), abs=5e-3
    )
    assert state.wet_bulb == pytest.approx(
        psychrolib.GetTWetBulbFromRelHum(t_db, relative_humidity / 100.0, P_ATM), abs=5e-3
    )
    assert state.enthalpy == pytest.approx(
        psychrolib.GetMoistAirEnthalpy(t_db, reference_w) / 1000.0, abs=5e-3
    )
    assert state.specific_volume == pytest.approx(
        psychrolib.GetMoistAirVolume(t_db, reference_w, P_ATM), rel=1e-4
    )

@requires_psychrolib
@pytest.mark.parametrize("pressure_pa", [85000.0, 95000.0, 101325.0, 105000.0])
def test_matches_psychrolib_away_from_sea_level(pressure_pa):
    state = st.from_temperature_relative_humidity(25.0, 70.0, pressure_pa)
    assert state.humidity_ratio == pytest.approx(
        psychrolib.GetHumRatioFromRelHum(25.0, 0.70, pressure_pa), rel=1e-3
    )
    assert state.wet_bulb == pytest.approx(
        psychrolib.GetTWetBulbFromRelHum(25.0, 0.70, pressure_pa), abs=5e-3
    )

ROUND_TRIP_CONDITIONS = [
    (5.0, 90.0),
    (15.0, 60.0),
    (20.0, 50.0),
    (25.0, 75.0),
    (31.2, 72.0),
    (35.0, 20.0),
    (35.0, 85.0),
    (40.0, 99.0),
    (-5.0, 80.0),
]

@pytest.mark.parametrize("t_db, relative_humidity", ROUND_TRIP_CONDITIONS)
def test_relative_humidity_round_trips(t_db, relative_humidity):
    w = psy.humidity_ratio_from_relative_humidity(t_db, relative_humidity, P_ATM)
    back = psy.relative_humidity_from_humidity_ratio(t_db, w, P_ATM)
    assert back == pytest.approx(relative_humidity, abs=1e-9)

@pytest.mark.parametrize("t_db, relative_humidity", ROUND_TRIP_CONDITIONS)
def test_wet_bulb_round_trips(t_db, relative_humidity):
    w = psy.humidity_ratio_from_relative_humidity(t_db, relative_humidity, P_ATM)
    t_wb = psy.wet_bulb_temperature(t_db, w, P_ATM)
    assert psy.humidity_ratio_from_wet_bulb(t_db, t_wb, P_ATM) == pytest.approx(w, rel=1e-8)

@pytest.mark.parametrize("t_db, relative_humidity", ROUND_TRIP_CONDITIONS)
def test_dew_point_round_trips(t_db, relative_humidity):
    w = psy.humidity_ratio_from_relative_humidity(t_db, relative_humidity, P_ATM)
    p_w = psy.vapour_pressure_from_humidity_ratio(w, P_ATM)
    t_dp = psy.dew_point_temperature(p_w)
    assert psy.saturation_vapour_pressure(t_dp) == pytest.approx(p_w, rel=1e-9)

@pytest.mark.parametrize("t_db, relative_humidity", ROUND_TRIP_CONDITIONS)
def test_enthalpy_round_trips(t_db, relative_humidity):
    w = psy.humidity_ratio_from_relative_humidity(t_db, relative_humidity, P_ATM)
    h = psy.enthalpy(t_db, w)
    assert psy.humidity_ratio_from_enthalpy(t_db, h) == pytest.approx(w, rel=1e-9)
    assert psy.temperature_from_enthalpy(h, w) == pytest.approx(t_db, abs=1e-9)

@pytest.mark.parametrize("t_db, relative_humidity", ROUND_TRIP_CONDITIONS)
def test_specific_volume_round_trips(t_db, relative_humidity):
    w = psy.humidity_ratio_from_relative_humidity(t_db, relative_humidity, P_ATM)
    v = psy.specific_volume(t_db, w, P_ATM)
    assert psy.temperature_from_specific_volume(v, w, P_ATM) == pytest.approx(t_db, abs=1e-9)

@pytest.mark.parametrize("t_db, relative_humidity", ROUND_TRIP_CONDITIONS)
def test_state_constructors_agree(t_db, relative_humidity):
    reference = st.from_temperature_relative_humidity(t_db, relative_humidity, P_ATM)

    from_dew = st.from_temperature_dew_point(t_db, reference.dew_point, P_ATM)
    from_wb = st.from_temperature_wet_bulb(t_db, reference.wet_bulb, P_ATM)
    from_w = st.from_temperature_humidity_ratio(t_db, reference.humidity_ratio, P_ATM)

    for other in (from_dew, from_wb, from_w):
        assert other.humidity_ratio == pytest.approx(reference.humidity_ratio, rel=1e-7)
        assert other.enthalpy == pytest.approx(reference.enthalpy, rel=1e-7)
        assert other.vapour_pressure_deficit == pytest.approx(
            reference.vapour_pressure_deficit, abs=1e-3
        )

@pytest.mark.parametrize("t_db, relative_humidity", ROUND_TRIP_CONDITIONS)
def test_temperature_ordering_holds(t_db, relative_humidity):
    state = st.from_temperature_relative_humidity(t_db, relative_humidity, P_ATM)
    assert state.dew_point <= state.wet_bulb + 1e-6
    assert state.wet_bulb <= state.temperature + 1e-6

def test_saturated_air_collapses_the_three_temperatures():
    state = st.from_temperature_relative_humidity(22.0, 100.0, P_ATM)
    assert state.dew_point == pytest.approx(22.0, abs=1e-3)
    assert state.wet_bulb == pytest.approx(22.0, abs=1e-3)
    assert state.vapour_pressure_deficit == pytest.approx(0.0, abs=1e-6)
    assert state.dew_point_depression == pytest.approx(0.0, abs=1e-3)

def test_vpd_increases_with_temperature_at_fixed_relative_humidity():
    previous = -1.0
    for t_db in range(10, 41, 5):
        state = st.from_temperature_relative_humidity(float(t_db), 70.0, P_ATM)
        assert state.vapour_pressure_deficit > previous
        previous = state.vapour_pressure_deficit

def test_vpd_decreases_with_relative_humidity_at_fixed_temperature():
    previous = float("inf")
    for relative_humidity in range(10, 101, 10):
        state = st.from_temperature_relative_humidity(25.0, float(relative_humidity), P_ATM)
        assert state.vapour_pressure_deficit < previous
        previous = state.vapour_pressure_deficit

def test_reference_condition_20c_50rh():
    state = st.from_temperature_relative_humidity(20.0, 50.0, P_ATM)
    assert state.humidity_ratio == pytest.approx(0.0072617, abs=1e-7)
    assert state.dew_point == pytest.approx(9.27239, abs=1e-5)
    assert state.wet_bulb == pytest.approx(13.78355, abs=1e-5)
    assert state.enthalpy == pytest.approx(38.55174, abs=1e-5)
    assert state.specific_volume == pytest.approx(0.8401563, abs=1e-7)
    assert state.vpd_kpa == pytest.approx(1.169402, abs=1e-6)
    assert state.absolute_humidity == pytest.approx(8.64332, abs=1e-5)

def test_degree_of_saturation_is_close_to_but_not_equal_to_relative_humidity():
    state = st.from_temperature_relative_humidity(30.0, 80.0, P_ATM)
    assert state.degree_of_saturation == pytest.approx(80.0, abs=1.0)
    assert state.degree_of_saturation != state.relative_humidity

def test_pressure_changes_the_state():
    sea_level = st.from_temperature_relative_humidity(25.0, 60.0, P_ATM)
    highland = st.from_temperature_relative_humidity(25.0, 60.0, 85000.0)

    assert highland.humidity_ratio > sea_level.humidity_ratio
    assert highland.specific_volume > sea_level.specific_volume
    assert highland.dew_point == pytest.approx(sea_level.dew_point, abs=1e-9)
    assert highland.vapour_pressure_deficit == pytest.approx(
        sea_level.vapour_pressure_deficit, abs=1e-6
    )

def test_standard_atmosphere_matches_ashrae_table():
    """ASHRAE Eq. (3) against the table in Ch. 1."""
    assert psy.standard_atmospheric_pressure(0.0) == pytest.approx(101325.0, abs=1.0)
    assert psy.standard_atmospheric_pressure(500.0) == pytest.approx(95461.0, rel=1e-4)
    assert psy.standard_atmospheric_pressure(1000.0) == pytest.approx(89875.0, rel=1e-4)
    assert psy.standard_atmospheric_pressure(2000.0) == pytest.approx(79495.0, rel=1e-4)

def test_altitude_inverts_standard_atmosphere():
    for altitude in [0.0, 250.0, 1500.0, 3000.0]:
        pressure = psy.standard_atmospheric_pressure(altitude)
        assert psy.altitude_from_pressure(pressure) == pytest.approx(altitude, abs=1e-3)

def test_pressure_in_kilopascal_is_rejected():
    with pytest.raises(psy.PsychrometricRangeError, match="not kPa"):
        st.from_temperature_relative_humidity(25.0, 60.0, 101.325)

def test_relative_humidity_outside_range_is_rejected():
    with pytest.raises(psy.PsychrometricRangeError):
        st.from_temperature_relative_humidity(25.0, 101.0, P_ATM)
    with pytest.raises(psy.PsychrometricRangeError):
        st.from_temperature_relative_humidity(25.0, -0.1, P_ATM)

def test_wet_bulb_above_dry_bulb_is_rejected():
    with pytest.raises(psy.PsychrometricRangeError):
        st.from_temperature_wet_bulb(20.0, 21.0, P_ATM)

def test_dew_point_above_dry_bulb_is_rejected():
    with pytest.raises(psy.PsychrometricRangeError):
        st.from_temperature_dew_point(20.0, 21.0, P_ATM)

def test_dew_point_below_freezing_uses_the_ice_branch():
    """Below 0 degC ASHRAE's dew point is a frost point; the two must differ."""
    state = st.from_temperature_relative_humidity(-5.0, 70.0, P_ATM)
    over_water = psy.dew_point_over_water(state.vapour_pressure)

    assert state.dew_point < 0.0
    assert state.dew_point > over_water
    assert 0.5 < state.dew_point - over_water < 2.0

def test_wet_bulb_below_freezing_uses_equation_34():
    state = st.from_temperature_relative_humidity(-8.0, 60.0, P_ATM)
    assert state.wet_bulb < 0.0
    assert state.dew_point <= state.wet_bulb <= state.temperature

def test_unit_conversions_round_trip():
    from psychromol.core import units

    assert units.kpa_to_pa(units.pa_to_kpa(101325.0)) == pytest.approx(101325.0)
    assert units.hpa_to_pa(units.pa_to_hpa(101325.0)) == pytest.approx(101325.0)
    assert units.bar_to_pa(units.pa_to_bar(101325.0)) == pytest.approx(101325.0)
    assert units.to_pascal(101.325, "kPa") == pytest.approx(101325.0)
    assert units.to_pascal(1013.25, "hPa") == pytest.approx(101325.0)
    assert units.to_pascal(1.0, "atm") == pytest.approx(101325.0)

def test_unknown_pressure_unit_is_rejected():
    from psychromol.core import units

    with pytest.raises(ValueError, match="unknown pressure unit"):
        units.to_pascal(1.0, "psi")
