from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from psychromol.api.app import _is_due
from psychromol.db.models import DEFAULT_POLL_INTERVAL_SECONDS

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)

def fake_profile(last_polled_at=None, poll_interval_seconds=None):
    return SimpleNamespace(
        last_polled_at=last_polled_at, poll_interval_seconds=poll_interval_seconds
    )

def test_a_never_polled_profile_is_always_due():
    assert _is_due(fake_profile(), NOW) is True

def test_a_profile_is_not_due_before_its_interval_elapses():
    profile = fake_profile(last_polled_at=NOW - timedelta(seconds=3), poll_interval_seconds=5)
    assert _is_due(profile, NOW) is False

def test_a_profile_becomes_due_once_its_interval_elapses():
    profile = fake_profile(last_polled_at=NOW - timedelta(seconds=5), poll_interval_seconds=5)
    assert _is_due(profile, NOW) is True

def test_a_profile_without_a_custom_interval_uses_the_default():
    just_under = fake_profile(
        last_polled_at=NOW - timedelta(seconds=DEFAULT_POLL_INTERVAL_SECONDS - 1)
    )
    assert _is_due(just_under, NOW) is False
    just_over = fake_profile(
        last_polled_at=NOW - timedelta(seconds=DEFAULT_POLL_INTERVAL_SECONDS + 1)
    )
    assert _is_due(just_over, NOW) is True
