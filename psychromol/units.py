from __future__ import annotations

PRESSURE_UNITS: dict[str, float] = {"kPa": 1.0, "hPa": 0.1, "Pa": 0.001}


def kpa_from(value: float, unit: str) -> float:
    try:
        factor = PRESSURE_UNITS[unit]
    except KeyError as exc:
        raise ValueError(f"unknown pressure unit {unit!r}") from exc
    return value * factor
