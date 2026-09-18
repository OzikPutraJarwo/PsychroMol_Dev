from __future__ import annotations

import math
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from psychromol.config import get_settings
from psychromol.db.repository import Repository
from psychromol.db.session import create_all, get_sessionmaker, init_engine

DAYS = 7
STEP_MINUTES = 10

EXAMPLE = {
    "name": "Example · synthetic data",
    "crop_name": "Tomato",
    "stage": "vegetative",
    "temperature_min": 17.0,
    "temperature_max": 27.0,
    "temperature_reference": (
        "Shamshiri et al. (2018), p. 289. “Greenhouse crops are mostly warm-season crops which are "
        "adapted to optimal air temperatures between 17-27°C, with the lower and upper marginal "
        "temperature of 10 and 35°C (Kittas et al., 2005).”"
    ),
    "humidity_min": 60.0,
    "humidity_max": 90.0,
    "humidity_reference": (
        "Shamshiri et al. (2018), p. 290. “For most greenhouse tomato varieties, relative humidity "
        "range between 60-90% is considered appropriate by ASABE (2015) standards.”"
    ),
}


def synthetic(now: datetime) -> list[dict]:
    random.seed(20260917)
    start = now - timedelta(days=DAYS)
    rows = []
    for index in range(int(DAYS * 24 * 60 / STEP_MINUTES)):
        moment = start + timedelta(minutes=index * STEP_MINUTES)
        daily = math.sin((moment.hour + moment.minute / 60 - 9) / 24 * 2 * math.pi)
        temperature = 22.5 + 6.5 * daily + random.gauss(0, 0.35)
        humidity = min(97.0, max(32.0, 72.0 - 17.0 * daily + random.gauss(0, 2.0)))
        rows.append(
            {
                "measured_at": moment,
                "received_at": moment,
                "temperature_c": round(temperature, 2),
                "relative_humidity_percent": round(humidity, 1),
                "pressure_kpa": None,
            }
        )
    return rows


def main() -> int:
    settings = get_settings()
    init_engine(settings)
    create_all()
    session = get_sessionmaker()()
    try:
        repository = Repository(session)
        profile = repository.create_profile(**EXAMPLE)
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        rows = synthetic(now)
        for row in rows:
            repository.add_reading(profile.id, **row)
        session.commit()
        print(f"profile {profile.id} “{profile.name}” with {len(rows)} synthetic readings")
        print("its default rules are added the first time it is opened in the browser")
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
