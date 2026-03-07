"""Tests for earnings calendar."""

from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from diamond.data.earnings import get_earnings_calendar, get_portfolio_earnings


@pytest.fixture
def mock_ticker_factory():
    """Create a mock yfinance Ticker with configurable calendar."""
    def _make(calendar_data):
        ticker = MagicMock()
        ticker.calendar = calendar_data
        return ticker
    return _make


class TestGetEarningsCalendar:
    @patch("diamond.data.earnings.yf.Ticker")
    def test_dict_format_with_earnings_date(self, mock_yf):
        """Calendar returned as dict with 'Earnings Date' key."""
        earnings_dt = datetime(2026, 7, 15)
        mock_yf.return_value.calendar = {
            "Earnings Date": [earnings_dt],
        }

        result = get_earnings_calendar(["RELIANCE.NS"])
        assert len(result) == 1
        assert result[0]["ticker"] == "RELIANCE.NS"
        assert result[0]["earnings_date"] == "2026-07-15"
        assert "days_until" in result[0]
        assert result[0]["quarter"] == "Q2 FY27"

    @patch("diamond.data.earnings.yf.Ticker")
    def test_dict_format_single_value(self, mock_yf):
        """Calendar dict with single datetime (not a list)."""
        earnings_dt = datetime(2026, 1, 20)
        mock_yf.return_value.calendar = {
            "Earnings Date": earnings_dt,
        }

        result = get_earnings_calendar(["TCS.NS"])
        assert len(result) == 1
        assert result[0]["earnings_date"] == "2026-01-20"
        # Jan = Q4, FY = year - 1 = 2025 -> Q4 FY26
        assert result[0]["quarter"] == "Q4 FY26"

    @patch("diamond.data.earnings.yf.Ticker")
    def test_dataframe_format(self, mock_yf):
        """Calendar returned as DataFrame with 'Earnings Date' column."""
        earnings_dt = pd.Timestamp("2026-05-10")
        df = pd.DataFrame({"Earnings Date": [earnings_dt]})
        mock_yf.return_value.calendar = df

        result = get_earnings_calendar(["INFY.NS"])
        assert len(result) == 1
        assert result[0]["earnings_date"] == "2026-05-10"
        assert result[0]["quarter"] == "Q1 FY27"

    @patch("diamond.data.earnings.yf.Ticker")
    def test_dataframe_fallback_first_column(self, mock_yf):
        """DataFrame without 'Earnings Date' column — uses first column."""
        earnings_dt = pd.Timestamp("2026-11-01")
        df = pd.DataFrame({"SomeDate": [earnings_dt]})
        mock_yf.return_value.calendar = df

        result = get_earnings_calendar(["HDFC.NS"])
        assert len(result) == 1
        assert result[0]["earnings_date"] == "2026-11-01"
        assert result[0]["quarter"] == "Q3 FY27"

    @patch("diamond.data.earnings.yf.Ticker")
    def test_sorted_by_days_until(self, mock_yf):
        """Results sorted by days_until ascending."""
        today = date.today()
        near = datetime(today.year, today.month, today.day)
        far = datetime(today.year + 1, today.month, today.day)

        def make_ticker(ticker_str):
            mock = MagicMock()
            if "NEAR" in ticker_str:
                mock.calendar = {"Earnings Date": [near]}
            else:
                mock.calendar = {"Earnings Date": [far]}
            return mock

        mock_yf.side_effect = make_ticker

        result = get_earnings_calendar(["FAR.NS", "NEAR.NS"])
        assert len(result) == 2
        assert result[0]["days_until"] <= result[1]["days_until"]

    @patch("diamond.data.earnings.yf.Ticker")
    def test_no_calendar_data_returns_empty(self, mock_yf):
        """Ticker with no calendar returns empty list."""
        mock_yf.return_value.calendar = None

        result = get_earnings_calendar(["MISSING.NS"])
        assert result == []

    @patch("diamond.data.earnings.yf.Ticker")
    def test_empty_tickers_returns_empty(self, mock_yf):
        result = get_earnings_calendar([])
        assert result == []
        mock_yf.assert_not_called()

    @patch("diamond.data.earnings.yf.Ticker")
    def test_yfinance_error_returns_empty(self, mock_yf):
        """Graceful failure on yfinance exception."""
        mock_yf.side_effect = Exception("API error")

        result = get_earnings_calendar(["RELIANCE.NS"])
        assert result == []

    @patch("diamond.data.earnings.yf.Ticker")
    def test_quarter_labels(self, mock_yf):
        """Verify quarter label formatting for each quarter."""
        test_cases = [
            (datetime(2026, 2, 15), "Q4 FY26"),   # Jan-Mar -> Q4, FY = year-1+1
            (datetime(2026, 5, 10), "Q1 FY27"),   # Apr-Jun -> Q1
            (datetime(2026, 8, 20), "Q2 FY27"),   # Jul-Sep -> Q2
            (datetime(2026, 11, 5), "Q3 FY27"),   # Oct-Dec -> Q3
        ]

        for dt, expected_quarter in test_cases:
            mock_yf.return_value.calendar = {"Earnings Date": [dt]}
            result = get_earnings_calendar(["TEST.NS"])
            assert result[0]["quarter"] == expected_quarter, f"Failed for {dt}: expected {expected_quarter}, got {result[0]['quarter']}"

    @patch("diamond.data.earnings.yf.Ticker")
    def test_string_date_format(self, mock_yf):
        """Calendar with string date instead of datetime."""
        mock_yf.return_value.calendar = {
            "Earnings Date": "2026-09-15T00:00:00",
        }

        result = get_earnings_calendar(["TEST.NS"])
        assert len(result) == 1
        assert result[0]["earnings_date"] == "2026-09-15"


class TestGetPortfolioEarnings:
    @patch("diamond.data.earnings.Ledger")
    @patch("diamond.data.earnings.get_earnings_calendar")
    def test_portfolio_with_holdings(self, mock_cal, mock_ledger):
        """Returns earnings for all portfolio holdings."""
        mock_ledger.return_value.get_holdings.return_value = {
            "RELIANCE.NS": 10,
            "TCS.NS": 5,
        }
        mock_cal.return_value = [{"ticker": "RELIANCE.NS", "days_until": 5}]

        result = get_portfolio_earnings("gods_plan")
        mock_cal.assert_called_once_with(["RELIANCE.NS", "TCS.NS"])
        assert len(result) == 1

    @patch("diamond.data.earnings.Ledger")
    def test_empty_holdings_returns_empty(self, mock_ledger):
        """Returns empty list for empty portfolio."""
        mock_ledger.return_value.get_holdings.return_value = {}

        result = get_portfolio_earnings("gods_plan")
        assert result == []

    @patch("diamond.data.earnings.Ledger")
    def test_ledger_error_returns_empty(self, mock_ledger):
        """Graceful failure on ledger error."""
        mock_ledger.side_effect = Exception("DB error")

        result = get_portfolio_earnings("gods_plan")
        assert result == []
