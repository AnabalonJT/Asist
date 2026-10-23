"""Unit tests for the shared reminder schedule formatter
(``app.services.reminder_format``).

All helpers are pure (no DB, no Telegram), so these tests exercise
``format_reminder_schedule`` and ``format_reminder_line`` directly across every
frequency: daily, weekdays, weekends, specific_days, once (with date/time),
biweekly, and weekly. Day numbering is 0 = Mon .. 6 = Sun → Lun..Dom.

User-facing text is Spanish; identifiers and comments are English.
"""
import pytest

from app.services.reminder_format import (
    format_reminder_schedule,
    format_reminder_line,
    format_reminder_from_model,
)


class TestFormatReminderSchedule:
    def test_daily(self):
        assert format_reminder_schedule("daily", schedule="07:30") == "Todos los días"

    def test_weekdays(self):
        assert format_reminder_schedule("weekdays", schedule="08:00") == "Lun a Vie"

    def test_weekends(self):
        assert format_reminder_schedule("weekends", schedule="10:00") == "Sáb y Dom"

    def test_specific_days_mon_wed(self):
        # "0,2" → Lun y Mié
        assert (
            format_reminder_schedule("specific_days", schedule="07:30", schedule_days="0,2")
            == "Lun y Mié"
        )

    def test_specific_days_three_days(self):
        assert (
            format_reminder_schedule("specific_days", schedule_days="0,2,4")
            == "Lun y Mié y Vie"
        )

    def test_specific_days_with_spaces_and_sunday(self):
        assert (
            format_reminder_schedule("specific_days", schedule_days="4, 6")
            == "Vie y Dom"
        )

    def test_specific_days_empty_falls_back(self):
        assert format_reminder_schedule("specific_days", schedule_days=None) == "Días específicos"

    def test_once_with_date_and_time(self):
        # "6 Jul 08:00" — leading zero stripped from day, Spanish short month.
        assert (
            format_reminder_schedule("once", schedule="08:00", schedule_date="2026-07-06")
            == "6 Jul 08:00"
        )

    def test_once_without_time(self):
        assert format_reminder_schedule("once", schedule_date="2026-12-25") == "25 Dic"

    def test_once_without_date(self):
        assert format_reminder_schedule("once", schedule="09:00") == "09:00"

    def test_once_no_info(self):
        assert format_reminder_schedule("once") == "una vez"

    def test_once_malformed_date_preserved(self):
        assert format_reminder_schedule("once", schedule_date="next week", schedule="08:00") == "next week 08:00"

    def test_biweekly(self):
        assert format_reminder_schedule("biweekly", schedule="18:00") == "Cada 2 semanas"

    def test_weekly(self):
        assert format_reminder_schedule("weekly", schedule="20:00") == "Semanal"

    def test_unknown_frequency_passthrough(self):
        assert format_reminder_schedule("something_new") == "something_new"


class TestFormatReminderLine:
    def test_recurring_specific_days_line(self):
        line = format_reminder_line(
            "Correr", "specific_days", schedule="07:30", schedule_days="0,2"
        )
        assert line == "🔁 Correr — 07:30 (Lun y Mié)"

    def test_recurring_daily_line(self):
        line = format_reminder_line("Meditar", "daily", schedule="08:00")
        assert line == "🔁 Meditar — 08:00 (Todos los días)"

    def test_one_time_line_is_distinct(self):
        line = format_reminder_line(
            "Ir al Dr", "once", schedule="08:00", schedule_date="2026-07-06"
        )
        # One-time uses 📅 and a "(una vez)" tag to distinguish from recurring.
        assert line == "📅 Ir al Dr — 6 Jul 08:00 (una vez)"
        assert "🔁" not in line

    def test_recurring_without_schedule(self):
        line = format_reminder_line("Beber agua", "daily")
        assert line == "🔁 Beber agua — Todos los días"


class TestFormatReminderFromModel:
    def test_reads_model_attributes(self):
        class FakeReminder:
            message = "Gym"
            frequency = "weekends"
            schedule = "10:00"
            schedule_days = None
            schedule_date = None

        assert format_reminder_from_model(FakeReminder()) == "🔁 Gym — 10:00 (Sáb y Dom)"

    def test_reads_model_one_time(self):
        class FakeReminder:
            message = "Dentista"
            frequency = "once"
            schedule = "09:30"
            schedule_days = None
            schedule_date = "2026-03-15"

        assert format_reminder_from_model(FakeReminder()) == "📅 Dentista — 15 Mar 09:30 (una vez)"
