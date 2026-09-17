from __future__ import annotations

import pytest

from psychromol.core.state import from_temperature_relative_humidity
from psychromol.defaults import DEFAULT_RULES
from psychromol.rules import (
    EQUIPMENT,
    METRICS,
    evaluate,
    metric_value,
    resolve_threshold,
    validate_conditions,
)

TARGETS = {
    "temperature": {"min": 18.0, "max": 28.0},
    "relative_humidity": {"min": 60.0, "max": 80.0},
    "vpd": {"min": 0.5, "max": 1.2},
}

class FakeRule:
    def __init__(self, **fields):
        self.id = fields.get("id", 1)
        self.name = fields.get("name", "Rule")
        self.conditions = fields.get("conditions", [])
        self.severity = fields.get("severity", "warning")
        self.recommendation = fields.get("recommendation", "")
        self.requires_equipment = fields.get("requires_equipment")
        self.priority = fields.get("priority", 50)
        self.enabled = fields.get("enabled", True)

def state(temperature=24.0, humidity=70.0):
    return from_temperature_relative_humidity(temperature, humidity, 101325.0)

@pytest.mark.parametrize("metric", list(METRICS))
def test_every_offered_metric_can_be_read(metric):
    assert isinstance(metric_value(state(), metric), float)

def test_an_unknown_metric_reads_as_nothing():
    assert metric_value(state(), "colour") is None

def test_all_conditions_must_hold():
    rule = FakeRule(
        conditions=[
            {"metric": "temperature", "operator": ">", "value": 30},
            {"metric": "relative_humidity", "operator": ">", "value": 80},
        ]
    )
    assert not evaluate(state(32, 70), TARGETS, [rule]).matches
    assert evaluate(state(32, 85), TARGETS, [rule]).matches

def test_a_condition_can_point_at_a_crop_target():
    rule = FakeRule(
        conditions=[{"metric": "temperature", "operator": ">", "target": "temperature.max"}]
    )
    assert not evaluate(state(27), TARGETS, [rule]).matches
    assert evaluate(state(29), TARGETS, [rule]).matches

def test_an_offset_shifts_the_target():
    condition = {
        "metric": "temperature",
        "operator": ">",
        "target": "temperature.max",
        "offset": 5,
    }
    assert resolve_threshold(condition, TARGETS) == 33.0

def test_changing_the_crop_changes_what_fires():
    rule = FakeRule(
        conditions=[{"metric": "temperature", "operator": ">", "target": "temperature.max"}]
    )
    cool = {"temperature": {"min": 10.0, "max": 20.0}}
    warm = {"temperature": {"min": 20.0, "max": 32.0}}
    assert evaluate(state(25), cool, [rule]).matches
    assert not evaluate(state(25), warm, [rule]).matches

def test_a_target_the_crop_does_not_define_cannot_fire():
    rule = FakeRule(conditions=[{"metric": "vpd", "operator": ">", "target": "vpd.max"}])
    assert not evaluate(state(24, 70), {"temperature": {"min": 1, "max": 2}}, [rule]).matches

def test_disabled_rules_are_skipped():
    rule = FakeRule(
        conditions=[{"metric": "temperature", "operator": ">", "value": 1}], enabled=False
    )
    assert not evaluate(state(), TARGETS, [rule]).matches

def test_a_rule_with_no_conditions_never_fires():
    assert not evaluate(state(), TARGETS, [FakeRule(conditions=[])]).matches

def test_the_worst_severity_sets_the_status():
    rules = [
        FakeRule(id=1, name="Warn", severity="warning", priority=40,
                 conditions=[{"metric": "temperature", "operator": ">", "value": 1}]),
        FakeRule(id=2, name="Critical", severity="critical", priority=10,
                 conditions=[{"metric": "temperature", "operator": ">", "value": 2}]),
    ]
    assessment = evaluate(state(), TARGETS, rules)
    assert assessment.status == "critical"
    assert assessment.headline == "Critical"

def test_matches_are_ordered_by_priority():
    rules = [
        FakeRule(id=1, name="Late", priority=90,
                 conditions=[{"metric": "temperature", "operator": ">", "value": 1}]),
        FakeRule(id=2, name="Early", priority=10,
                 conditions=[{"metric": "temperature", "operator": ">", "value": 1}]),
    ]
    names = [match.name for match in evaluate(state(), TARGETS, rules).matches]
    assert names == ["Early", "Late"]

def test_nothing_matching_is_reported_as_ok():
    rule = FakeRule(conditions=[{"metric": "temperature", "operator": ">", "value": 99}])
    assessment = evaluate(state(), TARGETS, [rule])
    assert assessment.status == "ok"
    assert assessment.matches == []

def test_advice_is_still_given_when_the_equipment_is_missing():
    rule = FakeRule(
        conditions=[{"metric": "temperature", "operator": ">", "value": 1}],
        requires_equipment="roof_vent",
    )
    match = evaluate(state(), TARGETS, [rule], equipment=[]).matches[0]
    assert match.equipment_missing == "roof_vent"

    match = evaluate(state(), TARGETS, [rule], equipment=["roof_vent"]).matches[0]
    assert match.equipment_missing is None

def test_a_match_names_the_values_that_triggered_it():
    rule = FakeRule(conditions=[{"metric": "temperature", "operator": ">", "value": 20}])
    condition = evaluate(state(24.0), TARGETS, [rule]).matches[0].conditions[0]
    assert condition.actual == pytest.approx(24.0)
    assert condition.threshold == 20.0
    assert condition.to_dict()["unit"] == "°C"

@pytest.mark.parametrize(
    "conditions, problem",
    [
        ([], "at least one condition"),
        ([{"metric": "colour", "operator": ">", "value": 1}], "unknown metric"),
        ([{"metric": "temperature", "operator": "~", "value": 1}], "operator must be"),
        ([{"metric": "temperature", "operator": ">"}], "needs a value"),
        ([{"metric": "temperature", "operator": ">", "target": "temperature"}], "target must look like"),
    ],
)
def test_broken_rules_are_rejected_with_a_reason(conditions, problem):
    assert any(problem in message for message in validate_conditions(conditions))

def test_a_good_rule_passes_validation():
    assert validate_conditions(
        [{"metric": "temperature", "operator": ">", "target": "temperature.max"}]
    ) == []

def test_the_default_rules_are_all_valid():
    for rule in DEFAULT_RULES:
        assert validate_conditions(rule["conditions"]) == []
        assert rule["severity"] in ("info", "warning", "critical")
        assert rule["requires_equipment"] in EQUIPMENT
        assert rule["recommendation"]

def test_the_default_rules_have_distinct_priorities():
    priorities = [rule["priority"] for rule in DEFAULT_RULES]
    assert len(priorities) == len(set(priorities))

def test_hot_and_humid_outranks_too_hot():
    rules = [FakeRule(id=index, **entry) for index, entry in enumerate(DEFAULT_RULES)]
    assessment = evaluate(state(34.0, 88.0), TARGETS, rules)
    assert assessment.headline == "Hot and humid"
    assert assessment.status == "critical"
    names = [match.name for match in assessment.matches]
    assert names.index("Hot and humid") < names.index("Too hot")
