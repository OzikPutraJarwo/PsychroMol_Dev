from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from conftest import LINKED, PROFILE

from psychromol import fetcher
from psychromol.db.models import Reading, Rule

START = datetime(2026, 9, 17, 0, 0, tzinfo=timezone.utc)

RULE = {
    "name": "Hot and humid",
    "conditions": {"temperature": "HIGH", "humidity": "HIGH", "vpd": "ANY"},
    "severity": "critical",
    "recommendation": "Ventilate.",
    "reference": "BC Ministry of Agriculture (2015), p. 3.",
    "priority": 10,
}


def create(client, **changes):
    response = client.post("/api/v1/profiles", json={**PROFILE, **changes})
    assert response.status_code == 201, response.text
    return response.json()


def add_readings(settings, profile_id, count, step_seconds=60):
    from psychromol.db.session import get_sessionmaker

    session = get_sessionmaker()()
    try:
        for index in range(count):
            session.add(
                Reading(
                    profile_id=profile_id,
                    measured_at=START + timedelta(seconds=index * step_seconds),
                    received_at=START + timedelta(seconds=index * step_seconds),
                    temperature_c=20.0 + index * 0.01,
                    relative_humidity_percent=70.0,
                )
            )
        session.commit()
    finally:
        session.close()


def test_health(client):
    assert client.get("/api/v1/health").json()["status"] == "ok"


def test_a_profile_round_trips(client):
    created = create(client, **LINKED, poll_interval_seconds=5)
    assert created["stage"] == "vegetative"
    assert created["pressure_mode"] == "standard"
    assert created["rules_seeded"] is False
    assert created["field_temperature"] == "/temperature"
    assert client.get(f"/api/v1/profiles/{created['id']}").json() == created
    assert [profile["id"] for profile in client.get("/api/v1/profiles").json()] == [created["id"]]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"temperature_min": 30}, "temperature minimum must be below"),
        ({"humidity_max": 50}, "humidity minimum must be below"),
        ({"temperature_reference": "   "}, "temperature_reference"),
        ({"vpd_min": 0.4}, "both a minimum and a maximum"),
        ({"vpd_min": 0.4, "vpd_max": 0.9}, "needs its reference"),
        ({"vpd_min": 0.9, "vpd_max": 0.4, "vpd_reference": "Trial"}, "VPD minimum must be below"),
        ({"pressure_mode": "fixed"}, "needs a value in kPa"),
        ({"pressure_mode": "fixed", "pressure_kpa": 101325}, "pressure_kpa"),
        ({"pressure_mode": "field"}, "needs its field"),
        ({"source_url": "https://example.test/a.json"}, "choose the temperature and humidity"),
        ({"source_url": "ftp://example.test/a.json"}, "http:// or https://"),
        ({**LINKED, "field_temperature": "temperature"}, "must start with /"),
        ({"stage": "seedling"}, "stage"),
        ({"humidity_max": 120}, "humidity_max"),
        ({"surprise": 1}, "surprise"),
    ],
)
def test_an_invalid_profile_is_refused_with_the_reason(client, changes, message):
    response = client.post("/api/v1/profiles", json={**PROFILE, **changes})
    assert response.status_code == 422
    assert message in response.text


def test_a_custom_vpd_band_keeps_its_reference_and_removing_it_clears_the_reference(client):
    created = create(client, vpd_min=0.4, vpd_max=0.9, vpd_reference="Own trial")
    assert (created["vpd_min"], created["vpd_max"], created["vpd_reference"]) == (0.4, 0.9, "Own trial")
    updated = client.put(
        f"/api/v1/profiles/{created['id']}", json={**PROFILE, "vpd_reference": "Own trial"}
    ).json()
    assert (updated["vpd_min"], updated["vpd_max"], updated["vpd_reference"]) == (None, None, None)


def test_changing_the_source_clears_the_last_poll(client, profile, session):
    profile.last_polled_at = START
    profile.last_poll_error = "temperature: nothing at /temperature"
    session.commit()
    body = {**PROFILE, **LINKED, "field_temperature": "/air/t"}
    updated = client.put(f"/api/v1/profiles/{profile.id}", json=body).json()
    assert updated["last_polled_at"] is None and updated["last_poll_error"] is None

    renamed = client.put(f"/api/v1/profiles/{profile.id}", json={**body, "name": "Renamed"}).json()
    assert renamed["name"] == "Renamed"


def test_deleting_a_profile_deletes_its_readings_and_rules(client, settings):
    created = create(client)
    add_readings(settings, created["id"], 3)
    client.put(f"/api/v1/profiles/{created['id']}/rules", json=[RULE])
    assert client.delete(f"/api/v1/profiles/{created['id']}").status_code == 204
    assert client.get(f"/api/v1/profiles/{created['id']}").status_code == 404

    from psychromol.db.session import get_sessionmaker

    session = get_sessionmaker()()
    try:
        assert session.query(Reading).count() == 0
        assert session.query(Rule).count() == 0
    finally:
        session.close()


def test_readings_are_paged_newest_first_with_a_total(client, settings):
    created = create(client)
    add_readings(settings, created["id"], 25)
    url = f"/api/v1/profiles/{created['id']}/readings"
    page = client.get(url, params={"limit": 10, "offset": 10}).json()
    assert page["total"] == 25
    assert [row["measured_at"] for row in page["items"]][0] == "2026-09-17T00:14:00.000Z"
    assert len(page["items"]) == 10

    oldest = client.get(url, params={"limit": 2, "order": "asc"}).json()["items"]
    assert oldest[0]["measured_at"] == "2026-09-17T00:00:00.000Z"
    assert set(oldest[0]) == {"id", "measured_at", "received_at", "temperature_c", "relative_humidity_percent", "pressure_kpa"}


