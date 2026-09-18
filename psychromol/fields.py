from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from .units import PRESSURE_UNITS, kpa_from

NUMBER_TEXT = re.compile(r"\s*([+-]?[0-9]+(?:[.,][0-9]+)?)\s*[^0-9\s.,+-]*\s*")
ISO_TIME = re.compile(
    r"([0-9]{4})-([0-9]{2})-([0-9]{2})"
    r"(?:[Tt ]([0-9]{2}):([0-9]{2})(?::([0-9]{2})(?:[.,]([0-9]+))?)?)?"
    r"\s*([Zz]|[+-][0-9]{2}(?::?[0-9]{2})?)?"
)
EPOCH_TEXT = re.compile(r"[0-9]{10,}(?:\.[0-9]+)?")
ARRAY_INDEX = re.compile(r"0|[1-9][0-9]*")
EPOCH_MILLISECONDS_ABOVE = 1e11
EARLIEST_YEAR = 1970
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

MISSING = object()


def segments_of(pointer: str) -> list[str]:
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise ValueError(f'a JSON Pointer starts with "/", got {pointer!r}')
    return [part.replace("~1", "/").replace("~0", "~") for part in pointer[1:].split("/")]


def resolve(document: Any, pointer: str) -> Any:
    current = document
    for segment in segments_of(pointer):
        if isinstance(current, list):
            if not ARRAY_INDEX.fullmatch(segment) or int(segment) >= len(current):
                return MISSING
            current = current[int(segment)]
        elif isinstance(current, dict):
            if segment not in current:
                return MISSING
            current = current[segment]
        else:
            return MISSING
    return current


def to_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if not isinstance(value, str):
        return None
    match = NUMBER_TEXT.fullmatch(value)
    return float(match.group(1).replace(",", ".")) if match else None


def _from_epoch(number: float) -> datetime | None:
    if not number > 0:
        return None
    milliseconds = number if number > EPOCH_MILLISECONDS_ABOVE else number * 1000
    try:
        moment = EPOCH + timedelta(milliseconds=math.floor(milliseconds))
    except OverflowError:
        return None
    return moment


def to_time(value: Any) -> datetime | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return _from_epoch(float(value)) if math.isfinite(value) else None
    if not isinstance(value, str):
        return None
    text = value.strip()
    if EPOCH_TEXT.fullmatch(text):
        return _from_epoch(float(text))
    match = ISO_TIME.fullmatch(text)
    if not match:
        return None
    year, month, day, hour, minute, second, fraction, zone = match.groups()
    if int(year) < EARLIEST_YEAR:
        return None
    try:
        moment = datetime(
            int(year), int(month), int(day),
            int(hour or 0), int(minute or 0), int(second or 0),
            int((fraction or "").ljust(3, "0")[:3]) * 1000,
            tzinfo=timezone.utc,
        )
    except ValueError:
        return None
    if zone and zone.upper() != "Z":
        sign = -1 if zone[0] == "-" else 1
        digits = zone[1:].replace(":", "")
        moment -= timedelta(minutes=sign * (int(digits[:2]) * 60 + int(digits[2:] or "0")))
    return moment


@dataclass
class Extraction:
    measured_at: datetime | None = None
    temperature_c: float | None = None
    relative_humidity_percent: float | None = None
    pressure_kpa: float | None = None
    errors: list[tuple[str, str]] = field(default_factory=list)


def _shown(raw: Any) -> str:
    return json.dumps(raw, ensure_ascii=False)


def _truncate_to_milliseconds(moment: datetime) -> datetime:
    return moment.replace(microsecond=moment.microsecond // 1000 * 1000)


def extract(document: Any, mapping: Mapping[str, str | None], received_at: datetime) -> Extraction:
    result = Extraction()

    time_pointer = mapping.get("time")
    if time_pointer:
        raw = resolve(document, time_pointer)
        moment = None if raw is MISSING else to_time(raw)
        if raw is MISSING:
            result.errors.append(("time", f"nothing at {time_pointer}"))
        elif moment is None:
            result.errors.append(
                ("time", f"{_shown(raw)} at {time_pointer} is not an ISO 8601 time or an epoch number")
            )
        else:
            result.measured_at = moment
    else:
        result.measured_at = _truncate_to_milliseconds(received_at.astimezone(timezone.utc))

    for name, target in (("temperature", "temperature_c"), ("humidity", "relative_humidity_percent")):
        pointer = mapping.get(name)
        if not pointer:
            result.errors.append((name, f"no {name} field chosen"))
            continue
        raw = resolve(document, pointer)
        number = None if raw is MISSING else to_number(raw)
        if raw is MISSING:
            result.errors.append((name, f"nothing at {pointer}"))
        elif number is None:
            result.errors.append((name, f"{_shown(raw)} at {pointer} is not a number"))
        else:
            setattr(result, target, number)

    pressure_pointer = mapping.get("pressure")
    if pressure_pointer:
        unit = mapping.get("pressure_unit") or ""
        if unit not in PRESSURE_UNITS:
            result.errors.append(("pressure", f"unknown pressure unit {unit}"))
        else:
            raw = resolve(document, pressure_pointer)
            number = None if raw is MISSING else to_number(raw)
            if raw is MISSING:
                result.errors.append(("pressure", f"nothing at {pressure_pointer}"))
            elif number is None:
                result.errors.append(("pressure", f"{_shown(raw)} at {pressure_pointer} is not a number"))
            else:
                result.pressure_kpa = kpa_from(number, unit)
    return result
