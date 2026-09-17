from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

TIME_KEYS = (
    "timestamp",
    "time",
    "datetime",
    "date_time",
    "measured_at",
    "recorded_at",
    "ts",
    "date",
)
TEMPERATURE_KEYS = (
    "temperature",
    "temp",
    "temperature_c",
    "temp_c",
    "air_temperature",
    "t",
)
HUMIDITY_KEYS = (
    "relative_humidity",
    "humidity",
    "rh",
    "hum",
    "humidity_percent",
    "relative_humidity_percent",
    "rh_percent",
)
CONTAINER_KEYS = ("data", "readings", "results", "items", "records", "rows", "values")

MISSING = {"", "na", "n/a", "nan", "null", "none", "-", "--", "---"}

class ParseError(ValueError):
    pass

@dataclass(frozen=True)
class Sample:
    measured_at: datetime
    temperature: float
    relative_humidity: float

def _clean(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")

def _pick(row: dict[str, Any], candidates: Iterable[str]) -> Any:
    normalised = {_clean(key): value for key, value in row.items()}
    names = tuple(candidates)

    for candidate in names:
        if candidate in normalised:
            return normalised[candidate]

    for candidate in names:
        if len(candidate) < 3:
            continue
        for key, value in normalised.items():
            if candidate in key.split("_"):
                return value

    for candidate in names:
        if len(candidate) < 3:
            continue
        for key, value in normalised.items():
            if candidate in key:
                return value
    return None

def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return None if number != number else number
    text = str(value).strip().replace(",", ".")
    if text.lower() in MISSING:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if match is None:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None

def _to_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        seconds = float(value)
        if seconds > 1e11:
            seconds /= 1000.0
        try:
            moment = datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    else:
        text = str(value).strip()
        if not text or text.lower() in MISSING:
            return None
        if text.isdigit() and len(text) >= 10:
            return _to_datetime(float(text))
        candidate = text.replace("Z", "+00:00").replace("/", "-")
        moment = None
        try:
            moment = datetime.fromisoformat(candidate)
        except ValueError:
            for pattern in (
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
                "%d-%m-%Y %H:%M:%S",
                "%d-%m-%Y %H:%M",
                "%m-%d-%Y %H:%M:%S",
                "%m-%d-%Y %H:%M",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d",
            ):
                try:
                    moment = datetime.strptime(candidate, pattern)
                    break
                except ValueError:
                    continue
        if moment is None:
            return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)

def _rows_from_json(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in CONTAINER_KEYS:
            inner = payload.get(key)
            if isinstance(inner, list):
                return [row for row in inner if isinstance(row, dict)]
        for value in payload.values():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                return [row for row in value if isinstance(row, dict)]
        if _pick(payload, TEMPERATURE_KEYS) is not None:
            return [payload]
    raise ParseError("no list of readings found in the JSON")

def samples_from_rows(rows: Iterable[dict[str, Any]]) -> tuple[list[Sample], int]:
    samples: list[Sample] = []
    skipped = 0
    for row in rows:
        moment = _to_datetime(_pick(row, TIME_KEYS))
        temperature = _to_float(_pick(row, TEMPERATURE_KEYS))
        humidity = _to_float(_pick(row, HUMIDITY_KEYS))
        if moment is None or temperature is None or humidity is None:
            skipped += 1
            continue
        samples.append(Sample(moment, temperature, humidity))
    samples.sort(key=lambda item: item.measured_at)
    return samples, skipped

def parse_json(text: str | bytes) -> tuple[list[Sample], int]:
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ParseError(f"invalid JSON: {exc.msg}") from exc
    return samples_from_rows(_rows_from_json(payload))

def parse_csv(text: str | bytes) -> tuple[list[Sample], int]:
    if isinstance(text, bytes):
        text = text.decode("utf-8-sig", errors="replace")
    sample_text = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample_text, delimiters=",;\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if not reader.fieldnames:
        raise ParseError("the file has no header row")
    return samples_from_rows(reader)

def parse_any(text: str | bytes, filename: str = "") -> tuple[list[Sample], int]:
    lowered = filename.lower()
    if lowered.endswith(".json"):
        return parse_json(text)
    if lowered.endswith(".csv") or lowered.endswith(".txt"):
        return parse_csv(text)
    probe = text.decode("utf-8", errors="replace") if isinstance(text, bytes) else text
    if probe.lstrip()[:1] in ("[", "{"):
        return parse_json(text)
    return parse_csv(text)
