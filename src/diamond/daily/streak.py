"""Streak tracking and portfolio milestones.

Tracks daily check-ins, portfolio milestones, and generates weekly/monthly
performance recaps. State persisted in a small SQLite database.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class StreakInfo:
    """Current streak and check-in stats."""

    current_streak: int
    longest_streak: int
    total_checkins: int
    last_checkin: str  # YYYY-MM-DD
    is_new_today: bool  # First check-in today
    checkin_message: str  # "Day 5! Keep it up"


@dataclass
class Milestone:
    """A portfolio milestone."""

    label: str
    achieved: bool
    value: str
    date_achieved: str = ""


@dataclass
class PerformanceRecap:
    """Weekly or monthly recap."""

    period: str  # "This Week" / "This Month"
    start_nav: float
    end_nav: float
    return_pct: float
    trades_count: int
    best_day_pct: float
    worst_day_pct: float


@dataclass
class StreakReport:
    """Full gamification report."""

    streak: StreakInfo
    milestones: list[Milestone] = field(default_factory=list)
    recap: PerformanceRecap | None = None
    fun_fact: str = ""


# ---------------------------------------------------------------------------
# SQLite persistence
# ---------------------------------------------------------------------------


def _db_path() -> Path:
    from diamond.config import get_config

    path = Path(get_config().data_dir) / "streak.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _init_db(db: Path) -> None:
    with sqlite3.connect(db) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS checkins (
                date TEXT PRIMARY KEY,
                nav REAL DEFAULT 0,
                timestamp TEXT
            );
            CREATE TABLE IF NOT EXISTS milestones (
                label TEXT PRIMARY KEY,
                value TEXT,
                date_achieved TEXT
            );
        """)


def _record_checkin(db: Path, nav: float = 0) -> tuple[bool, str]:
    """Record today's check-in. Returns (is_new, date_str)."""
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with sqlite3.connect(db) as conn:
        existing = conn.execute("SELECT date FROM checkins WHERE date = ?", (today,)).fetchone()

        if existing:
            # Update NAV if we have a better one
            if nav > 0:
                conn.execute("UPDATE checkins SET nav = ? WHERE date = ?", (nav, today))
            return False, today

        conn.execute(
            "INSERT INTO checkins (date, nav, timestamp) VALUES (?, ?, ?)",
            (today, nav, now),
        )
        return True, today


def _compute_streak(db: Path) -> tuple[int, int, int, str]:
    """Compute current streak, longest streak, total, last date."""
    with sqlite3.connect(db) as conn:
        rows = conn.execute("SELECT date FROM checkins ORDER BY date DESC").fetchall()

    if not rows:
        return 0, 0, 0, ""

    dates = [datetime.strptime(r[0], "%Y-%m-%d").date() for r in rows]
    total = len(dates)
    last_date = dates[0].isoformat()

    # Current streak (consecutive days from today or yesterday)
    today = datetime.now().date()
    current = 0
    expected = today

    for d in dates:
        if d == expected:
            current += 1
            expected -= timedelta(days=1)
        elif d == expected + timedelta(days=1):
            # Missed today but had yesterday
            continue
        else:
            break

    # If latest check-in was before yesterday, streak is 0
    if dates[0] < today - timedelta(days=1):
        current = 0

    # Longest streak ever
    longest = 1
    run = 1
    for i in range(1, len(dates)):
        if dates[i - 1] - dates[i] == timedelta(days=1):
            run += 1
            longest = max(longest, run)
        else:
            run = 1

    return current, longest, total, last_date


def _get_streak_message(streak: int, is_new: bool) -> str:
    if not is_new:
        if streak == 0:
            return "Welcome back! Start a new streak today."
        return f"Day {streak} streak — already checked in today."

    if streak == 1:
        return "New streak started! Come back tomorrow to build it."
    elif streak <= 3:
        return f"Day {streak}! Building momentum..."
    elif streak <= 7:
        return f"Day {streak}! One week is within reach."
    elif streak == 7:
        return "7 days! Full week streak unlocked."
    elif streak <= 14:
        return f"Day {streak}! Two weeks is the next milestone."
    elif streak <= 30:
        return f"Day {streak}! You're building a real habit."
    elif streak <= 60:
        return f"Day {streak}! Consistency is your edge."
    elif streak <= 100:
        return f"Day {streak}! Most investors don't track this closely."
    else:
        return f"Day {streak}! Diamond hands."


# ---------------------------------------------------------------------------
# Milestones
# ---------------------------------------------------------------------------