def test_readings_filter_by_time_and_a_naive_time_is_utc(client, settings):
    created = create(client)
    add_readings(settings, created["id"], 25)
    url = f"/api/v1/profiles/{created['id']}/readings"
    found = client.get(url, params={"start": "2026-09-17T00:05:00", "end": "2026-09-17T07:09:00+07:00"}).json()
    assert found["total"] == 5
    assert [row["measured_at"][11:16] for row in found["items"]] == ["00:09", "00:08", "00:07", "00:06", "00:05"]


def test_a_long_range_is_thinned_to_real_readings_including_the_first_and_last(client, settings):
    created = create(client)
    add_readings(settings, created["id"], 1001)
    body = client.get(f"/api/v1/profiles/{created['id']}/readings", params={"max_points": 100}).json()
    items = body["items"]
    assert body["total"] == 1001
    assert len(items) <= 101
    assert items[0]["measured_at"] == "2026-09-17T00:00:00.000Z"
    assert items[-1]["measured_at"] == (START + timedelta(minutes=1000)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    times = [item["measured_at"] for item in items]
    assert times == sorted(times)

    small = client.get(f"/api/v1/profiles/{created['id']}/readings", params={"max_points": 5000}).json()
    assert len(small["items"]) == 1001


def test_the_latest_reading(client, settings):
    created = create(client)
    url = f"/api/v1/profiles/{created['id']}/readings/latest"
    assert client.get(url).json() is None
    add_readings(settings, created["id"], 3)
    assert client.get(url).json()["measured_at"] == "2026-09-17T00:02:00.000Z"


def test_refresh_fetches_and_stores_through_the_profiles_mapping(client, monkeypatch):
    created = create(client, **LINKED)
    document = {"timestamp": "2026-09-17T09:10:04Z", "temperature": 27.0, "humidity": 44.6}
    monkeypatch.setattr(fetcher, "fetch_json", lambda url: document)
    url = f"/api/v1/profiles/{created['id']}/refresh"
    first = client.post(url).json()
    assert first["stored"] is True and first["error"] is None
    assert first["latest"]["temperature_c"] == 27.0
    assert first["profile"]["last_polled_at"] is not None

    second = client.post(url).json()
    assert second["stored"] is False and second["latest"]["id"] == first["latest"]["id"]


def test_rules_belong_to_one_profile(client):
    one = create(client)
    two = create(client, name="Second house")
    replaced = client.put(f"/api/v1/profiles/{one['id']}/rules", json=[RULE, {**RULE, "name": "Other", "priority": 5}])
    assert replaced.status_code == 200
    assert [rule["name"] for rule in replaced.json()] == ["Other", "Hot and humid"]
    assert client.get(f"/api/v1/profiles/{one['id']}").json()["rules_seeded"] is True
    assert client.get(f"/api/v1/profiles/{two['id']}/rules").json() == []

    added = client.post(f"/api/v1/profiles/{two['id']}/rules", json=RULE).json()
    assert added["conditions"] == RULE["conditions"] and added["profile_id"] == two["id"]
    changed = client.put(f"/api/v1/rules/{added['id']}", json={**RULE, "enabled": False, "conditions": {"vpd": "LOW"}}).json()
    assert changed["enabled"] is False
    assert changed["conditions"] == {"temperature": "ANY", "humidity": "ANY", "vpd": "LOW"}
    assert client.delete(f"/api/v1/rules/{added['id']}").status_code == 204
    assert client.delete(f"/api/v1/rules/{added['id']}").status_code == 404
    assert client.get(f"/api/v1/profiles/{two['id']}").json()["rules_seeded"] is False


@pytest.mark.parametrize(
    "changes",
    [
        {"reference": ""},
        {"severity": "urgent"},
        {"conditions": {"temperature": "WARM"}},
        {"priority": "first"},
    ],
)
def test_an_invalid_rule_is_refused(client, changes):
    created = create(client)
    response = client.post(f"/api/v1/profiles/{created['id']}/rules", json={**RULE, **changes})
    assert response.status_code == 422


def test_an_unknown_profile_is_404(client):
    for method, url in (
        ("get", "/api/v1/profiles/99"),
        ("get", "/api/v1/profiles/99/readings"),
        ("get", "/api/v1/profiles/99/rules"),
        ("post", "/api/v1/profiles/99/refresh"),
        ("delete", "/api/v1/profiles/99"),
    ):
        assert getattr(client, method)(url).status_code == 404, url


def test_the_source_proxy_returns_the_document_or_the_reason(client, monkeypatch):
    monkeypatch.setattr(fetcher, "fetch_json", lambda url: {"temperature": 21})
    assert client.get("/api/v1/sources/fetch", params={"url": "https://example.test/a.json"}).json() == {
        "ok": True, "document": {"temperature": 21}, "error": None,
    }

    def broken(url):
        raise fetcher.SourceError("the source returned HTTP 500")

    monkeypatch.setattr(fetcher, "fetch_json", broken)
    body = client.get("/api/v1/sources/fetch", params={"url": "https://example.test/a.json"}).json()
    assert body == {"ok": False, "document": None, "error": "the source returned HTTP 500"}


def test_the_frontend_is_served_at_the_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "PsychroMol" in response.text
