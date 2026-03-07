"""Tests for the daily learning engine."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from diamond.daily.learn import (
    DailyLesson,
    LessonExample,
    get_daily_lesson,
    list_topics,
    _lesson_beta,
    _lesson_alpha,
    _lesson_volatility,
    _lesson_hurst,
    _lesson_cagr,
    _lesson_vix,
    _lesson_drawdown,
    _lesson_position_sizing,
    _lesson_quality_score,
    _lesson_sector_diversification,
)


class TestLessonGenerators:
    """Each lesson generator should return a valid DailyLesson even with empty data."""

    GENERATORS = [
        _lesson_beta, _lesson_alpha, _lesson_volatility, _lesson_hurst,
        _lesson_cagr, _lesson_vix, _lesson_drawdown, _lesson_position_sizing,
        _lesson_quality_score, _lesson_sector_diversification,
    ]

    @pytest.mark.parametrize("gen", GENERATORS)
    def test_empty_data(self, gen):
        lesson = gen({}, {})
        assert isinstance(lesson, DailyLesson)
        assert len(lesson.topic) > 0
        assert len(lesson.concept) > 0
        assert len(lesson.explanation) > 0
        assert lesson.category in ("RISK", "VALUATION", "TECHNICAL", "PORTFOLIO", "")

    def test_beta_with_holdings(self):
        holdings = {"RELIANCE.NS": 10, "TCS.NS": 5}
        screener = {
            "RELIANCE.NS": {"Beta": 0.85},
            "TCS.NS": {"Beta": 1.15},
        }
        lesson = _lesson_beta(holdings, screener)
        assert len(lesson.examples) == 2
        assert lesson.examples[0].ticker == "RELIANCE"
        assert "0.85" in lesson.examples[0].value

    def test_alpha_with_holdings(self):
        holdings = {"HDFCBANK.NS": 20}
        screener = {"HDFCBANK.NS": {"Alpha": 0.45}}
        lesson = _lesson_alpha(holdings, screener)
        assert len(lesson.examples) == 1
        assert "outperformer" in lesson.examples[0].interpretation

    def test_volatility_with_holdings(self):
        holdings = {"INFY.NS": 10}
        screener = {"INFY.NS": {"Volatility": 0.22}}
        lesson = _lesson_volatility(holdings, screener)
        assert len(lesson.examples) == 1
        assert "low volatility" in lesson.examples[0].interpretation

    def test_cagr_with_holdings(self):
        holdings = {"RELIANCE.NS": 10}
        screener = {"RELIANCE.NS": {"CAGR": 0.18}}
        lesson = _lesson_cagr(holdings, screener)
        assert len(lesson.examples) == 1
        assert "L" in lesson.examples[0].interpretation  # Shows growth in lakhs

    def test_quality_score_with_holdings(self):
        holdings = {"RELIANCE.NS": 10}
        screener = {
            "RELIANCE.NS": {
                "CAGR": 0.20, "Alpha": 0.5, "Volatility": 0.20,
                "Beta": 0.9, "Hurst": 0.6,
            }
        }
        lesson = _lesson_quality_score(holdings, screener)
        assert len(lesson.examples) == 1
        assert "Quality" in lesson.examples[0].value


class TestListTopics:
    def test_returns_all_topics(self):
        topics = list_topics()
        assert len(topics) == 10
        assert all(isinstance(t, str) for t in topics)


class TestGetDailyLesson:
    @patch("diamond.data.ledger.Ledger")
    def test_with_forced_topic(self, MockLedger):
        MockLedger.return_value.get_holdings.return_value = {}
        lesson = get_daily_lesson("test", topic_index=0)
        assert isinstance(lesson, DailyLesson)
        assert "Beta" in lesson.topic

    @patch("diamond.data.ledger.Ledger")
    def test_rotates_by_day(self, MockLedger):
        MockLedger.return_value.get_holdings.return_value = {}
        lesson = get_daily_lesson("test")
        assert isinstance(lesson, DailyLesson)

    @patch("diamond.data.ledger.Ledger")
    def test_topic_wraps_around(self, MockLedger):
        MockLedger.return_value.get_holdings.return_value = {}
        lesson = get_daily_lesson("test", topic_index=100)
        assert isinstance(lesson, DailyLesson)
