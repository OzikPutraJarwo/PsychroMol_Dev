from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from psychromol.config import Settings, reload_settings
from psychromol.db.repository import Repository
from psychromol.db.session import create_all, get_sessionmaker, init_engine

PROFILE = {
    "name": "Tomato house",
    "crop_name": "Tomato",
    "stage": "vegetative",
    "temperature_min": 18.0,
    "temperature_max": 28.0,
    "temperature_reference": "Own record",
    "humidity_min": 60.0,
    "humidity_max": 80.0,
    "humidity_reference": "Own record",
}

LINKED = {
    "source_url": "https://example.test/live.json",
    "field_time": "/timestamp",
    "field_temperature": "/temperature",
    "field_humidity": "/humidity",
}


@pytest.fixture
def settings(tmp_path, monkeypatch) -> Iterator[Settings]:
    monkeypatch.setenv("PSYCHROMOL_DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    current = reload_settings()
    init_engine(current)
    create_all()
    yield current
    reload_settings()


@pytest.fixture
def session(settings: Settings) -> Iterator[Session]:
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    finally:
        session.close()


@pytest.fixture
def repository(session: Session) -> Repository:
    return Repository(session)


@pytest.fixture
def profile(repository: Repository, session: Session):
    created = repository.create_profile(**PROFILE, **LINKED)
    session.commit()
    return created


@pytest.fixture
def client(settings: Settings, monkeypatch) -> Iterator[TestClient]:
    from psychromol.api import app as app_module

    monkeypatch.setattr(app_module, "POLL_TICK_SECONDS", 3600.0)
    with TestClient(app_module.create_app()) as client:
        yield client
