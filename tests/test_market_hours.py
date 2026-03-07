"""Tests for NSE market hours utility functions."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from diamond.data.market import (
    IST,
    NSE_HOLIDAYS_2026,
    is_market_open,
    next_market_open,
)


class TestIsMarketOpen:
    """Tests for is_market_open()."""

    def test_open_during_trading_hours(self):
        """Market should be open on a weekday during trading hours."""
        # Wednesday 2026-03-04 at 10:00 AM IST (not a holiday)
        dt = datetime(2026, 3, 4, 10, 0, 0, tzinfo=IST)
        assert is_market_open(dt) is True

    def test_open_at_exact_open_time(self):
        """Market should be open at exactly 9:15 AM IST."""
        dt = datetime(2026, 3, 4, 9, 15, 0, tzinfo=IST)
        assert is_market_open(dt) is True

    def test_open_at_exact_close_time(self):
        """Market should be open at exactly 3:30 PM IST."""
        dt = datetime(2026, 3, 4, 15, 30, 0, tzinfo=IST)
        assert is_market_open(dt) is True

    def test_closed_before_open(self):
        """Market should be closed before 9:15 AM."""
        dt = datetime(2026, 3, 4, 9, 14, 59, tzinfo=IST)
        assert is_market_open(dt) is False

    def test_closed_after_close(self):
        """Market should be closed after 3:30 PM."""
        dt = datetime(2026, 3, 4, 15, 30, 1, tzinfo=IST)
        assert is_market_open(dt) is False

    def test_closed_on_saturday(self):
        """Market should be closed on Saturday."""
        # 2026-03-07 is a Saturday
        dt = datetime(2026, 3, 7, 12, 0, 0, tzinfo=IST)
        assert is_market_open(dt) is False

    def test_closed_on_sunday(self):
        """Market should be closed on Sunday."""
        dt = datetime(2026, 3, 8, 12, 0, 0, tzinfo=IST)
        assert is_market_open(dt) is False

    def test_closed_on_republic_day(self):
        """Market should be closed on Republic Day (Jan 26)."""
        # 2026-01-26 is a Monday
        dt = datetime(2026, 1, 26, 12, 0, 0, tzinfo=IST)
        assert is_market_open(dt) is False

    def test_closed_on_holi(self):
        """Market should be closed on Holi."""
        dt = datetime(2026, 3, 10, 12, 0, 0, tzinfo=IST)
        assert is_market_open(dt) is False

    def test_closed_on_independence_day(self):
        """Market should be closed on Independence Day."""
        dt = datetime(2026, 8, 15, 12, 0, 0, tzinfo=IST)
        assert is_market_open(dt) is False

    def test_closed_on_diwali(self):
        """Market should be closed on Diwali."""
        dt = datetime(2026, 11, 9, 12, 0, 0, tzinfo=IST)
        assert is_market_open(dt) is False

    def test_closed_on_christmas(self):
        """Market should be closed on Christmas."""
        dt = datetime(2026, 12, 25, 12, 0, 0, tzinfo=IST)
        assert is_market_open(dt) is False

    def test_naive_datetime_treated_as_ist(self):
        """Naive datetime should be treated as IST."""
        dt = datetime(2026, 3, 4, 12, 0, 0)  # No tzinfo
        assert is_market_open(dt) is True

    def test_utc_timezone_converted_to_ist(self):
        """UTC time should be converted to IST (UTC+5:30)."""
        utc = ZoneInfo("UTC")
        # 4:00 AM UTC = 9:30 AM IST (market open)
        dt = datetime(2026, 3, 4, 4, 0, 0, tzinfo=utc)
        assert is_market_open(dt) is True

        # 11:00 AM UTC = 4:30 PM IST (market closed)
        dt = datetime(2026, 3, 4, 11, 0, 0, tzinfo=utc)
        assert is_market_open(dt) is False

    def test_open_at_midday(self):
        """Market should be open at noon on a regular weekday."""
        dt = datetime(2026, 3, 5, 12, 0, 0, tzinfo=IST)  # Thursday
        assert is_market_open(dt) is True

    def test_closed_late_evening(self):
        """Market should be closed late in the evening."""
        dt = datetime(2026, 3, 4, 20, 0, 0, tzinfo=IST)
        assert is_market_open(dt) is False


class TestNextMarketOpen:
    """Tests for next_market_open()."""

    def test_next_open_from_weekday_evening(self):
        """After market close on a weekday, next open is next business day."""
        # Wednesday evening -> Thursday 9:15
        dt = datetime(2026, 3, 4, 18, 0, 0, tzinfo=IST)
        result = next_market_open(dt)
        assert result.date() == date(2026, 3, 5)
        assert result.hour == 9
        assert result.minute == 15

    def test_next_open_from_friday_evening(self):
        """After Friday close, next open is Monday."""
        # Friday 2026-03-06 evening -> Monday 2026-03-09
        dt = datetime(2026, 3, 6, 18, 0, 0, tzinfo=IST)
        result = next_market_open(dt)
        assert result.date() == date(2026, 3, 9)
        assert result.weekday() == 0  # Monday

    def test_next_open_from_saturday(self):
        """From Saturday, next open is Monday."""
        dt = datetime(2026, 3, 7, 12, 0, 0, tzinfo=IST)
        result = next_market_open(dt)
        assert result.date() == date(2026, 3, 9)

    def test_next_open_from_sunday(self):
        """From Sunday, next open is Monday."""
        dt = datetime(2026, 3, 8, 12, 0, 0, tzinfo=IST)
        result = next_market_open(dt)
        assert result.date() == date(2026, 3, 9)

    def test_next_open_skips_holiday(self):
        """Next open skips over a holiday."""
        # Monday 2026-03-09 evening, Tuesday 2026-03-10 is Holi
        dt = datetime(2026, 3, 9, 18, 0, 0, tzinfo=IST)
        result = next_market_open(dt)
        assert result.date() == date(2026, 3, 11)  # Wednesday

    def test_next_open_from_holiday(self):
        """From a holiday date, next open is next business day."""
        dt = datetime(2026, 3, 10, 12, 0, 0, tzinfo=IST)  # Holi
        result = next_market_open(dt)
        assert result.date() == date(2026, 3, 11)

    def test_next_open_before_market_open_same_day(self):
        """Before 9:15 on a trading day, next open is same day."""
        dt = datetime(2026, 3, 4, 7, 0, 0, tzinfo=IST)  # Wednesday 7 AM
        result = next_market_open(dt)
        assert result.date() == date(2026, 3, 4)
        assert result.hour == 9
        assert result.minute == 15

    def test_next_open_during_market_hours_is_next_day(self):
        """During market hours, next open is the following business day."""
        dt = datetime(2026, 3, 4, 12, 0, 0, tzinfo=IST)
        result = next_market_open(dt)
        assert result.date() == date(2026, 3, 5)

    def test_next_open_returns_ist_timezone(self):
        """Result should always be timezone-aware in IST."""
        dt = datetime(2026, 3, 4, 18, 0, 0, tzinfo=IST)
        result = next_market_open(dt)
        assert result.tzinfo is not None
        assert str(result.tzinfo) == "Asia/Kolkata"

    def test_next_open_skips_consecutive_holidays(self):
        """Should skip consecutive holidays and weekends."""
        # 2026-03-30 Mon (Eid) + 2026-03-31 Tue (Eid) -> April 1 Wed
        dt = datetime(2026, 3, 29, 18, 0, 0, tzinfo=IST)  # Sunday
        result = next_market_open(dt)
        assert result.date() == date(2026, 4, 1)

    def test_next_open_from_naive_datetime(self):
        """Naive datetime should be treated as IST."""
        dt = datetime(2026, 3, 4, 18, 0, 0)  # No tzinfo
        result = next_market_open(dt)
        assert result.date() == date(2026, 3, 5)


class TestHolidayList:
    """Tests for the holiday list itself."""

    def test_holidays_are_date_objects(self):
        """All holidays should be date objects."""
        for h in NSE_HOLIDAYS_2026:
            assert isinstance(h, date)

    def test_holidays_are_in_2026(self):
        """All holidays should be in 2026."""
        for h in NSE_HOLIDAYS_2026:
            assert h.year == 2026

    def test_republic_day_in_holidays(self):
        assert date(2026, 1, 26) in NSE_HOLIDAYS_2026

    def test_independence_day_in_holidays(self):
        assert date(2026, 8, 15) in NSE_HOLIDAYS_2026

    def test_gandhi_jayanti_in_holidays(self):
        assert date(2026, 10, 2) in NSE_HOLIDAYS_2026

    def test_christmas_in_holidays(self):
        assert date(2026, 12, 25) in NSE_HOLIDAYS_2026

    def test_reasonable_number_of_holidays(self):
        """NSE typically has 14-18 holidays per year."""
        assert 14 <= len(NSE_HOLIDAYS_2026) <= 22
