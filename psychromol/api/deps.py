from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..db.repository import Repository
from ..db.session import get_sessionmaker
from ..pipeline import Pipeline


def get_db() -> Iterator[Session]:
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

def get_repository(session: Annotated[Session, Depends(get_db)]) -> Repository:
    return Repository(session)

def get_pipeline(
    repository: Annotated[Repository, Depends(get_repository)],
) -> Pipeline:
    return Pipeline(repository)

SessionDep = Annotated[Session, Depends(get_db)]
RepositoryDep = Annotated[Repository, Depends(get_repository)]
PipelineDep = Annotated[Pipeline, Depends(get_pipeline)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
