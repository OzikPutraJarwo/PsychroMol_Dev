from __future__ import annotations

import json

import pytest

from psychromol.defaults import SAMPLE_CROP, SAMPLE_FACILITY
from psychromol.rules import EQUIPMENT, METRICS

CROP = {
    "name": "Tomato",
    "temperature_min": 18.0,
    "temperature_max": 28.0,
    "humidity_min": 60.0,
    "humidity_max": 80.0,
    "extra_targets": [{"metric": "vpd", "min": 0.5, "max": 1.2}],
}
FACILITY = {"name": "House 1", "altitude_m": 30.0, "equipment": ["roof_vent", "heater"]}

def make_profile(client, crop=None, facility=None, **extra):
    crop_id = client.post("/api/v1/crops", json=crop or CROP).json()["id"]
    facility_id = client.post("/api/v1/facilities", json=facility or FACILITY).json()["id"]
    body = {"name": "Tomato House", "crop_id": crop_id, "facility_id": facility_id, **extra}
    return client.post("/api/v1/profiles", json=body).json()

def add_readings(client, profile_id, rows):
    return client.post(
        f"/api/v1/profiles/{profile_id}/paste",
        json={"text": json.dumps(rows), "filename": "x.json"},
    )

def test_health_answers(client):
    assert client.get("/api/v1/health").json()["status"] == "ok"

def test_meta_offers_the_whole_vocabulary(client):
    meta = client.get("/api/v1/meta").json()
    assert {item["id"] for item in meta["metrics"]} == set(METRICS)
    assert {item["id"] for item in meta["equipment"]} == set(EQUIPMENT)
    assert meta["operators"] == [">", ">=", "<", "<="]
    assert meta["severities"] == ["info", "warning", "critical"]


def test_meta_offers_the_displayable_fields_and_their_default(client):
    from psychromol.api.routers.data import FIELDS

    meta = client.get("/api/v1/meta").json()
    assert {item["id"] for item in meta["fields"]} == set(FIELDS)
    assert all(item["label"] and item["unit"] is not None for item in meta["fields"])
    assert meta["default_display_fields"] == ["temperature", "relative_humidity"]

def test_the_rule_catalogue_is_seeded_on_first_start(client):
    rules = client.get("/api/v1/rules").json()
    assert len(rules) == 11
    assert rules[0]["priority"] <= rules[-1]["priority"]

def test_a_crop_round_trips(client):
    created = client.post("/api/v1/crops", json=CROP).json()
    assert created["targets"]["temperature"] == {"min": 18.0, "max": 28.0}
    assert created["targets"]["vpd"] == {"min": 0.5, "max": 1.2}

    updated = client.put(
        f"/api/v1/crops/{created['id']}", json={**CROP, "name": "Cherry tomato"}
    ).json()
    assert updated["name"] == "Cherry tomato"
    assert [crop["name"] for crop in client.get("/api/v1/crops").json()] == ["Cherry tomato"]

@pytest.mark.parametrize(
    "field, value",
    [("temperature_max", 10.0), ("humidity_max", 10.0), ("humidity_min", 150.0)],
)
def test_an_impossible_crop_band_is_refused(client, field, value):
    response = client.post("/api/v1/crops", json={**CROP, field: value})
    assert response.status_code == 422

def test_a_facility_keeps_only_known_equipment(client):
    response = client.post(
        "/api/v1/facilities", json={**FACILITY, "equipment": ["roof_vent", "teleporter"]}
    )
    assert response.status_code == 422
    assert "teleporter" in response.json()["detail"]

def test_equipment_comes_back_in_a_stable_order(client):
    created = client.post(
        "/api/v1/facilities", json={**FACILITY, "equipment": ["heater", "fan", "roof_vent"]}
    ).json()
    assert created["equipment"] == ["fan", "roof_vent", "heater"]

def test_a_crop_still_in_use_cannot_be_deleted(client):
    profile = make_profile(client)
    response = client.delete(f"/api/v1/crops/{profile['crop_id']}")
    assert response.status_code == 409
    assert "profile" in response.json()["detail"]

def test_a_facility_still_in_use_cannot_be_deleted(client):
    profile = make_profile(client)
    assert client.delete(f"/api/v1/facilities/{profile['facility_id']}").status_code == 409

def test_a_profile_needs_a_crop_and_a_facility_that_exist(client):
    response = client.post(
        "/api/v1/profiles", json={"name": "X", "crop_id": 99, "facility_id": 99}
    )
    assert response.status_code == 422

def test_the_first_profile_becomes_the_default(client):
    first = make_profile(client)
    assert first["is_default"] is True

