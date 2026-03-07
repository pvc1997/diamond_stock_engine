"""Tests for corporate actions handler."""

from pathlib import Path

from diamond.data.corporate_actions import (
    CorporateAction,
    apply_bonus,
    apply_dividend,
    apply_split,
)
from diamond.data.ledger import Ledger, Trade


class TestApplySplit:
    def test_2_for_1_split(self, tmp_path: Path):
        ledger = Ledger("test_split", db_path=tmp_path / "test_split.db")
        ledger.record_trade(Trade("2024-01-15", "BUY", "RELIANCE.NS", 10, 2500.0, 50.0, "Buy"))

        action = CorporateAction(
            ticker="RELIANCE.NS",
            action_type="split",
            date="2024-06-01",
            ratio=2.0,
            value=0.0,
        )
        result = apply_split(ledger, action)

        assert result is not None
        assert ledger.get_holdings()["RELIANCE.NS"] == 20  # 10 * 2
        assert abs(ledger.get_avg_price("RELIANCE.NS") - 1250.0) < 0.01  # 2500 / 2
        assert action.applied is True

    def test_5_for_1_split(self, tmp_path: Path):
        ledger = Ledger("test_split5", db_path=tmp_path / "test_split5.db")
        ledger.record_trade(Trade("2024-01-15", "BUY", "TCS.NS", 20, 3000.0, 60.0, "Buy"))

        action = CorporateAction(
            ticker="TCS.NS",
            action_type="split",
            date="2024-06-01",
            ratio=5.0,
            value=0.0,
        )
        apply_split(ledger, action)

        assert ledger.get_holdings()["TCS.NS"] == 100  # 20 * 5
        assert abs(ledger.get_avg_price("TCS.NS") - 600.0) < 0.01  # 3000 / 5

    def test_split_no_position(self, tmp_path: Path):
        ledger = Ledger("test_split_none", db_path=tmp_path / "test_split_none.db")

        action = CorporateAction(
            ticker="RELIANCE.NS",
            action_type="split",
            date="2024-06-01",
            ratio=2.0,
            value=0.0,
        )
        result = apply_split(ledger, action)
        assert result is None

    def test_split_preserves_total_value(self, tmp_path: Path):
        """Total position value should be unchanged after split."""
        ledger = Ledger("test_split_val", db_path=tmp_path / "test_split_val.db")
        ledger.record_trade(Trade("2024-01-15", "BUY", "INFY.NS", 50, 1500.0, 30.0, "Buy"))

        # Pre-split value
        pre_shares = ledger.get_holdings()["INFY.NS"]
        pre_avg = ledger.get_avg_price("INFY.NS")
        pre_value = pre_shares * pre_avg

        action = CorporateAction(
            ticker="INFY.NS",
            action_type="split",
            date="2024-06-01",
            ratio=2.0,
            value=0.0,
        )
        apply_split(ledger, action)

        post_shares = ledger.get_holdings()["INFY.NS"]
        post_avg = ledger.get_avg_price("INFY.NS")
        post_value = post_shares * post_avg

        assert abs(pre_value - post_value) < 0.01

    def test_split_no_cash_impact(self, tmp_path: Path):
        ledger = Ledger("test_split_cash", db_path=tmp_path / "test_split_cash.db")
        ledger.record_trade(Trade("2024-01-15", "BUY", "RELIANCE.NS", 10, 2500.0, 50.0, "Buy"))
        cash_before = ledger.get_cash()

        action = CorporateAction(
            ticker="RELIANCE.NS",
            action_type="split",
            date="2024-06-01",
            ratio=2.0,
            value=0.0,
        )
        apply_split(ledger, action)

        assert ledger.get_cash() == cash_before


class TestApplyBonus:
    def test_1_for_1_bonus(self, tmp_path: Path):
        ledger = Ledger("test_bonus", db_path=tmp_path / "test_bonus.db")
        ledger.record_trade(Trade("2024-01-15", "BUY", "RELIANCE.NS", 10, 2500.0, 50.0, "Buy"))

        result = apply_bonus(ledger, "RELIANCE.NS", ratio=1.0, date="2024-06-01")
        assert result is not None
        assert ledger.get_holdings()["RELIANCE.NS"] == 20  # 10 * 2 (1:1 bonus)

    def test_1_for_2_bonus(self, tmp_path: Path):
        ledger = Ledger("test_bonus2", db_path=tmp_path / "test_bonus2.db")
        ledger.record_trade(Trade("2024-01-15", "BUY", "TCS.NS", 20, 3000.0, 60.0, "Buy"))

        apply_bonus(ledger, "TCS.NS", ratio=0.5, date="2024-06-01")
        assert ledger.get_holdings()["TCS.NS"] == 30  # 20 * 1.5


class TestApplyDividend:
    def test_dividend_adds_cash(self, tmp_path: Path):
        ledger = Ledger("test_div", db_path=tmp_path / "test_div.db")
        ledger.record_trade(Trade("2024-01-15", "BUY", "ITC.NS", 100, 400.0, 40.0, "Buy"))
        cash_before = ledger.get_cash()

        action = CorporateAction(
            ticker="ITC.NS",
            action_type="dividend",
            date="2024-06-15",
            ratio=1.0,
            value=6.50,   # 6.50 INR per share
        )
        result = apply_dividend(ledger, action)

        assert result is not None
        expected_div = 100 * 6.50  # 650 INR
        assert ledger.get_cash() == cash_before + expected_div

    def test_dividend_no_position(self, tmp_path: Path):
        ledger = Ledger("test_div_none", db_path=tmp_path / "test_div_none.db")

        action = CorporateAction(
            ticker="ITC.NS",
            action_type="dividend",
            date="2024-06-15",
            ratio=1.0,
            value=6.50,
        )
        result = apply_dividend(ledger, action)
        assert result is None

    def test_dividend_no_share_change(self, tmp_path: Path):
        ledger = Ledger("test_div_shares", db_path=tmp_path / "test_div_shares.db")
        ledger.record_trade(Trade("2024-01-15", "BUY", "ITC.NS", 100, 400.0, 40.0, "Buy"))

        action = CorporateAction(
            ticker="ITC.NS",
            action_type="dividend",
            date="2024-06-15",
            ratio=1.0,
            value=6.50,
        )
        apply_dividend(ledger, action)

        assert ledger.get_holdings()["ITC.NS"] == 100  # Unchanged

    def test_dividend_records_trade(self, tmp_path: Path):
        ledger = Ledger("test_div_trade", db_path=tmp_path / "test_div_trade.db")
        ledger.record_trade(Trade("2024-01-15", "BUY", "ITC.NS", 100, 400.0, 40.0, "Buy"))

        action = CorporateAction(
            ticker="ITC.NS",
            action_type="dividend",
            date="2024-06-15",
            ratio=1.0,
            value=6.50,
        )
        apply_dividend(ledger, action)

        trades = ledger.get_trades()
        assert len(trades) == 2  # Original buy + dividend record
        assert "Dividend" in trades[1].rationale
