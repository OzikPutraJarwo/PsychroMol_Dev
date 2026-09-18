from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from ... import fetcher

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("/fetch")
def fetch_source(url: str = Query(..., min_length=1, max_length=2000)) -> dict[str, Any]:
    try:
        return {"ok": True, "document": fetcher.fetch_json(url), "error": None}
    except fetcher.SourceError as exc:
        return {"ok": False, "document": None, "error": str(exc)}
