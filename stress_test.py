"""Monte Carlo stress test for strategy backtests.

Bootstraps historical window returns to simulate thousands of possible
return sequences. Quantifies the range of outcomes and tail risk.

Usage:
    python stress_test.py [strategy] [num_simulations]
"""

import json
import sys

import numpy as np


def load_backtest_results(strategy: str) -> dict:
    """Load backtest JSON results."""
    path = f"reports/backtest/{strategy}/backtest_results.json"
    with open(path) as f:
        return json.load(f)


def run_stress_test(strategy: str, n_sims: int = 10000):
    """Bootstrap window returns to simulate outcome distribution."""
    data = load_backtest_results(strategy)
    windows = data["windows"]
    initial_capital = data["metrics"]["initial_capital"]

    # Extract per-window return factors (1 + return_pct/100)
    return_factors = np.array([1 + w["return_pct"] / 100 for w in windows])
    n_windows = len(return_factors)

    print(f"Strategy: {strategy}")
    print(f"Windows: {n_windows}, Initial Capital: {initial_capital:,.0f} INR")
    print(f"Historical returns per window: {[f'{(r-1)*100:+.1f}%' for r in return_factors]}")
    print(f"\nRunning {n_sims:,} bootstrap simulations...")

    rng = np.random.default_rng(42)

    # Bootstrap: randomly sample n_windows returns with replacement
    final_navs = np.zeros(n_sims)
    cagrs = np.zeros(n_sims)
    max_drawdowns = np.zeros(n_sims)
    years = data["metrics"]["years"]

    for i in range(n_sims):
        # Sample window returns with replacement
        sampled = rng.choice(return_factors, size=n_windows, replace=True)

        # Compute cumulative NAV path
        nav_path = initial_capital * np.cumprod(sampled)
        final_navs[i] = nav_path[-1]

        # CAGR
        if nav_path[-1] > 0:
            cagrs[i] = (nav_path[-1] / initial_capital) ** (1 / years) - 1
        else:
            cagrs[i] = -1.0

        # Max drawdown from the path
        peak = initial_capital
        max_dd = 0.0
        for nav in nav_path:
            if nav > peak:
                peak = nav
            dd = (peak - nav) / peak if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
        max_drawdowns[i] = max_dd

    # Compute percentiles
    print(f"\n{'='*60}")
    print(f"  MONTE CARLO STRESS TEST: {strategy.upper()}")
    print(f"  {n_sims:,} simulations, {n_windows} windows bootstrapped")
    print(f"{'='*60}")

    print(f"\n  Final NAV Distribution ({initial_capital:,.0f} INR initial):")
    for pct in [1, 5, 10, 25, 50, 75, 90, 95, 99]:
        val = np.percentile(final_navs, pct)
        print(f"    P{pct:>2}: {val:>14,.0f} INR  ({(val/initial_capital - 1)*100:>+8.1f}%)")

    print(f"\n  CAGR Distribution:")
    for pct in [1, 5, 10, 25, 50, 75, 90, 95, 99]:
        val = np.percentile(cagrs, pct) * 100
        print(f"    P{pct:>2}: {val:>+8.2f}%")

    print(f"\n  Max Drawdown Distribution:")
    for pct in [50, 75, 90, 95, 99]:
        val = np.percentile(max_drawdowns, pct) * 100
        print(f"    P{pct:>2}: {val:>8.2f}%")

    # Risk metrics
    prob_loss = np.mean(final_navs < initial_capital) * 100
    prob_double = np.mean(final_navs > initial_capital * 2) * 100
    prob_5x = np.mean(final_navs > initial_capital * 5) * 100
    prob_10x = np.mean(final_navs > initial_capital * 10) * 100
    prob_20x = np.mean(final_navs > initial_capital * 20) * 100

    print(f"\n  Probability Outcomes:")
    print(f"    Loss (< initial):   {prob_loss:>5.1f}%")
    print(f"    > 2x initial:       {prob_double:>5.1f}%")
    print(f"    > 5x initial:       {prob_5x:>5.1f}%")
    print(f"    > 10x initial:      {prob_10x:>5.1f}%")
    print(f"    > 20x initial:      {prob_20x:>5.1f}%")

    # Worst-case analysis
    worst_1pct = np.percentile(final_navs, 1)
    worst_5pct = np.percentile(final_navs, 5)
    print(f"\n  Tail Risk:")
    print(f"    1% worst case:      {worst_1pct:>14,.0f} INR ({(worst_1pct/initial_capital - 1)*100:>+.1f}%)")
    print(f"    5% worst case:      {worst_5pct:>14,.0f} INR ({(worst_5pct/initial_capital - 1)*100:>+.1f}%)")
    print(f"    Median outcome:     {np.median(final_navs):>14,.0f} INR")
    print(f"    Historical actual:  {data['metrics']['final_nav']:>14,.0f} INR")
    print(f"{'='*60}")