def test_a_profile_defaults_to_a_60_second_poll_interval(client):
    profile = make_profile(client)
    assert profile["poll_interval_seconds"] == 60

def test_a_profiles_poll_interval_round_trips(client):
    profile = make_profile(client, poll_interval_seconds=5)
    assert profile["poll_interval_seconds"] == 5
    updated = client.put(
        f"/api/v1/profiles/{profile['id']}",
        json={
            "name": profile["name"],
            "crop_id": profile["crop_id"],
            "facility_id": profile["facility_id"],
            "poll_interval_seconds": 1,
        },
    ).json()
    assert updated["poll_interval_seconds"] == 1

@pytest.mark.parametrize("value", [0, -5, 3601])
def test_an_out_of_range_poll_interval_is_refused(client, value):
    existing = make_profile(client)
    response = client.post(
        "/api/v1/profiles",
        json={
            "name": "X",
            "crop_id": existing["crop_id"],
            "facility_id": existing["facility_id"],
            "poll_interval_seconds": value,
        },
    )
    assert response.status_code == 422

def test_only_one_profile_is_default(client):
    first = make_profile(client)
    second = client.post(
        "/api/v1/profiles",
        json={
            "name": "Second",
            "crop_id": first["crop_id"],
            "facility_id": first["facility_id"],
            "is_default": True,
        },
    ).json()
    profiles = {entry["id"]: entry for entry in client.get("/api/v1/profiles").json()}
    assert profiles[second["id"]]["is_default"] is True
    assert profiles[first["id"]]["is_default"] is False

def test_deleting_a_profile_takes_its_readings_with_it(client):
    profile = make_profile(client)
    add_readings(client, profile["id"], [
        {"timestamp": "2026-09-14T03:00:00Z", "temperature": 24, "humidity": 70}
    ])
    assert client.delete(f"/api/v1/profiles/{profile['id']}").status_code == 204
    assert client.get(f"/api/v1/profiles/{profile['id']}/current").status_code == 404


def test_deleting_a_profile_also_removes_its_own_crop_and_facility(client):
    profile = make_profile(client)
    assert client.delete(f"/api/v1/profiles/{profile['id']}").status_code == 204
    assert client.get("/api/v1/crops").json() == []
    assert client.get("/api/v1/facilities").json() == []


def test_deleting_a_profile_keeps_a_crop_or_facility_still_used_elsewhere(client):
    first = make_profile(client)
    second = client.post(
        "/api/v1/profiles",
        json={
            "name": "Second",
            "crop_id": first["crop_id"],
            "facility_id": first["facility_id"],
        },
    ).json()
    client.delete(f"/api/v1/profiles/{first['id']}")
    assert any(c["id"] == second["crop_id"] for c in client.get("/api/v1/crops").json())
    assert any(f["id"] == second["facility_id"] for f in client.get("/api/v1/facilities").json())

def test_a_data_link_must_be_http(client):
    profile = make_profile(client)
    response = client.put(
        f"/api/v1/profiles/{profile['id']}",
        json={
            "name": profile["name"],
            "crop_id": profile["crop_id"],
            "facility_id": profile["facility_id"],
            "source_url": "file:///etc/passwd",
        },
    )
    assert response.status_code == 422

def test_current_reports_the_air_and_the_advice(client):
    profile = make_profile(client)
    add_readings(client, profile["id"], [
        {"timestamp": "2026-09-14T03:00:00Z", "temperature": 34, "humidity": 88}
    ])
    payload = client.get(f"/api/v1/profiles/{profile['id']}/current").json()

    assert payload["temperature_c"] == pytest.approx(34.0)
    assert payload["assessment"]["status"] == "critical"
    assert payload["assessment"]["headline"] == "Hot and humid"
    assert payload["profile"]["crop"]["name"] == "Tomato"
    first = payload["assessment"]["matches"][0]
    assert first["conditions"][0]["actual"] == pytest.approx(34.0)
    assert first["recommendation"]

def test_current_says_so_when_nothing_has_arrived(client):
    profile = make_profile(client)
    assert client.get(f"/api/v1/profiles/{profile['id']}/current").status_code == 404

def test_advice_marks_equipment_the_facility_lacks(client):
    profile = make_profile(
        client, facility={"name": "Bare", "altitude_m": 0, "equipment": []}
    )
    add_readings(client, profile["id"], [
        {"timestamp": "2026-09-14T03:00:00Z", "temperature": 34, "humidity": 88}
    ])
    matches = client.get(
        f"/api/v1/profiles/{profile['id']}/current"
    ).json()["assessment"]["matches"]
    assert all(match["equipment_missing"] for match in matches)

