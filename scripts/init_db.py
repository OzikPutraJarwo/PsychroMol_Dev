from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from psychromol.config import get_settings
from psychromol.db.models import Base
from psychromol.db.session import create_all, init_engine


def main() -> int:
    settings = get_settings()
    init_engine(settings)
    create_all()
    print(f"database {settings.database_url}")
    for name in sorted(Base.metadata.tables):
        print(f"  table {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
