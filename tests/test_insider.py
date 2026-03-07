"""Tests for insider activity tracker."""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from diamond.analysis.insider import (
    get_bulk_deals,
    get_insider_activity,
    get_portfolio_insider_signals,
)


def _make_mock_ticker(major_holders=None, insider_transactions=None, institutional_holders=None):
    """Create a mock yfinance Ticker with configurable attributes."""
    ticker = MagicMock()
    ticker.major_holders = major_holders
    ticker.insider_transactions = insider_transactions
    ticker.institutional_holders = institutional_holders
    return ticker


class TestGetInsiderActivity:
    @patch("diamond.analysis.insider.yf.Ticker")
    def test_returns_correct_structure(self, mock_yf):
        """Result has all expected keys."""
        mock_yf.return_value = _make_mock_ticker()

        result = get_insider_activity("RELIANCE.NS")
        assert result["ticker"] == "RELIANCE.NS"
        assert "promoter_holding_pct" in result
        assert "institutional_holding_pct" in result
        assert "recent_transactions" in result
        assert "net_insider_sentiment" in result

    @patch("diamond.analysis.insider.yf.Ticker")
    def test_appends_ns_suffix(self, mock_yf):
        """Appends .NS if not present."""
        mock_yf.return_value = _make_mock_ticker()

        result = get_insider_activity("RELIANCE")
        assert result["ticker"] == "RELIANCE.NS"

    @patch("diamond.analysis.insider.yf.Ticker")
    def test_already_has_ns_suffix(self, mock_yf):
        mock_yf.return_value = _make_mock_ticker()

        result = get_insider_activity("TCS.NS")
        assert result["ticker"] == "TCS.NS"

    @patch("diamond.analysis.insider.yf.Ticker")
    def test_major_holders_parsed(self, mock_yf):
        """Parses promoter and institutional holdings from major_holders."""
        holders = pd.DataFrame({
            0: [55.0, 30.0],
            1: ["% of Shares Held by All Insider", "% of Shares Held by Institutions"],
        })
        mock_yf.return_value = _make_mock_ticker(major_holders=holders)

        result = get_insider_activity("RELIANCE.NS")
        assert result["promoter_holding_pct"] == 55.0
        assert result["institutional_holding_pct"] == 30.0

    @patch("diamond.analysis.insider.yf.Ticker")
    def test_missing_major_holders(self, mock_yf):
        """Handles None major_holders gracefully."""
        mock_yf.return_value = _make_mock_ticker(major_holders=None)

        result = get_insider_activity("RELIANCE.NS")
        assert result["promoter_holding_pct"] is None
        assert result["institutional_holding_pct"] is None

    @patch("diamond.analysis.insider.yf.Ticker")
    def test_empty_major_holders(self, mock_yf):
        """Handles empty DataFrame major_holders."""
        mock_yf.return_value = _make_mock_ticker(major_holders=pd.DataFrame())

        result = get_insider_activity("RELIANCE.NS")
        assert result["promoter_holding_pct"] is None

    @patch("diamond.analysis.insider.yf.Ticker")
    def test_insider_transactions_buying_sentiment(self, mock_yf):
        """Net buying produces 'buying' sentiment."""
        txns = pd.DataFrame({
            "Start Date": [pd.Timestamp("2026-01-15"), pd.Timestamp("2026-02-01")],
            "Insider Name": ["CEO", "CFO"],
            "Shares": [1000, 500],
            "Value": [250000, 150000],
            "Transaction": ["Purchase", "Purchase"],
        })
        mock_yf.return_value = _make_mock_ticker(insider_transactions=txns)

        result = get_insider_activity("RELIANCE.NS")
        assert result["net_insider_sentiment"] == "buying"
        assert len(result["recent_transactions"]) == 2

    @patch("diamond.analysis.insider.yf.Ticker")
    def test_insider_transactions_selling_sentiment(self, mock_yf):
        """Net selling produces 'selling' sentiment."""
        txns = pd.DataFrame({
            "Start Date": [pd.Timestamp("2026-01-15")],
            "Insider Name": ["CEO"],
            "Shares": [5000],
            "Value": [1000000],
            "Transaction": ["Sale"],
        })
        mock_yf.return_value = _make_mock_ticker(insider_transactions=txns)

        result = get_insider_activity("RELIANCE.NS")
        assert result["net_insider_sentiment"] == "selling"

    @patch("diamond.analysis.insider.yf.Ticker")
    def test_insider_transactions_neutral(self, mock_yf):
        """No transactions produces 'neutral' sentiment."""
        mock_yf.return_value = _make_mock_ticker(insider_transactions=None)

        result = get_insider_activity("RELIANCE.NS")
        assert result["net_insider_sentiment"] == "neutral"

    @patch("diamond.analysis.insider.yf.Ticker")
    def test_missing_insider_transactions(self, mock_yf):
        """Handles missing insider_transactions gracefully."""
        mock_yf.return_value = _make_mock_ticker(insider_transactions=None)

        result = get_insider_activity("RELIANCE.NS")
        assert result["recent_transactions"] == []
        assert result["net_insider_sentiment"] == "neutral"

    @patch("diamond.analysis.insider.yf.Ticker")
    def test_yfinance_exception(self, mock_yf):
        """Graceful failure on yfinance error."""
        mock_yf.return_value = MagicMock()
        mock_yf.return_value.major_holders = MagicMock(
            side_effect=Exception("API down")
        )
        # The outer try catches exceptions on the ticker object itself
        mock_yf.side_effect = Exception("Connection failed")

        result = get_insider_activity("ERROR.NS")
        assert "error" in result


