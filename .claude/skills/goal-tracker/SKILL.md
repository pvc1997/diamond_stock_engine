---
name: goal-tracker
description: Tracks investment goals and milestones. Activates when the user mentions goals like "I want 20% CAGR", "when will I reach 10 lakhs?", "am I on track?", "how far to doubling?", "years to 1 crore", "my target is...", or discusses long-term investment objectives.
argument-hint: [goal]
allowed-tools: mcp__diamond__*, Read, Write
---

# Goal Tracker — Investment Milestones & Progress

## Goal Types

### Return Goals
- "I want 20% CAGR" → track annualized return vs target
- "Beat Nifty by 5%" → track alpha vs benchmark
- "Never lose more than 15%" → track max drawdown vs limit

### Capital Goals
- "Reach 10 lakhs" → project timeline based on current CAGR
- "Double my money" → calculate doubling time (Rule of 72: 72/CAGR)
- "1 crore by 2030" → required CAGR to hit target

### Income Goals
- "5% dividend yield" → track portfolio yield
- "INR 50,000/year from dividends" → track dividend income

## Data Gathering

1. `portfolio_status` — current NAV, initial capital, returns
2. `portfolio_summary` — CAGR, benchmark comparison
3. `risk_report` — drawdown for risk goals

## Goal Progress Calculation

For capital goals:
- **Current NAV**: INR X,XX,XXX
- **Target**: INR Y,YY,YYY
- **Progress**: X/Y = Z%
- **Current CAGR**: A%
- **Required CAGR** to hit target by date: B%
- **On track?**: Yes if A >= B, No if A < B
- **Projected date at current pace**: Calculate from CAGR

For return goals:
- **Current CAGR**: X%
- **Target CAGR**: Y%
- **Gap**: Z percentage points
- **Trend**: Improving / Declining / Stable (compare 3M, 6M, 1Y rolling CAGR)

## Goal Storage

Store goals in a simple file at `data/goals.json`:
```json
{
  "goals": [
    {"type": "capital", "target": 1000000, "deadline": "2027-12-31", "created": "2026-03-07"},
    {"type": "cagr", "target": 20, "created": "2026-03-07"},
    {"type": "drawdown_limit", "target": -15, "created": "2026-03-07"}
  ]
}
```

When user sets a new goal, write to this file.
When user asks progress, read and calculate.

## Output Format

### Progress Dashboard
```
Goal: Reach INR 10,00,000 by Dec 2027
[=========>-----------] 48% there
Current: INR 4,80,000 | Need: INR 5,20,000 more
Current CAGR: 18% | Required: 22%
Status: SLIGHTLY BEHIND — need to accelerate by 4% points
```

### Milestones Hit
- First 1 lakh invested
- First 10% return
- First dividend received
- Portfolio crossed 5L / 10L / 25L / 50L / 1Cr
- 100-day streak
- Survived a >10% drawdown without panic selling

## Motivation

When on track: "You're ahead of schedule. At this pace, you'll hit your goal X months early."
When behind: "You're behind by X%. Options: (1) Add INR Y more capital, (2) Increase equity allocation, (3) Extend timeline by Z months."
When goal hit: "Congratulations! You've reached your goal of X. Time to set a new target?"