def run_regime_stress_test(strategy: str, n_sims: int = 10000):
    """Regime-aware stress test: clusters bad windows together.

    Unlike standard bootstrap (independent draws), this simulates
    market regime persistence — bear markets cluster, so do bull markets.
    Uses a Markov chain: if current window is negative, next window has
    higher probability of also being negative (and vice versa).
    """
    data = load_backtest_results(strategy)
    windows = data["windows"]
    initial_capital = data["metrics"]["initial_capital"]

    return_factors = np.array([1 + w["return_pct"] / 100 for w in windows])
    n_windows = len(return_factors)
    years = data["metrics"]["years"]

    # Split into positive and negative windows
    pos_returns = return_factors[return_factors >= 1.0]
    neg_returns = return_factors[return_factors < 1.0]

    if len(neg_returns) == 0:
        neg_returns = np.array([0.95])  # Fallback
    if len(pos_returns) == 0:
        pos_returns = np.array([1.05])

    # Historical transition probabilities
    transitions = {"pos_to_pos": 0, "pos_to_neg": 0, "neg_to_pos": 0, "neg_to_neg": 0}
    for i in range(1, len(return_factors)):
        prev_pos = return_factors[i - 1] >= 1.0
        curr_pos = return_factors[i] >= 1.0
        if prev_pos and curr_pos:
            transitions["pos_to_pos"] += 1
        elif prev_pos and not curr_pos:
            transitions["pos_to_neg"] += 1
        elif not prev_pos and curr_pos:
            transitions["neg_to_pos"] += 1
        else:
            transitions["neg_to_neg"] += 1

    # Compute transition probabilities
    pos_total = transitions["pos_to_pos"] + transitions["pos_to_neg"]
    neg_total = transitions["neg_to_pos"] + transitions["neg_to_neg"]
    p_stay_pos = transitions["pos_to_pos"] / pos_total if pos_total > 0 else 0.7
    p_stay_neg = transitions["neg_to_neg"] / neg_total if neg_total > 0 else 0.4

    print(f"\nStrategy: {strategy}")
    print(f"Windows: {n_windows} ({len(pos_returns)} positive, {len(neg_returns)} negative)")
    print(f"Regime persistence: P(pos->pos)={p_stay_pos:.0%}, P(neg->neg)={p_stay_neg:.0%}")
    print(f"\nRunning {n_sims:,} regime-aware simulations...")

    rng = np.random.default_rng(42)

    final_navs = np.zeros(n_sims)
    max_drawdowns = np.zeros(n_sims)
    max_consecutive_losses = np.zeros(n_sims, dtype=int)

    for i in range(n_sims):
        # Start with random state
        in_positive = rng.random() < len(pos_returns) / n_windows
        sampled = np.zeros(n_windows)
        consec_loss = 0
        max_consec = 0

        for j in range(n_windows):
            if in_positive:
                sampled[j] = rng.choice(pos_returns)
                consec_loss = 0
            else:
                sampled[j] = rng.choice(neg_returns)
                consec_loss += 1
                max_consec = max(max_consec, consec_loss)

            # Transition
            if in_positive:
                in_positive = rng.random() < p_stay_pos
            else:
                in_positive = rng.random() >= p_stay_neg

        nav_path = initial_capital * np.cumprod(sampled)
        final_navs[i] = nav_path[-1]
        max_consecutive_losses[i] = max_consec

        peak = initial_capital
        max_dd = 0.0
        for nav in nav_path:
            if nav > peak:
                peak = nav
            dd = (peak - nav) / peak if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
        max_drawdowns[i] = max_dd

    print(f"\n{'='*60}")
    print(f"  REGIME-AWARE STRESS TEST: {strategy.upper()}")
    print(f"  {n_sims:,} simulations with clustered regimes")
    print(f"{'='*60}")

    print(f"\n  Final NAV Distribution ({initial_capital:,.0f} INR initial):")
    for pct in [1, 5, 10, 25, 50, 75, 90, 95, 99]:
        val = np.percentile(final_navs, pct)
        print(f"    P{pct:>2}: {val:>14,.0f} INR  ({(val/initial_capital - 1)*100:>+8.1f}%)")

    cagrs = np.where(
        final_navs > 0,
        (final_navs / initial_capital) ** (1 / years) - 1,
        -1.0,
    )
    print(f"\n  CAGR Distribution:")
    for pct in [1, 5, 10, 25, 50, 75, 90, 95, 99]:
        val = np.percentile(cagrs, pct) * 100
        print(f"    P{pct:>2}: {val:>+8.2f}%")

    print(f"\n  Max Drawdown Distribution:")
    for pct in [50, 75, 90, 95, 99]:
        val = np.percentile(max_drawdowns, pct) * 100
        print(f"    P{pct:>2}: {val:>8.2f}%")

    print(f"\n  Max Consecutive Loss Windows:")
    for pct in [50, 75, 90, 95, 99]:
        val = int(np.percentile(max_consecutive_losses, pct))
        print(f"    P{pct:>2}: {val} windows ({val * 6} months)")

    prob_loss = np.mean(final_navs < initial_capital) * 100
    prob_10x = np.mean(final_navs > initial_capital * 10) * 100
    prob_20x = np.mean(final_navs > initial_capital * 20) * 100

    print(f"\n  Probability Outcomes:")
    print(f"    Loss (< initial):   {prob_loss:>5.1f}%")
    print(f"    > 10x initial:      {prob_10x:>5.1f}%")
    print(f"    > 20x initial:      {prob_20x:>5.1f}%")

    worst_1pct = np.percentile(final_navs, 1)
    print(f"\n  Tail Risk (vs standard bootstrap):")
    print(f"    1% worst case:      {worst_1pct:>14,.0f} INR ({(worst_1pct/initial_capital - 1)*100:>+.1f}%)")
    print(f"    Median outcome:     {np.median(final_navs):>14,.0f} INR")
    print(f"    Historical actual:  {data['metrics']['final_nav']:>14,.0f} INR")
    print(f"{'='*60}")


if __name__ == "__main__":
    strategy = sys.argv[1] if len(sys.argv) > 1 else "gods_plan"
    n_sims = int(sys.argv[2]) if len(sys.argv) > 2 else 10000
    mode = sys.argv[3] if len(sys.argv) > 3 else "standard"

    if mode == "regime":
        run_regime_stress_test(strategy, n_sims)
    elif mode == "both":
        run_stress_test(strategy, n_sims)
        print("\n" + "=" * 60 + "\n")
        run_regime_stress_test(strategy, n_sims)
    else:
        run_stress_test(strategy, n_sims)
