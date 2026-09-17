"""Moist-air relations from ASHRAE Handbook -- Fundamentals (2017), Chapter 1.

This module is the single source of numerical truth in PsychroMol. Every
number the API returns, the chart draws or the decision-support system reasons
about is produced here or derived from something produced here.

Design rules
------------
* **Pure functions.** No I/O, no globals, no framework imports, no caching.
  The module imports only ``math`` and this package's own constants, so the
  science can be reproduced with a bare Python install.
* **Pressure is always a parameter.** Nothing assumes sea level.
* **Inputs outside a correlation's validated range raise**, rather than
  silently extrapolating. Sensor data is not always sane, and an out-of-range
  extrapolation that looks plausible is worse than an error.
* **Inverses are numerical, not curve fits.** Where ASHRAE prints both an
  exact relation and a convenience fit, this module inverts the exact relation
  by bisection so round-trips close to solver tolerance. The printed fits are
  retained *in the test suite* as independent cross-checks, which is the only
  role they can play without weakening the result.

Each public function names its ASHRAE equation number in its docstring.
Assumptions and validity ranges are recorded in
``docs/psychrometric-methodology.md``.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from .constants import (
    CP_DRY_AIR,
    CP_ICE,
    CP_LIQUID_WATER,
    CP_WATER_VAPOUR,
    H_FG_0C,
    H_IG_0C,
    MAX_PRESSURE_PA,
    MAX_TEMPERATURE_C,
    MIN_PRESSURE_PA,
    MIN_TEMPERATURE_C,
    MW_RATIO,
    R_DRY_AIR,
    SPECIFIC_VOLUME_W_COEFF,
    STANDARD_PRESSURE_PA,
    ZERO_CELSIUS_IN_KELVIN,
)

__all__ = [
    "PsychrometricRangeError",
    "saturation_vapour_pressure",
    "saturation_vapour_pressure_over_water",
    "saturation_vapour_pressure_over_ice",
    "saturation_temperature",
    "humidity_ratio_from_vapour_pressure",
    "vapour_pressure_from_humidity_ratio",
    "saturation_humidity_ratio",
    "humidity_ratio_from_relative_humidity",
    "relative_humidity_from_humidity_ratio",
    "relative_humidity_from_dew_point",
    "degree_of_saturation",
    "dew_point_temperature",
    "dew_point_over_water",
    "frost_point_temperature",
    "humidity_ratio_from_wet_bulb",
    "wet_bulb_temperature",
    "enthalpy",
    "humidity_ratio_from_enthalpy",
    "temperature_from_enthalpy",
    "specific_volume",
    "temperature_from_specific_volume",
    "moist_air_density",
    "dry_air_density",
    "vapour_pressure_deficit",
    "absolute_humidity",
    "standard_atmospheric_pressure",
    "altitude_from_pressure",
    "validate_pressure",
    "validate_relative_humidity",
]


class PsychrometricRangeError(ValueError):
    """An input falls outside the validated range of the correlation used.

    A distinct exception type so the ingestion layer can flag the measurement
    as INVALID and carry on, rather than treating it as a programming error.
    """


# ---------------------------------------------------------------------------
# Numerical settings
# ---------------------------------------------------------------------------

# Bisection stops when the bracket is narrower than this. On the widest
# bracket used here (300 K) that is reached in about 48 halvings; the
# iteration cap below is therefore never the binding constraint.
_TEMPERATURE_TOLERANCE_C = 1e-10
_HUMIDITY_RATIO_TOLERANCE = 1e-14
_MAX_ITERATIONS = 200


# ---------------------------------------------------------------------------
# 1. Saturation vapour pressure -- ASHRAE Eq. (5) and (6)
# ---------------------------------------------------------------------------

# Eq. (5): saturation over ice, valid -100 degC .. 0 degC.
_ICE_C1 = -5.6745359e03
_ICE_C2 = 6.3925247e00
_ICE_C3 = -9.6778430e-03
_ICE_C4 = 6.2215701e-07
_ICE_C5 = 2.0747825e-09
_ICE_C6 = -9.4840240e-13
_ICE_C7 = 4.1635019e00

# Eq. (6): saturation over liquid water, valid 0 degC .. 200 degC.
_WATER_C8 = -5.8002206e03
_WATER_C9 = 1.3914993e00
_WATER_C10 = -4.8640239e-02
_WATER_C11 = 4.1764768e-05
_WATER_C12 = -1.4452093e-08
_WATER_C13 = 6.5459673e00


def saturation_vapour_pressure_over_ice(t_db: float) -> float:
    """Saturation vapour pressure over ice -- ASHRAE Eq. (5).

    ``ln(p_ws) = C1/T + C2 + C3 T + C4 T^2 + C5 T^3 + C6 T^4 + C7 ln(T)``
    with ``T`` in kelvin.

    Valid -100 .. 0 degC. Evaluating it above 0 degC is an extrapolation and
    is only meaningful as an intermediate in :func:`frost_point_temperature`.

    :param t_db: dry-bulb temperature [degC]
    :returns: saturation vapour pressure [Pa]
    """
    t_k = t_db + ZERO_CELSIUS_IN_KELVIN
    ln_p = (
        _ICE_C1 / t_k
        + _ICE_C2
        + _ICE_C3 * t_k
        + _ICE_C4 * t_k**2
        + _ICE_C5 * t_k**3
        + _ICE_C6 * t_k**4
        + _ICE_C7 * math.log(t_k)
    )
    return math.exp(ln_p)


def saturation_vapour_pressure_over_water(t_db: float) -> float:
    """Saturation vapour pressure over liquid water -- ASHRAE Eq. (6).

    ``ln(p_ws) = C8/T + C9 + C10 T + C11 T^2 + C12 T^3 + C13 ln(T)``
    with ``T`` in kelvin.

    Valid 0 .. 200 degC. Below 0 degC this is the *supercooled water* branch;
    it is well behaved and is what :func:`dew_point_over_water` inverts.

    :param t_db: dry-bulb temperature [degC]
    :returns: saturation vapour pressure [Pa]
    """
    t_k = t_db + ZERO_CELSIUS_IN_KELVIN
    ln_p = (
        _WATER_C8 / t_k
        + _WATER_C9
        + _WATER_C10 * t_k
        + _WATER_C11 * t_k**2
        + _WATER_C12 * t_k**3
        + _WATER_C13 * math.log(t_k)
    )
    return math.exp(ln_p)


def saturation_vapour_pressure(t_db: float) -> float:
    """Saturation vapour pressure of water in moist air -- ASHRAE Eq. (5)/(6).

    Branches at 0 degC exactly as ASHRAE does: Eq. (5) over ice below
    freezing, Eq. (6) over liquid water at and above it. At 0 degC itself the
    water branch is taken (611.21 Pa), which is the conventional value.

    The branch choice propagates into :func:`dew_point_temperature`, which is
    therefore a *frost* point below 0 degC in ASHRAE's convention. For
    greenhouse condensation analysis on cold glass, that is the physically
    relevant quantity; :func:`dew_point_over_water` is available where the
    supercooled-water convention is wanted instead.

    :param t_db: dry-bulb temperature [degC], valid -100 .. 200
    :returns: saturation vapour pressure [Pa]
    :raises PsychrometricRangeError: outside -100 .. 200 degC
    """
    _validate_temperature(t_db)
    if t_db < 0.0:
        return saturation_vapour_pressure_over_ice(t_db)
    return saturation_vapour_pressure_over_water(t_db)


def saturation_temperature(p_ws: float) -> float:
    """Temperature at which moist air saturates at ``p_ws`` -- inverse of Eq. (5)/(6).

    ASHRAE prints no closed-form inverse; its Eq. (37)/(38) are separate curve
    fits accurate to roughly +/-0.3 degC. This function inverts the correlation
    numerically instead, so ``saturation_temperature(saturation_vapour_pressure(t))``
    returns ``t`` to solver tolerance. Eq. (37)/(38) are kept as an independent
    check in ``tests/test_psychrometrics.py``.

    :param p_ws: saturation vapour pressure [Pa], must be > 0
    :returns: saturation temperature [degC]
    """
    if p_ws <= 0.0:
        raise PsychrometricRangeError(
            f"saturation vapour pressure must be positive, got {p_ws} Pa"
        )
    return _bisect_increasing(
        saturation_vapour_pressure, p_ws, MIN_TEMPERATURE_C, MAX_TEMPERATURE_C
    )


# ---------------------------------------------------------------------------
# 2. Humidity ratio, vapour pressure, relative humidity
# ---------------------------------------------------------------------------


def humidity_ratio_from_vapour_pressure(p_w: float, pressure: float) -> float:
    """Humidity ratio from partial vapour pressure -- ASHRAE Eq. (20).

    ``W = 0.621945 p_w / (p - p_w)``

    :param p_w: partial pressure of water vapour [Pa]
    :param pressure: total (atmospheric) pressure [Pa]
    :returns: humidity ratio [kg_water/kg_dry_air]
    """
    if p_w < 0.0:
        raise PsychrometricRangeError(f"vapour pressure must be >= 0, got {p_w} Pa")
    if pressure <= p_w:
        raise PsychrometricRangeError(
            f"vapour pressure {p_w} Pa must be below total pressure {pressure} Pa"
        )
    return MW_RATIO * p_w / (pressure - p_w)


def vapour_pressure_from_humidity_ratio(humidity_ratio: float, pressure: float) -> float:
    """Partial vapour pressure from humidity ratio -- ASHRAE Eq. (20) rearranged.

    ``p_w = p W / (0.621945 + W)``

    :param humidity_ratio: [kg_water/kg_dry_air]
    :param pressure: total pressure [Pa]
    :returns: partial vapour pressure [Pa]
    """
    if humidity_ratio < 0.0:
        raise PsychrometricRangeError(
            f"humidity ratio must be non-negative, got {humidity_ratio}"
        )
    return pressure * humidity_ratio / (MW_RATIO + humidity_ratio)


def saturation_humidity_ratio(t_db: float, pressure: float) -> float:
    """Humidity ratio of saturated moist air -- Eq. (20) evaluated at ``p_ws``.

    :param t_db: dry-bulb temperature [degC]
    :param pressure: total pressure [Pa]
    :returns: saturation humidity ratio [kg/kg_da]
    """
    return humidity_ratio_from_vapour_pressure(
        saturation_vapour_pressure(t_db), pressure
    )


def humidity_ratio_from_relative_humidity(
    t_db: float, relative_humidity: float, pressure: float
) -> float:
    """Humidity ratio from dry-bulb temperature and RH -- Eq. (12) with Eq. (20).

    ``p_w = phi p_ws(t)``, then ``W`` from Eq. (20). This is the entry point
    used for every sensor reading, since temperature and RH are what a
    greenhouse sensor delivers.

    :param t_db: dry-bulb temperature [degC]
    :param relative_humidity: relative humidity [%], 0 .. 100
    :param pressure: total pressure [Pa]
    :returns: humidity ratio [kg/kg_da]
    """
    validate_relative_humidity(relative_humidity)
    p_w = saturation_vapour_pressure(t_db) * relative_humidity / 100.0
    return humidity_ratio_from_vapour_pressure(p_w, pressure)


def relative_humidity_from_humidity_ratio(
    t_db: float, humidity_ratio: float, pressure: float
) -> float:
    """Relative humidity [%] -- ASHRAE Eq. (12): ``phi = p_w / p_ws``.

    Expressed as the ratio of partial pressures. Equivalent to the Eq. (24)
    form written via the degree of saturation, and better conditioned.
    """
    p_w = vapour_pressure_from_humidity_ratio(humidity_ratio, pressure)
    return 100.0 * p_w / saturation_vapour_pressure(t_db)


def relative_humidity_from_dew_point(t_db: float, t_dew: float) -> float:
    """Relative humidity [%] from the dry-bulb / dew-point pair -- Eq. (12).

    ``phi = p_ws(t_dew) / p_ws(t_db)``. Pressure-independent, which is why
    some reference datasets report dew point rather than RH.
    """
    if t_dew > t_db + 1e-9:
        raise PsychrometricRangeError(
            f"dew point {t_dew} degC cannot exceed dry-bulb {t_db} degC"
        )
    return 100.0 * saturation_vapour_pressure(t_dew) / saturation_vapour_pressure(t_db)


def degree_of_saturation(t_db: float, humidity_ratio: float, pressure: float) -> float:
    """Degree of saturation ``mu = W / W_s`` -- ASHRAE Eq. (12), as a percentage.

    Distinct from relative humidity: ``mu`` compares humidity *ratios*, ``phi``
    compares vapour *pressures*. They differ by a few tenths of a percent at
    ordinary greenhouse conditions. Reported separately so the distinction is
    visible rather than glossed over.
    """
    w_sat = saturation_humidity_ratio(t_db, pressure)
    if w_sat <= 0.0:
        return 0.0
    return 100.0 * humidity_ratio / w_sat


# ---------------------------------------------------------------------------
# 3. Dew point and frost point
# ---------------------------------------------------------------------------


def dew_point_temperature(p_w: float) -> float:
    """Dew-point temperature from partial vapour pressure.

    Obtained by inverting the ASHRAE saturation curve (see
    :func:`saturation_temperature`), so that feeding the result back through
    :func:`saturation_vapour_pressure` reproduces ``p_w`` exactly.

    Below 0 degC the ASHRAE curve is taken over ice, so the value returned
    there is a frost point in ASHRAE's convention -- the temperature at which
    vapour would deposit on a cold surface. That is the quantity that matters
    for greenhouse condensation risk on glazing.

    :param p_w: partial pressure of water vapour [Pa]
    :returns: dew-point temperature [degC]; ``MIN_TEMPERATURE_C`` for
        perfectly dry air, which has no dew point
    """
    if p_w <= 0.0:
        return MIN_TEMPERATURE_C
    return saturation_temperature(p_w)


def dew_point_over_water(p_w: float) -> float:
    """Dew point against the supercooled-water branch alone -- inverse of Eq. (6).

    Provided because meteorological practice and some sensor datasheets report
    dew point over water at all temperatures. Above 0 degC it is identical to
    :func:`dew_point_temperature`; below, it is a few tenths of a degree lower.
    """
    if p_w <= 0.0:
        return MIN_TEMPERATURE_C
    return _bisect_increasing(
        saturation_vapour_pressure_over_water, p_w, MIN_TEMPERATURE_C, MAX_TEMPERATURE_C
    )


def frost_point_temperature(p_w: float) -> float:
    """Frost point -- inverse of the ice branch, ASHRAE Eq. (5).

    Above 0 degC the ice branch is an extrapolation with no physical meaning;
    callers should use :func:`dew_point_temperature` there. This function
    exists so that sub-freezing analysis can name the quantity it means.
    """
    if p_w <= 0.0:
        return MIN_TEMPERATURE_C
    return _bisect_increasing(
        saturation_vapour_pressure_over_ice, p_w, MIN_TEMPERATURE_C, 0.0
    )


# ---------------------------------------------------------------------------
# 4. Wet-bulb temperature -- ASHRAE Eq. (33) and (34)
# ---------------------------------------------------------------------------


def humidity_ratio_from_wet_bulb(t_db: float, t_wb: float, pressure: float) -> float:
    """Humidity ratio from the dry-bulb / wet-bulb pair -- ASHRAE Eq. (33)/(34).

    Above freezing, Eq. (33)::

        W = ((2501 - 2.326 t*) W_s* - 1.006 (t - t*)) / (2501 + 1.86 t - 4.186 t*)

    At or below freezing, Eq. (34), sublimation replacing vaporisation::

        W = ((2830 - 0.24 t*) W_s* - 1.006 (t - t*)) / (2830 + 1.86 t - 2.1 t*)

    The numeric coefficients 2.326 and 0.24 are ``cp_liquid - cp_vapour`` and
    ``cp_ice - cp_vapour``; they are written here in terms of the named
    constants so the physics stays visible.

    :param t_db: dry-bulb temperature [degC]
    :param t_wb: thermodynamic wet-bulb temperature [degC]
    :param pressure: total pressure [Pa]
    :returns: humidity ratio [kg/kg_da], clamped at zero
    """
    if t_wb > t_db + 1e-9:
        raise PsychrometricRangeError(
            f"wet-bulb {t_wb} degC cannot exceed dry-bulb {t_db} degC"
        )
    w_sat_wb = saturation_humidity_ratio(t_wb, pressure)

    if t_wb >= 0.0:
        numerator = (
            H_FG_0C - (CP_LIQUID_WATER - CP_WATER_VAPOUR) * t_wb
        ) * w_sat_wb - CP_DRY_AIR * (t_db - t_wb)
        denominator = H_FG_0C + CP_WATER_VAPOUR * t_db - CP_LIQUID_WATER * t_wb
    else:
        numerator = (
            H_IG_0C - (CP_ICE - CP_WATER_VAPOUR) * t_wb
        ) * w_sat_wb - CP_DRY_AIR * (t_db - t_wb)
        denominator = H_IG_0C + CP_WATER_VAPOUR * t_db - CP_ICE * t_wb

    return max(numerator / denominator, 0.0)


def wet_bulb_temperature(t_db: float, humidity_ratio: float, pressure: float) -> float:
    """Thermodynamic wet-bulb temperature -- numerical inverse of Eq. (33)/(34).

    ``humidity_ratio_from_wet_bulb`` increases monotonically in ``t_wb`` on the
    physically admissible interval ``[t_dew, t_db]``, so the root is bracketed
    by construction. Bracketing on the dew point rather than on a fixed lower
    bound is what keeps this robust for cold and very dry air, where a fixed
    bound can fail to bracket the root at all.

    Bisection rather than Newton: the relations are cheap, the bracket is known
    a priori, and bisection cannot diverge -- which matters for code that runs
    unattended against live sensor data.

    :param t_db: dry-bulb temperature [degC]
    :param humidity_ratio: humidity ratio [kg/kg_da]
    :param pressure: total pressure [Pa]
    :returns: wet-bulb temperature [degC]
    """
    p_w = vapour_pressure_from_humidity_ratio(humidity_ratio, pressure)
    lower = dew_point_temperature(p_w) if p_w > 0.0 else MIN_TEMPERATURE_C
    upper = t_db

    if upper - lower < _TEMPERATURE_TOLERANCE_C:
        # Saturated air: wet bulb, dry bulb and dew point coincide.
        return t_db

    def w_at(t_wb: float) -> float:
        return humidity_ratio_from_wet_bulb(t_db, t_wb, pressure)

    return _bisect_increasing(w_at, humidity_ratio, lower, upper)


# ---------------------------------------------------------------------------
# 5. Enthalpy, specific volume, density
# ---------------------------------------------------------------------------


def enthalpy(t_db: float, humidity_ratio: float) -> float:
    """Specific enthalpy of moist air -- ASHRAE Eq. (30).

    ``h = 1.006 t + W (2501 + 1.86 t)``   [kJ/kg dry air]

    The datum is dry air and liquid water, both at 0 degC. Enthalpy is
    independent of total pressure, which is why ``pressure`` is not a
    parameter -- a fact worth stating because the Mollier chart is often drawn
    for a nominal pressure and the two are easily conflated.
    """
    return CP_DRY_AIR * t_db + humidity_ratio * (H_FG_0C + CP_WATER_VAPOUR * t_db)


def humidity_ratio_from_enthalpy(t_db: float, h: float) -> float:
    """Humidity ratio along an isenthalp -- Eq. (30) solved for ``W``.

    Used to draw the constant-enthalpy family on both charts.
    """
    return (h - CP_DRY_AIR * t_db) / (H_FG_0C + CP_WATER_VAPOUR * t_db)


def temperature_from_enthalpy(h: float, humidity_ratio: float) -> float:
    """Dry-bulb temperature from enthalpy and humidity ratio -- Eq. (30) for ``t``."""
    return (h - humidity_ratio * H_FG_0C) / (
        CP_DRY_AIR + humidity_ratio * CP_WATER_VAPOUR
    )


def specific_volume(t_db: float, humidity_ratio: float, pressure: float) -> float:
    """Specific volume of moist air -- ASHRAE Eq. (26).

    ``v = R_da (t + 273.15) (1 + 1.607858 W) / p``   [m3/kg dry air]

    Per kilogram of *dry air*, not per kilogram of mixture -- the distinction
    that makes :func:`moist_air_density` a ``(1 + W)/v`` and not a ``1/v``.
    """
    validate_pressure(pressure)
    t_k = t_db + ZERO_CELSIUS_IN_KELVIN
    return R_DRY_AIR * t_k * (1.0 + SPECIFIC_VOLUME_W_COEFF * humidity_ratio) / pressure


def temperature_from_specific_volume(
    v: float, humidity_ratio: float, pressure: float
) -> float:
    """Dry-bulb temperature on a constant-specific-volume line -- Eq. (26) for ``t``."""
    return (
        v * pressure / (R_DRY_AIR * (1.0 + SPECIFIC_VOLUME_W_COEFF * humidity_ratio))
        - ZERO_CELSIUS_IN_KELVIN
    )


def moist_air_density(t_db: float, humidity_ratio: float, pressure: float) -> float:
    """Density of moist air [kg/m3] -- ASHRAE Eq. (11) rearranged.

    ``rho = (1 + W) / v`` -- the mass of dry air *plus* its water vapour per
    cubic metre. This is the quantity a gravimetric measurement would return.
    """
    return (1.0 + humidity_ratio) / specific_volume(t_db, humidity_ratio, pressure)


def dry_air_density(t_db: float, humidity_ratio: float, pressure: float) -> float:
    """Mass of dry air per cubic metre of moist air [kg/m3], ``1/v``.

    Reported separately from :func:`moist_air_density` because ventilation
    calculations use one and buoyancy calculations the other.
    """
    return 1.0 / specific_volume(t_db, humidity_ratio, pressure)


# ---------------------------------------------------------------------------
# 6. Derived agronomic quantities
# ---------------------------------------------------------------------------


def vapour_pressure_deficit(t_db: float, humidity_ratio: float, pressure: float) -> float:
    """Vapour-pressure deficit of the air [Pa].

    ``VPD = p_ws(t_air) - p_w``

    This is the **air VPD**, evaluated at air temperature. It is *not* the
    leaf-to-air VPD used in much plant-physiology work, which substitutes leaf
    temperature into the saturation term. PsychroMol does not model leaf
    temperature and therefore does not report that quantity; the distinction is
    stated in ``docs/psychrometric-methodology.md`` so no reader mistakes one
    for the other.
    """
    p_w = vapour_pressure_from_humidity_ratio(humidity_ratio, pressure)
    return saturation_vapour_pressure(t_db) - p_w


def absolute_humidity(t_db: float, humidity_ratio: float, pressure: float) -> float:
    """Absolute humidity, i.e. vapour mass concentration [g/m3].

    ``AH = 1000 W / v`` -- grams of water vapour per cubic metre of moist air.
    The unit horticulturalists use when talking about a dehumidifier's duty.
    """
    return 1000.0 * humidity_ratio / specific_volume(t_db, humidity_ratio, pressure)


# ---------------------------------------------------------------------------
# 7. Atmosphere
# ---------------------------------------------------------------------------


def standard_atmospheric_pressure(altitude_m: float = 0.0) -> float:
    """Standard-atmosphere pressure at altitude -- ASHRAE Eq. (3).

    ``p = 101325 (1 - 2.25577e-5 Z)^5.2559``, ``Z`` in metres, ``p`` in Pa.

    Lets a highland installation configure a physically sensible default
    instead of assuming sea level, when no barometer is fitted.
    """
    return STANDARD_PRESSURE_PA * (1.0 - 2.25577e-5 * altitude_m) ** 5.2559


def altitude_from_pressure(pressure: float) -> float:
    """Altitude implied by a pressure under the standard atmosphere -- Eq. (3) inverted.

    Diagnostic only: it reports what altitude a configured pressure corresponds
    to, which catches a kPa/Pa mix-up at configuration time.
    """
    validate_pressure(pressure)
    return (1.0 - (pressure / STANDARD_PRESSURE_PA) ** (1.0 / 5.2559)) / 2.25577e-5


# ---------------------------------------------------------------------------
# 8. Input validation
# ---------------------------------------------------------------------------


def _validate_temperature(t_db: float) -> None:
    if not math.isfinite(t_db):
        raise PsychrometricRangeError(f"temperature must be finite, got {t_db}")
    if not MIN_TEMPERATURE_C <= t_db <= MAX_TEMPERATURE_C:
        raise PsychrometricRangeError(
            f"temperature {t_db} degC is outside the validated correlation range "
            f"{MIN_TEMPERATURE_C}..{MAX_TEMPERATURE_C} degC"
        )


def validate_pressure(pressure: float) -> None:
    """Reject a total pressure that cannot be a real atmospheric measurement.

    The commonest cause of a value here being wrong by three orders of
    magnitude is a kPa value passed where Pa was expected, so this check is
    load-bearing rather than defensive.
    """
    if not math.isfinite(pressure):
        raise PsychrometricRangeError(f"pressure must be finite, got {pressure}")
    if not MIN_PRESSURE_PA <= pressure <= MAX_PRESSURE_PA:
        raise PsychrometricRangeError(
            f"total pressure {pressure} Pa is outside {MIN_PRESSURE_PA}.."
            f"{MAX_PRESSURE_PA} Pa -- check the unit (this package works in Pa, "
            f"not kPa)"
        )


def validate_relative_humidity(relative_humidity: float) -> None:
    """Reject a relative humidity outside 0..100 %."""
    if not math.isfinite(relative_humidity):
        raise PsychrometricRangeError(
            f"relative humidity must be finite, got {relative_humidity}"
        )
    if not 0.0 <= relative_humidity <= 100.0:
        raise PsychrometricRangeError(
            f"relative humidity must be within 0..100 %, got {relative_humidity}"
        )


# ---------------------------------------------------------------------------
# 9. Shared numerics
# ---------------------------------------------------------------------------


def _bisect_increasing(
    fn: Callable[[float], float], target: float, lower: float, upper: float
) -> float:
    """Bisect a monotonically increasing ``fn`` for ``fn(x) == target``.

    Returns the nearer bracket end when the target lies outside ``[fn(lower),
    fn(upper)]`` -- saturating rather than raising, because the callers here
    bracket on physical bounds and a target just outside them is a rounding
    artefact, not an error.
    """
    f_lower = fn(lower)
    if f_lower >= target:
        return lower
    f_upper = fn(upper)
    if f_upper <= target:
        return upper

    for _ in range(_MAX_ITERATIONS):
        midpoint = 0.5 * (lower + upper)
        if fn(midpoint) < target:
            lower = midpoint
        else:
            upper = midpoint
        if upper - lower < _TEMPERATURE_TOLERANCE_C:
            break

    return 0.5 * (lower + upper)
