#!/usr/bin/env python3
"""Generate a printable Diamond Stock Engine investing cheatsheet PDF."""

from fpdf import FPDF

# --- Colors ---
NAVY = (15, 23, 42)
SLATE = (51, 65, 85)
GRAY = (100, 116, 139)
LIGHT_BG = (248, 250, 252)
ACCENT = (37, 99, 235)    # Blue
GREEN = (22, 163, 74)
AMBER = (217, 119, 6)
RED = (220, 38, 38)
WHITE = (255, 255, 255)
BORDER_COLOR = (226, 232, 240)
CARD_BG = (241, 245, 249)


class CheatsheetPDF(FPDF):
    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.set_auto_page_break(auto=True, margin=12)

    def _draw_rounded_rect(self, x, y, w, h, r, fill_color, border_color=None):
        self.set_fill_color(*fill_color)
        if border_color:
            self.set_draw_color(*border_color)
            self.rect(x, y, w, h, style="DF")
        else:
            self.rect(x, y, w, h, style="F")

    def section_title(self, text, color=ACCENT):
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(*color)
        self.cell(0, 8, text, new_x="LMARGIN", new_y="NEXT")
        # Underline
        self.set_draw_color(*color)
        self.set_line_width(0.6)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(3)

    def subsection(self, text):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(*SLATE)
        self.cell(0, 6, text, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def body_text(self, text, bold=False):
        style = "B" if bold else ""
        self.set_font("Helvetica", style, 9)
        self.set_text_color(*SLATE)
        self.multi_cell(0, 4.5, text)
        self.ln(1)

    def bullet(self, text, indent=8, icon=None):
        x = self.get_x()
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*SLATE)
        if icon:
            self.set_x(x + indent - 5)
            self.set_font("Helvetica", "B", 9)
            self.set_text_color(*ACCENT)
            self.cell(5, 4.5, icon, new_x="END")
            self.set_font("Helvetica", "", 9)
            self.set_text_color(*SLATE)
            self.multi_cell(0, 4.5, " " + text)
        else:
            self.set_x(x + indent)
            self.multi_cell(0, 4.5, "- " + text)
        self.ln(0.5)

    def cmd_row(self, cmd, desc, col_w=52):
        y = self.get_y()
        x = self.get_x()
        self.set_font("Courier", "B", 8)
        self.set_text_color(*ACCENT)
        self.cell(col_w, 5, cmd)
        self.set_font("Helvetica", "", 8.5)
        self.set_text_color(*SLATE)
        self.set_xy(x + col_w, y)
        w = self.w - self.r_margin - (x + col_w)
        self.multi_cell(w, 5, desc)
        if self.get_y() - y < 6:
            self.ln(0.5)

    def card(self, title, items, color=ACCENT):
        start_y = self.get_y()
        card_x = self.l_margin
        card_w = self.w - self.l_margin - self.r_margin

        # Calculate height needed
        self.set_font("Helvetica", "", 9)
        h = 9 + len(items) * 5.5 + 3

        if start_y + h > self.h - 15:
            self.add_page()
            start_y = self.get_y()

        self._draw_rounded_rect(card_x, start_y, card_w, h, 2, CARD_BG, BORDER_COLOR)

        # Title bar
        self.set_xy(card_x + 3, start_y + 1.5)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(*color)
        self.cell(0, 6, title)

        self.set_xy(card_x + 5, start_y + 8)
        for item in items:
            self.set_x(card_x + 5)
            self.set_font("Helvetica", "", 9)
            self.set_text_color(*SLATE)
            self.cell(0, 5, item, new_x="LMARGIN", new_y="NEXT")

        self.set_y(start_y + h + 3)

    def time_block(self, time_label, color, commands):
        """Draw a time-based routine block."""
        x = self.l_margin
        w = self.w - self.l_margin - self.r_margin

        start_y = self.get_y()
        block_h = 7 + len(commands) * 5.5 + 2

        if start_y + block_h > self.h - 15:
            self.add_page()
            start_y = self.get_y()

        # Left color bar
        self.set_fill_color(*color)
        self.rect(x, start_y, 3, block_h, style="F")

        # Background
        self._draw_rounded_rect(x + 3, start_y, w - 3, block_h, 0, LIGHT_BG)

        # Time label
        self.set_xy(x + 6, start_y + 1)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(*color)
        self.cell(0, 5.5, time_label)

        self.set_y(start_y + 7)
        for cmd, desc in commands:
            self.set_x(x + 8)
            self.set_font("Courier", "B", 8.5)
            self.set_text_color(*NAVY)
            self.cell(48, 5, cmd, new_x="END")
            self.set_font("Helvetica", "", 8.5)
            self.set_text_color(*GRAY)
            self.cell(0, 5, desc, new_x="LMARGIN", new_y="NEXT")

        self.set_y(start_y + block_h + 2)


