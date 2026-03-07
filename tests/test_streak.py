"""Tests for the streak tracking engine."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from diamond.daily.streak import (
    StreakInfo,
    StreakReport,
    Milestone,
    _init_db,
    _record_checkin,
    _compute_streak,
    _get_streak_message,
    _check_milestones,
    _pick_fun_fact,
    get_streak_report,
)


@pytest.fixture
def streak_db(tmp_path):
    db = tmp_path / "test_streak.db"
    _init_db(db)
    return db


class TestRecordCheckin:
    def test_first_checkin_is_new(self, streak_db):
        is_new, date_str = _record_checkin(streak_db, nav=500000)
        assert is_new is True
        assert date_str == datetime.now().strftime("%Y-%m-%d")

    def test_second_checkin_same_day_not_new(self, streak_db):
        _record_checkin(streak_db, nav=500000)
        is_new, _ = _record_checkin(streak_db, nav=510000)
        assert is_new is False

    def test_nav_updated_on_second_checkin(self, streak_db):
        _record_checkin(streak_db, nav=500000)
        _record_checkin(streak_db, nav=510000)
        with sqlite3.connect(streak_db) as conn:
            row = conn.execute("SELECT nav FROM checkins").fetchone()
            assert row[0] == 510000


class TestComputeStreak:
    def test_empty_db(self, streak_db):
        current, longest, total, last = _compute_streak(streak_db)
        assert current == 0
        assert total == 0

    def test_single_checkin_today(self, streak_db):
        _record_checkin(streak_db)
        current, longest, total, _ = _compute_streak(streak_db)
        assert current == 1
        assert total == 1

    def test_consecutive_days(self, streak_db):
        today = datetime.now().date()
        with sqlite3.connect(streak_db) as conn:
            for i in range(5):
                d = (today - timedelta(days=i)).isoformat()
                conn.execute(
                    "INSERT INTO checkins (date, nav, timestamp) VALUES (?, 0, ?)",
                    (d, d),
                )
        current, longest, total, _ = _compute_streak(streak_db)
        assert current == 5
        assert longest == 5
        assert total == 5

    def test_broken_streak(self, streak_db):
        today = datetime.now().date()
        with sqlite3.connect(streak_db) as conn:
            # Today and yesterday
            for i in range(2):
                d = (today - timedelta(days=i)).isoformat()
                conn.execute(
                    "INSERT INTO checkins (date, nav, timestamp) VALUES (?, 0, ?)",
                    (d, d),
                )
            # Skip a day, then 3 more
            for i in range(3, 6):
                d = (today - timedelta(days=i)).isoformat()
                conn.execute(
                    "INSERT INTO checkins (date, nav, timestamp) VALUES (?, 0, ?)",
                    (d, d),
                )
        current, longest, total, _ = _compute_streak(streak_db)
        assert current == 2  # Only today + yesterday
        assert longest == 3  # Days 3,4,5
        assert total == 5

    def test_old_checkin_no_current_streak(self, streak_db):
        old_date = (datetime.now().date() - timedelta(days=10)).isoformat()
        with sqlite3.connect(streak_db) as conn:
            conn.execute(
                "INSERT INTO checkins (date, nav, timestamp) VALUES (?, 0, ?)",
                (old_date, old_date),
            )
        current, _, total, _ = _compute_streak(streak_db)
        assert current == 0
        assert total == 1


class TestStreakMessage:
    def test_new_day_1(self):
        msg = _get_streak_message(1, is_new=True)
        assert "new" in msg.lower() or "started" in msg.lower()

    def test_new_day_7(self):
        msg = _get_streak_message(7, is_new=True)
        assert "7" in msg

    def test_already_checked_in(self):
        msg = _get_streak_message(5, is_new=False)
        assert "already" in msg.lower()

    def test_zero_streak_welcome(self):
        msg = _get_streak_message(0, is_new=False)
        assert "welcome" in msg.lower() or "start" in msg.lower()


class TestCheckMilestones:
    def test_first_trade_achieved(self, streak_db):
        milestones = _check_milestones(streak_db, nav=510000, initial=500000, streak_days=1, trade_count=1)
        first_trade = next(m for m in milestones if m.label == "First Trade")
        assert first_trade.achieved is True

    def test_5pct_return(self, streak_db):
        milestones = _check_milestones(streak_db, nav=525000, initial=500000, streak_days=1, trade_count=5)
        pct5 = next(m for m in milestones if m.label == "5% Return")
        assert pct5.achieved is True

    def test_unachieved_milestone(self, streak_db):
        milestones = _check_milestones(streak_db, nav=500000, initial=500000, streak_days=1, trade_count=0)
        first_trade = next(m for m in milestones if m.label == "First Trade")
        assert first_trade.achieved is False

    def test_milestones_persisted(self, streak_db):
        # First call achieves milestone
        _check_milestones(streak_db, nav=550000, initial=500000, streak_days=1, trade_count=1)
        # Second call should still show it achieved
        milestones = _check_milestones(streak_db, nav=490000, initial=500000, streak_days=1, trade_count=1)
        pct10 = next(m for m in milestones if m.label == "10% Return")
        assert pct10.achieved is True  # Was achieved on first call


class TestPickFunFact:
    def test_returns_string(self):
        fact = _pick_fun_fact()
        assert isinstance(fact, str)
        assert len(fact) > 10


class TestGetStreakReport:
    @patch("diamond.daily.streak._db_path")
    @patch("diamond.data.ledger.Ledger")
    def test_returns_report(self, MockLedger, mock_db_path, tmp_path):
        mock_db_path.return_value = tmp_path / "streak.db"
        MockLedger.return_value.get_portfolio_value.return_value = 500000
        MockLedger.return_value.get_cash.return_value = 500000
        MockLedger.return_value.get_initial_capital.return_value = 500000
        MockLedger.return_value.get_trades.return_value = []

        report = get_streak_report("test")
        assert isinstance(report, StreakReport)
        assert report.streak.is_new_today is True
        assert report.streak.current_streak == 1
        assert len(report.fun_fact) > 0
