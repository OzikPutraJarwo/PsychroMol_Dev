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
from psychromol.defaults import DEFAULT_RULES, SAMPLE_CROP, SAMPLE_FACILITY
from psychromol.ingest import Sample
from psychromol.pipeline import Pipeline

DAYS = 7
STEP_MINUTES = 10

def build_samples(now: datetime) -> list[Sample]:
    random.seed(20260914)
    samples: list[Sample] = []
    start = now - timedelta(days=DAYS)
    steps = int(DAYS * 24 * 60 / STEP_MINUTES)
    for index in range(steps):
        moment = start + timedelta(minutes=index * STEP_MINUTES)
        hour = moment.hour + moment.minute / 60.0
        day = index * STEP_MINUTES / (24 * 60)

        daily = math.sin((hour - 9.0) / 24.0 * 2 * math.pi)
        seasonal = 0.8 * math.sin(day / DAYS * 2 * math.pi)
        temperature = 22.5 + 6.5 * daily + seasonal + random.gauss(0, 0.35)
        humidity = 72.0 - 17.0 * daily + random.gauss(0, 2.0)
        humidity = min(97.0, max(32.0, humidity))
        samples.append(Sample(moment, round(temperature, 2), round(humidity, 1)))
    return samples

def main() -> int:
    settings = get_settings()
    init_engine(settings)
    create_all()

    session = get_sessionmaker()()
    try:
        repository = Repository(session)
        if not repository.list_rules():
            repository.replace_rules(DEFAULT_RULES)

        crop = repository.create_crop(**SAMPLE_CROP)
        facility = repository.create_facility(**SAMPLE_FACILITY)
        profile = repository.create_profile(
            name=f"{crop.name} · {facility.name}",
            crop_id=crop.id,
            facility_id=facility.id,
            is_default=True,
        )

        pipeline = Pipeline(repository)
        result = pipeline.store_samples(profile, build_samples(datetime.now(timezone.utc)))
        session.commit()

        print(f"profile  {profile.name} (id {profile.id})")
        print(f"crop     {crop.name}  {crop.temperature_min}-{crop.temperature_max} °C, "
              f"{crop.humidity_min}-{crop.humidity_max} %")
        print(f"facility {facility.name}  {len(facility.equipment)} items, "
              f"{facility.altitude_m:.0f} m")
        print(f"rules    {len(repository.list_rules())}")
        print(f"readings {result.stored} over the last {DAYS} days")
        print()
        print("Start the server with:  .venv/bin/python -m psychromol.api")
    finally:
        session.close()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
