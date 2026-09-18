from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ..config import PROJECT_ROOT, get_settings
from ..db.repository import Repository
from ..db.session import create_all, get_sessionmaker, init_engine
from ..fetcher import is_due, refresh
from ..logging_setup import configure_logging
from .routers import profiles, readings, rules, sources

logger = logging.getLogger(__name__)

VERSION = "3.0.0"
POLL_TICK_SECONDS = 1.0

DESCRIPTION = """
Storage and data collection for PsychroMol.

The server keeps the database and fetches each profile's JSON link on the
profile's own interval, storing only what was measured: a time, a temperature,
a humidity and, when mapped, a pressure. Every calculation, classification and
recommendation happens in the browser. Every field name carries its unit.
"""


async def poll_sources(stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=POLL_TICK_SECONDS)
            return
        except asyncio.TimeoutError:
            pass
        try:
            await asyncio.to_thread(poll_once)
        except Exception:
            logger.exception("source polling failed")


def poll_once() -> None:
    session = get_sessionmaker()()
    try:
        repository = Repository(session)
        now = datetime.now(timezone.utc)
        for profile in repository.list_profiles():
            if not is_due(profile, now):
                continue
            result = refresh(repository, profile, now)
            session.commit()
            if result.error:
                logger.warning("profile %s: %s", profile.id, result.error)
    finally:
        session.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings)
    init_engine(settings)
    create_all()
    logger.info("PsychroMol %s starting", VERSION)

    stop = asyncio.Event()
    task = asyncio.create_task(poll_sources(stop))
    try:
        yield
    finally:
        stop.set()
        task.cancel()
        with contextlib.suppress(BaseException):
            await task
        logger.info("PsychroMol stopping")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="PsychroMol",
        description=DESCRIPTION,
        version=VERSION,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/v1/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok", "version": VERSION}

    for router in (profiles.router, readings.router, rules.router, sources.router):
        app.include_router(router, prefix="/api/v1")

    frontend = PROJECT_ROOT / "frontend"
    if frontend.is_dir():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return app


app = create_app()