@pytest.mark.parametrize("kind", ["psychrometric", "mollier"])
def test_the_chart_covers_the_full_default_range(client, kind):
    profile = make_profile(client)
    chart = client.get(f"/api/v1/profiles/{profile['id']}/chart?kind={kind}").json()
    assert chart["curves"]
    if kind == "psychrometric":
        assert chart["x_axis"]["min"] == -20.0
        assert chart["x_axis"]["max"] == 50.0
        assert chart["y_axis"]["min"] == 0.0
        assert chart["y_axis"]["max"] == 50.0

@pytest.mark.parametrize("kind", ["psychrometric", "mollier"])
def test_the_chart_shades_the_crops_target_zone(client, kind):
    profile = make_profile(client)
    chart = client.get(f"/api/v1/profiles/{profile['id']}/chart?kind={kind}").json()
    zones = [curve for curve in chart["curves"] if curve["family"] == "target_zone"]
    assert len(zones) == 1
    points = zones[0]["points"]
    assert points[0] == points[-1]
    assert len(points) > 4


def test_a_narrower_crop_target_gives_a_smaller_zone(client):
    narrow = make_profile(client, crop={**CROP, "name": "Narrow", "temperature_min": 20.0, "temperature_max": 22.0})
    wide = make_profile(client, crop={**CROP, "name": "Wide", "temperature_min": 5.0, "temperature_max": 45.0},
                         facility=FACILITY)
    narrow_zone = next(
        c for c in client.get(f"/api/v1/profiles/{narrow['id']}/chart").json()["curves"]
        if c["family"] == "target_zone"
    )
    wide_zone = next(
        c for c in client.get(f"/api/v1/profiles/{wide['id']}/chart").json()["curves"]
        if c["family"] == "target_zone"
    )
    narrow_ts = [p[0] for p in narrow_zone["points"]]
    wide_ts = [p[0] for p in wide_zone["points"]]
    assert max(narrow_ts) - min(narrow_ts) < max(wide_ts) - min(wide_ts)


def test_an_unknown_chart_kind_is_refused(client):
    profile = make_profile(client)
    assert client.get(
        f"/api/v1/profiles/{profile['id']}/chart?kind=pie"
    ).status_code == 422

def test_the_chart_follows_the_facility_altitude(client):
    sea = make_profile(client)
    high = make_profile(
        client,
        crop={**CROP, "name": "Other"},
        facility={"name": "Hill", "altitude_m": 1500.0, "equipment": []},
    )
    a = client.get(f"/api/v1/profiles/{sea['id']}/chart").json()["pressure_kpa"]
    b = client.get(f"/api/v1/profiles/{high['id']}/chart").json()["pressure_kpa"]
    assert b < a - 10

def test_readings_default_to_the_last_day(client):
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    profile = make_profile(client)
    add_readings(client, profile["id"], [
        {"timestamp": (now - timedelta(hours=1)).isoformat(), "temperature": 24, "humidity": 70},
        {"timestamp": (now - timedelta(days=3)).isoformat(), "temperature": 20, "humidity": 60},
    ])
    payload = client.get(f"/api/v1/profiles/{profile['id']}/readings").json()
    assert payload["count"] == 1

    wider = client.get(f"/api/v1/profiles/{profile['id']}/readings?hours=168").json()
    assert wider["count"] == 2

def test_readings_can_be_narrowed_to_chosen_fields(client):
    from datetime import datetime, timezone

    profile = make_profile(client)
    add_readings(client, profile["id"], [
        {"timestamp": datetime.now(timezone.utc).isoformat(), "temperature": 24, "humidity": 70}
    ])
    payload = client.get(
        f"/api/v1/profiles/{profile['id']}/readings?fields=temperature&fields=vpd"
    ).json()
    assert [field["id"] for field in payload["fields"]] == ["temperature", "vpd"]
    assert set(payload["readings"][0]) == {"measured_at", "temperature_c", "vpd_kpa"}

@pytest.mark.parametrize("fmt, media", [("csv", "text/csv"), ("json", "application/json")])
def test_export_returns_a_file(client, fmt, media):
    from datetime import datetime, timezone

    profile = make_profile(client)
    add_readings(client, profile["id"], [
        {"timestamp": datetime.now(timezone.utc).isoformat(), "temperature": 24, "humidity": 70}
    ])
    response = client.get(f"/api/v1/profiles/{profile['id']}/export?format={fmt}")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(media)
    assert "attachment" in response.headers["content-disposition"]
    assert "·" not in response.headers["content-disposition"]

def test_an_unknown_export_format_is_refused(client):
    profile = make_profile(client)
    assert client.get(
        f"/api/v1/profiles/{profile['id']}/export?format=pdf"
    ).status_code == 422

