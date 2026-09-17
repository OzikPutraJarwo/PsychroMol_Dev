from __future__ import annotations

from psychromol.api.routers import preview
from psychromol.pipeline import SourceError


def test_preview_returns_parsed_rows_for_valid_json(client, monkeypatch):
    text = '[{"timestamp": "2026-09-14T08:00:00Z", "temperature": 24.5, "humidity": 68}]'
    monkeypatch.setattr(preview, "fetch_source", lambda url: (text, "application/json"))

    response = client.get("/api/v1/sources/preview", params={"url": "https://example.com/x.json"})
    body = response.json()

    assert response.status_code == 200
    assert body["ok"] is True
    assert body["count"] == 1
    assert body["rows"][0]["temperature"] == 24.5

def test_preview_reports_a_source_error(client, monkeypatch):
    def fail(url):
        raise SourceError("could not reach the source: timed out")

    monkeypatch.setattr(preview, "fetch_source", fail)

    response = client.get("/api/v1/sources/preview", params={"url": "https://example.com/x.json"})
    body = response.json()

    assert response.status_code == 200
    assert body["ok"] is False
    assert "timed out" in body["error"]

def test_preview_reports_a_parse_error(client, monkeypatch):
    monkeypatch.setattr(preview, "fetch_source", lambda url: ("not json", "text/plain"))

    response = client.get("/api/v1/sources/preview", params={"url": "https://example.com/x.json"})
    body = response.json()

    assert response.status_code == 200
    assert body["ok"] is False
    assert body["error"]
