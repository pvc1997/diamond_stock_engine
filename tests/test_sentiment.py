"""Tests for AI sentiment analysis."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from diamond.analysis.sentiment import (
    _heuristic_news,
    _heuristic_fundamental,
    _make_result,
    analyze_stock,
)


class TestHeuristicNews:
    def test_bullish_headlines(self):
        result = _heuristic_news(["Record profit and expansion announced"])
        assert result["score"] > 0
        assert result["sentiment"] in ("Bullish", "Positive")

    def test_toxic_headlines(self):
        result = _heuristic_news(["Fraud investigation by SEBI, CEO arrested in scam"])
        assert result["score"] < 0
        assert result["sentiment"] in ("Toxic", "Bearish")

    def test_neutral_headlines(self):
        result = _heuristic_news(["Company holds annual general meeting"])
        assert result["sentiment"] == "Neutral"
        assert -1.0 <= result["score"] <= 1.0

    def test_negation_flips_sentiment(self):
        positive = _heuristic_news(["Growth and profit surge"])
        negated = _heuristic_news(["No growth and no profit"])
        assert negated["score"] < positive["score"]

    def test_toxic_keywords_lower_multiplier(self):
        result = _heuristic_news(["Fraud detected in company accounts"])
        assert result["multiplier"] < 1.0

    def test_growth_keywords_raise_multiplier(self):
        result = _heuristic_news(["Major acquisition and expansion"])
        assert result["multiplier"] > 1.0

    def test_empty_headlines(self):
        result = _heuristic_news([])
        assert result["sentiment"] == "Neutral"
        assert result["score"] == 0.0

    def test_score_clamped_to_range(self):
        result = _heuristic_news(
            ["fraud scam default bankruptcy arrest investigation penalty"] * 3
        )
        assert result["score"] >= -10.0


class TestHeuristicFundamental:
    def test_strong_buy_with_high_roe(self):
        info = {"recommendationKey": "strongBuy", "returnOnEquity": 0.20}
        result = _heuristic_fundamental(info)
        assert result["score"] > 0
        assert result["sentiment"] in ("Bullish", "Positive")

    def test_sell_with_negative_roe(self):
        info = {"recommendationKey": "sell", "returnOnEquity": -0.05}
        result = _heuristic_fundamental(info)
        assert result["score"] < 0
        assert result["sentiment"] in ("Bearish", "Toxic")

    def test_hold_neutral(self):
        info = {"recommendationKey": "hold", "returnOnEquity": 0.08}
        result = _heuristic_fundamental(info)
        assert result["sentiment"] in ("Neutral", "Positive")

    def test_missing_data(self):
        result = _heuristic_fundamental({})
        assert result["sentiment"] == "Neutral"
        assert result["source"] == "heuristic"

    def test_multiplier_is_conservative(self):
        result = _heuristic_fundamental({"recommendationKey": "buy"})
        assert result["multiplier"] == 0.9


class TestMakeResult:
    def test_clamps_score(self):
        r = _make_result(15.0, "Bullish", 1.0, "test", "test")
        assert r["score"] == 10.0

        r = _make_result(-15.0, "Toxic", 1.0, "test", "test")
        assert r["score"] == -10.0

    def test_includes_all_fields(self):
        r = _make_result(5.0, "Positive", 1.2, "reason", "gemini")
        assert set(r.keys()) == {"score", "sentiment", "multiplier", "rationale", "source"}


class TestAnalyzeStock:
    def _mock_yf(self, news_list):
        """Helper to mock yfinance inside analyze_stock."""
        import yfinance
        mock_ticker = MagicMock()
        mock_ticker.news = news_list
        return patch.object(yfinance, "Ticker", return_value=mock_ticker)

    @patch("diamond.analysis.sentiment._gemini_analyze", return_value=None)
    @patch("diamond.data.market.get_stock_info", return_value={})
    @patch("diamond.analysis.sentiment._load_cache", return_value={})
    @patch("diamond.analysis.sentiment._save_cache")
    def test_falls_back_to_heuristic(self, mock_save, mock_load, mock_info, mock_gemini):
        with self._mock_yf([{"title": "Record profit growth"}]):
            result = analyze_stock("RELIANCE.NS")
        assert result["source"] == "heuristic"
        assert result["score"] > 0

    @patch("diamond.analysis.sentiment._gemini_analyze")
    @patch("diamond.data.market.get_stock_info", return_value={})
    @patch("diamond.analysis.sentiment._load_cache", return_value={})
    @patch("diamond.analysis.sentiment._save_cache")
    def test_uses_gemini_when_available(self, mock_save, mock_load, mock_info, mock_gemini):
        mock_gemini.return_value = _make_result(8.0, "Bullish", 1.3, "AI analysis", "gemini")
        with self._mock_yf([{"title": "Strong results"}]):
            result = analyze_stock("TCS.NS")
        assert result["source"] == "gemini"
        assert result["score"] == 8.0

    @patch("diamond.analysis.sentiment._load_cache")
    def test_uses_cache_when_fresh(self, mock_load):
        import time
        cached_data = _make_result(5.0, "Positive", 1.1, "cached", "gemini")
        mock_load.return_value = {
            "TEST.NS": {
                "cached_at": time.time(),
                "data": cached_data,
            }
        }

        result = analyze_stock("TEST.NS")
        assert result["score"] == 5.0
        assert result["source"] == "gemini"

    @patch("diamond.analysis.sentiment._gemini_analyze", return_value=None)
    @patch("diamond.data.market.get_stock_info", return_value={"recommendationKey": "buy", "returnOnEquity": 0.18})
    @patch("diamond.analysis.sentiment._load_cache", return_value={})
    @patch("diamond.analysis.sentiment._save_cache")
    def test_fundamental_fallback_when_no_news(self, mock_save, mock_load, mock_info, mock_gemini):
        with self._mock_yf([]):
            result = analyze_stock("INFY.NS")
        assert result["source"] == "heuristic"
        assert "fundamental" in result["rationale"].lower()

    @patch("diamond.analysis.sentiment._gemini_analyze", return_value=None)
    @patch("diamond.data.market.get_stock_info", return_value={})
    @patch("diamond.analysis.sentiment._load_cache", return_value={})
    @patch("diamond.analysis.sentiment._save_cache")
    def test_saves_to_cache(self, mock_save, mock_load, mock_info, mock_gemini):
        with self._mock_yf([{"title": "News headline"}]):
            analyze_stock("HAL.NS")
        mock_save.assert_called_once()
        cache_arg = mock_save.call_args[0][0]
        assert "HAL.NS" in cache_arg
