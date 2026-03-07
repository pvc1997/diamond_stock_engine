"""Tests for portfolio export and report generation."""

import csv
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from diamond.data.ledger import Ledger, Trade
from diamond.analysis.export import (
    ExportResult,
    export_all,
    export_full_json,
    export_holdings_csv,
    export_portfolio_summary,
    export_trades_csv,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

PRICES = {
    "RELIANCE.NS": 2500.0,
    "TCS.NS": 3800.0,
    "HDFCBANK.NS": 1700.0,
}


@pytest.fixture
def ledger(tmp_path: Path) -> Ledger:
    """Create a ledger with known holdings and trades."""
    db = tmp_path / "ledgers" / "test_strat.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    led = Ledger("test_strat", db_path=db)
    led.set_cash(500_000.0)

    # Record some trades
    led.record_trade(Trade(
        timestamp="2025-06-01", action="BUY", ticker="RELIANCE.NS",
        shares=10, price=2400.0, total_cost=50.0, rationale="initial buy",
    ))
    led.record_trade(Trade(
        timestamp="2025-06-01", action="BUY", ticker="TCS.NS",
        shares=5, price=3700.0, total_cost=40.0, rationale="initial buy",
    ))
    led.record_trade(Trade(
        timestamp="2025-06-01", action="BUY", ticker="HDFCBANK.NS",
        shares=20, price=1650.0, total_cost=35.0, rationale="initial buy",
    ))
    led.record_trade(Trade(
        timestamp="2025-09-15", action="SELL", ticker="HDFCBANK.NS",
        shares=5, price=1700.0, total_cost=20.0, rationale="rebalance trim",
    ))
    return led


@pytest.fixture
def empty_ledger(tmp_path: Path) -> Ledger:
    """Create a ledger with no trades (empty portfolio)."""
    db = tmp_path / "ledgers" / "empty_strat.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    return Ledger("empty_strat", db_path=db)


def _patch_ledger(ledger_fixture: Ledger):
    """Return a patcher that makes Ledger() return the given fixture."""
    return patch(
        "diamond.analysis.export.Ledger",
        return_value=ledger_fixture,
    )


# ---------------------------------------------------------------------------
# Markdown summary
# ---------------------------------------------------------------------------

class TestExportPortfolioSummary:
    def test_creates_markdown_file(self, ledger: Ledger, tmp_path: Path):
        with _patch_ledger(ledger):
            result = export_portfolio_summary("test_strat", tmp_path, PRICES)
        assert result.path.exists()
        assert result.format == "md"
        assert result.report_type == "summary"

    def test_contains_strategy_name(self, ledger: Ledger, tmp_path: Path):
        with _patch_ledger(ledger):
            result = export_portfolio_summary("test_strat", tmp_path, PRICES)
        content = result.path.read_text()
        assert "test_strat" in content

    def test_contains_holdings_section(self, ledger: Ledger, tmp_path: Path):
        with _patch_ledger(ledger):
            result = export_portfolio_summary("test_strat", tmp_path, PRICES)
        content = result.path.read_text()
        assert "## Holdings" in content
        assert "RELIANCE.NS" in content
        assert "TCS.NS" in content

    def test_contains_trades_section(self, ledger: Ledger, tmp_path: Path):
        with _patch_ledger(ledger):
            result = export_portfolio_summary("test_strat", tmp_path, PRICES)
        content = result.path.read_text()
        assert "## Recent Trades" in content
        assert "BUY" in content

    def test_contains_return_info(self, ledger: Ledger, tmp_path: Path):
        with _patch_ledger(ledger):
            result = export_portfolio_summary("test_strat", tmp_path, PRICES)
        content = result.path.read_text()
        assert "Total Return" in content
        assert "NAV" in content

    def test_contains_sector_allocation(self, ledger: Ledger, tmp_path: Path):
        with _patch_ledger(ledger):
            result = export_portfolio_summary("test_strat", tmp_path, PRICES)
        content = result.path.read_text()
        assert "## Sector Allocation" in content

    def test_rows_matches_holdings_count(self, ledger: Ledger, tmp_path: Path):
        with _patch_ledger(ledger):
            result = export_portfolio_summary("test_strat", tmp_path, PRICES)
        # 3 tickers bought, 5 shares of HDFCBANK sold but 15 remain
        assert result.rows == 3

    def test_empty_portfolio(self, empty_ledger: Ledger, tmp_path: Path):
        with _patch_ledger(empty_ledger):
            result = export_portfolio_summary("empty_strat", tmp_path, {})
        assert result.path.exists()
        content = result.path.read_text()
        assert "No holdings" in content or result.rows == 0

    def test_paper_mode_detected(self, ledger: Ledger, tmp_path: Path):
        with _patch_ledger(ledger):
            result = export_portfolio_summary("test_paper", tmp_path, PRICES)
        content = result.path.read_text()
        assert "paper" in content.lower()


# ---------------------------------------------------------------------------
# Holdings CSV
# ---------------------------------------------------------------------------

class TestExportHoldingsCsv:
    def test_creates_csv_file(self, ledger: Ledger, tmp_path: Path):
        with _patch_ledger(ledger):
            result = export_holdings_csv("test_strat", tmp_path, PRICES)
        assert result.path.exists()
        assert result.format == "csv"
        assert result.report_type == "holdings"

    def test_correct_columns(self, ledger: Ledger, tmp_path: Path):
        with _patch_ledger(ledger):
            result = export_holdings_csv("test_strat", tmp_path, PRICES)
        with open(result.path, newline="") as f:
            reader = csv.DictReader(f)
            fields = reader.fieldnames or []
            assert "ticker" in fields
            assert "sector" in fields
            assert "shares" in fields
            assert "avg_price" in fields
            assert "current_price" in fields
            assert "value" in fields
            assert "weight" in fields
            assert "pnl_pct" in fields
            assert "pnl_inr" in fields

    def test_data_rows_match(self, ledger: Ledger, tmp_path: Path):
        with _patch_ledger(ledger):
            result = export_holdings_csv("test_strat", tmp_path, PRICES)
        with open(result.path, newline="") as f:
            reader = list(csv.DictReader(f))
        # 3 holding rows + 1 TOTAL row
        data_rows = [r for r in reader if r["ticker"] != "TOTAL"]
        assert len(data_rows) == 3
        assert result.rows == 3

    def test_summary_row_present(self, ledger: Ledger, tmp_path: Path):
        with _patch_ledger(ledger):
            result = export_holdings_csv("test_strat", tmp_path, PRICES)
        with open(result.path, newline="") as f:
            reader = list(csv.DictReader(f))
        totals = [r for r in reader if r["ticker"] == "TOTAL"]
        assert len(totals) == 1
        assert float(totals[0]["weight"]) == 100.0

    def test_empty_portfolio_csv(self, empty_ledger: Ledger, tmp_path: Path):
        with _patch_ledger(empty_ledger):
            result = export_holdings_csv("empty_strat", tmp_path, {})
        assert result.path.exists()
        assert result.rows == 0
        with open(result.path, newline="") as f:
            reader = list(csv.DictReader(f))
        assert len(reader) == 0  # no data rows, no TOTAL row


# ---------------------------------------------------------------------------
# Trades CSV
# ---------------------------------------------------------------------------

class TestExportTradesCsv:
    def test_creates_csv_file(self, ledger: Ledger, tmp_path: Path):
        with _patch_ledger(ledger):
            result = export_trades_csv("test_strat", tmp_path)
        assert result.path.exists()
        assert result.format == "csv"
        assert result.report_type == "trades"

    def test_all_trades_exported(self, ledger: Ledger, tmp_path: Path):
        with _patch_ledger(ledger):
            result = export_trades_csv("test_strat", tmp_path)
        assert result.rows == 4  # 3 buys + 1 sell

    def test_since_filter(self, ledger: Ledger, tmp_path: Path):
        with _patch_ledger(ledger):
            result = export_trades_csv("test_strat", tmp_path, since="2025-09-01")
        # Only the sell on 2025-09-15 should pass the filter
        assert result.rows == 1
        with open(result.path, newline="") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 1
        assert rows[0]["action"] == "SELL"

    def test_trade_columns(self, ledger: Ledger, tmp_path: Path):
        with _patch_ledger(ledger):
            result = export_trades_csv("test_strat", tmp_path)
        with open(result.path, newline="") as f:
            reader = csv.DictReader(f)
            fields = reader.fieldnames or []
        for col in ["date", "action", "ticker", "shares", "price", "value", "cost", "rationale"]:
            assert col in fields

    def test_empty_trades(self, empty_ledger: Ledger, tmp_path: Path):
        with _patch_ledger(empty_ledger):
            result = export_trades_csv("empty_strat", tmp_path)
        assert result.rows == 0
        assert result.path.exists()


# ---------------------------------------------------------------------------
# Full JSON export
# ---------------------------------------------------------------------------

class TestExportFullJson:
    def test_creates_json_file(self, ledger: Ledger, tmp_path: Path):
        with _patch_ledger(ledger):
            result = export_full_json("test_strat", tmp_path, PRICES)
        assert result.path.exists()
        assert result.format == "json"
        assert result.report_type == "full"

    def test_valid_json(self, ledger: Ledger, tmp_path: Path):
        with _patch_ledger(ledger):
            result = export_full_json("test_strat", tmp_path, PRICES)
        data = json.loads(result.path.read_text())
        assert isinstance(data, dict)

    def test_expected_top_level_keys(self, ledger: Ledger, tmp_path: Path):
        with _patch_ledger(ledger):
            result = export_full_json("test_strat", tmp_path, PRICES)
        data = json.loads(result.path.read_text())
        for key in ["strategy", "mode", "exported_at", "summary", "holdings", "trades", "config", "sector_allocation"]:
            assert key in data, f"Missing top-level key: {key}"

    def test_summary_metrics(self, ledger: Ledger, tmp_path: Path):
        with _patch_ledger(ledger):
            result = export_full_json("test_strat", tmp_path, PRICES)
        data = json.loads(result.path.read_text())
        summary = data["summary"]
        assert "nav" in summary
        assert "cash" in summary
        assert "total_return_pct" in summary
        assert summary["holdings_count"] == 3
        assert summary["total_trades"] == 4

    def test_holdings_data(self, ledger: Ledger, tmp_path: Path):
        with _patch_ledger(ledger):
            result = export_full_json("test_strat", tmp_path, PRICES)
        data = json.loads(result.path.read_text())
        tickers = [h["ticker"] for h in data["holdings"]]
        assert "RELIANCE.NS" in tickers
        assert "TCS.NS" in tickers

    def test_empty_portfolio_json(self, empty_ledger: Ledger, tmp_path: Path):
        with _patch_ledger(empty_ledger):
            result = export_full_json("empty_strat", tmp_path, {})
        data = json.loads(result.path.read_text())
        assert data["holdings"] == []
        assert data["trades"] == []
        assert data["summary"]["holdings_count"] == 0


# ---------------------------------------------------------------------------
# Export all
# ---------------------------------------------------------------------------

class TestExportAll:
    def test_produces_four_files(self, ledger: Ledger, tmp_path: Path):
        with _patch_ledger(ledger):
            results = export_all("test_strat", tmp_path, PRICES)
        assert len(results) == 4
        formats = {r.format for r in results}
        assert formats == {"md", "csv", "json"}
        types = {r.report_type for r in results}
        assert types == {"summary", "holdings", "trades", "full"}

    def test_all_files_exist(self, ledger: Ledger, tmp_path: Path):
        with _patch_ledger(ledger):
            results = export_all("test_strat", tmp_path, PRICES)
        for r in results:
            assert r.path.exists(), f"File not found: {r.path}"

    def test_output_dir_created(self, ledger: Ledger, tmp_path: Path):
        out = tmp_path / "nested" / "reports"
        with _patch_ledger(ledger):
            results = export_all("test_strat", out, PRICES)
        assert out.exists()
        assert len(list(out.iterdir())) == 4


# ---------------------------------------------------------------------------
# ExportResult dataclass
# ---------------------------------------------------------------------------

class TestExportResult:
    def test_fields(self):
        r = ExportResult(path=Path("/tmp/x.csv"), format="csv", report_type="holdings", rows=5)
        assert r.path == Path("/tmp/x.csv")
        assert r.format == "csv"
        assert r.report_type == "holdings"
        assert r.rows == 5
