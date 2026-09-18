from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .db.models import Profile, Reading
from .db.repository import Repository
from .fields import extract

FETCH_TIMEOUT_SECONDS = 10
MAX_BYTES = 2 * 1024 * 1024
USER_AGENT = "PsychroMol"


class SourceError(RuntimeError):
    pass


def _reject_constant(name: str) -> Any:
    raise ValueError(f"{name} is not valid JSON")


def fetch_json(url: str) -> Any:
    if not url.lower().startswith(("http://", "https://")):
        raise SourceError("the link must start with http:// or https://")
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
            raw = response.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise SourceError(f"the source returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise SourceError(f"could not reach the source: {exc.reason}") from exc
    except (TimeoutError, OSError, ValueError) as exc:
        raise SourceError(f"could not reach the source: {exc}") from exc
    if len(raw) > MAX_BYTES:
        raise SourceError("the source is larger than 2 MB")
    try:
        return json.loads(raw.decode("utf-8-sig"), parse_constant=_reject_constant)
    except (UnicodeDecodeError, ValueError) as exc:
        raise SourceError(f"the source is not valid JSON: {exc}") from exc


def mapping_of(profile: Profile) -> dict[str, str | None]:
    return {
        "time": profile.field_time,
        "temperature": profile.field_temperature,
        "humidity": profile.field_humidity,
        "pressure": profile.field_pressure if profile.pressure_mode == "field" else None,
        "pressure_unit": profile.pressure_unit,
    }


@dataclass(frozen=True)
class RefreshResult:
    stored: bool
    reading: Reading | None
    error: str | None


def refresh(
    repository: Repository,
    profile: Profile,
    now: datetime | None = None,
    fetch: Callable[[str], Any] | None = None,
) -> RefreshResult:
    now = now or datetime.now(timezone.utc)
    if not profile.source_url:
        return RefreshResult(False, None, "this profile has no JSON link")
    try:
        document = (fetch or fetch_json)(profile.source_url)
    except SourceError as exc:
        repository.mark_polled(profile, now, str(exc))
        return RefreshResult(False, None, str(exc))

    extraction = extract(document, mapping_of(profile), now)
    if extraction.errors:
        message = "; ".join(f"{field}: {problem}" for field, problem in extraction.errors)
        repository.mark_polled(profile, now, message)
        return RefreshResult(False, None, message)

    reading, created = repository.add_reading(
        profile.id,
        measured_at=extraction.measured_at,
        received_at=now,
        temperature_c=extraction.temperature_c,
        relative_humidity_percent=extraction.relative_humidity_percent,
        pressure_kpa=extraction.pressure_kpa,
    )
    repository.mark_polled(profile, now, None)
    return RefreshResult(created, reading, None)


def is_due(profile: Profile, now: datetime) -> bool:
    if not profile.source_url:
        return False
    if profile.last_polled_at is None:
        return True
    return (now - profile.last_polled_at).total_seconds() >= profile.poll_interval_seconds
