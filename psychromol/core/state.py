"""``MoistAirState`` -- one fully evaluated psychrometric state.

This is the scientific layer the brief (SS4) insists on: temperature and
relative humidity are *not* the analytical variables. They are inputs to a
transformation whose output -- this object -- is what the environmental-state
classifier and the decision-support engine reason about.

A state is immutable. It is constructed once, from one measurement, and every
consumer downstream reads the same numbers. Nothing recomputes a property on
demand, so there is no way for two parts of the system to disagree about what
the greenhouse air is doing.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from . import psychrometrics as psy
from .constants import STANDARD_PRESSURE_PA
from .units import pa_to_kpa

__all__ = ["MoistAirState", "from_temperature_relative_humidity",
           "from_temperature_dew_point", "from_temperature_wet_bulb",
           "from_temperature_humidity_ratio"]


@dataclass(frozen=True, slots=True)
class MoistAirState:
    """A complete moist-air state at a known total pressure.

    All quantities are in this package's base units (degC, Pa, kg/kg_da,
    kJ/kg_da, m3/kg_da). Use :meth:`to_dict` for the API-facing form, which
    converts pressures to kPa and states the units explicitly.

    Attributes
    ----------
    temperature:
        Dry-bulb temperature [degC].
    relative_humidity:
        Relative humidity [%].
    pressure:
        Total (atmospheric) pressure [Pa].
    saturation_vapour_pressure:
        ``p_ws(t)`` [Pa] -- ASHRAE Eq. (5)/(6).
    vapour_pressure:
        Partial vapour pressure ``p_w`` [Pa].
    humidity_ratio:
        ``W`` [kg water / kg dry air] -- Eq. (20).
    dew_point:
        Dew-point (frost-point below 0 degC) temperature [degC].
    wet_bulb:
        Thermodynamic wet-bulb temperature [degC] -- Eq. (33)/(34).
    enthalpy:
        Specific enthalpy [kJ/kg dry air] -- Eq. (30).
    specific_volume:
        Specific volume [m3/kg dry air] -- Eq. (26).
    density:
        Moist-air density [kg/m3].
    vapour_pressure_deficit:
        Air VPD [Pa]. Air-temperature based, not leaf-to-air.
    absolute_humidity:
        Vapour concentration [g/m3].
    degree_of_saturation:
        ``W/W_s`` [%] -- distinct from relative humidity.
    saturation_humidity_ratio:
        ``W_s(t, p)`` [kg/kg_da]; the ceiling ``humidity_ratio`` can reach at
        this temperature and pressure.
    dew_point_depression:
        ``t - t_dew`` [K]. How far the air is from saturating. The primary
        condensation-risk variable when no surface temperature is measured.
    """

    temperature: float
    relative_humidity: float
    pressure: float
    saturation_vapour_pressure: float
    vapour_pressure: float
    humidity_ratio: float
    dew_point: float
    wet_bulb: float
    enthalpy: float
    specific_volume: float
    density: float
    vapour_pressure_deficit: float
    absolute_humidity: float
    degree_of_saturation: float
    saturation_humidity_ratio: float
    dew_point_depression: float

    # -- derived conveniences -------------------------------------------

    @property
    def vpd_kpa(self) -> float:
        """Vapour-pressure deficit in kPa, the unit horticulture uses."""
        return pa_to_kpa(self.vapour_pressure_deficit)

    @property
    def humidity_ratio_g_per_kg(self) -> float:
        """Humidity ratio in g/kg dry air, the unit both charts label."""
        return self.humidity_ratio * 1000.0

    @property
    def mollier_ordinate(self) -> float:
        """``h - 2501 W`` [kJ/kg_da] -- the skewed ordinate of the h-x chart.

        See :mod:`psychromol.core.mollier` for why this particular skew is
        what makes a Mollier diagram a Mollier diagram.
        """
        from .mollier import mollier_ordinate

        return mollier_ordinate(self.enthalpy, self.humidity_ratio)

    def is_saturated(self, tolerance_percent: float = 0.5) -> bool:
        """True when the air is at (or within ``tolerance_percent`` of) saturation."""
        return self.relative_humidity >= 100.0 - tolerance_percent

    # -- serialisation ---------------------------------------------------

    def to_dict(self) -> dict[str, float]:
        """Base-unit dictionary. Pressures stay in Pa; nothing is converted."""
        return asdict(self)

    def to_api_dict(self) -> dict[str, Any]:
        """API-facing form: pressures in kPa, VPD in kPa, W in both units.

        The conversion happens exactly here, once, so that no consumer has to
        guess which pressure unit a field is in (brief SS11).
        """
        return {
            "temperature_c": round(self.temperature, 4),
            "relative_humidity_percent": round(self.relative_humidity, 4),
            "pressure_kpa": round(pa_to_kpa(self.pressure), 5),
            "saturation_vapour_pressure_kpa": round(
                pa_to_kpa(self.saturation_vapour_pressure), 6
            ),
            "vapour_pressure_kpa": round(pa_to_kpa(self.vapour_pressure), 6),
            "humidity_ratio_kg_kg": round(self.humidity_ratio, 8),
            "humidity_ratio_g_kg": round(self.humidity_ratio_g_per_kg, 5),
            "dew_point_c": round(self.dew_point, 4),
            "wet_bulb_c": round(self.wet_bulb, 4),
            "enthalpy_kj_kg": round(self.enthalpy, 4),
            "specific_volume_m3_kg": round(self.specific_volume, 6),
            "density_kg_m3": round(self.density, 5),
            "vpd_kpa": round(self.vpd_kpa, 5),
            "absolute_humidity_g_m3": round(self.absolute_humidity, 4),
            "degree_of_saturation_percent": round(self.degree_of_saturation, 4),
            "saturation_humidity_ratio_kg_kg": round(
                self.saturation_humidity_ratio, 8
            ),
            "dew_point_depression_k": round(self.dew_point_depression, 4),
            "mollier_ordinate_kj_kg": round(self.mollier_ordinate, 4),
        }


# ---------------------------------------------------------------------------
# Constructors
#
# One per input pair a real instrument might deliver. Each resolves its pair to
# (t, W) and then hands off to _evaluate, so there is exactly one place where a
# complete state is assembled and no constructor can produce an inconsistent
# one.
# ---------------------------------------------------------------------------


def _evaluate(t_db: float, humidity_ratio: float, pressure: float) -> MoistAirState:
    """Assemble the complete state from the canonical pair ``(t, W)``."""
    psy.validate_pressure(pressure)
    p_ws = psy.saturation_vapour_pressure(t_db)
    p_w = psy.vapour_pressure_from_humidity_ratio(humidity_ratio, pressure)

    # Sensor noise and rounding can push p_w a hair above p_ws at saturation.
    # Clamping RH at 100 % keeps the reported state physical; the raw reading
    # is untouched in the database, and the quality layer is what flags it.
    relative_humidity = min(100.0, 100.0 * p_w / p_ws)

    dew_point = psy.dew_point_temperature(p_w)
    specific_volume = psy.specific_volume(t_db, humidity_ratio, pressure)

    return MoistAirState(
        temperature=t_db,
        relative_humidity=relative_humidity,
        pressure=pressure,
        saturation_vapour_pressure=p_ws,
        vapour_pressure=p_w,
        humidity_ratio=humidity_ratio,
        dew_point=dew_point,
        wet_bulb=psy.wet_bulb_temperature(t_db, humidity_ratio, pressure),
        enthalpy=psy.enthalpy(t_db, humidity_ratio),
        specific_volume=specific_volume,
        density=(1.0 + humidity_ratio) / specific_volume,
        vapour_pressure_deficit=p_ws - p_w,
        absolute_humidity=1000.0 * humidity_ratio / specific_volume,
        degree_of_saturation=psy.degree_of_saturation(t_db, humidity_ratio, pressure),
        saturation_humidity_ratio=psy.saturation_humidity_ratio(t_db, pressure),
        dew_point_depression=t_db - dew_point,
    )


def from_temperature_relative_humidity(
    temperature: float,
    relative_humidity: float,
    pressure: float = STANDARD_PRESSURE_PA,
) -> MoistAirState:
    """Evaluate a state from dry-bulb temperature and relative humidity.

    The primary constructor: this is the pair a greenhouse sensor delivers.

    :param temperature: dry-bulb temperature [degC]
    :param relative_humidity: relative humidity [%]
    :param pressure: total pressure [Pa]; defaults to the standard atmosphere
        at sea level, which is a **default, not an assumption** -- supply the
        measured or altitude-corrected value where one exists
    """
    psy.validate_pressure(pressure)
    humidity_ratio = psy.humidity_ratio_from_relative_humidity(
        temperature, relative_humidity, pressure
    )
    return _evaluate(temperature, humidity_ratio, pressure)


def from_temperature_dew_point(
    temperature: float, dew_point: float, pressure: float = STANDARD_PRESSURE_PA
) -> MoistAirState:
    """Evaluate a state from dry-bulb and dew-point temperature.

    Some reference datasets and chilled-mirror hygrometers report this pair.
    """
    psy.validate_pressure(pressure)
    if dew_point > temperature + 1e-9:
        raise psy.PsychrometricRangeError(
            f"dew point {dew_point} degC cannot exceed dry-bulb {temperature} degC"
        )
    p_w = psy.saturation_vapour_pressure(dew_point)
    return _evaluate(
        temperature, psy.humidity_ratio_from_vapour_pressure(p_w, pressure), pressure
    )


def from_temperature_wet_bulb(
    temperature: float, wet_bulb: float, pressure: float = STANDARD_PRESSURE_PA
) -> MoistAirState:
    """Evaluate a state from the dry-bulb / wet-bulb pair -- Eq. (33)/(34).

    The pair a sling psychrometer delivers, still the reference instrument for
    field verification of an electronic sensor.
    """
    psy.validate_pressure(pressure)
    humidity_ratio = psy.humidity_ratio_from_wet_bulb(temperature, wet_bulb, pressure)
    return _evaluate(temperature, humidity_ratio, pressure)


def from_temperature_humidity_ratio(
    temperature: float, humidity_ratio: float, pressure: float = STANDARD_PRESSURE_PA
) -> MoistAirState:
    """Evaluate a state from the canonical pair ``(t, W)``.

    Used when re-evaluating a stored state, and by the chart geometry.
    """
    return _evaluate(temperature, humidity_ratio, pressure)
