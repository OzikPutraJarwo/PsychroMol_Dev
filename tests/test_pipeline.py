from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from psychromol.core import psychrometrics as psy
from psychromol.db.models import Reading
from psychromol.ingest import Sample
from psychromol.pipeline import SourceError, pressure_for, state_from_reading

NOON = datetime(2026, 9, 14, 3, 0, tzinfo=timezone.utc)

def samples(count, start=NOON, temperature=24.0, humidity=70.0, step=10):
    return [
        Sample(start + timedelta(minutes=step * index), temperature, humidity)
        for index in range(count)
    ]

def test_a_stored_reading_carries_its_derived_state(pipeline, profile, session):
    result = pipeline.store_samples(profile, samples(1))
    assert result.stored == 1

    row = session.query(Reading).one()
    assert row.temperature == 24.0
    assert row.relative_humidity == 70.0
    assert row.vpd is not None
    assert row.dew_point is not None
    assert row.engine_version == "1.0.0"
    assert row.error is None

def test_the_derived_state_reproduces_from_the_stored_row(pipeline, profile, session):
    pipeline.store_samples(profile, samples(1))
    row = session.query(Reading).one()
    again = state_from_reading(row)
    assert again.vpd_kpa == pytest.approx(row.vpd, abs=1e-9)
    assert again.dew_point == pytest.approx(row.dew_point, abs=1e-9)
    assert again.humidity_ratio == pytest.approx(row.humidity_ratio, abs=1e-12)

def test_altitude_sets_the_pressure_every_reading_uses(
    repository, pipeline, crop, session
):
    high = repository.create_facility(name="Highland", altitude_m=1000.0, equipment=[])
    profile = repository.create_profile(
        name="High", crop_id=crop.id, facility_id=high.id
    )
    assert pressure_for(profile) == pytest.approx(
        psy.standard_atmospheric_pressure(1000.0)
    )

    pipeline.store_samples(profile, samples(1))
    row = session.query(Reading).one()
    assert row.pressure == pytest.approx(89874.5, abs=1.0)

def test_the_same_reading_weighs_more_moisture_at_altitude(
    repository, pipeline, crop, session
):
    low = repository.create_facility(name="Sea", altitude_m=0.0, equipment=[])
    high = repository.create_facility(name="Hill", altitude_m=1000.0, equipment=[])
    a = repository.create_profile(name="A", crop_id=crop.id, facility_id=low.id)
    b = repository.create_profile(name="B", crop_id=crop.id, facility_id=high.id)

    pipeline.store_samples(a, samples(1))
    pipeline.store_samples(b, samples(1))
    rows = {row.profile_id: row for row in session.query(Reading).all()}
    ratio = rows[b.id].humidity_ratio / rows[a.id].humidity_ratio
    assert ratio == pytest.approx(1.128, abs=0.01)

def test_the_same_timestamp_twice_is_a_duplicate_not_an_error(pipeline, profile):
    pipeline.store_samples(profile, samples(1))
    result = pipeline.store_samples(profile, samples(1))
    assert result.stored == 0
    assert result.duplicates == 1

def test_two_profiles_may_hold_the_same_timestamp(
    repository, pipeline, crop, facility, session
):
    a = repository.create_profile(name="A", crop_id=crop.id, facility_id=facility.id)
    b = repository.create_profile(name="B", crop_id=crop.id, facility_id=facility.id)
    pipeline.store_samples(a, samples(1))
    pipeline.store_samples(b, samples(1))
    assert session.query(Reading).count() == 2

@pytest.mark.parametrize("temperature", [-200.0, 250.0])
def test_a_reading_outside_the_usable_range_is_kept_and_marked(
    pipeline, profile, session, temperature
):
    result = pipeline.store_samples(profile, [Sample(NOON, temperature, 50.0)])
    assert result.failed == 1
    assert result.stored == 0

    row = session.query(Reading).one()
    assert row.temperature == temperature
    assert row.error is not None
    assert row.humidity_ratio is None
    assert not row.usable

def test_a_humidity_a_little_over_100_is_evaluated_at_saturation(
    pipeline, profile, session
):
    pipeline.store_samples(profile, [Sample(NOON, 24.0, 101.5)])
    row = session.query(Reading).one()
    assert row.relative_humidity == 101.5
    assert row.usable
    assert row.dew_point == pytest.approx(24.0, abs=0.01)

def test_an_unusable_reading_is_not_the_latest(pipeline, profile, repository):
    pipeline.store_samples(profile, [Sample(NOON, 24.0, 70.0)])
    pipeline.store_samples(profile, [Sample(NOON + timedelta(minutes=10), 900.0, 70.0)])
    latest = repository.latest_reading(profile.id)
    assert latest.temperature == 24.0

def test_assessment_needs_a_reading(pipeline, profile):
    assert pipeline.assess(profile) is None

def test_assessment_reports_the_state_and_the_advice(pipeline, profile, rules):
    pipeline.store_samples(profile, [Sample(NOON, 34.0, 88.0)])
    payload = pipeline.assess(profile)

    assert payload["temperature_c"] == pytest.approx(34.0)
    assert payload["vpd_kpa"] > 0
    assert payload["targets"]["temperature"]["max"] == 28.0
    assert payload["assessment"]["status"] == "critical"
    assert payload["assessment"]["headline"] == "Hot and humid"

def test_a_profile_with_no_link_cannot_refresh(pipeline, profile):
    with pytest.raises(SourceError, match="no data link"):
        pipeline.refresh(profile)

def test_a_broken_link_is_recorded_on_the_profile(
    pipeline, repository, profile, monkeypatch
):
    repository.update_profile(profile.id, source_url="https://example.invalid/x.json")
    with pytest.raises(SourceError):
        pipeline.refresh(profile)
    assert profile.last_poll_error
    assert profile.last_polled_at is not None

def test_a_good_fetch_clears_the_error(pipeline, repository, profile, monkeypatch):
    repository.update_profile(
        profile.id, source_url="https://example.test/x.json", last_poll_error="old"
    )
    monkeypatch.setattr(
        "psychromol.pipeline.fetch_source",
        lambda url: ('[{"ts": "2026-09-14T03:00:00Z", "t": 22, "rh": 65}]', "application/json"),
    )
    result = pipeline.refresh(profile)
    assert result.stored == 1
    assert profile.last_poll_error is None

def test_text_that_holds_no_readings_is_refused(pipeline, profile):
    with pytest.raises(SourceError, match="no list of readings"):
        pipeline.load_text(profile, '{"status": "ok", "list": []}')

def test_unreadable_text_is_refused(pipeline, profile):
    with pytest.raises(SourceError):
        pipeline.load_text(profile, "{not json")

def test_rows_that_could_not_be_read_are_reported(pipeline, profile):
    result = pipeline.load_text(
        profile,
        "time,temp,rh\n2026-09-14 03:00,24,70\n2026-09-14 03:10,,70\n",
    )
    assert result.stored == 1
    assert result.skipped == 1
