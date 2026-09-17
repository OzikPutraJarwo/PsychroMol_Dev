from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from psychromol.config import Settings, reload_settings
from psychromol.db.repository import Repository
from psychromol.db.session import create_all, get_sessionmaker, init_engine
from psychromol.defaults import DEFAULT_RULES, SAMPLE_CROP, SAMPLE_FACILITY
from psychromol.pipeline import Pipeline

NOON = datetime(2026, 9, 14, 3, 0, tzinfo=timezone.utc)

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
def pipeline(repository: Repository) -> Pipeline:
    return Pipeline(repository)

@pytest.fixture
def crop(repository: Repository):
    return repository.create_crop(**SAMPLE_CROP)

@pytest.fixture
def facility(repository: Repository):
    return repository.create_facility(**SAMPLE_FACILITY)

@pytest.fixture
def profile(repository: Repository, crop, facility):
    return repository.create_profile(
        name="Tomato House", crop_id=crop.id, facility_id=facility.id, is_default=True
    )

@pytest.fixture
def rules(repository: Repository):
    return repository.replace_rules(DEFAULT_RULES)

@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    from psychromol.api.app import create_app

    with TestClient(create_app()) as client:
        yield client

def payload(moment: datetime, temperature: float, humidity: float) -> dict:
    return {
        "timestamp": moment.isoformat(),
        "temperature": temperature,
        "humidity": humidity,
    }

def series(count: int, start: datetime = NOON) -> list[dict]:
    return [
        payload(start + timedelta(minutes=10 * index), 22.0 + index * 0.1, 70.0)
        for index in range(count)
    ]
