from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from ..config import PROJECT_ROOT, get_settings
from ..core.psychrometrics import PsychrometricRangeError
from ..db.models import DEFAULT_POLL_INTERVAL_SECONDS
from ..db.repository import Repository
from ..db.session import create_all, get_sessionmaker, init_engine
from ..defaults import DEFAULT_RULES
from ..hardware import HardwareError
from ..hardware import runtime as hardware_runtime
from ..logging_setup import configure_logging
from ..pipeline import ENGINE_VERSION, Pipeline, SourceError
from .routers import catalogue, data, hardware, preview, profiles, rules

logger = logging.getLogger(__name__)

POLL_TICK_SECONDS = 1.0

DESCRIPTION = """
Psychrometric decision support for greenhouse environment management.

Rule-based: every recommendation comes from a rule you can read and edit, and
names the measured values that triggered it. Psychrometric basis is the ASHRAE
Handbook — Fundamentals (2017), Chapter 1. The API speaks kPa and every field
name carries its unit.
"""

def seed_rules() -> None:
    session = get_sessionmaker()()
    try:
        repository = Repository(session)
        if not repository.list_rules():
            repository.replace_rules(DEFAULT_RULES)
            session.commit()
    finally:
        session.close()

def _is_due(profile, now: datetime) -> bool:
    if profile.last_polled_at is None:
        return True
    interval = profile.poll_interval_seconds or DEFAULT_POLL_INTERVAL_SECONDS
    return (now - profile.last_polled_at).total_seconds() >= interval

async def poll_sources(stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=POLL_TICK_SECONDS)
            return
        except asyncio.TimeoutError:
            pass
        try:
            await asyncio.to_thread(_poll_once)
        except Exception:
            logger.exception("source polling failed")

def _poll_once() -> None:
    session = get_sessionmaker()()
    try:
        repository = Repository(session)
        pipeline = Pipeline(repository)
        now = datetime.now(timezone.utc)
        for profile in repository.list_profiles():
            if not profile.source_url or not _is_due(profile, now):
                continue
            try:
                result = pipeline.refresh(profile)
            except SourceError as exc:
                logger.warning("profile %s: %s", profile.id, exc)
                session.commit()
                continue
            if result.stored:
                logger.info("profile %s: %s new readings", profile.id, result.stored)
            session.commit()
    finally:
        session.close()

async def poll_hardware(stop: asyncio.Event, rig, profile_id: int, interval: float) -> None:
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
            return
        except asyncio.TimeoutError:
            pass
        try:
            await asyncio.to_thread(_poll_hardware_once, rig, profile_id)
        except Exception:
            logger.exception("hardware polling failed")

def _poll_hardware_once(rig, profile_id: int) -> None:
    session = get_sessionmaker()()
    try:
        repository = Repository(session)
        profile = repository.get_profile(profile_id)
        if profile is None:
            logger.error("hardware profile %s not found", profile_id)
            return
        pipeline = Pipeline(repository)
        hardware_runtime.poll_once(rig, pipeline, profile)
        session.commit()
    finally:
        session.close()

def start_hardware(settings) -> object | None:
    if not settings.hardware_enabled:
        return None
    if settings.hardware_profile_id is None:
        logger.error("PSYCHROMOL_HARDWARE_ENABLED is set but PSYCHROMOL_HARDWARE_PROFILE_ID is not")
        return None
    try:
        rig = hardware_runtime.build_rig()
    except HardwareError as exc:
        logger.error("hardware setup failed: %s", exc)
        return None
    hardware_runtime.set_active_rig(rig)
    return rig

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings)
    init_engine(settings)
    create_all()
    seed_rules()
    logger.info("PsychroMol starting, engine %s", ENGINE_VERSION)

    stop = asyncio.Event()
    tasks = [asyncio.create_task(poll_sources(stop))]

    rig = start_hardware(settings)
    if rig is not None:
        tasks.append(
            asyncio.create_task(
                poll_hardware(stop, rig, settings.hardware_profile_id, settings.hardware_poll_seconds)
            )
        )
        logger.info("hardware polling started, profile %s", settings.hardware_profile_id)

    try:
        yield
    finally:
        stop.set()
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(BaseException):
                await task
        hardware_runtime.set_active_rig(None)
        logger.info("PsychroMol stopping")

def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="PsychroMol",
        description=DESCRIPTION,
        version=ENGINE_VERSION,
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

    @app.exception_handler(PsychrometricRangeError)
    async def psychrometric_range_handler(
        request: Request, exc: PsychrometricRangeError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": str(exc)},
        )

    @app.get("/api/v1/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok", "engine": ENGINE_VERSION}

    routers = (
        catalogue.router, profiles.router, data.router, preview.router, rules.router,
        hardware.router,
    )
    for router in routers:
        app.include_router(router, prefix="/api/v1")

    frontend = PROJECT_ROOT / "frontend"
    if frontend.is_dir():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")

    return app

app = create_app()
