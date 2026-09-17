from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from psychromol.ingest import ParseError, parse_any, parse_csv, parse_json


def test_a_plain_list_of_objects_is_read():
    samples, skipped = parse_json(
        '[{"timestamp": "2026-09-14T08:00:00Z", "temperature": 24.5, "humidity": 68}]'
    )
    assert skipped == 0
    assert samples[0].temperature == 24.5
    assert samples[0].relative_humidity == 68.0
    assert samples[0].measured_at == datetime(2026, 9, 14, 8, 0, tzinfo=timezone.utc)

@pytest.mark.parametrize(
    "wrapper", ["data", "readings", "results", "items", "records", "rows", "values"]
)
def test_a_wrapped_list_is_found(wrapper):
    body = json.dumps({wrapper: [{"ts": "2026-09-14T08:00:00Z", "t": 20, "rh": 55}]})
    samples, _ = parse_json(body)
    assert len(samples) == 1

def test_a_single_object_is_accepted_as_one_reading():
    samples, _ = parse_json('{"time": "2026-09-14T08:00:00Z", "temp": 21, "hum": 60}')
    assert len(samples) == 1

@pytest.mark.parametrize(
    "time_key, temperature_key, humidity_key",
    [
        ("timestamp", "temperature", "humidity"),
        ("time", "temp", "rh"),
        ("datetime", "temperature_c", "relative_humidity"),
        ("measured_at", "air_temperature", "humidity_percent"),
        ("ts", "t", "hum"),
    ],
)
def test_common_field_spellings_are_recognised(time_key, temperature_key, humidity_key):
    body = json.dumps(
        [{time_key: "2026-09-14T08:00:00Z", temperature_key: 23, humidity_key: 65}]
    )
    samples, skipped = parse_json(body)
    assert skipped == 0
    assert samples[0].temperature == 23.0

def test_a_messy_header_still_maps():
    samples, _ = parse_csv(
        "Date Time,Air Temperature (C),Relative Humidity (%)\n"
        "2026-09-14 08:00,24.5,68\n"
    )
    assert samples[0].temperature == 24.5

@pytest.mark.parametrize("delimiter", [",", ";", "\t", "|"])
def test_delimiters_are_sniffed(delimiter):
    header = delimiter.join(["time", "temp", "rh"])
    row = delimiter.join(["2026-09-14 08:00", "24.5", "68"])
    samples, _ = parse_csv(f"{header}\n{row}\n")
    assert len(samples) == 1

def test_epoch_seconds_and_milliseconds_both_work():
    seconds, _ = parse_json('[{"ts": 1789430400, "t": 20, "rh": 50}]')
    millis, _ = parse_json('[{"ts": 1789430400000, "t": 20, "rh": 50}]')
    assert seconds[0].measured_at == millis[0].measured_at

def test_rows_that_cannot_be_read_are_counted_not_guessed():
    samples, skipped = parse_csv(
        "time,temp,rh\n"
        "2026-09-14 08:00,24.5,68\n"
        "2026-09-14 08:10,,70\n"
        "not a date,21,60\n"
    )
    assert len(samples) == 1
    assert skipped == 2

def test_readings_come_back_in_time_order():
    samples, _ = parse_json(
        '[{"ts": "2026-09-14T09:00:00Z", "t": 25, "rh": 60},'
        ' {"ts": "2026-09-14T08:00:00Z", "t": 22, "rh": 70}]'
    )
    assert samples[0].temperature == 22.0
    assert samples[1].temperature == 25.0

def test_a_naive_timestamp_is_read_as_utc():
    samples, _ = parse_json('[{"ts": "2026-09-14T08:00:00", "t": 20, "rh": 50}]')
    assert samples[0].measured_at.tzinfo is timezone.utc

def test_an_offset_timestamp_keeps_its_instant():
    samples, _ = parse_json('[{"ts": "2026-09-14T17:00:00+09:00", "t": 20, "rh": 50}]')
    assert samples[0].measured_at == datetime(2026, 9, 14, 8, 0, tzinfo=timezone.utc)

def test_comma_decimals_are_read():
    samples, _ = parse_csv("time,temp,rh\n2026-09-14 08:00,\"24,5\",\"68,2\"\n")
    assert samples[0].temperature == 24.5

@pytest.mark.parametrize("marker", ["", "NA", "n/a", "null", "-", "NaN"])
def test_missing_markers_are_not_read_as_numbers(marker):
    samples, skipped = parse_csv(f"time,temp,rh\n2026-09-14 08:00,{marker},68\n")
    assert samples == []
    assert skipped == 1

def test_invalid_json_says_so():
    with pytest.raises(ParseError, match="invalid JSON"):
        parse_json("{not json")

def test_json_without_readings_says_so():
    with pytest.raises(ParseError, match="no list of readings"):
        parse_json('{"status": "ok"}')

def test_format_is_detected_without_a_filename():
    from_json, _ = parse_any('[{"ts": "2026-09-14T08:00:00Z", "t": 20, "rh": 50}]')
    from_csv, _ = parse_any("time,temp,rh\n2026-09-14 08:00,20,50\n")
    assert len(from_json) == 1
    assert len(from_csv) == 1

def test_the_filename_extension_wins_when_given():
    samples, _ = parse_any("time,temp,rh\n2026-09-14 08:00,20,50\n", "readings.csv")
    assert len(samples) == 1
