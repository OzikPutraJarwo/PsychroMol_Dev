from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from .core.state import MoistAirState

EQUIPMENT = (
    "fan",
    "side_window",
    "roof_vent",
    "heater",
    "cooling",
    "fogging",
    "dehumidifier",
    "shade_screen",
    "thermal_screen",
    "irrigation",
    "supplemental_light",
    "co2_injection",
)

EQUIPMENT_LABELS = {
    "fan": "Circulation fan",
    "side_window": "Side window",
    "roof_vent": "Roof vent",
    "heater": "Heater",
    "cooling": "Cooling",
    "fogging": "Fogging",
    "dehumidifier": "Dehumidifier",
    "shade_screen": "Shade screen",
    "thermal_screen": "Thermal screen",
    "irrigation": "Irrigation",
    "supplemental_light": "Supplemental light",
    "co2_injection": "CO2 injection",
}

METRICS: dict[str, dict[str, str]] = {
    "temperature": {"label": "Temperature", "unit": "°C"},
    "relative_humidity": {"label": "Relative humidity", "unit": "%"},
    "vpd": {"label": "VPD", "unit": "kPa"},
    "dew_point": {"label": "Dew point", "unit": "°C"},
    "dew_point_depression": {"label": "Dew point margin", "unit": "K"},
    "wet_bulb": {"label": "Wet bulb", "unit": "°C"},
    "humidity_ratio": {"label": "Humidity ratio", "unit": "g/kg"},
    "enthalpy": {"label": "Enthalpy", "unit": "kJ/kg"},
    "absolute_humidity": {"label": "Absolute humidity", "unit": "g/m³"},
    "specific_volume": {"label": "Specific volume", "unit": "m³/kg"},
    "density": {"label": "Density", "unit": "kg/m³"},
    "degree_of_saturation": {"label": "Degree of saturation", "unit": "%"},
    "vapour_pressure": {"label": "Vapour pressure", "unit": "kPa"},
    "saturation_vapour_pressure": {"label": "Saturation pressure", "unit": "kPa"},
}

OPERATORS = (">", ">=", "<", "<=")

SEVERITIES = ("info", "warning", "critical")

SEVERITY_ORDER = {"ok": 0, "info": 1, "warning": 2, "critical": 3}

def metric_value(state: MoistAirState, metric: str) -> float | None:
    if metric == "temperature":
        return state.temperature
    if metric == "relative_humidity":
        return state.relative_humidity
    if metric == "vpd":
        return state.vpd_kpa
    if metric == "dew_point":
        return state.dew_point
    if metric == "dew_point_depression":
        return state.dew_point_depression
    if metric == "wet_bulb":
        return state.wet_bulb
    if metric == "humidity_ratio":
        return state.humidity_ratio_g_per_kg
    if metric == "enthalpy":
        return state.enthalpy
    if metric == "absolute_humidity":
        return state.absolute_humidity
    if metric == "specific_volume":
        return state.specific_volume
    if metric == "density":
        return state.density
    if metric == "degree_of_saturation":
        return state.degree_of_saturation
    if metric == "vapour_pressure":
        return state.vapour_pressure / 1000.0
    if metric == "saturation_vapour_pressure":
        return state.saturation_vapour_pressure / 1000.0
    return None

def resolve_threshold(
    condition: dict[str, Any], targets: dict[str, dict[str, float | None]]
) -> float | None:
    offset = float(condition.get("offset") or 0.0)
    target = condition.get("target")
    if target:
        parts = str(target).split(".")
        if len(parts) != 2:
            return None
        band = targets.get(parts[0])
        if not band:
            return None
        base = band.get(parts[1])
        if base is None:
            return None
        return float(base) + offset
    value = condition.get("value")
    if value is None:
        return None
    return float(value) + offset

def compare(actual: float, operator: str, threshold: float) -> bool:
    if operator == ">":
        return actual > threshold
    if operator == ">=":
        return actual >= threshold
    if operator == "<":
        return actual < threshold
    if operator == "<=":
        return actual <= threshold
    return False

