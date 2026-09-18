from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db.models import Profile
from ..db.repository import Repository
from ..db.session import get_sessionmaker


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


RepositoryDep = Annotated[Repository, Depends(get_repository)]


def get_profile(profile_id: int, repository: RepositoryDep) -> Profile:
    profile = repository.get_profile(profile_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no profile {profile_id}")
    return profile


ProfileDep = Annotated[Profile, Depends(get_profile)]
