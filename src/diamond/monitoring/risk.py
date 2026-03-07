"""Portfolio risk management engine.

Computes VaR, CVaR, correlation metrics, tracks drawdowns against
high-water marks, and generates de-risking signals when thresholds breach.

All risk metrics are computed as pure functions. The RiskReport dataclass
aggregates results for consumption by alerts and the CLI.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd

from diamond.data.ledger import Ledger

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RiskReport:
    """Snapshot of portfolio risk metrics."""

    timestamp: str
    nav: float
    high_water_mark: float
    drawdown_pct: float  # Current drawdown from HWM (0-100)
    var_95: float  # 1-day 95% VaR in INR (positive = loss)
    var_99: float  # 1-day 99% VaR in INR
    cvar_95: float  # Expected Shortfall at 95%
    max_correlation: float  # Highest pairwise correlation in portfolio
    avg_correlation: float  # Average pairwise correlation
    beta: float  # Portfolio beta to benchmark
    volatility_annual: float  # Annualized portfolio volatility (%)
    signals: list[str] = field(default_factory=list)  # De-risking signals


# ---------------------------------------------------------------------------
# Pure metric functions
# ---------------------------------------------------------------------------


def portfolio_returns(
    holdings: dict[str, int],
    prices_df: pd.DataFrame,
) -> pd.Series:
    """Compute daily portfolio returns from holdings and price matrix.

    Args:
        holdings: {ticker: shares}
        prices_df: DataFrame with tickers as columns, dates as index.

    Returns:
        Series of daily portfolio returns.
    """
    tickers = [t for t in holdings if t in prices_df.columns]
    if not tickers:
        return pd.Series(dtype=float)

    subset = prices_df[tickers].dropna(how="all")
    if len(subset) < 2:
        return pd.Series(dtype=float)

    # Weight by position value at first available date
    first_prices = subset.iloc[0]
    weights = pd.Series({t: holdings[t] * first_prices[t] for t in tickers if pd.notna(first_prices[t])})
    total = weights.sum()
    if total <= 0:
        return pd.Series(dtype=float)
    weights = weights / total

    daily_returns = pd.DataFrame(subset.pct_change().dropna(how="all"))
    port_returns_df = pd.DataFrame(daily_returns[weights.index]).mul(weights).sum(axis=1)
    return pd.Series(port_returns_df).dropna()


def calculate_var(returns: pd.Series, confidence: float = 0.95, portfolio_value: float = 1.0) -> float:
    """Historical Value-at-Risk.

    Args:
        returns: Daily return series.
        confidence: Confidence level (0.95 or 0.99).
        portfolio_value: Current portfolio value in INR.

    Returns:
        VaR as a positive INR amount (potential loss).
    """
    if returns.empty or len(returns) < 10:
        return 0.0
    percentile = (1 - confidence) * 100
    var_pct = float(-np.percentile(returns, percentile))
    return round(var_pct * portfolio_value, 2)


def calculate_cvar(returns: pd.Series, confidence: float = 0.95, portfolio_value: float = 1.0) -> float:
    """Conditional VaR (Expected Shortfall).

    Average loss beyond the VaR threshold.
    """
    if returns.empty or len(returns) < 10:
        return 0.0
    percentile = (1 - confidence) * 100
    threshold = np.percentile(returns, percentile)
    tail = returns[returns <= threshold]
    if len(tail) == 0:
        return 0.0
    cvar_pct = -tail.mean()
    return round(cvar_pct * portfolio_value, 2)


def correlation_matrix(prices_df: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    """Pairwise correlation matrix for holdings."""
    available = [t for t in tickers if t in prices_df.columns]
    if len(available) < 2:
        return pd.DataFrame()
    returns_df = pd.DataFrame(prices_df[available].pct_change().dropna())
    if len(returns_df) < 20:
        return pd.DataFrame()
    return returns_df.corr()


def portfolio_beta(
    port_returns: pd.Series,
    benchmark_returns: pd.Series,
) -> float:
    """Portfolio beta relative to benchmark."""
    aligned = pd.DataFrame({"port": port_returns, "bench": benchmark_returns}).dropna()
    if len(aligned) < 20:
        return 1.0
    cov = float(pd.Series(aligned["port"]).cov(pd.Series(aligned["bench"])))
    var = float(aligned["bench"].var())
    if var == 0:
        return 1.0
    return round(cov / var, 4)


# ---------------------------------------------------------------------------
# De-risking signal generation
# ---------------------------------------------------------------------------

_DRAWDOWN_WARNING = 10.0  # % from HWM
_DRAWDOWN_CRITICAL = 15.0  # % from HWM
_VAR_CAPITAL_PCT = 3.0  # 1-day VaR > 3% of NAV
_CORRELATION_HIGH = 0.80  # Average correlation threshold
_VOLATILITY_HIGH = 30.0  # Annualized vol % threshold


def generate_signals(report: RiskReport) -> list[str]:
    """Generate de-risking signals from a risk report."""
    signals: list[str] = []

    if report.drawdown_pct >= _DRAWDOWN_CRITICAL:
        signals.append(f"CRITICAL: Drawdown {report.drawdown_pct:.1f}% from high-water mark — consider liquidating")
    elif report.drawdown_pct >= _DRAWDOWN_WARNING:
        signals.append(f"WARNING: Drawdown {report.drawdown_pct:.1f}% from high-water mark")

    if report.nav > 0 and report.var_95 / report.nav * 100 > _VAR_CAPITAL_PCT:
        signals.append(
            f"WARNING: 1-day VaR₉₅ is {report.var_95:,.0f} INR ({report.var_95 / report.nav * 100:.1f}% of NAV)"
        )

    if report.avg_correlation > _CORRELATION_HIGH:
        signals.append(
            f"WARNING: High avg correlation ({report.avg_correlation:.2f}) — portfolio lacks diversification"
        )

    if report.volatility_annual > _VOLATILITY_HIGH:
        signals.append(
            f"WARNING: Annualized volatility {report.volatility_annual:.1f}% exceeds {_VOLATILITY_HIGH}% threshold"
        )

    return signals


# ---------------------------------------------------------------------------
# High-water mark tracking (stored in ledger state table)
# ---------------------------------------------------------------------------


def _get_hwm(ledger: Ledger) -> float:
    """Read high-water mark from ledger state."""
    with ledger._conn() as conn:
        row = conn.execute("SELECT value FROM state WHERE key = 'high_water_mark'").fetchone()
        if row:
            return float(row[0])
    return ledger.get_initial_capital()


def _set_hwm(ledger: Ledger, hwm: float) -> None:
    """Write high-water mark to ledger state."""
    with ledger._conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO state (key, value) VALUES ('high_water_mark', ?)",
            (str(hwm),),
        )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def compute_risk_report(
    strategy: str,
    current_prices: dict[str, float],
    prices_df: pd.DataFrame | None = None,
    benchmark_returns: pd.Series | None = None,
) -> RiskReport:
    """Compute comprehensive risk report for a strategy.

    Args:
        strategy: Strategy name (for ledger lookup).
        current_prices: {ticker: price} for current holdings.
        prices_df: Historical prices DataFrame (if None, returns partial report).
        benchmark_returns: Benchmark daily returns for beta calculation.

    Returns:
        RiskReport with all risk metrics and de-risking signals.
    """
    ledger = Ledger(strategy)
    holdings = ledger.get_holdings()
    nav = ledger.get_portfolio_value(current_prices)

    # Update high-water mark
    hwm = _get_hwm(ledger)
    if nav > hwm:
        hwm = nav
        _set_hwm(ledger, hwm)

    drawdown_pct = ((hwm - nav) / hwm * 100) if hwm > 0 else 0.0

    # Compute return-based metrics if price history available
    var_95 = 0.0
    var_99 = 0.0
    cvar_95 = 0.0
    max_corr = 0.0
    avg_corr = 0.0
    beta = 1.0
    vol_annual = 0.0

    if prices_df is not None and not prices_df.empty:
        port_ret = portfolio_returns(holdings, prices_df)

        if len(port_ret) >= 10:
            var_95 = calculate_var(port_ret, 0.95, nav)
            var_99 = calculate_var(port_ret, 0.99, nav)
            cvar_95 = calculate_cvar(port_ret, 0.95, nav)
            vol_annual = round(float(port_ret.std() * np.sqrt(252) * 100), 2)

        # Correlation
        tickers = list(holdings.keys())
        corr = correlation_matrix(prices_df, tickers)
        if not corr.empty:
            # Extract upper triangle (excluding diagonal)
            mask = np.triu(np.ones(corr.shape, dtype=bool), k=1)
            upper = corr.where(mask)
            stacked = upper.stack()
            if len(stacked) > 0:
                max_corr = round(float(stacked.max()), 4)
                avg_corr = round(float(stacked.mean()), 4)

        # Beta
        if benchmark_returns is not None and len(port_ret) >= 20:
            beta = portfolio_beta(port_ret, benchmark_returns)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    report = RiskReport(
        timestamp=timestamp,
        nav=round(nav, 2),
        high_water_mark=round(hwm, 2),
        drawdown_pct=round(drawdown_pct, 2),
        var_95=var_95,
        var_99=var_99,
        cvar_95=cvar_95,
        max_correlation=max_corr,
        avg_correlation=avg_corr,
        beta=beta,
        volatility_annual=vol_annual,
    )

    # Generate signals (create new report with signals since frozen)
    signals = generate_signals(report)
    if signals:
        report = RiskReport(
            timestamp=report.timestamp,
            nav=report.nav,
            high_water_mark=report.high_water_mark,
            drawdown_pct=report.drawdown_pct,
            var_95=report.var_95,
            var_99=report.var_99,
            cvar_95=report.cvar_95,
            max_correlation=report.max_correlation,
            avg_correlation=report.avg_correlation,
            beta=report.beta,
            volatility_annual=report.volatility_annual,
            signals=signals,
        )

    return report