@dataclass(frozen=True)
class ConditionResult:
    metric: str
    operator: str
    threshold: float
    actual: float

    def to_dict(self) -> dict[str, Any]:
        meta = METRICS.get(self.metric, {"label": self.metric, "unit": ""})
        return {
            "metric": self.metric,
            "label": meta["label"],
            "unit": meta["unit"],
            "operator": self.operator,
            "threshold": round(self.threshold, 4),
            "actual": round(self.actual, 4),
        }

@dataclass(frozen=True)
class Match:
    rule_id: int
    name: str
    severity: str
    recommendation: str
    priority: int
    conditions: tuple[ConditionResult, ...]
    equipment_missing: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "severity": self.severity,
            "recommendation": self.recommendation,
            "priority": self.priority,
            "conditions": [item.to_dict() for item in self.conditions],
            "equipment_missing": self.equipment_missing,
        }

@dataclass
class Assessment:
    status: str = "ok"
    headline: str = "Conditions are within target"
    matches: list[Match] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "headline": self.headline,
            "matches": [item.to_dict() for item in self.matches],
        }

def validate_conditions(conditions: Any) -> list[str]:
    problems: list[str] = []
    if not isinstance(conditions, list) or not conditions:
        return ["at least one condition is required"]
    for index, condition in enumerate(conditions, start=1):
        if not isinstance(condition, dict):
            problems.append(f"condition {index} is not an object")
            continue
        metric = condition.get("metric")
        if metric not in METRICS:
            problems.append(f"condition {index}: unknown metric {metric!r}")
        if condition.get("operator") not in OPERATORS:
            problems.append(
                f"condition {index}: operator must be one of {', '.join(OPERATORS)}"
            )
        has_value = condition.get("value") is not None
        target = condition.get("target")
        if not has_value and not target:
            problems.append(f"condition {index}: needs a value or a crop target")
        if target:
            parts = str(target).split(".")
            if len(parts) != 2 or parts[1] not in ("min", "max"):
                problems.append(
                    f"condition {index}: target must look like temperature.max"
                )
    return problems

def evaluate(
    state: MoistAirState,
    targets: dict[str, dict[str, float | None]],
    rules: Iterable[Any],
    equipment: Iterable[str] = (),
) -> Assessment:
    available = set(equipment or ())
    matches: list[Match] = []

    for rule in rules:
        if not getattr(rule, "enabled", True):
            continue
        conditions = getattr(rule, "conditions", None) or []
        if not conditions:
            continue
        results: list[ConditionResult] = []
        satisfied = True
        for condition in conditions:
            metric = condition.get("metric")
            actual = metric_value(state, metric) if metric else None
            threshold = resolve_threshold(condition, targets)
            operator = condition.get("operator")
            if actual is None or threshold is None or operator not in OPERATORS:
                satisfied = False
                break
            if not compare(actual, operator, threshold):
                satisfied = False
                break
            results.append(ConditionResult(metric, operator, threshold, actual))
        if not satisfied:
            continue
        required = getattr(rule, "requires_equipment", None)
        matches.append(
            Match(
                rule_id=getattr(rule, "id", 0),
                name=getattr(rule, "name", ""),
                severity=getattr(rule, "severity", "warning"),
                recommendation=getattr(rule, "recommendation", ""),
                priority=getattr(rule, "priority", 50),
                conditions=tuple(results),
                equipment_missing=(
                    required if required and required not in available else None
                ),
            )
        )

    matches.sort(key=lambda item: (item.priority, item.rule_id))

    if not matches:
        return Assessment()

    status = "ok"
    for item in matches:
        if SEVERITY_ORDER.get(item.severity, 0) > SEVERITY_ORDER.get(status, 0):
            status = item.severity

    leading = next(
        (item for item in matches if item.severity == status), matches[0]
    )
    return Assessment(status=status, headline=leading.name, matches=matches)