def build_pdf():
    pdf = CheatsheetPDF()
    pdf.set_margin(12)

    # ===================== PAGE 1 =====================
    pdf.add_page()

    # Header
    pdf.set_fill_color(*NAVY)
    pdf.rect(0, 0, 210, 34, style="F")
    pdf.set_xy(12, 6)
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(*WHITE)
    pdf.cell(0, 10, "Diamond Stock Engine", new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(12)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(148, 163, 184)
    pdf.cell(0, 7, "Daily Investing Cheatsheet  |  Print & Pin This", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)

    # === THE GOLDEN RULE ===
    rule_y = pdf.get_y()
    pdf._draw_rounded_rect(12, rule_y, 186, 16, 2, (254, 252, 232), (250, 204, 21))
    pdf.set_xy(16, rule_y + 2)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*AMBER)
    pdf.cell(0, 6, "THE GOLDEN RULE", new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(16)
    pdf.set_font("Helvetica", "", 9.5)
    pdf.set_text_color(*SLATE)
    pdf.cell(0, 5, "WAIT is the default. Most days, the best trade is no trade. Let the system tell you when to act.", new_x="LMARGIN", new_y="NEXT")
    pdf.set_y(rule_y + 20)

    # === DAILY ROUTINE ===
    pdf.section_title("Your Daily Routine")

    pdf.time_block("Every Morning (2 min)", GREEN, [
        ("/morning", "Market verdict + NAV + alerts + streak"),
        ("Any alerts?", "Catches stop-losses, concentration, delisted stocks"),
    ])

    pdf.time_block("Every Week (10 min)", ACCENT, [
        ("/weekly", "Attribution + risk + drift + benchmark comparison"),
        ("/compare gods_plan steady", "Are you in the right strategy?"),
        ("/buy", "Systematic screening for opportunities"),
    ])

    pdf.time_block("Every Month (20 min)", AMBER, [
        ("/monthly", "Full review + export all reports"),
        ("/tax", "STCG vs LTCG awareness - minimize tax drag"),
        ("/scenario -15", "Stress test: know your worst case"),
        ("/rebalance", "Preview trades if drift has built up"),
    ])

    pdf.ln(2)

    # === BEFORE ANY TRADE ===
    pdf.section_title("Before Any Trade (Checklist)", RED)

    checklist = [
        "Check market pulse:  /morning  (is it DEPLOY, WAIT, or DEFENSIVE?)",
        "Analyze the stock:  /analyze TICKER",
        "Simulate the impact:  /whatif add TICKER",
        "Check tax impact:  /tax  (avoid unnecessary STCG)",
        "If verdict is WAIT  -> do nothing. Come back tomorrow.",
        "If verdict is DEPLOY -> use /buy to get sized recommendations",
    ]
    for item in checklist:
        pdf.set_x(14)
        # Checkbox
        self_y = pdf.get_y()
        pdf.set_draw_color(*BORDER_COLOR)
        pdf.rect(14, self_y + 0.5, 3.5, 3.5)
        pdf.set_x(20)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*SLATE)
        pdf.multi_cell(0, 4.5, item)
        pdf.ln(1)

    pdf.ln(2)

    # === STRATEGY OVERVIEW ===
    pdf.section_title("God's Plan Strategy (Primary)")

    # Three-tier visual
    tiers = [
        ("55%  Quality Growth", "High-alpha trending stocks, inverse-vol weighted", GREEN),
        ("25%  Defensive Anchor", "Low-beta quality stocks for downside protection", ACCENT),
        ("20%  Opportunistic Value", "Low P/B + positive alpha, mean-reversion", AMBER),
    ]
    for label, desc, color in tiers:
        y = pdf.get_y()
        pdf.set_fill_color(*color)
        pdf.rect(14, y, 2.5, 10, style="F")
        pdf.set_xy(19, y)
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_text_color(*color)
        pdf.cell(50, 5, label, new_x="END")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*GRAY)
        pdf.cell(0, 5, desc, new_x="LMARGIN", new_y="NEXT")
        pdf.set_y(y + 10)

    pdf.ln(1)
    pdf.set_font("Helvetica", "I", 8.5)
    pdf.set_text_color(*GRAY)
    pdf.cell(0, 4, "Target: 18-22% CAGR  |  Max 18 stocks  |  <30% max drawdown  |  Quarterly rebalance", new_x="LMARGIN", new_y="NEXT")

    # ===================== PAGE 2 =====================
    pdf.add_page()

    # Header bar
    pdf.set_fill_color(*NAVY)
    pdf.rect(0, 0, 210, 14, style="F")
    pdf.set_xy(12, 3)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*WHITE)
    pdf.cell(0, 8, "Diamond Stock Engine  |  Quick Reference", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # === ESSENTIAL COMMANDS ===
    pdf.section_title("Essential Commands")

    categories = [
        ("Daily Routine", [
            ("/morning", "Pre-market scan: verdict + NAV + alerts"),
            ("/daily", "Full briefing with sector rotation + opportunities"),
            ("/weekly", "Weekly review: attribution + risk + drift"),
            ("/monthly", "Month-end review + export all reports"),
        ]),
        ("Trading Decisions", [
            ("/buy", "Market-aware buy opportunities"),
            ("/buy RELIANCE", "Deep-dive before buying a specific stock"),
            ("/sell", "Review what to trim/sell (tax-smart)"),
            ("/analyze INFY", "Full technical + fundamental + sentiment"),
            ("/whatif add HDFC", "Simulate adding a stock"),
        ]),
        ("Portfolio Management", [
            ("/portfolio", "Comprehensive review with attribution"),
            ("/status", "Quick cross-strategy overview"),
            ("/drift", "Check position drift from targets"),
            ("/rebalance", "Preview rebalance trades + costs"),
            ("/orders", "View/manage pending orders"),
        ]),
        ("Risk & Monitoring", [
            ("/watch", "Manage watchlist + price alerts"),
            ("/watch add RELIANCE 2500", "Add stock with target price"),
            ("/tax", "Capital gains: STCG vs LTCG breakdown"),
            ("/scenario -15", "Stress test a 15% crash"),
            ("/scenario add 50000", "Simulate adding cash"),
        ]),
    ]

    for cat_name, commands in categories:
        pdf.subsection(cat_name)
        for cmd, desc in commands:
            pdf.cmd_row(cmd, desc)
        pdf.ln(2)

    # === RISK THRESHOLDS ===
    pdf.section_title("Risk Thresholds to Know", RED)

    thresholds = [
        ("Drawdown", "WARNING at 10% from peak | CRITICAL at 15% (blocks trades)"),
        ("VaR", "WARNING when 1-day Value-at-Risk > 3% of NAV"),
        ("Correlation", "WARNING when avg pairwise > 0.80"),
        ("Volatility", "WARNING when annualized > 30%"),
        ("Concentration", "WARNING at 12.5% weight | CRITICAL at 15%"),
        ("Stop Loss", "Auto-alert at 10% loss | 5-day cooldown after trigger"),
    ]
    for label, desc in thresholds:
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*RED)
        pdf.cell(28, 5, label, new_x="END")
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(*SLATE)
        pdf.multi_cell(0, 5, desc)
        pdf.ln(0.5)

    pdf.ln(3)

    # === MARKET PULSE ACTIONS ===
    pdf.section_title("Market Pulse Decision Matrix", GREEN)

    # Table header
    y = pdf.get_y()
    pdf.set_fill_color(*NAVY)
    pdf.rect(12, y, 186, 6, style="F")
    pdf.set_xy(14, y)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*WHITE)
    pdf.cell(35, 6, "Verdict")
    pdf.cell(50, 6, "Cash to Deploy")
    pdf.cell(0, 6, "What to Do", new_x="LMARGIN", new_y="NEXT")

    rows = [
        ("DEPLOY", "50% of available cash", "Run /buy, execute top opportunities, full position sizes"),
        ("WAIT", "30% of available cash", "Only add to existing winners, half position sizes"),
        ("DEFENSIVE", "15% of available cash", "No new entries, trim laggards, raise cash"),
    ]
    colors = [GREEN, AMBER, RED]
    for i, (verdict, cash, action) in enumerate(rows):
        y = pdf.get_y()
        bg = LIGHT_BG if i % 2 == 0 else WHITE
        pdf.set_fill_color(*bg)
        pdf.rect(12, y, 186, 6, style="F")
        pdf.set_xy(14, y)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*colors[i])
        pdf.cell(35, 6, verdict)
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(*SLATE)
        pdf.cell(50, 6, cash)
        pdf.cell(0, 6, action, new_x="LMARGIN", new_y="NEXT")

    pdf.ln(5)

    # === 5 HABITS ===
    pdf.section_title("5 Habits That Build Wealth")

    habits = [
        ("1. Never skip /morning", "Consistency beats intensity. The streak system tracks this."),
        ("2. Always check before acting", "/analyze + /whatif before every buy. No impulse trades."),
        ("3. Let the system say WAIT", "The conservative bias IS the edge. Respect it."),
        ("4. Paper trade first", "diamond paper gods_plan before going live with changes."),
        ("5. Act on alerts, not emotions", "/alerts --act gives structured decisions, not panic moves."),
    ]
    for title, desc in habits:
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_text_color(*NAVY)
        pdf.cell(0, 5, title, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(*GRAY)
        pdf.cell(0, 4.5, desc, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    # Footer
    pdf.ln(3)
    pdf.set_draw_color(*BORDER_COLOR)
    pdf.line(12, pdf.get_y(), 198, pdf.get_y())
    pdf.ln(2)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(*GRAY)
    pdf.cell(0, 4, "Diamond Stock Engine  |  Systematic investing removes emotion from every decision  |  WAIT is the default", align="C")

    # Save
    out_path = "data/diamond_cheatsheet.pdf"
    pdf.output(out_path)
    print(f"Cheatsheet saved to: {out_path}")


if __name__ == "__main__":
    build_pdf()
