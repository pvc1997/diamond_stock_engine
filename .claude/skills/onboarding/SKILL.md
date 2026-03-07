---
name: onboarding
description: Guides new users through first-time setup. Activates when the user appears to be new (no portfolio exists, asks "how do I start?", "what is this?", "help me set up", "I'm new here", "first time"), or when no gods_plan holdings are found.
allowed-tools: mcp__diamond__*, Bash(uv run diamond:*)
---

# Onboarding — Welcome to Diamond

## Detection

Trigger this skill when:
- `portfolio_status` returns empty/no holdings for all strategies
- User explicitly asks for help getting started
- User seems confused about what commands to use

## Welcome Message

"Welcome to Diamond — your systematic Indian equity portfolio manager.

I'll help you set up in 3 simple steps. Just talk to me in plain English — no commands needed."

## Step 1: Choose Your Style (ask the user)

"First, what kind of investor are you?

**A) Conservative** — I want steady growth with minimal stress
   → I'll set you up with the **Steady** strategy (15-18% CAGR target, <25% drawdown)

**B) Aggressive** — I want maximum growth and can handle volatility
   → I'll set you up with **God's Plan** (18-22% CAGR target, <30% drawdown)

**C) Passive** — Just track the Nifty 50, keep it simple
   → I'll set you up with **Baseline** (market returns, minimal effort)

**D) Not sure** — Help me decide
   → I'll ask you 3 quick questions to figure this out"

### If they say "Not sure" — Risk Profiling
1. "If your portfolio dropped 15% in a week, would you: (a) Buy more, (b) Hold, (c) Sell some, (d) Sell everything?"
2. "How long can you leave this money invested? (a) 1-2 years, (b) 3-5 years, (c) 5+ years"
3. "How often do you want to check your portfolio? (a) Daily, (b) Weekly, (c) Monthly"

Map answers to strategy recommendation.

## Step 2: Set Your Capital

"How much are you starting with? (e.g., '5 lakhs', '50k', '2,00,000')

I recommend starting with paper trading first — simulated trades with real market data, zero risk. You can go live when you're confident."

Then run: `uv run diamond paper <strategy> --capital <AMOUNT>`

## Step 3: First Look

After paper portfolio is created:
1. Run `market_pulse` — show current market conditions
2. Run `portfolio_status` — show the new portfolio
3. Show 3 things they can do:
   - "Say 'how's the market?' for a quick check"
   - "Say 'show me opportunities' to see what the strategy wants to buy"
   - "Say 'tell me about RELIANCE' to research any stock"

## Closing

"You're all set! Here's your daily habit:
- Say 'good morning' each day for a market briefing
- I'll track your streak and alert you to any issues
- When you're ready to go live (after ~30 days), just say 'go live'

What would you like to do first?"