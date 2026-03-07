"""Tests for targeted sell/buy/cleanup/trim operations."""

from unittest.mock import patch, MagicMock

import pytest

from diamond.data.ledger import Ledger, Trade
from diamond.execution.executor import (
    execute_sell,
    execute_buy,
    execute_cleanup,
    execute_trim,
)
from diamond.monitoring.alerts import (
    check_concentration,
    check_delisted,
    get_actionable_alerts,
    Alert,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ledger(tmp_path):
    """Create a test ledger with some holdings."""
    db = tmp_path / "test.db"
    with patch("diamond.data.ledger.get_config") as mock_cfg:
        mock_cfg.return_value = MagicMock(
            ledger_path=MagicMock(return_value=db),
            risk=MagicMock(initial_capital=100000.0),
            ledger_dir=tmp_path,
        )
        led = Ledger("test", db_path=db)
    return led


def _seed_holdings(ledger, holdings):
    """Seed holdings into a ledger."""
    for ticker, shares, price in holdings:
        trade = Trade(
            timestamp="2026-01-01",
            action="BUY",
            ticker=ticker,
            shares=shares,
            price=price,
            total_cost=0,
            rationale="Seed",
        )
        ledger.record_trade(trade)


# ---------------------------------------------------------------------------
# Ledger.write_off
# ---------------------------------------------------------------------------

class TestWriteOff:
    def test_write_off_removes_holding(self, ledger):
        _seed_holdings(ledger, [("DELISTED.NS", 100, 10.0)])
        assert "DELISTED.NS" in ledger.get_holdings()

        result = ledger.write_off("DELISTED.NS", "Delisted")
        assert result is True
        assert "DELISTED.NS" not in ledger.get_holdings()

    def test_write_off_no_cash_change(self, ledger):
        _seed_holdings(ledger, [("DELISTED.NS", 100, 10.0)])
        cash_before = ledger.get_cash()

        ledger.write_off("DELISTED.NS")
        # Cash doesn't increase (money is lost)
        assert ledger.get_cash() == cash_before

    def test_write_off_records_trade(self, ledger):
        _seed_holdings(ledger, [("DELISTED.NS", 100, 10.0)])
        ledger.write_off("DELISTED.NS", "Test write-off")

        trades = ledger.get_trades()
        sell_trades = [t for t in trades if t.action == "SELL" and t.ticker == "DELISTED.NS"]
        assert len(sell_trades) == 1
        assert sell_trades[0].price == 0
        assert sell_trades[0].shares == 100
        assert "write-off" in sell_trades[0].rationale

    def test_write_off_nonexistent_returns_false(self, ledger):
        assert ledger.write_off("FAKE.NS") is False

    def test_write_off_already_zero(self, ledger):
        assert ledger.write_off("NOSHARES.NS") is False


# ---------------------------------------------------------------------------
# execute_sell
# ---------------------------------------------------------------------------

class TestExecuteSell:
    @patch("diamond.execution.executor._get_current_prices")
    @patch("diamond.execution.executor.Ledger")
    def test_sell_all_shares(self, mock_ledger_cls, mock_prices):
        mock_ledger = MagicMock()
        mock_ledger.get_holdings.return_value = {"TCS.NS": 14}
        mock_ledger.get_cash.return_value = 50000.0
        mock_ledger_cls.return_value = mock_ledger
        mock_prices.return_value = {"TCS.NS": 2500.0}

        result = execute_sell("test", "TCS.NS")
        assert result["status"] == "executed"
        assert result["shares"] == 14
        assert result["ticker"] == "TCS.NS"
        mock_ledger.record_trade.assert_called_once()

    @patch("diamond.execution.executor._get_current_prices")
    @patch("diamond.execution.executor.Ledger")
    def test_sell_partial(self, mock_ledger_cls, mock_prices):
        mock_ledger = MagicMock()
        mock_ledger.get_holdings.return_value = {"TCS.NS": 14}
        mock_ledger_cls.return_value = mock_ledger
        mock_prices.return_value = {"TCS.NS": 2500.0}

        result = execute_sell("test", "TCS.NS", shares=5)
        assert result["status"] == "executed"
        assert result["shares"] == 5

    @patch("diamond.execution.executor._get_current_prices")
    @patch("diamond.execution.executor.Ledger")
    def test_sell_not_in_holdings(self, mock_ledger_cls, mock_prices):
        mock_ledger = MagicMock()
        mock_ledger.get_holdings.return_value = {"TCS.NS": 14}
        mock_ledger_cls.return_value = mock_ledger

        result = execute_sell("test", "FAKE.NS")
        assert result["status"] == "error"

    @patch("diamond.execution.executor._get_current_prices")
    @patch("diamond.execution.executor.Ledger")
    def test_sell_dry_run(self, mock_ledger_cls, mock_prices):
        mock_ledger = MagicMock()
        mock_ledger.get_holdings.return_value = {"TCS.NS": 14}
        mock_ledger_cls.return_value = mock_ledger
        mock_prices.return_value = {"TCS.NS": 2500.0}

        result = execute_sell("test", "TCS.NS", dry_run=True)
        assert result["status"] == "dry_run"
        assert result["proceeds"] > 0
        mock_ledger.record_trade.assert_not_called()

    @patch("diamond.execution.executor._get_current_prices")
    @patch("diamond.execution.executor.Ledger")
    def test_sell_no_price(self, mock_ledger_cls, mock_prices):
        mock_ledger = MagicMock()
        mock_ledger.get_holdings.return_value = {"TCS.NS": 14}
        mock_ledger_cls.return_value = mock_ledger
        mock_prices.return_value = {}

        result = execute_sell("test", "TCS.NS")
        assert result["status"] == "error"

    @patch("diamond.execution.paper._paper_strategy_name", return_value="test_paper")
    @patch("diamond.execution.executor._get_current_prices")
    @patch("diamond.execution.executor.Ledger")
    def test_sell_paper_mode(self, mock_ledger_cls, mock_prices, mock_paper_name):
        mock_ledger = MagicMock()
        mock_ledger.get_holdings.return_value = {"TCS.NS": 14}
        mock_ledger.get_cash.return_value = 50000.0
        mock_ledger_cls.return_value = mock_ledger
        mock_prices.return_value = {"TCS.NS": 2500.0}

        result = execute_sell("test", "TCS.NS", paper=True)
        assert result["status"] == "executed"
        mock_ledger_cls.assert_called_with("test_paper")


# ---------------------------------------------------------------------------
# execute_buy
# ---------------------------------------------------------------------------

class TestExecuteBuy:
    @patch("diamond.execution.executor._get_current_prices")
    @patch("diamond.execution.executor.Ledger")
    @patch("diamond.execution.executor.get_config")
    def test_buy_by_amount(self, mock_config, mock_ledger_cls, mock_prices):
        mock_config.return_value = MagicMock(
            portfolio=MagicMock(max_position_weight=0.10),
        )
        mock_ledger = MagicMock()
        mock_ledger.get_holdings.return_value = {}
        mock_ledger.get_cash.return_value = 500000.0
        mock_ledger.get_portfolio_value.return_value = 500000.0
        mock_ledger_cls.return_value = mock_ledger
        mock_prices.return_value = {"RELIANCE.NS": 1250.0}

        result = execute_buy("test", "RELIANCE.NS", amount=50000)
        assert result["status"] == "executed"
        assert result["shares"] == 40  # 50000 / 1250

    @patch("diamond.execution.executor._get_current_prices")
    @patch("diamond.execution.executor.Ledger")
    @patch("diamond.execution.executor.get_config")
    def test_buy_by_shares(self, mock_config, mock_ledger_cls, mock_prices):
        mock_config.return_value = MagicMock(
            portfolio=MagicMock(max_position_weight=0.10),
        )
        mock_ledger = MagicMock()
        mock_ledger.get_holdings.return_value = {}
        mock_ledger.get_cash.return_value = 100000.0
        mock_ledger.get_portfolio_value.return_value = 100000.0
        mock_ledger_cls.return_value = mock_ledger
        mock_prices.return_value = {"RELIANCE.NS": 1250.0}

        result = execute_buy("test", "RELIANCE.NS", shares=10)
        assert result["status"] == "executed"
        assert result["shares"] == 10

    @patch("diamond.execution.executor._get_current_prices")
    @patch("diamond.execution.executor.Ledger")
    @patch("diamond.execution.executor.get_config")
    def test_buy_insufficient_cash(self, mock_config, mock_ledger_cls, mock_prices):
        mock_config.return_value = MagicMock(
            portfolio=MagicMock(max_position_weight=0.10),
        )
        mock_ledger = MagicMock()
        mock_ledger.get_holdings.return_value = {}
        mock_ledger.get_cash.return_value = 100.0
        mock_ledger.get_portfolio_value.return_value = 100.0
        mock_ledger_cls.return_value = mock_ledger
        mock_prices.return_value = {"RELIANCE.NS": 1250.0}

        result = execute_buy("test", "RELIANCE.NS", amount=50000)
        assert result["status"] == "error"

    @patch("diamond.execution.executor._get_current_prices")
    @patch("diamond.execution.executor.Ledger")
    @patch("diamond.execution.executor.get_config")
    def test_buy_no_amount_or_shares(self, mock_config, mock_ledger_cls, mock_prices):
        mock_config.return_value = MagicMock()
        mock_ledger = MagicMock()
        mock_ledger_cls.return_value = mock_ledger
        mock_prices.return_value = {"RELIANCE.NS": 1250.0}

        result = execute_buy("test", "RELIANCE.NS")
        assert result["status"] == "error"

    @patch("diamond.execution.executor._get_current_prices")
    @patch("diamond.execution.executor.Ledger")
    @patch("diamond.execution.executor.get_config")
    def test_buy_dry_run(self, mock_config, mock_ledger_cls, mock_prices):
        mock_config.return_value = MagicMock(
            portfolio=MagicMock(max_position_weight=0.10),
        )
        mock_ledger = MagicMock()
        mock_ledger.get_holdings.return_value = {}
        mock_ledger.get_cash.return_value = 500000.0
        mock_ledger.get_portfolio_value.return_value = 500000.0
        mock_ledger_cls.return_value = mock_ledger
        mock_prices.return_value = {"RELIANCE.NS": 1250.0}

        result = execute_buy("test", "RELIANCE.NS", amount=50000, dry_run=True)
        assert result["status"] == "dry_run"
        mock_ledger.record_trade.assert_not_called()


# ---------------------------------------------------------------------------
# execute_cleanup
# ---------------------------------------------------------------------------

class TestExecuteCleanup:
    @patch("diamond.execution.executor._get_current_prices")
    @patch("diamond.execution.executor.Ledger")
    def test_cleanup_finds_delisted(self, mock_ledger_cls, mock_prices):
        mock_ledger = MagicMock()
        mock_ledger.get_holdings.return_value = {"GOOD.NS": 10, "DEAD.NS": 100}
        mock_ledger.write_off.return_value = True
        mock_ledger_cls.return_value = mock_ledger
        # Only GOOD.NS has a price
        mock_prices.return_value = {"GOOD.NS": 500.0}

        result = execute_cleanup("test")
        assert result["count"] == 1
        assert result["written_off"][0]["ticker"] == "DEAD.NS"
        mock_ledger.write_off.assert_called_once()

    @patch("diamond.execution.executor._get_current_prices")
    @patch("diamond.execution.executor.Ledger")
    def test_cleanup_dry_run(self, mock_ledger_cls, mock_prices):
        mock_ledger = MagicMock()
        mock_ledger.get_holdings.return_value = {"DEAD.NS": 100}
        mock_ledger_cls.return_value = mock_ledger
        mock_prices.return_value = {}

        result = execute_cleanup("test", dry_run=True)
        assert result["status"] == "dry_run"
        assert result["count"] == 1
        mock_ledger.write_off.assert_not_called()

    @patch("diamond.execution.executor._get_current_prices")
    @patch("diamond.execution.executor.Ledger")
    def test_cleanup_nothing_to_clean(self, mock_ledger_cls, mock_prices):
        mock_ledger = MagicMock()
        mock_ledger.get_holdings.return_value = {"GOOD.NS": 10}
        mock_ledger_cls.return_value = mock_ledger
        mock_prices.return_value = {"GOOD.NS": 500.0}

        result = execute_cleanup("test")
        assert result["count"] == 0


# ---------------------------------------------------------------------------
# execute_trim
# ---------------------------------------------------------------------------

class TestExecuteTrim:
    @patch("diamond.execution.executor._get_current_prices")
    @patch("diamond.execution.executor.Ledger")
    @patch("diamond.execution.executor.get_config")
    def test_trim_overweight_position(self, mock_config, mock_ledger_cls, mock_prices):
        mock_config.return_value = MagicMock(
            portfolio=MagicMock(max_position_weight=0.10),
        )
        mock_ledger = MagicMock()
        # SAIL at 50% weight, OTHER within 10%
        mock_ledger.get_holdings.return_value = {"SAIL.NS": 500, "OTHER.NS": 10}
        mock_ledger.get_portfolio_value.return_value = 100000.0
        mock_ledger.get_cash.return_value = 45000.0
        mock_ledger_cls.return_value = mock_ledger

        # SAIL = 500*100 = 50000 (50%), OTHER = 10*500 = 5000 (5%)
        prices = {"SAIL.NS": 100.0, "OTHER.NS": 500.0}
        result = execute_trim("test", current_prices=prices, dry_run=True)

        assert result["count"] == 1
        assert result["trims"][0]["ticker"] == "SAIL.NS"
        # Should sell down to 10% = 10000 / 100 = 100 shares. Sell 400.
        assert result["trims"][0]["sell_shares"] == 400

    @patch("diamond.execution.executor._get_current_prices")
    @patch("diamond.execution.executor.Ledger")
    @patch("diamond.execution.executor.get_config")
    def test_trim_nothing_overweight(self, mock_config, mock_ledger_cls, mock_prices):
        mock_config.return_value = MagicMock(
            portfolio=MagicMock(max_position_weight=0.10),
        )
        mock_ledger = MagicMock()
        mock_ledger.get_holdings.return_value = {"A.NS": 10, "B.NS": 10}
        mock_ledger.get_portfolio_value.return_value = 100000.0
        mock_ledger_cls.return_value = mock_ledger

        prices = {"A.NS": 500.0, "B.NS": 500.0}
        result = execute_trim("test", current_prices=prices)
        assert result["count"] == 0


# ---------------------------------------------------------------------------
# Alerts: check_concentration (tiered)
# ---------------------------------------------------------------------------

class TestConcentrationAlerts:
    def test_critical_at_1_5x(self, ledger):
        _seed_holdings(ledger, [("BIG.NS", 1000, 50.0)])
        # BIG.NS = 50000, cash = 50000, NAV = 100000
        # Weight = 50% = 5x the 10% limit -> critical
        prices = {"BIG.NS": 50.0}

        with patch("diamond.monitoring.alerts.get_config") as mock_cfg:
            mock_cfg.return_value = MagicMock(
                portfolio=MagicMock(max_position_weight=0.10),
            )
            alerts = check_concentration(ledger, prices)

        critical = [a for a in alerts if a.level == "critical"]
        assert len(critical) == 1
        assert "CONCENTRATION" in critical[0].message

    def test_warning_at_1_25x(self, ledger):
        # Position at ~13% (1.3x of 10% limit) -> warning but not critical
        _seed_holdings(ledger, [("MED.NS", 15, 1000.0)])
        # MED.NS = 15000, cash = 85000, NAV = 100000, weight = 15%
        prices = {"MED.NS": 1000.0}

        with patch("diamond.monitoring.alerts.get_config") as mock_cfg:
            mock_cfg.return_value = MagicMock(
                portfolio=MagicMock(max_position_weight=0.10),
            )
            alerts = check_concentration(ledger, prices)

        # 15% is exactly 1.5x, so it's critical
        assert len(alerts) == 1

    def test_no_alert_within_limit(self, ledger):
        _seed_holdings(ledger, [("SMALL.NS", 5, 100.0)])
        prices = {"SMALL.NS": 100.0}

        with patch("diamond.monitoring.alerts.get_config") as mock_cfg:
            mock_cfg.return_value = MagicMock(
                portfolio=MagicMock(max_position_weight=0.10),
            )
            alerts = check_concentration(ledger, prices)

        assert len(alerts) == 0


# ---------------------------------------------------------------------------
# Alerts: check_delisted
# ---------------------------------------------------------------------------

class TestDelistedAlerts:
    def test_detects_missing_price(self, ledger):
        _seed_holdings(ledger, [("DELISTED.NS", 100, 10.0), ("GOOD.NS", 50, 20.0)])
        prices = {"GOOD.NS": 25.0}  # No price for DELISTED.NS

        alerts = check_delisted(ledger, prices)
        assert len(alerts) == 1
        assert alerts[0].category == "delisted"
        assert "DELISTED.NS" in alerts[0].message

    def test_detects_zero_price(self, ledger):
        _seed_holdings(ledger, [("ZERO.NS", 100, 10.0)])
        prices = {"ZERO.NS": 0}

        alerts = check_delisted(ledger, prices)
        assert len(alerts) == 1

    def test_no_alert_for_priced_stocks(self, ledger):
        _seed_holdings(ledger, [("GOOD.NS", 50, 20.0)])
        prices = {"GOOD.NS": 25.0}

        alerts = check_delisted(ledger, prices)
        assert len(alerts) == 0


# ---------------------------------------------------------------------------
# Alerts: get_actionable_alerts
# ---------------------------------------------------------------------------

class TestActionableAlerts:
    @patch("diamond.monitoring.alerts.Ledger")
    @patch("diamond.monitoring.alerts.get_config")
    def test_combines_stop_loss_and_delisted(self, mock_config, mock_ledger_cls):
        mock_config.return_value = MagicMock(
            risk=MagicMock(stop_loss_threshold=0.10),
            portfolio=MagicMock(max_position_weight=0.10),
        )
        mock_ledger = MagicMock()
        mock_ledger.get_holdings.return_value = {"LOSER.NS": 10, "DEAD.NS": 100}
        mock_ledger.get_avg_price.side_effect = lambda t: {"LOSER.NS": 1000, "DEAD.NS": 50}.get(t, 0)
        mock_ledger.get_portfolio_value.return_value = 100000.0
        mock_ledger.get_cash.return_value = 90000.0
        mock_ledger_cls.return_value = mock_ledger

        prices = {"LOSER.NS": 800.0}  # 20% loss, no price for DEAD

        alerts = get_actionable_alerts("test", prices)
        categories = {a.category for a in alerts}
        assert "stop_loss" in categories
        assert "delisted" in categories
