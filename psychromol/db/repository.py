from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, or_, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, aliased

from .models import Profile, Reading, Rule

CONDITION_KEYS = ("temperature", "humidity", "vpd")


def _rule_columns(fields: dict[str, Any]) -> dict[str, Any]:
    columns = {key: value for key, value in fields.items() if key != "conditions"}
    conditions = fields.get("conditions") or {}
    for key in CONDITION_KEYS:
        columns[key] = conditions.get(key, "ANY")
    return columns


class Repository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_profiles(self) -> list[Profile]:
        return list(self.session.scalars(select(Profile).order_by(Profile.name, Profile.id)))

    def get_profile(self, profile_id: int) -> Profile | None:
        return self.session.get(Profile, profile_id)

    def create_profile(self, **fields: Any) -> Profile:
        profile = Profile(**fields)
        self.session.add(profile)
        self.session.flush()
        return profile

    def update_profile(self, profile: Profile, **fields: Any) -> Profile:
        for key, value in fields.items():
            setattr(profile, key, value)
        self.session.flush()
        return profile

    def delete_profile(self, profile: Profile) -> None:
        self.session.execute(delete(Rule).where(Rule.profile_id == profile.id))
        self.session.execute(delete(Reading).where(Reading.profile_id == profile.id))
        self.session.delete(profile)
        self.session.flush()

    def mark_polled(self, profile: Profile, moment: datetime, error: str | None) -> None:
        profile.last_polled_at = moment
        profile.last_poll_error = error
        self.session.flush()

    def add_reading(self, profile_id: int, **fields: Any) -> tuple[Reading, bool]:
        inserted = self.session.execute(
            sqlite_insert(Reading)
            .values(profile_id=profile_id, **fields)
            .on_conflict_do_nothing(index_elements=["profile_id", "measured_at"])
        )
        reading = self.session.scalar(
            select(Reading).where(
                Reading.profile_id == profile_id, Reading.measured_at == fields["measured_at"]
            )
        )
        assert reading is not None
        return reading, bool(inserted.rowcount)

    def latest_reading(self, profile_id: int) -> Reading | None:
        return self.session.scalar(
            select(Reading)
            .where(Reading.profile_id == profile_id)
            .order_by(Reading.measured_at.desc())
            .limit(1)
        )

    def _range(self, query, profile_id: int, start: datetime | None, end: datetime | None):
        query = query.where(Reading.profile_id == profile_id)
        if start is not None:
            query = query.where(Reading.measured_at >= start)
        if end is not None:
            query = query.where(Reading.measured_at <= end)
        return query

    def count_readings(self, profile_id: int, start: datetime | None, end: datetime | None) -> int:
        query = self._range(select(func.count()).select_from(Reading), profile_id, start, end)
        return int(self.session.scalar(query) or 0)

    def readings(
        self,
        profile_id: int,
        start: datetime | None,
        end: datetime | None,
        limit: int,
        offset: int,
        newest_first: bool,
    ) -> list[Reading]:
        order = Reading.measured_at.desc() if newest_first else Reading.measured_at.asc()
        query = self._range(select(Reading), profile_id, start, end).order_by(order)
        return list(self.session.scalars(query.limit(limit).offset(offset)))

    def thinned_readings(
        self, profile_id: int, start: datetime | None, end: datetime | None, max_points: int
    ) -> list[Reading]:
        total = self.count_readings(profile_id, start, end)
        if total <= max_points:
            return self.readings(profile_id, start, end, total or 1, 0, newest_first=False)
        step = -(-total // max_points)
        numbered = self._range(
            select(
                Reading,
                func.row_number().over(order_by=Reading.measured_at).label("position"),
            ),
            profile_id,
            start,
            end,
        ).subquery()
        row = aliased(Reading, numbered)
        query = (
            select(row)
            .where(or_((numbered.c.position - 1) % step == 0, numbered.c.position == total))
            .order_by(numbered.c.measured_at)
        )
        return list(self.session.scalars(query))

    def list_rules(self, profile_id: int) -> list[Rule]:
        return list(
            self.session.scalars(
                select(Rule).where(Rule.profile_id == profile_id).order_by(Rule.priority, Rule.id)
            )
        )

    def get_rule(self, rule_id: int) -> Rule | None:
        return self.session.get(Rule, rule_id)

    def create_rule(self, profile_id: int, **fields: Any) -> Rule:
        rule = Rule(profile_id=profile_id, **_rule_columns(fields))
        self.session.add(rule)
        self.session.flush()
        return rule

    def update_rule(self, rule: Rule, **fields: Any) -> Rule:
        for key, value in _rule_columns(fields).items():
            setattr(rule, key, value)
        self.session.flush()
        return rule

    def delete_rule(self, rule: Rule) -> None:
        self.session.delete(rule)
        self.session.flush()

    def replace_rules(self, profile: Profile, rules: Sequence[dict[str, Any]]) -> list[Rule]:
        self.session.execute(delete(Rule).where(Rule.profile_id == profile.id))
        for fields in rules:
            self.create_rule(profile.id, **fields)
        profile.rules_seeded = True
        self.session.flush()
        return self.list_rules(profile.id)
