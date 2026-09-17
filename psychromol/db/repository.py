from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .models import Crop, Facility, Profile, Reading, Rule


class Repository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_crops(self) -> list[Crop]:
        return list(self.session.scalars(select(Crop).order_by(Crop.name)))

    def get_crop(self, crop_id: int) -> Crop | None:
        return self.session.get(Crop, crop_id)

    def create_crop(self, **fields: Any) -> Crop:
        crop = Crop(**fields)
        self.session.add(crop)
        self.session.flush()
        return crop

    def update_crop(self, crop_id: int, **fields: Any) -> Crop | None:
        crop = self.session.get(Crop, crop_id)
        if crop is None:
            return None
        for key, value in fields.items():
            setattr(crop, key, value)
        self.session.flush()
        return crop

    def delete_crop(self, crop_id: int) -> bool:
        crop = self.session.get(Crop, crop_id)
        if crop is None:
            return False
        self.session.delete(crop)
        self.session.flush()
        return True

    def crop_in_use(self, crop_id: int) -> int:
        return int(
            self.session.scalar(
                select(func.count()).select_from(Profile).where(Profile.crop_id == crop_id)
            )
            or 0
        )

    def list_facilities(self) -> list[Facility]:
        return list(self.session.scalars(select(Facility).order_by(Facility.name)))

    def get_facility(self, facility_id: int) -> Facility | None:
        return self.session.get(Facility, facility_id)

    def create_facility(self, **fields: Any) -> Facility:
        facility = Facility(**fields)
        self.session.add(facility)
        self.session.flush()
        return facility

    def update_facility(self, facility_id: int, **fields: Any) -> Facility | None:
        facility = self.session.get(Facility, facility_id)
        if facility is None:
            return None
        for key, value in fields.items():
            setattr(facility, key, value)
        self.session.flush()
        return facility

    def delete_facility(self, facility_id: int) -> bool:
        facility = self.session.get(Facility, facility_id)
        if facility is None:
            return False
        self.session.delete(facility)
        self.session.flush()
        return True

    def facility_in_use(self, facility_id: int) -> int:
        return int(
            self.session.scalar(
                select(func.count())
                .select_from(Profile)
                .where(Profile.facility_id == facility_id)
            )
            or 0
        )

    def list_profiles(self) -> list[Profile]:
        return list(
            self.session.scalars(
                select(Profile).order_by(Profile.is_default.desc(), Profile.name)
            ).unique()
        )

    def get_profile(self, profile_id: int) -> Profile | None:
        return self.session.get(Profile, profile_id)

    def default_profile(self) -> Profile | None:
        found = self.session.scalars(
            select(Profile).where(Profile.is_default.is_(True)).limit(1)
        ).unique().first()
        if found is not None:
            return found
        return self.session.scalars(
            select(Profile).order_by(Profile.id).limit(1)
        ).unique().first()

    def create_profile(self, **fields: Any) -> Profile:
        profile = Profile(**fields)
        self.session.add(profile)
        self.session.flush()
        if profile.is_default:
            self._clear_other_defaults(profile.id)
        elif self.session.scalar(select(func.count()).select_from(Profile)) == 1:
            profile.is_default = True
        self.session.flush()
        return profile

    def update_profile(self, profile_id: int, **fields: Any) -> Profile | None:
        profile = self.session.get(Profile, profile_id)
        if profile is None:
            return None
        for key, value in fields.items():
            setattr(profile, key, value)
        self.session.flush()
        if profile.is_default:
            self._clear_other_defaults(profile.id)
        return profile

    def delete_profile(self, profile_id: int) -> bool:
        profile = self.session.get(Profile, profile_id)
        if profile is None:
            return False
        was_default = profile.is_default
        crop_id = profile.crop_id
        facility_id = profile.facility_id
        self.session.execute(delete(Reading).where(Reading.profile_id == profile_id))
        self.session.delete(profile)
        self.session.flush()
        if not self.crop_in_use(crop_id):
            crop = self.session.get(Crop, crop_id)
            if crop is not None:
                self.session.delete(crop)
        if not self.facility_in_use(facility_id):
            facility = self.session.get(Facility, facility_id)
            if facility is not None:
                self.session.delete(facility)
        self.session.flush()
        if was_default:
            replacement = self.session.scalars(
                select(Profile).order_by(Profile.id).limit(1)
            ).unique().first()
            if replacement is not None:
                replacement.is_default = True
                self.session.flush()
        return True

    def _clear_other_defaults(self, keep_id: int) -> None:
        for other in self.session.scalars(
            select(Profile).where(Profile.id != keep_id, Profile.is_default.is_(True))
        ).unique():
            other.is_default = False

    def mark_polled(
        self, profile_id: int, moment: datetime, error: str | None = None
    ) -> None:
        profile = self.session.get(Profile, profile_id)
        if profile is None:
            return
        profile.last_polled_at = moment
        profile.last_poll_error = error
        self.session.flush()

    def add_reading(self, **fields: Any) -> Reading | None:
        existing = self.session.scalar(
            select(Reading).where(
                Reading.profile_id == fields["profile_id"],
                Reading.measured_at == fields["measured_at"],
            )
        )
        if existing is not None:
            return None
        reading = Reading(**fields)
        self.session.add(reading)
        self.session.flush()
        return reading

    def latest_reading(self, profile_id: int) -> Reading | None:
        return self.session.scalar(
            select(Reading)
            .where(Reading.profile_id == profile_id, Reading.error.is_(None))
            .order_by(Reading.measured_at.desc())
            .limit(1)
        )

    def readings_between(
        self, profile_id: int, start: datetime, end: datetime, limit: int = 20000
    ) -> list[Reading]:
        return list(
            self.session.scalars(
                select(Reading)
                .where(
                    Reading.profile_id == profile_id,
                    Reading.measured_at >= start,
                    Reading.measured_at <= end,
                )
                .order_by(Reading.measured_at)
                .limit(limit)
            )
        )

    def recent_readings(self, profile_id: int, hours: float = 24.0) -> list[Reading]:
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=hours)
        return self.readings_between(profile_id, start, end)

    def reading_count(self, profile_id: int) -> int:
        return int(
            self.session.scalar(
                select(func.count())
                .select_from(Reading)
                .where(Reading.profile_id == profile_id)
            )
            or 0
        )

    def reading_span(self, profile_id: int) -> tuple[datetime | None, datetime | None]:
        row = self.session.execute(
            select(func.min(Reading.measured_at), func.max(Reading.measured_at)).where(
                Reading.profile_id == profile_id
            )
        ).first()
        return (row[0], row[1]) if row else (None, None)

    def list_rules(self, enabled_only: bool = False) -> list[Rule]:
        statement = select(Rule).order_by(Rule.priority, Rule.id)
        if enabled_only:
            statement = statement.where(Rule.enabled.is_(True))
        return list(self.session.scalars(statement))

    def get_rule(self, rule_id: int) -> Rule | None:
        return self.session.get(Rule, rule_id)

    def create_rule(self, **fields: Any) -> Rule:
        rule = Rule(**fields)
        self.session.add(rule)
        self.session.flush()
        return rule

    def update_rule(self, rule_id: int, **fields: Any) -> Rule | None:
        rule = self.session.get(Rule, rule_id)
        if rule is None:
            return None
        for key, value in fields.items():
            setattr(rule, key, value)
        self.session.flush()
        return rule

    def delete_rule(self, rule_id: int) -> bool:
        rule = self.session.get(Rule, rule_id)
        if rule is None:
            return False
        self.session.delete(rule)
        self.session.flush()
        return True

    def replace_rules(self, rules: Sequence[dict[str, Any]]) -> list[Rule]:
        self.session.execute(delete(Rule))
        created = [Rule(**entry) for entry in rules]
        self.session.add_all(created)
        self.session.flush()
        return created
