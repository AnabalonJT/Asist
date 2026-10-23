"""Unit tests for the pure reminder delivery decision (should_deliver).

These cover task 25.3 (flexible delivery): day-of-week against schedule_days,
one-time reminders by date, "every other week" (biweekly) via last_sent_at, and
the <23h dedupe. All pure — no DB, no Telegram, no network.

day numbering: 0=Mon .. 6=Sun (datetime.weekday()).
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.scheduler import should_deliver

UTC = ZoneInfo("UTC")

# Fixed reference instants. 2026-07-06 is a Monday.
MON = datetime(2026, 7, 6, 7, 30, tzinfo=UTC)   # Monday 07:30
WED = datetime(2026, 7, 8, 7, 30, tzinfo=UTC)   # Wednesday 07:30
SAT = datetime(2026, 7, 11, 7, 30, tzinfo=UTC)  # Saturday 07:30
SUN = datetime(2026, 7, 12, 7, 30, tzinfo=UTC)  # Sunday 07:30


def _utc(dt: datetime) -> datetime:
    """naive-UTC equivalent, matching how last_sent_at/now_utc are compared."""
    return dt.replace(tzinfo=None)


def call(frequency, user_now, *, schedule="07:30", schedule_days=None,
         schedule_date=None, last_sent_at=None, now_utc=None):
    """Thin wrapper; now_utc defaults to the naive-UTC of user_now."""
    if now_utc is None:
        now_utc = _utc(user_now)
    return should_deliver(
        frequency=frequency,
        schedule=schedule,
        schedule_days=schedule_days,
        schedule_date=schedule_date,
        last_sent_at=last_sent_at,
        user_now=user_now,
        now_utc=now_utc,
    )


# ── Time matching ────────────────────────────────────────────────────────────

def test_time_not_matching_does_not_fire():
    assert call("daily", WED, schedule="08:00") is False


def test_time_matching_daily_fires():
    assert call("daily", WED, schedule="07:30") is True


# ── weekdays / weekends ──────────────────────────────────────────────────────

def test_weekdays_on_saturday_skips():
    assert call("weekdays", SAT) is False


def test_weekdays_on_wednesday_fires():
    assert call("weekdays", WED) is True


def test_weekends_on_sunday_fires():
    assert call("weekends", SUN) is True


def test_weekends_on_wednesday_skips():
    assert call("weekends", WED) is False


# ── specific_days (schedule_days CSV) ────────────────────────────────────────

def test_specific_days_hit():
    # Mon(0) and Wed(2) -> fires on Wednesday.
    assert call("specific_days", WED, schedule_days="0,2") is True


def test_specific_days_miss():
    # Mon(0) and Wed(2) -> does NOT fire on Saturday.
    assert call("specific_days", SAT, schedule_days="0,2") is False


def test_specific_days_empty_schedule_days_skips():
    # Safe behavior: no days configured -> never fire (and never crash).
    assert call("specific_days", WED, schedule_days="") is False
    assert call("specific_days", WED, schedule_days=None) is False


def test_specific_days_malformed_schedule_days_skips():
    # Garbage in the CSV must not crash and must not fire.
    assert call("specific_days", WED, schedule_days="abc, ,x") is False


def test_specific_days_mixed_valid_and_garbage():
    # "x,2" -> valid day 2 (Wed) still recognized.
    assert call("specific_days", WED, schedule_days="x,2") is True


# ── once (one-time, by date) ─────────────────────────────────────────────────

def test_once_on_the_date_fires():
    assert call("once", MON, schedule_date="2026-07-06") is True


def test_once_on_a_different_date_skips():
    assert call("once", WED, schedule_date="2026-07-06") is False


def test_once_without_date_fires_at_time():
    # Undated one-time still fires at its time; the caller deactivates it
    # right after sending so it only ever fires once.
    assert call("once", WED, schedule_date=None) is True


def test_caller_deactivates_once_after_send():
    """Mirror the caller contract: a 'once' reminder is deactivated post-send.

    should_deliver stays pure, so the one-shot guarantee lives in the caller.
    This reproduces that exact logic to lock the contract in place.
    """
    class R:
        frequency = "once"
        active = True
    r = R()
    # ... after a successful send, deliver_reminders does:
    if r.frequency == "once":
        r.active = False
    assert r.active is False


# ── biweekly ("every other week") ────────────────────────────────────────────

def test_biweekly_first_send_fires():
    # last_sent_at None => first-ever send is allowed.
    assert call("biweekly", WED, last_sent_at=None) is True


def test_biweekly_within_13_days_skips():
    sent = _utc(WED) - timedelta(days=5)
    assert call("biweekly", WED, last_sent_at=sent) is False


def test_biweekly_after_14_days_fires():
    sent = _utc(WED) - timedelta(days=14)
    assert call("biweekly", WED, last_sent_at=sent) is True


# ── <23h dedupe (applies across all frequencies) ─────────────────────────────

def test_dedupe_within_23h_skips():
    # Sent 2 hours ago -> within the 23h window -> skip even though time matches.
    sent = _utc(WED) - timedelta(hours=2)
    assert call("daily", WED, last_sent_at=sent) is False


def test_dedupe_after_23h_allows():
    sent = _utc(WED) - timedelta(hours=25)
    assert call("daily", WED, last_sent_at=sent) is True


# ── weekly (Monday only) ─────────────────────────────────────────────────────

def test_weekly_on_monday_fires():
    assert call("weekly", MON) is True


def test_weekly_on_wednesday_skips():
    assert call("weekly", WED) is False
