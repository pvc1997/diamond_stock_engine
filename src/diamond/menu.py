"""Interactive tree menu for Diamond Stock Engine.

Provides a navigable tree of all commands so you never need to
remember flags or subcommands. Just run `diamond` with no arguments.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field

from simple_term_menu import TerminalMenu

# ---------------------------------------------------------------------------
# Menu tree structure
# ---------------------------------------------------------------------------


@dataclass
class MenuItem:
    """A single menu item — either a leaf (command) or a branch (submenu)."""

    label: str
    description: str = ""
    command: str | None = None  # Shell command to run (leaf)
    prompt: str | None = None  # Prompt user for input before running
    children: list[MenuItem] = field(default_factory=list)

    @property
    def is_leaf(self) -> bool:
        return self.command is not None and not self.children


def build_menu_tree() -> MenuItem:
    """Build the full command tree."""
    return MenuItem(
        label="Diamond Stock Engine",
        description="Systematic Indian equity portfolio management",
        children=[
            # --- Daily ---
            MenuItem(
                label="Daily",
                description="Your daily routine",
                children=[
                    MenuItem(
                        label="Today's Briefing",
                        description="Market + portfolio + opportunities + insight",
                        command="diamond today",
                    ),
                    MenuItem(
                        label="Learn",
                        description="Today's market concept (uses your portfolio)",
                        command="diamond learn",
                    ),
                    MenuItem(
                        label="Learn — Pick Topic",
                        description="Choose a specific topic to learn",
                        children=[
                            MenuItem(label="Beta", command="diamond learn --topic 0"),
                            MenuItem(label="Alpha", command="diamond learn --topic 1"),
                            MenuItem(label="Volatility", command="diamond learn --topic 2"),
                            MenuItem(label="Hurst Exponent", command="diamond learn --topic 3"),
                            MenuItem(label="CAGR", command="diamond learn --topic 4"),
                            MenuItem(label="India VIX", command="diamond learn --topic 5"),
                            MenuItem(label="Sector Diversification", command="diamond learn --topic 6"),
                            MenuItem(label="Drawdown", command="diamond learn --topic 7"),
                            MenuItem(label="Position Sizing", command="diamond learn --topic 8"),
                            MenuItem(label="Quality Score", command="diamond learn --topic 9"),
                        ],
                    ),
                    MenuItem(
                        label="Streak",
                        description="Check-in streak + milestones",
                        command="diamond streak",
                    ),
                    MenuItem(
                        label="Market Pulse",
                        description="Market regime + investment verdict",
                        command="diamond pulse",
                    ),
                ],
            ),
            # --- Portfolio ---
            MenuItem(
                label="Portfolio",
                description="View and manage your holdings",
                children=[
                    MenuItem(
                        label="Dashboard",
                        description="Live portfolio dashboard (Ctrl+C to exit)",
                        children=[
                            MenuItem(label="God's Plan", command="diamond dashboard gods_plan"),
                            MenuItem(label="Steady", command="diamond dashboard steady"),
                            MenuItem(label="Baseline", command="diamond dashboard baseline"),
                            MenuItem(label="Accumulate", command="diamond dashboard accumulate"),
                        ],
                    ),
                    MenuItem(
                        label="Status",
                        description="Quick portfolio status across all strategies",
                        command="diamond status",
                    ),
                    MenuItem(
                        label="Health Check",
                        description="Drawdown, drift, stop-loss alerts",
                        children=[
                            MenuItem(label="God's Plan", command="diamond health gods_plan"),
                            MenuItem(label="Steady", command="diamond health steady"),
                            MenuItem(label="Accumulate", command="diamond health accumulate"),
                        ],
                    ),
                    MenuItem(
                        label="Risk Report",
                        description="VaR, CVaR, correlation, beta, volatility",
                        children=[
                            MenuItem(label="God's Plan", command="diamond risk gods_plan"),
                            MenuItem(label="Steady", command="diamond risk steady"),
                            MenuItem(label="Accumulate", command="diamond risk accumulate"),
                        ],
                    ),
                    MenuItem(
                        label="Drift Check",
                        description="How far is your portfolio from target weights?",
                        children=[
                            MenuItem(label="God's Plan", command="diamond drift gods_plan"),
                            MenuItem(label="Steady", command="diamond drift steady"),
                        ],
                    ),
                    MenuItem(
                        label="Performance Attribution",
                        description="Which stocks/sectors drove your returns?",
                        children=[
                            MenuItem(
                                label="Last 1 Month",
                                command="diamond attribution accumulate --period 1M",
                            ),
                            MenuItem(
                                label="Last 3 Months",
                                command="diamond attribution accumulate --period 3M",
                            ),
                            MenuItem(
                                label="Last 6 Months",
                                command="diamond attribution accumulate --period 6M",
                            ),
                            MenuItem(
                                label="Year to Date",
                                command="diamond attribution accumulate --period YTD",
                            ),
                            MenuItem(
                                label="Last 1 Year",
                                command="diamond attribution accumulate --period 1Y",
                            ),
                        ],
                    ),
                    MenuItem(
                        label="Orders",
                        description="View order book",
                        children=[
                            MenuItem(label="God's Plan", command="diamond orders gods_plan"),
                            MenuItem(label="Steady", command="diamond orders steady"),
                            MenuItem(label="Accumulate", command="diamond orders accumulate"),
                        ],
                    ),
                ],
            ),
            # --- Accumulate ---
            MenuItem(
                label="Accumulate",
                description="Long-term capital deployment",
                children=[
                    MenuItem(
                        label="Status",
                        description="Current accumulate portfolio",
                        command="diamond accumulate --status",
                    ),
                    MenuItem(
                        label="Opportunities",
                        description="See what to buy (no execution)",
                        command="diamond accumulate --opportunities",
                    ),
                    MenuItem(
                        label="Deploy — Dry Run",
                        description="Preview buys without executing",
                        command="diamond accumulate --deploy --dry-run",
                    ),
                    MenuItem(
                        label="Deploy — Execute",
                        description="Execute buys with real capital",
                        command="diamond accumulate --deploy",
                    ),
                    MenuItem(
                        label="Review Holdings",
                        description="Check for quality drops and stop-losses",
                        command="diamond accumulate --review",
                    ),
                    MenuItem(
                        label="Review + Swap (Dry Run)",
                        description="Preview sell/buy swap suggestions",
                        command="diamond accumulate --review --swap --dry-run",
                    ),
                    MenuItem(
                        label="Review + Swap (Execute)",
                        description="Execute swap suggestions",
                        command="diamond accumulate --review --swap",
                    ),
                    MenuItem(
                        label="Add Cash",
                        description="Top up cash for next deployment",
                        prompt="Amount in INR",
                        command="diamond accumulate --add-cash {input}",
                    ),
                    MenuItem(
                        label="Reset Portfolio",
                        description="Reset accumulate to fresh start",
                        prompt="Capital in INR (default 500000)",
                        command="diamond accumulate --reset --capital {input}",
                    ),
                ],
            ),
            # --- Strategies ---
            MenuItem(
                label="Run Strategy",
                description="Execute a portfolio strategy",
                children=[
                    MenuItem(
                        label="God's Plan",
                        children=[
                            MenuItem(label="Dry Run", command="diamond run gods_plan --dry-run"),
                            MenuItem(label="Execute (offline)", command="diamond run gods_plan"),
                            MenuItem(label="Execute (live/Kite)", command="diamond run gods_plan --live"),
                            MenuItem(
                                label="Live Dry Run",
                                command="diamond run gods_plan --live --dry-run",
                            ),
                        ],
                    ),
                    MenuItem(
                        label="Steady",
                        children=[
                            MenuItem(label="Dry Run", command="diamond run steady --dry-run"),
                            MenuItem(label="Execute (offline)", command="diamond run steady"),
                            MenuItem(label="Execute (live/Kite)", command="diamond run steady --live"),
                        ],
                    ),
                    MenuItem(
                        label="Baseline",
                        children=[
                            MenuItem(label="Dry Run", command="diamond run baseline --dry-run"),
                            MenuItem(label="Execute (offline)", command="diamond run baseline"),
                        ],
                    ),
                ],
            ),
            # --- Paper Trading ---
            MenuItem(
                label="Paper Trading",
                description="Simulated trading (no real money)",
                children=[
                    MenuItem(
                        label="God's Plan — Paper",
                        children=[
                            MenuItem(label="Run paper", command="diamond paper gods_plan"),
                            MenuItem(label="Status", command="diamond paper gods_plan --status"),
                            MenuItem(label="Reset", command="diamond paper gods_plan --reset"),
                        ],
                    ),
                    MenuItem(
                        label="Steady — Paper",
                        children=[
                            MenuItem(label="Run paper", command="diamond paper steady"),
                            MenuItem(label="Status", command="diamond paper steady --status"),
                            MenuItem(label="Reset", command="diamond paper steady --reset"),
                        ],
                    ),
                    MenuItem(
                        label="Promote to Live",
                        children=[
                            MenuItem(label="God's Plan (preview)", command="diamond promote gods_plan"),
                            MenuItem(
                                label="God's Plan (execute)",
                                command="diamond promote gods_plan --execute",
                            ),
                            MenuItem(label="Steady (preview)", command="diamond promote steady"),
                            MenuItem(label="Steady (execute)", command="diamond promote steady --execute"),
                        ],
                    ),
                ],
            ),
            # --- Analysis ---
            MenuItem(
                label="Analysis",
                description="Stock screening, deep analysis, sentiment",
                children=[
                    MenuItem(
                        label="Market Screener",
                        description="Screen NSE 500 for alpha, beta, CAGR, volatility",
                        command="diamond screen",
                    ),
                    MenuItem(
                        label="Deep Stock Analysis",
                        description="Technicals + fundamentals + AI verdict",
                        prompt="Ticker (e.g., RELIANCE.NS)",
                        command="diamond analyze {input}",
                    ),
                    MenuItem(
                        label="Sentiment Analysis",
                        description="AI-powered sentiment for a stock",
                        prompt="Ticker (e.g., RELIANCE.NS)",
                        command="diamond sentiment {input}",
                    ),
                    MenuItem(
                        label="Compare Strategies",
                        description="Side-by-side strategy comparison",
                        command="diamond compare gods_plan steady",
                    ),
                    MenuItem(
                        label="What-If (Add/Remove stocks)",
                        description="Simulate adding/removing stocks",
                        prompt="Tickers to add (comma-separated, blank to skip)",
                        command="diamond whatif gods_plan",
                    ),
                ],
            ),
            # --- Scenarios ---
            MenuItem(
                label="Scenarios",
                description="What-if stress tests and simulations",
                children=[
                    MenuItem(
                        label="Market Crash -5%",
                        command="diamond scenario --crash -5",
                    ),
                    MenuItem(
                        label="Market Crash -10%",
                        command="diamond scenario --crash -10",
                    ),
                    MenuItem(
                        label="Market Crash -20%",
                        command="diamond scenario --crash -20",
                    ),
                    MenuItem(
                        label="Market Rally +5%",
                        command="diamond scenario --crash 5",
                    ),
                    MenuItem(
                        label="Market Rally +10%",
                        command="diamond scenario --crash 10",
                    ),
                    MenuItem(
                        label="Add Cash",
                        description="What if I add money today?",
                        prompt="Amount in INR",
                        command="diamond scenario --add {input}",
                    ),
                    MenuItem(
                        label="Compare Stocks",
                        description="What if I'd bought X instead of Y?",
                        prompt="HELD:ALT (e.g., RELIANCE:TCS)",
                        command="diamond scenario --compare {input}",
                    ),
                ],
            ),
            # --- Backtest ---
            MenuItem(
                label="Backtest",
                description="Historical walk-forward backtesting",
                children=[
                    MenuItem(
                        label="God's Plan (5 year)",
                        command="diamond backtest gods_plan --start 2020-01-01 --end 2025-01-01",
                    ),
                    MenuItem(
                        label="God's Plan (10 year)",
                        command="diamond backtest gods_plan --start 2015-01-01 --end 2025-01-01",
                    ),
                    MenuItem(
                        label="Steady (5 year)",
                        command="diamond backtest steady --start 2020-01-01 --end 2025-01-01",
                    ),
                    MenuItem(
                        label="Baseline (5 year)",
                        command="diamond backtest baseline --start 2020-01-01 --end 2025-01-01",
                    ),
                    MenuItem(
                        label="Custom",
                        prompt="Strategy start end (e.g., gods_plan 2018-01-01 2025-01-01)",
                        command="diamond backtest {input}",
                    ),
                ],
            ),
            # --- Reports & Export ---
            MenuItem(
                label="Reports",
                description="Export and tax reports",
                children=[
                    MenuItem(
                        label="Export — All Formats",
                        children=[
                            MenuItem(label="God's Plan", command="diamond export gods_plan --format all"),
                            MenuItem(label="Steady", command="diamond export steady --format all"),
                            MenuItem(label="Accumulate", command="diamond export accumulate --format all"),
                        ],
                    ),
                    MenuItem(
                        label="Export — Markdown Summary",
                        children=[
                            MenuItem(
                                label="God's Plan",
                                command="diamond export gods_plan --format markdown",
                            ),
                            MenuItem(
                                label="Accumulate",
                                command="diamond export accumulate --format markdown",
                            ),
                        ],
                    ),
                    MenuItem(
                        label="Tax Report",
                        children=[
                            MenuItem(label="God's Plan", command="diamond tax gods_plan"),
                            MenuItem(label="Steady", command="diamond tax steady"),
                            MenuItem(label="Accumulate", command="diamond tax accumulate"),
                        ],
                    ),
                    MenuItem(
                        label="Corporate Actions",
                        description="Scan for splits/dividends and apply to ledger",
                        children=[
                            MenuItem(label="God's Plan", command="diamond actions gods_plan"),
                            MenuItem(label="Steady", command="diamond actions steady"),
                            MenuItem(label="Accumulate", command="diamond actions accumulate"),
                        ],
                    ),
                ],
            ),
            # --- Watchlist ---
            MenuItem(
                label="Watchlist",
                description="Track stocks outside your portfolio",
                children=[
                    MenuItem(
                        label="View Watchlist",
                        command="diamond watch --show",
                    ),
                    MenuItem(
                        label="Add Stock",
                        prompt="Ticker (e.g., RELIANCE.NS)",
                        command="diamond watch --add {input}",
                    ),
                    MenuItem(
                        label="Remove Stock",
                        prompt="Ticker (e.g., RELIANCE.NS)",
                        command="diamond watch --remove {input}",
                    ),
                    MenuItem(
                        label="Check Alerts",
                        command="diamond watch --alerts",
                    ),
                ],
            ),
            # --- Kite / Broker ---
            MenuItem(
                label="Broker (Kite)",
                description="Zerodha Kite Connect integration",
                children=[
                    MenuItem(
                        label="Login",
                        description="Open browser for Kite authentication",
                        command="diamond kite --auth",
                    ),
                    MenuItem(
                        label="Set Token",
                        prompt="Request token from URL",
                        command="diamond kite --token {input}",
                    ),
                    MenuItem(
                        label="Authorize Sells (TPIN)",
                        command="diamond kite --authorize-sells",
                    ),
                    MenuItem(
                        label="Import Holdings",
                        children=[
                            MenuItem(label="God's Plan", command="diamond kite --import gods_plan"),
                            MenuItem(label="Accumulate", command="diamond kite --import accumulate"),
                        ],
                    ),
                    MenuItem(
                        label="Reconcile",
                        children=[
                            MenuItem(label="God's Plan", command="diamond reconcile gods_plan"),
                            MenuItem(label="Accumulate", command="diamond reconcile accumulate"),
                        ],
                    ),
                    MenuItem(
                        label="Session Status",
                        command="diamond kite --status",
                    ),
                ],
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Interactive menu runner
# ---------------------------------------------------------------------------


def _format_entry(item: MenuItem) -> str:
    """Format a menu item for display."""
    if item.children:
        suffix = f"  ({item.description})" if item.description else ""
        return f"{item.label}  >{suffix}"
    suffix = f"  — {item.description}" if item.description else ""
    return f"{item.label}{suffix}"


def _run_command(cmd: str) -> None:
    """Run a diamond command, showing output in the terminal."""
    print(f"\n  Running: {cmd}\n")
    print("─" * 60)
    subprocess.run(cmd, shell=True)
    print("─" * 60)
    input("\n  Press Enter to continue...")


def _prompt_input(label: str) -> str | None:
    """Prompt user for input. Returns None if cancelled."""
    try:
        value = input(f"\n  {label}: ").strip()
        if not value:
            return None
        return value
    except (KeyboardInterrupt, EOFError):
        return None


def navigate(node: MenuItem | None = None, breadcrumb: list[str] | None = None) -> None:
    """Navigate the menu tree interactively."""
    if node is None:
        node = build_menu_tree()
    if breadcrumb is None:
        breadcrumb = []

    while True:
        # Build breadcrumb display
        path = " > ".join(["Diamond"] + breadcrumb) if breadcrumb else "Diamond"

        # If this is a leaf node, execute it
        if node.is_leaf:
            cmd = node.command or ""
            if node.prompt and "{input}" in cmd:
                value = _prompt_input(node.prompt)
                if value is None:
                    return
                cmd = cmd.replace("{input}", value)
            _run_command(cmd)
            return

        # Build menu entries
        entries = [_format_entry(child) for child in node.children]
        entries.append("")  # separator
        if breadcrumb:
            entries.append("< Back")
        entries.append("Exit")

        # Clear screen for clean display
        os.system("clear" if os.name != "nt" else "cls")
        print(f"\n  {path}\n")

        menu = TerminalMenu(
            entries,
            title=f"  {node.description}" if node.description else None,
            menu_cursor_style=("fg_cyan", "bold"),
            menu_highlight_style=("bg_gray", "fg_black", "bold"),
            skip_empty_entries=True,
        )

        raw_idx = menu.show()

        if raw_idx is None:
            # Escape pressed
            return

        idx = raw_idx[0] if isinstance(raw_idx, tuple) else raw_idx

        # Handle Back / Exit
        real_entries = [e for e in entries if e]  # skip empty separator
        selected_label = real_entries[idx] if idx < len(real_entries) else ""

        if selected_label == "Exit" or selected_label == "< Back":
            return

        if idx < len(node.children):
            child = node.children[idx]
            if child.is_leaf:
                cmd = child.command or ""
                if child.prompt and "{input}" in cmd:
                    value = _prompt_input(child.prompt)
                    if value is None:
                        continue
                    cmd = cmd.replace("{input}", value)
                _run_command(cmd)
            else:
                navigate(child, breadcrumb + [child.label])
