"""Tests for portfolio monitoring alerts."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from diamond.data.ledger import Ledger, Trade
from diamond.monitoring.alerts import (
    Alert,
    check_drawdown,
    check_stop_loss,
    check_position_drift,
    check_concentration,
    run_health_check,
)


@pytest.fixture
def ledger(tmp_path):
    """Create a test ledger with diversified holdings."""
    db_path = tmp_path / "test.db"
    l = Ledger("test", db_path=db_path)
    l.reset(initial_capital=100000)

    # Buy 10 stocks equally for diversified portfolio
    for i in range(10):
        ticker = f"S{i}.NS"
        l.record_trade(Trade("2024-01-01", "BUY", ticker, 20, 500.0, 5.0, "test"))
    return l


class TestCheckDrawdown:
    def test_no_alert_when_healthy(self, ledger):
        prices = {f"S{i}.NS": 500.0 for i in range(10)}
        alerts = check_drawdown(ledger, prices)
        assert len(alerts) == 0

    def test_warning_at_10_pct(self, tmp_path):
        db_path = tmp_path / "dd.db"
        l = Ledger("dd", db_path=db_path)
        l.reset(initial_capital=100000)
        l.record_trade(Trade("2024-01-01", "BUY", "X.NS", 100, 950.0, 50.0, "test"))
        # Now cash ~5000, holdings 100*950=95000, NAV~100000
        # Price drops to 800 => holdings=80000, NAV=85000 => 15% drawdown
        prices = {"X.NS": 800.0}
        alerts = check_drawdown(l, prices)
        assert any(a.level in ("warning", "critical") for a in alerts)

    def test_critical_at_15_pct(self, tmp_path):
        db_path = tmp_path / "dd2.db"
        l = Ledger("dd2", db_path=db_path)
        l.reset(initial_capital=100000)
        l.record_trade(Trade("2024-01-01", "BUY", "X.NS", 100, 950.0, 50.0, "test"))
        # Price drops to 700 => holdings=70000, cash~5000, NAV=75000 => 25% drawdown
        prices = {"X.NS": 700.0}
        alerts = check_drawdown(l, prices)
        assert any(a.level == "critical" for a in alerts)


class TestCheckStopLoss:
    def test_no_alert_within_threshold(self, ledger):
        # Prices slightly below avg cost but within 10%
        prices = {f"S{i}.NS": 470.0 for i in range(10)}
        alerts = check_stop_loss(ledger, prices)
        assert len(alerts) == 0

    def test_alert_when_breached(self, ledger):
        # One stock drops 20%
        prices = {f"S{i}.NS": 500.0 for i in range(10)}
        prices["S0.NS"] = 400.0  # Down 20% from avg 500
        alerts = check_stop_loss(ledger, prices)
        assert len(alerts) >= 1
        assert alerts[0].category == "stop_loss"
        assert "S0.NS" in alerts[0].message

    def test_handles_missing_prices(self, ledger):
        prices = {}
        alerts = check_stop_loss(ledger, prices)
        assert len(alerts) == 0


class TestCheckPositionDrift:
    def test_no_alert_when_on_target(self, ledger):
        prices = {f"S{i}.NS": 500.0 for i in range(10)}
        target = {f"S{i}.NS": 10000.0 for i in range(10)}
        alerts = check_position_drift(ledger, target, prices)
        assert len(alerts) == 0

    def test_alert_on_large_drift(self, ledger):
        prices = {f"S{i}.NS": 500.0 for i in range(10)}
        # Target wants all in S0, but portfolio is diversified
        target = {"S0.NS": 90000.0, "S1.NS": 10000.0}
        alerts = check_position_drift(ledger, target, prices)
        assert len(alerts) >= 1
        assert alerts[0].category == "drift"


class TestCheckConcentration:
    def test_no_alert_diversified(self, ledger):
        # 10 equal positions = 10% each, max_position_weight = 10%
        # 1.5x limit = 15%, so 10% positions won't trigger
        prices = {f"S{i}.NS": 500.0 for i in range(10)}
        alerts = check_concentration(ledger, prices)
        assert len(alerts) == 0

    def test_alert_on_overconcentration(self, tmp_path):
        db_path = tmp_path / "conc.db"
        l = Ledger("conc", db_path=db_path)
        l.reset(initial_capital=100000)
        l.record_trade(Trade("2024-01-01", "BUY", "X.NS", 500, 190.0, 20.0, "test"))

        prices = {"X.NS": 190.0}
        alerts = check_concentration(l, prices)
        assert any(a.category == "concentration" for a in alerts)


class TestRunHealthCheck:
    def test_returns_list(self, ledger):
        prices = {f"S{i}.NS": 300.0 for i in range(10)}
        with patch("diamond.monitoring.alerts.Ledger", return_value=ledger):
            alerts = run_health_check("test", prices)
        assert isinstance(alerts, list)

    def test_all_clear_with_healthy_portfolio(self, ledger):
        prices = {f"S{i}.NS": 500.0 for i in range(10)}
        with patch("diamond.monitoring.alerts.Ledger", return_value=ledger):
            alerts = run_health_check("test", prices)
        critical = [a for a in alerts if a.level == "critical"]
        assert len(critical) == 0
