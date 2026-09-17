"""Explicit unit conversion.

The brief (SS11) requires that pressure units are never silently mixed. This
module is the only place a scale factor between pressure units appears. Call
these functions at the boundary between the engine (Pa) and anything that
speaks kPa -- the API, CSV files, the user interface.

Naming convention: ``<from>_to_<to>``. Every function is a pure scalar map.
"""

from __future__ import annotations

from .constants import ZERO_CELSIUS_IN_KELVIN

__all__ = [
    "pa_to_kpa", "kpa_to_pa", "pa_to_hpa", "hpa_to_pa", "pa_to_bar", "bar_to_pa",
    "celsius_to_kelvin", "kelvin_to_celsius",
    "kg_per_kg_to_g_per_kg", "g_per_kg_to_kg_per_kg",
    "PRESSURE_UNITS", "to_pascal",
]


def pa_to_kpa(value_pa: float) -> float:
    """Pascal -> kilopascal."""
    return value_pa / 1000.0


def kpa_to_pa(value_kpa: float) -> float:
    """Kilopascal -> pascal."""
    return value_kpa * 1000.0


def pa_to_hpa(value_pa: float) -> float:
    """Pascal -> hectopascal (= millibar, as used by weather stations)."""
    return value_pa / 100.0


def hpa_to_pa(value_hpa: float) -> float:
    """Hectopascal -> pascal."""
    return value_hpa * 100.0


def pa_to_bar(value_pa: float) -> float:
    """Pascal -> bar."""
    return value_pa / 100000.0


def bar_to_pa(value_bar: float) -> float:
    """Bar -> pascal."""
    return value_bar * 100000.0


def celsius_to_kelvin(value_c: float) -> float:
    """Degree Celsius -> kelvin."""
    return value_c + ZERO_CELSIUS_IN_KELVIN


def kelvin_to_celsius(value_k: float) -> float:
    """Kelvin -> degree Celsius."""
    return value_k - ZERO_CELSIUS_IN_KELVIN


def kg_per_kg_to_g_per_kg(value: float) -> float:
    """Humidity ratio kg/kg_da -> g/kg_da (the usual display unit)."""
    return value * 1000.0


def g_per_kg_to_kg_per_kg(value: float) -> float:
    """Humidity ratio g/kg_da -> kg/kg_da."""
    return value / 1000.0


#: Multipliers that take a value in the named unit to pascal. Used by the
#: import layer, where a real dataset may carry pressure in any of these.
PRESSURE_UNITS: dict[str, float] = {
    "Pa": 1.0,
    "hPa": 100.0,
    "mbar": 100.0,
    "kPa": 1000.0,
    "bar": 100000.0,
    "atm": 101325.0,
}


def to_pascal(value: float, unit: str) -> float:
    """Convert ``value`` given in ``unit`` to pascal.

    Raises
    ------
    ValueError
        If the unit is not recognised. Guessing would be exactly the silent
        unit mixing this module exists to prevent.
    """
    try:
        factor = PRESSURE_UNITS[unit]
    except KeyError:
        raise ValueError(
            f"unknown pressure unit {unit!r}; expected one of "
            f"{', '.join(sorted(PRESSURE_UNITS))}"
        ) from None
    return value * factor