class TestGetPortfolioInsiderSignals:
    @patch("diamond.analysis.insider.get_insider_activity")
    @patch("diamond.analysis.insider.Ledger")
    def test_scans_all_holdings(self, mock_ledger_cls, mock_activity):
        """Scans insider activity for every holding."""
        mock_ledger_cls.return_value.get_holdings.return_value = {
            "RELIANCE.NS": 10,
            "TCS.NS": 5,
        }
        mock_activity.side_effect = [
            {"ticker": "RELIANCE.NS", "net_insider_sentiment": "buying"},
            {"ticker": "TCS.NS", "net_insider_sentiment": "selling"},
        ]

        result = get_portfolio_insider_signals("gods_plan")
        assert len(result) == 2
        # Selling should be first (bearish sorted first)
        assert result[0]["net_insider_sentiment"] == "selling"
        assert result[1]["net_insider_sentiment"] == "buying"

    @patch("diamond.analysis.insider.Ledger")
    def test_empty_holdings(self, mock_ledger_cls):
        """Empty portfolio returns empty list."""
        mock_ledger_cls.return_value.get_holdings.return_value = {}

        result = get_portfolio_insider_signals("gods_plan")
        assert result == []

    @patch("diamond.analysis.insider.Ledger")
    def test_ledger_error_returns_empty(self, mock_ledger_cls):
        """Graceful failure on ledger error."""
        mock_ledger_cls.side_effect = Exception("DB error")

        result = get_portfolio_insider_signals("gods_plan")
        assert result == []


class TestGetBulkDeals:
    @patch("diamond.analysis.insider.yf.Ticker")
    def test_returns_institutional_holders(self, mock_yf):
        """Returns institutional holders data."""
        inst = pd.DataFrame({
            "Holder": ["Vanguard", "BlackRock"],
            "Shares": [1000000, 800000],
            "Date Reported": [pd.Timestamp("2026-01-01"), pd.Timestamp("2025-12-01")],
        })
        mock_yf.return_value.institutional_holders = inst

        result = get_bulk_deals("RELIANCE.NS")
        assert len(result) == 2
        assert result[0]["Holder"] == "Vanguard"

    @patch("diamond.analysis.insider.yf.Ticker")
    def test_empty_institutional_holders(self, mock_yf):
        """Empty institutional holders returns empty list."""
        mock_yf.return_value.institutional_holders = pd.DataFrame()

        result = get_bulk_deals("RELIANCE.NS")
        assert result == []

    @patch("diamond.analysis.insider.yf.Ticker")
    def test_none_institutional_holders(self, mock_yf):
        mock_yf.return_value.institutional_holders = None

        result = get_bulk_deals("TCS.NS")
        assert result == []

    @patch("diamond.analysis.insider.yf.Ticker")
    def test_appends_ns_suffix(self, mock_yf):
        """Appends .NS if missing."""
        mock_yf.return_value.institutional_holders = None

        get_bulk_deals("RELIANCE")
        # The ticker passed to yf.Ticker should be RELIANCE.NS
        mock_yf.assert_called_with("RELIANCE.NS")

    @patch("diamond.analysis.insider.yf.Ticker")
    def test_yfinance_exception(self, mock_yf):
        """Graceful failure on yfinance error."""
        mock_yf.side_effect = Exception("API error")

        result = get_bulk_deals("ERROR.NS")
        assert result == []
