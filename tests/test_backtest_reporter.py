"""Tests for backtest reporter."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from diamond.backtest.engine import BacktestResult, WindowResult
from diamond.backtest.reporter import compute_metrics, generate_report


def _make_result(
    returns: list[float] | None = None,
    nav_values: list[float] | None = None,
) -> BacktestResult:
    """Create a BacktestResult with synthetic data."""
    if returns is None:
        returns = [5.0, -2.0, 8.0, 3.0]

    windows = []
    capital = 100000
    all_nav: list[tuple[str, float]] = []

    for i, ret in enumerate(returns):
        final = capital * (1 + ret / 100)
        nav_entries = [
            (f"2023-{(i*3+1):02d}-01", capital),
            (f"2023-{(i*3+2):02d}-01", capital * (1 + ret / 200)),
            (f"2023-{(i*3+3):02d}-01", final),
        ]
        windows.append(WindowResult(
            window_id=i,
            start=f"2023-{(i*3+1):02d}-01",
            end=f"2023-{(i*3+3):02d}-01",
            initial_nav=round(capital, 2),
            final_nav=round(final, 2),
            return_pct=ret,
            num_trades=10 + i,
            total_fees=50.0 + i * 10,
            holdings_count=5,
            nav_history=nav_entries,
        ))
        all_nav.extend(nav_entries)
        capital = final

    if nav_values:
        all_nav = [(f"day-{i}", v) for i, v in enumerate(nav_values)]

    return BacktestResult(
        strategy="test",
        start_date="2023-01-01",
        end_date="2024-01-01",
        initial_capital=100000,
        final_nav=round(capital, 2),
        windows=windows,
        nav_history=all_nav,
    )


class TestComputeMetrics:
    def test_total_return(self):
        result = _make_result([10.0])
        m = compute_metrics(result)
        assert abs(m["total_return_pct"] - 10.0) < 0.1

    def test_cagr_positive_for_gains(self):
        result = _make_result([5.0, 5.0, 5.0, 5.0])
        m = compute_metrics(result)
        assert m["cagr"] > 0

    def test_win_rate(self):
        result = _make_result([5.0, -2.0, 8.0, -1.0])
        m = compute_metrics(result)
        assert m["win_rate_pct"] == 50.0

    def test_total_trades_summed(self):
        result = _make_result([5.0, 3.0])
        m = compute_metrics(result)
        # Window 0: 10 trades, Window 1: 11 trades
        assert m["total_trades"] == 21

    def test_total_fees_summed(self):
        result = _make_result([5.0, 3.0])
        m = compute_metrics(result)
        # Window 0: 50, Window 1: 60
        assert m["total_fees"] == 110.0

    def test_max_drawdown_detected(self):
        # NAV goes 100k -> 110k -> 90k -> 95k
        result = _make_result(nav_values=[100000, 110000, 90000, 95000])
        m = compute_metrics(result)
        # Drawdown from 110k to 90k = 18.18%
        assert m["max_drawdown_pct"] > 15.0

    def test_zero_windows(self):
        result = BacktestResult(
            strategy="empty",
            start_date="2023-01-01",
            end_date="2023-02-01",
            initial_capital=100000,
            final_nav=100000,
        )
        m = compute_metrics(result)
        assert m["total_return_pct"] == 0.0
        assert m["win_rate_pct"] == 0.0

    def test_sharpe_has_value(self):
        result = _make_result([5.0, -2.0, 8.0, 3.0])
        m = compute_metrics(result)
        # Sharpe should be a finite number
        assert isinstance(m["sharpe"], float)


class TestGenerateReport:
    def test_creates_markdown_and_json(self):
        result = _make_result([5.0, 3.0])

        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir)
            md_path = generate_report(result, output_dir=out)

            assert md_path.exists()
            assert md_path.suffix == ".md"

            json_path = out / "backtest_results.json"
            assert json_path.exists()

            data = json.loads(json_path.read_text())
            assert data["strategy"] == "test"
            assert "metrics" in data
            assert "windows" in data
            assert len(data["windows"]) == 2

    def test_report_contains_metrics(self):
        result = _make_result([10.0, -5.0])

        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir)
            md_path = generate_report(result, output_dir=out)
            content = md_path.read_text()

            assert "CAGR" in content
            assert "Sharpe" in content
            assert "Max Drawdown" in content
            assert "Win Rate" in content
            assert "TEST" in content  # strategy name uppercased

    def test_json_metrics_match(self):
        result = _make_result([8.0, 4.0, -2.0])

        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir)
            generate_report(result, output_dir=out)

            data = json.loads((out / "backtest_results.json").read_text())
            m = data["metrics"]

            assert m["total_return_pct"] > 0
            assert m["total_windows"] == 3
