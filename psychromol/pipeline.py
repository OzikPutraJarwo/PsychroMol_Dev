from __future__ import annotations

import urllib.error
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone

from .core import psychrometrics as psy
from .core.state import MoistAirState, from_temperature_relative_humidity
from .db.models import Profile, Reading
from .db.repository import Repository
from .ingest import ParseError, Sample, parse_any
from .rules import Assessment, evaluate

ENGINE_VERSION = "1.0.0"

USER_AGENT = "PsychroMol/1.0"
FETCH_TIMEOUT = 15.0
MAX_BYTES = 16 * 1024 * 1024

@dataclass
class StoreResult:
    stored: int = 0
    duplicates: int = 0
    failed: int = 0
    skipped: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "stored": self.stored,
            "duplicates": self.duplicates,
            "failed": self.failed,
            "skipped": self.skipped,
        }

class SourceError(RuntimeError):
    pass

def pressure_for(profile: Profile) -> float:
    altitude = 0.0
    if profile.facility is not None and profile.facility.altitude_m:
        altitude = float(profile.facility.altitude_m)
    return psy.standard_atmospheric_pressure(altitude)

def state_from_reading(reading: Reading) -> MoistAirState | None:
    if reading.temperature is None or reading.relative_humidity is None:
        return None
    try:
        return from_temperature_relative_humidity(
            reading.temperature,
            min(100.0, max(0.0, reading.relative_humidity)),
            reading.pressure,
        )
    except psy.PsychrometricRangeError:
        return None

def fetch_source(url: str) -> tuple[str, str]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT) as response:
            raw = response.read(MAX_BYTES + 1)
            content_type = response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        raise SourceError(f"the source returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise SourceError(f"could not reach the source: {exc.reason}") from exc
    except (TimeoutError, OSError) as exc:
        raise SourceError(f"could not reach the source: {exc}") from exc
    if len(raw) > MAX_BYTES:
        raise SourceError("the source is larger than 16 MB")
    return raw.decode("utf-8", errors="replace"), content_type

class Pipeline:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def store_samples(
        self, profile: Profile, samples: Iterable[Sample], skipped: int = 0
    ) -> StoreResult:
        result = StoreResult(skipped=skipped)
        pressure = pressure_for(profile)
        received = datetime.now(timezone.utc)

        for sample in samples:
            error: str | None = None
            state: MoistAirState | None = None
            if not -100.0 <= sample.temperature <= 200.0:
                error = f"temperature {sample.temperature} is outside the usable range"
            elif not -5.0 <= sample.relative_humidity <= 105.0:
                error = f"humidity {sample.relative_humidity} is outside the usable range"
            else:
                try:
                    state = from_temperature_relative_humidity(
                        sample.temperature,
                        min(100.0, max(0.0, sample.relative_humidity)),
                        pressure,
                    )
                except psy.PsychrometricRangeError as exc:
                    error = str(exc)

            fields = {
                "profile_id": profile.id,
                "measured_at": sample.measured_at,
                "received_at": received,
                "temperature": sample.temperature,
                "relative_humidity": sample.relative_humidity,
                "pressure": pressure,
                "engine_version": ENGINE_VERSION,
                "error": error,
            }
            if state is not None:
                fields.update(
                    {
                        "saturation_vapour_pressure": state.saturation_vapour_pressure,
                        "vapour_pressure": state.vapour_pressure,
                        "humidity_ratio": state.humidity_ratio,
                        "dew_point": state.dew_point,
                        "wet_bulb": state.wet_bulb,
                        "enthalpy": state.enthalpy,
                        "specific_volume": state.specific_volume,
                        "density": state.density,
                        "vpd": state.vpd_kpa,
                        "absolute_humidity": state.absolute_humidity,
                        "degree_of_saturation": state.degree_of_saturation,
                        "dew_point_depression": state.dew_point_depression,
                        "mollier_ordinate": state.mollier_ordinate,
                    }
                )

            stored = self.repository.add_reading(**fields)
            if stored is None:
                result.duplicates += 1
            elif error is not None:
                result.failed += 1
            else:
                result.stored += 1
        return result

    def load_text(
        self, profile: Profile, text: str, filename: str = ""
    ) -> StoreResult:
        try:
            samples, skipped = parse_any(text, filename)
        except ParseError as exc:
            raise SourceError(str(exc)) from exc
        if not samples:
            raise SourceError(
                "no readings could be read: each row needs a timestamp, "
                "a temperature and a humidity"
            )
        return self.store_samples(profile, samples, skipped)

    def refresh(self, profile: Profile) -> StoreResult:
        if not profile.source_url:
            raise SourceError("this profile has no data link")
        moment = datetime.now(timezone.utc)
        try:
            text, _ = fetch_source(profile.source_url)
            result = self.load_text(profile, text, profile.source_url)
        except SourceError as exc:
            self.repository.mark_polled(profile.id, moment, str(exc))
            raise
        self.repository.mark_polled(profile.id, moment, None)
        return result

    def assess(self, profile: Profile) -> dict | None:
        reading = self.repository.latest_reading(profile.id)
        if reading is None:
            return None
        state = state_from_reading(reading)
        if state is None:
            return None

        crop = profile.crop
        targets = crop.targets() if crop else {}
        equipment = profile.facility.equipment if profile.facility else []
        rules = self.repository.list_rules(enabled_only=True)
        assessment: Assessment = evaluate(state, targets, rules, equipment or [])

        payload = state.to_api_dict()
        payload.update(
            {
                "measured_at": reading.measured_at.isoformat(),
                "received_at": reading.received_at.isoformat(),
                "age_seconds": round(
                    (datetime.now(timezone.utc) - reading.measured_at).total_seconds(), 1
                ),
                "targets": targets,
                "assessment": assessment.to_dict(),
            }
        )
        return payload
