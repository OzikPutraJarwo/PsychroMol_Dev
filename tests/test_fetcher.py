from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from psychromol import fetcher
from psychromol.db.models import iso
from psychromol.fields import extract

CASES = json.loads((Path(__file__).parent / "fixtures" / "extraction-cases.json").read_text())["cases"]
NOW = datetime(2026, 9, 17, 9, 10, 6, 500000, tzinfo=timezone.utc)


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_the_server_reads_the_same_values_as_the_browser(case):
    received = datetime.fromisoformat(case["received_at"].replace("Z", "+00:00"))
    result = extract(case["document"], case["mapping"], received)
    expected = case["expected"]
    assert [field for field, _ in result.errors] == expected["error_fields"]
    assert iso(result.measured_at) == expected["reading"]["measured_at"]
    for key in ("temperature_c", "relative_humidity_percent", "pressure_kpa"):
        wanted = expected["reading"][key]
        if wanted is None:
            assert getattr(result, key) is None
        else:
            assert getattr(result, key) == pytest.approx(wanted, abs=1e-9)


def live(timestamp="2026-09-17T09:10:04Z", temperature=27.0, humidity=44.6, **extra):
    return {"timestamp": timestamp, "temperature": temperature, "humidity": humidity, **extra}


def test_a_refresh_stores_the_reading_once(repository, profile):
    first = fetcher.refresh(repository, profile, NOW, fetch=lambda url: live())
    assert first.stored and first.error is None
    assert first.reading.temperature_c == 27.0
    assert first.reading.relative_humidity_percent == 44.6
    assert first.reading.pressure_kpa is None
    assert profile.last_polled_at == NOW and profile.last_poll_error is None

    again = fetcher.refresh(repository, profile, NOW, fetch=lambda url: live(temperature=30.0))
    assert not again.stored
    assert again.reading.id == first.reading.id
    assert repository.count_readings(profile.id, None, None) == 1


def test_a_reading_the_link_does_not_contain_is_recorded_as_the_error(repository, profile):
    result = fetcher.refresh(repository, profile, NOW, fetch=lambda url: {"timestamp": "2026-09-17T09:10:04Z"})
    assert not result.stored
    assert "temperature: nothing at /temperature" in result.error
    assert profile.last_poll_error == result.error
    assert repository.count_readings(profile.id, None, None) == 0


def test_an_unreachable_source_is_recorded(repository, profile):
    def broken(url):
        raise fetcher.SourceError("could not reach the source: timed out")

    result = fetcher.refresh(repository, profile, NOW, fetch=broken)
    assert result.error == "could not reach the source: timed out"
    assert profile.last_poll_error == result.error


def test_pressure_is_read_only_when_the_profile_takes_it_from_the_link(repository, profile):
    profile.field_pressure = "/baro"
    profile.pressure_unit = "hPa"
    document = live(baro=1008.4)
    assert fetcher.refresh(repository, profile, NOW, fetch=lambda url: document).reading.pressure_kpa is None

    profile.pressure_mode = "field"
    later = live(timestamp="2026-09-17T09:10:05Z", baro=1008.4)
    reading = fetcher.refresh(repository, profile, NOW, fetch=lambda url: later).reading
    assert reading.pressure_kpa == pytest.approx(100.84)


def test_a_profile_without_a_link_is_not_fetched(repository, profile):
    profile.source_url = None
    result = fetcher.refresh(repository, profile, NOW, fetch=lambda url: pytest.fail("fetched"))
    assert result.error == "this profile has no JSON link"


class Source(BaseHTTPRequestHandler):
    bodies = {
        "/good.json": (200, b'{"timestamp": "2026-09-17T09:10:04Z", "temperature": 27.0}'),
        "/bom.json": (200, b'\xef\xbb\xbf{"temperature": 1}'),
        "/nan.json": (200, b'{"temperature": NaN}'),
        "/broken.json": (200, b'{"temperature": '),
    }

    def do_GET(self):
        status, body = self.bodies.get(self.path, (404, b"missing"))
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def source():
    server = HTTPServer(("127.0.0.1", 0), Source)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def test_fetching_a_json_link(source):
    assert fetcher.fetch_json(f"{source}/good.json")["temperature"] == 27.0
    assert fetcher.fetch_json(f"{source}/bom.json") == {"temperature": 1}


@pytest.mark.parametrize(
    ("path", "message"),
    [
        ("/missing.json", "HTTP 404"),
        ("/nan.json", "not valid JSON"),
        ("/broken.json", "not valid JSON"),
    ],
)
def test_a_bad_json_link_is_refused_with_a_reason(source, path, message):
    with pytest.raises(fetcher.SourceError, match=message):
        fetcher.fetch_json(f"{source}{path}")


def test_only_web_links_are_fetched():
    with pytest.raises(fetcher.SourceError, match="http"):
        fetcher.fetch_json("file:///etc/passwd")
