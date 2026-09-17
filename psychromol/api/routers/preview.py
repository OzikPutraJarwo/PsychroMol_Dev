from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from ...ingest import ParseError, parse_any
from ...pipeline import SourceError, fetch_source

router = APIRouter(tags=["data"])

PREVIEW_ROWS = 5

@router.get("/sources/preview")
def preview_source(url: str = Query(...)) -> dict[str, Any]:
    try:
        text, content_type = fetch_source(url)
    except SourceError as exc:
        return {"ok": False, "error": str(exc)}
    try:
        samples, skipped = parse_any(text, url)
    except ParseError as exc:
        return {"ok": False, "error": str(exc), "content_type": content_type}
    return {
        "ok": True,
        "error": None,
        "content_type": content_type,
        "count": len(samples),
        "skipped": skipped,
        "rows": [
            {
                "measured_at": sample.measured_at.isoformat(),
                "temperature": sample.temperature,
                "relative_humidity": sample.relative_humidity,
            }
            for sample in samples[-PREVIEW_ROWS:]
        ],
    }