_MILESTONE_DEFS = [
    ("First Trade", lambda nav, initial, days, trades: trades >= 1),
    ("5 Trades", lambda nav, initial, days, trades: trades >= 5),
    ("10 Trades", lambda nav, initial, days, trades: trades >= 10),
    (
        "1% Return",
        lambda nav, initial, days, trades: initial > 0 and (nav - initial) / initial >= 0.01,
    ),
    (
        "5% Return",
        lambda nav, initial, days, trades: initial > 0 and (nav - initial) / initial >= 0.05,
    ),
    (
        "10% Return",
        lambda nav, initial, days, trades: initial > 0 and (nav - initial) / initial >= 0.10,
    ),
    (
        "25% Return",
        lambda nav, initial, days, trades: initial > 0 and (nav - initial) / initial >= 0.25,
    ),
    (
        "50% Return",
        lambda nav, initial, days, trades: initial > 0 and (nav - initial) / initial >= 0.50,
    ),
    ("30 Day Streak", lambda nav, initial, days, trades: days >= 30),
    ("100 Day Streak", lambda nav, initial, days, trades: days >= 100),
    ("1 Year Active", lambda nav, initial, days, trades: days >= 365),
]


def _check_milestones(
    db: Path,
    nav: float,
    initial: float,
    streak_days: int,
    trade_count: int,
) -> list[Milestone]:
    today = datetime.now().strftime("%Y-%m-%d")

    with sqlite3.connect(db) as conn:
        existing = {
            r[0]: (r[1], r[2]) for r in conn.execute("SELECT label, value, date_achieved FROM milestones").fetchall()
        }

    milestones: list[Milestone] = []
    new_achievements: list[tuple[str, str]] = []

    for label, check_fn in _MILESTONE_DEFS:
        achieved = check_fn(nav, initial, streak_days, trade_count)

        if label in existing:
            val, date_ach = existing[label]
            milestones.append(Milestone(label=label, achieved=True, value=val, date_achieved=date_ach))
        elif achieved:
            if "Return" in label:
                ret_pct = (nav - initial) / initial * 100 if initial > 0 else 0
                val = f"{ret_pct:+.1f}%"
            elif "Streak" in label:
                val = f"{streak_days} days"
            else:
                val = f"{trade_count} trades"
            milestones.append(Milestone(label=label, achieved=True, value=val, date_achieved=today))
            new_achievements.append((label, val))
        else:
            milestones.append(Milestone(label=label, achieved=False, value="—"))

    # Persist new achievements
    if new_achievements:
        with sqlite3.connect(db) as conn:
            for label, val in new_achievements:
                conn.execute(
                    "INSERT OR REPLACE INTO milestones (label, value, date_achieved) VALUES (?, ?, ?)",
                    (label, val, today),
                )

    return milestones


# ---------------------------------------------------------------------------
# Fun facts
# ---------------------------------------------------------------------------

_FUN_FACTS = [
    "Warren Buffett made 99% of his wealth after age 50. Compounding takes time.",
    "The S&P 500 has been positive in ~73% of all calendar years since 1928.",
    "Missing the 10 best days in a 20-year period cuts your returns in half.",
    "Nifty 50 has delivered ~12% CAGR since inception. Your strategy targets higher.",
    "The average investor underperforms by 1.5% annually due to emotional trading.",
    "Diversification is the only free lunch in investing — Nobel Prize winner Harry Markowitz.",
    "Systematic investing removes the biggest risk factor: your own emotions.",
    "It took Amazon stock 10 years to recover from its 2000 crash. Then it went up 100x.",
    "The best time to invest was 20 years ago. The second best time is today.",
    "Dollar-cost averaging into quality stocks has beaten 90% of active fund managers.",
    "India's nominal GDP is expected to triple by 2035. You're investing in that growth.",
    "SIP investors in Nifty 50 have never lost money over any 10-year period.",
]


def _pick_fun_fact() -> str:
    day = datetime.now().timetuple().tm_yday
    return _FUN_FACTS[day % len(_FUN_FACTS)]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_streak_report(
    strategy: str = "accumulate",
    current_prices: dict[str, float] | None = None,
) -> StreakReport:
    """Record check-in and return streak report with milestones.

    Args:
        strategy: Portfolio to track milestones for.
        current_prices: Current prices for NAV computation.

    Returns:
        StreakReport with streak info, milestones, and fun fact.
    """
    db = _db_path()
    _init_db(db)

    # Get portfolio data
    nav = 0.0
    initial = 0.0
    trade_count = 0
    try:
        from diamond.data.ledger import Ledger

        ledger = Ledger(strategy)
        if current_prices:
            nav = ledger.get_portfolio_value(current_prices)
        else:
            nav = ledger.get_cash()
        initial = ledger.get_initial_capital()
        trade_count = len(ledger.get_trades())
    except Exception:
        pass

    # Record check-in
    is_new, _ = _record_checkin(db, nav)

    # Compute streak
    current, longest, total, last_date = _compute_streak(db)

    streak = StreakInfo(
        current_streak=current,
        longest_streak=longest,
        total_checkins=total,
        last_checkin=last_date,
        is_new_today=is_new,
        checkin_message=_get_streak_message(current, is_new),
    )

    # Milestones
    milestones = _check_milestones(db, nav, initial, current, trade_count)

    return StreakReport(
        streak=streak,
        milestones=milestones,
        fun_fact=_pick_fun_fact(),
    )
