from __future__ import annotations

from typing import Any

DEFAULT_RULES: list[dict[str, Any]] = [
    {
        "name": "Condensation forming",
        "conditions": [
            {"metric": "dew_point_depression", "operator": "<", "value": 1.0}
        ],
        "severity": "critical",
        "recommendation": "Water is forming on leaves and glass. Add a little heat and move the air.",
        "requires_equipment": "heater",
        "priority": 10,
    },
    {
        "name": "Hot and humid",
        "conditions": [
            {"metric": "temperature", "operator": ">", "target": "temperature.max"},
            {
                "metric": "relative_humidity",
                "operator": ">",
                "target": "relative_humidity.max",
            },
        ],
        "severity": "critical",
        "recommendation": "Ventilate first, then cool. Cooling alone makes the damp worse.",
        "requires_equipment": "roof_vent",
        "priority": 12,
    },
    {
        "name": "Cold and damp",
        "conditions": [
            {"metric": "temperature", "operator": "<", "target": "temperature.min"},
            {
                "metric": "relative_humidity",
                "operator": ">",
                "target": "relative_humidity.max",
            },
        ],
        "severity": "critical",
        "recommendation": "Heat and ventilate together. Heating alone will not remove the moisture.",
        "requires_equipment": "heater",
        "priority": 14,
    },
    {
        "name": "Much too hot",
        "conditions": [
            {
                "metric": "temperature",
                "operator": ">",
                "target": "temperature.max",
                "offset": 5,
            }
        ],
        "severity": "critical",
        "recommendation": "Open the vents fully and pull the shade screen.",
        "requires_equipment": "roof_vent",
        "priority": 20,
    },
    {
        "name": "Much too cold",
        "conditions": [
            {
                "metric": "temperature",
                "operator": "<",
                "target": "temperature.min",
                "offset": -5,
            }
        ],
        "severity": "critical",
        "recommendation": "Add heat now and close the thermal screen.",
        "requires_equipment": "heater",
        "priority": 22,
    },
    {
        "name": "Too hot",
        "conditions": [
            {"metric": "temperature", "operator": ">", "target": "temperature.max"}
        ],
        "severity": "warning",
        "recommendation": "Increase ventilation, or close the shade screen if the sun is strong.",
        "requires_equipment": "roof_vent",
        "priority": 40,
    },
    {
        "name": "Too cold",
        "conditions": [
            {"metric": "temperature", "operator": "<", "target": "temperature.min"}
        ],
        "severity": "warning",
        "recommendation": "Add heat, or close the thermal screen to hold what you have.",
        "requires_equipment": "heater",
        "priority": 42,
    },
    {
        "name": "Too humid",
        "conditions": [
            {
                "metric": "relative_humidity",
                "operator": ">",
                "target": "relative_humidity.max",
            }
        ],
        "severity": "warning",
        "recommendation": "Ventilate and add a little heat. Warm air carries the moisture out.",
        "requires_equipment": "side_window",
        "priority": 44,
    },
    {
        "name": "Too dry",
        "conditions": [
            {
                "metric": "relative_humidity",
                "operator": "<",
                "target": "relative_humidity.min",
            }
        ],
        "severity": "warning",
        "recommendation": "Fog, or damp the floor and paths.",
        "requires_equipment": "fogging",
        "priority": 46,
    },
    {
        "name": "Air drying the crop too fast",
        "conditions": [{"metric": "vpd", "operator": ">", "value": 1.5}],
        "severity": "warning",
        "recommendation": "The air pulls water faster than the roots replace it. Raise humidity or shade.",
        "requires_equipment": "shade_screen",
        "priority": 50,
    },
    {
        "name": "Air barely drying the crop",
        "conditions": [{"metric": "vpd", "operator": "<", "value": 0.4}],
        "severity": "warning",
        "recommendation": "The crop takes up little water. Move the air and ventilate gently.",
        "requires_equipment": "fan",
        "priority": 52,
    },
]

SAMPLE_CROP: dict[str, Any] = {
    "name": "Tomato",
    "temperature_min": 18.0,
    "temperature_max": 28.0,
    "humidity_min": 60.0,
    "humidity_max": 80.0,
    "extra_targets": [{"metric": "vpd", "min": 0.5, "max": 1.2}],
}

SAMPLE_FACILITY: dict[str, Any] = {
    "name": "House 1",
    "altitude_m": 30.0,
    "equipment": [
        "fan",
        "roof_vent",
        "side_window",
        "heater",
        "fogging",
        "shade_screen",
        "thermal_screen",
        "irrigation",
    ],
}
