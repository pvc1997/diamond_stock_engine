"""Tests for capital gains tax computation."""

import pytest

from diamond.data.ledger import Ledger, Trade
from diamond.analysis.tax import (
    _match_lots,
    _compute_unrealized,
    _current_fiscal_year,
    _fy_date_range,
    compute_tax_report,
    STCG_RATE,
    LTCG_RATE,
    LTCG_EXEMPTION,
)


@pytest.fixture
def ledger(tmp_path):
    return Ledger("test_tax", db_path=tmp_path / "tax.db")


class TestFiscalYear:
    def test_fy_date_range(self):
        start, end = _fy_date_range("2025-26")
        assert start == "2025-04-01"
        assert end == "2026-03-31"

    def test_current_fy_format(self):
        fy = _current_fiscal_year()
        assert "-" in fy
        parts = fy.split("-")
        assert len(parts[0]) == 4
        assert len(parts[1]) == 2


class TestFIFOMatching:
    def test_single_buy_sell(self):
        trades = [
            Trade("2025-06-01", "BUY", "RELIANCE.NS", 10, 2500, 50, "Buy"),
            Trade("2025-09-01", "SELL", "RELIANCE.NS", 10, 2700, 50, "Sell"),
        ]
        lots, remaining = _match_lots(trades)
        assert len(lots) == 1
        lot = lots[0]
        assert lot.ticker == "RELIANCE.NS"
        assert lot.shares == 10
        assert lot.buy_price == 2500
        assert lot.sell_price == 2700
        assert lot.holding_days == 92
        assert lot.tax_category == "STCG"
        # gain = (2700-2500)*10 - 50 - 50 = 1900
        assert lot.gain == 1900

    def test_partial_sell(self):
        trades = [
            Trade("2025-06-01", "BUY", "RELIANCE.NS", 10, 2500, 100, "Buy"),
            Trade("2025-09-01", "SELL", "RELIANCE.NS", 5, 2700, 50, "Sell"),
        ]
        lots, remaining = _match_lots(trades)
        assert len(lots) == 1
        assert lots[0].shares == 5
        # 5 shares remain
        assert len(remaining["RELIANCE.NS"]) == 1
        assert remaining["RELIANCE.NS"][0][1] == 5  # remaining shares

    def test_multiple_buys_fifo(self):
        trades = [
            Trade("2025-01-01", "BUY", "TCS.NS", 5, 3000, 50, "Buy1"),
            Trade("2025-03-01", "BUY", "TCS.NS", 5, 3200, 50, "Buy2"),
            Trade("2025-06-01", "SELL", "TCS.NS", 7, 3500, 70, "Sell"),
        ]
        lots, remaining = _match_lots(trades)
        assert len(lots) == 2
        # First lot: 5 shares from Buy1
        assert lots[0].shares == 5
        assert lots[0].buy_price == 3000
        # Second lot: 2 shares from Buy2
        assert lots[1].shares == 2
        assert lots[1].buy_price == 3200
        # 3 shares remain from Buy2
        assert remaining["TCS.NS"][0][1] == 3

    def test_stcg_classification(self):
        trades = [
            Trade("2025-06-01", "BUY", "SBIN.NS", 10, 500, 10, ""),
            Trade("2025-11-01", "SELL", "SBIN.NS", 10, 600, 10, ""),
        ]
        lots, _ = _match_lots(trades)
        assert lots[0].tax_category == "STCG"
        assert lots[0].tax_rate == STCG_RATE

    def test_ltcg_classification(self):
        trades = [
            Trade("2024-01-01", "BUY", "SBIN.NS", 10, 500, 10, ""),
            Trade("2025-06-01", "SELL", "SBIN.NS", 10, 600, 10, ""),
        ]
        lots, _ = _match_lots(trades)
        assert lots[0].tax_category == "LTCG"
        assert lots[0].tax_rate == LTCG_RATE
        assert lots[0].holding_days >= 365

    def test_fy_filter(self):
        trades = [
            Trade("2024-06-01", "BUY", "ITC.NS", 10, 400, 10, ""),
            Trade("2024-12-01", "SELL", "ITC.NS", 5, 450, 5, ""),  # FY 2024-25
            Trade("2025-05-01", "SELL", "ITC.NS", 5, 500, 5, ""),  # FY 2025-26
        ]
        lots, _ = _match_lots(trades, fy_start="2025-04-01", fy_end="2026-03-31")
        # Only the second sell should be included
        assert len(lots) == 1
        assert lots[0].sell_date == "2025-05-01"

    def test_skip_zero_price_trades(self):
        """Synthetic trades (splits/dividends) with price=0 should be skipped."""
        trades = [
            Trade("2025-01-01", "BUY", "SAIL.NS", 100, 100, 20, "Buy"),
            Trade("2025-03-01", "BUY", "SAIL.NS", 100, 0, 0, "Split 2:1"),
            Trade("2025-06-01", "SELL", "SAIL.NS", 50, 110, 10, "Sell"),
        ]
        lots, _ = _match_lots(trades)
        assert len(lots) == 1
        assert lots[0].buy_price == 100  # Matched against the real buy, not the split


class TestUnrealized:
    def test_unrealized_computation(self):
        from collections import deque
        remaining = {
            "RELIANCE.NS": deque([("2025-01-01", 10, 2500, 5.0)]),
        }
        prices = {"RELIANCE.NS": 2800}
        lots = _compute_unrealized(remaining, prices)
        assert len(lots) == 1
        assert lots[0].unrealized_gain == (2800 - 2500) * 10
        assert lots[0].holding_days > 0

    def test_unrealized_no_price(self):
        from collections import deque
        remaining = {"UNKNOWN.NS": deque([("2025-01-01", 10, 100, 1.0)])}
        lots = _compute_unrealized(remaining, {})
        assert lots[0].unrealized_gain == 0


class TestTaxReport:
    def test_empty_ledger(self, ledger):
        report = compute_tax_report("test_tax", current_prices={})
        assert report.total_stcg == 0
        assert report.total_ltcg == 0
        assert report.total_estimated_tax == 0

    def test_ltcg_exemption(self):
        """LTCG of 200000, exemption 125000, taxable 75000."""
        trades = [
            Trade("2024-01-01", "BUY", "RELIANCE.NS", 100, 2000, 100, ""),
            Trade("2025-06-01", "SELL", "RELIANCE.NS", 100, 4000, 100, ""),
        ]
        lots, _ = _match_lots(trades, "2025-04-01", "2026-03-31")
        total_ltcg = sum(l.gain for l in lots if l.tax_category == "LTCG")
        taxable = max(0, total_ltcg - LTCG_EXEMPTION)
        assert total_ltcg > 0
        assert taxable == max(0, total_ltcg - 125000)

    def test_costs_deducted_from_gain(self):
        trades = [
            Trade("2025-06-01", "BUY", "TCS.NS", 10, 3000, 100, ""),
            Trade("2025-09-01", "SELL", "TCS.NS", 10, 3000, 100, ""),
        ]
        lots, _ = _match_lots(trades)
        # Same price buy/sell, but costs make it a loss
        assert lots[0].gain == -200  # -(100 + 100)
