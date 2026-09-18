from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from psychromol.fetcher import is_due

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)


def fake_profile(last_polled_at=None, poll_interval_seconds=60, source_url="https://example.test/a.json"):
    return SimpleNamespace(
        source_url=source_url,
        last_polled_at=last_polled_at,
        poll_interval_seconds=poll_interval_seconds,
    )


def test_a_never_polled_profile_is_due():
    assert is_due(fake_profile(), NOW) is True


def test_a_profile_is_not_due_before_its_own_interval_elapses():
    assert is_due(fake_profile(NOW - timedelta(seconds=3), 5), NOW) is False


def test_a_profile_becomes_due_once_its_own_interval_elapses():
    assert is_due(fake_profile(NOW - timedelta(seconds=5), 5), NOW) is True


def test_a_fast_profile_is_not_held_back_by_a_slow_one():
    fast = fake_profile(NOW - timedelta(seconds=1), 1)
    slow = fake_profile(NOW - timedelta(seconds=1), 3600)
    assert (is_due(fast, NOW), is_due(slow, NOW)) == (True, False)


def test_a_profile_without_a_link_is_never_due():
    assert is_due(fake_profile(source_url=None), NOW) is False
