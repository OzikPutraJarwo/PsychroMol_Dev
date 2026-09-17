from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from psychromol.config import get_settings
from psychromol.db.models import Base
from psychromol.db.repository import Repository
from psychromol.db.session import create_all, get_sessionmaker, init_engine
from psychromol.defaults import DEFAULT_RULES


def main() -> int:
    settings = get_settings()
    init_engine(settings)
    create_all()

    session = get_sessionmaker()()
    try:
        repository = Repository(session)
        if not repository.list_rules():
            repository.replace_rules(DEFAULT_RULES)
            session.commit()
    finally:
        session.close()

    print(f"database {settings.database_url}")
    for name in sorted(Base.metadata.tables):
        print(f"  table {name}")
    print(f"  {len(DEFAULT_RULES)} default rules available")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