def test_a_csv_upload_is_accepted(client):
    profile = make_profile(client)
    response = client.post(
        f"/api/v1/profiles/{profile['id']}/upload",
        files={"file": ("readings.csv", "time,temp,rh\n2026-09-14 03:00,24,70\n", "text/csv")},
    )
    assert response.json()["stored"] == 1

def test_an_unreadable_upload_says_why(client):
    profile = make_profile(client)
    response = client.post(
        f"/api/v1/profiles/{profile['id']}/upload",
        files={"file": ("notes.txt", "hello there", "text/plain")},
    )
    assert response.status_code == 422
    assert response.json()["detail"]

def test_a_rule_round_trips(client):
    body = {
        "name": "Hot and humid",
        "conditions": [
            {"metric": "temperature", "operator": ">", "target": "temperature.max"},
            {"metric": "relative_humidity", "operator": ">", "value": 85},
        ],
        "severity": "critical",
        "recommendation": "Ventilate first.",
        "requires_equipment": "roof_vent",
        "priority": 5,
    }
    created = client.post("/api/v1/rules", json=body).json()
    assert len(created["conditions"]) == 2
    assert created["conditions"][0]["target"] == "temperature.max"
    assert "value" not in created["conditions"][0]

    updated = client.put(
        f"/api/v1/rules/{created['id']}", json={**body, "enabled": False}
    ).json()
    assert updated["enabled"] is False
    assert client.delete(f"/api/v1/rules/{created['id']}").status_code == 204

@pytest.mark.parametrize(
    "broken",
    [
        {"conditions": [{"metric": "colour", "operator": ">", "value": 1}]},
        {"conditions": [{"metric": "temperature", "operator": "~", "value": 1}]},
        {"conditions": [{"metric": "temperature", "operator": ">"}]},
        {"severity": "disastrous"},
        {"requires_equipment": "teleporter"},
    ],
)
def test_a_broken_rule_is_refused_with_a_reason(client, broken):
    body = {
        "name": "Test",
        "conditions": [{"metric": "temperature", "operator": ">", "value": 30}],
        "severity": "warning",
        "recommendation": "x",
        **broken,
    }
    response = client.post("/api/v1/rules", json=body)
    assert response.status_code == 422
    assert response.json()["detail"]

def test_a_rule_needs_at_least_one_condition(client):
    response = client.post(
        "/api/v1/rules", json={"name": "Empty", "conditions": [], "severity": "warning"}
    )
    assert response.status_code == 422

def test_rules_can_be_restored_to_the_defaults(client):
    for rule in client.get("/api/v1/rules").json():
        client.delete(f"/api/v1/rules/{rule['id']}")
    assert client.get("/api/v1/rules").json() == []

    restored = client.post("/api/v1/rules/reset").json()
    assert len(restored) == 11
    assert len(client.get("/api/v1/rules").json()) == 11

def test_editing_a_rule_changes_the_advice_immediately(client):
    profile = make_profile(client)
    add_readings(client, profile["id"], [
        {"timestamp": "2026-09-14T03:00:00Z", "temperature": 24, "humidity": 70}
    ])
    before = client.get(f"/api/v1/profiles/{profile['id']}/current").json()
    assert before["assessment"]["status"] == "ok"

    client.post("/api/v1/rules", json={
        "name": "Anything above freezing",
        "conditions": [{"metric": "temperature", "operator": ">", "value": 0}],
        "severity": "info",
        "recommendation": "Just checking.",
        "priority": 1,
    })
    after = client.get(f"/api/v1/profiles/{profile['id']}/current").json()
    assert after["assessment"]["status"] == "info"
    assert after["assessment"]["headline"] == "Anything above freezing"

def test_editing_the_crop_changes_the_advice_immediately(client):
    profile = make_profile(client)
    add_readings(client, profile["id"], [
        {"timestamp": "2026-09-14T03:00:00Z", "temperature": 26, "humidity": 70}
    ])
    assert client.get(
        f"/api/v1/profiles/{profile['id']}/current"
    ).json()["assessment"]["status"] == "ok"

    client.put(f"/api/v1/crops/{profile['crop_id']}", json={**CROP, "temperature_max": 24.0})
    after = client.get(f"/api/v1/profiles/{profile['id']}/current").json()
    assert after["assessment"]["status"] != "ok"

def test_the_sample_crop_and_facility_are_valid_input(client):
    crop = client.post("/api/v1/crops", json=SAMPLE_CROP)
    facility = client.post("/api/v1/facilities", json=SAMPLE_FACILITY)
    assert crop.status_code == 201
    assert facility.status_code == 201
