"""Tests for configuration system."""

from diamond.config import Config, get_config


class TestConfig:
    def test_default_values(self):
        cfg = Config()
        assert cfg.risk.initial_capital == 100000
        assert cfg.risk.stop_loss_threshold == 0.10
        assert cfg.portfolio.max_position_weight == 0.10
        assert cfg.portfolio.max_stocks_per_sector == 4
        assert cfg.rebalance.rebalance_frequency_days == 90
        assert cfg.screener.risk_free_rate == 0.065

    def test_gods_plan_defaults(self):
        cfg = Config()
        assert cfg.gods_plan.rebalance_days == 90
        assert cfg.gods_plan.max_position_weight == 0.12
        assert cfg.gods_plan.core_min_alpha == 0.15
        assert cfg.gods_plan.drawdown_critical_pct == 20.0

    def test_paths(self):
        cfg = Config()
        assert cfg.data_dir.name == "data"
        assert cfg.cache_dir.name == "cache"
        assert cfg.ledger_dir.name == "ledgers"
        assert cfg.ledger_path("baseline").suffix == ".db"

    def test_singleton(self):
        cfg1 = get_config()
        cfg2 = get_config()
        assert cfg1 is cfg2
