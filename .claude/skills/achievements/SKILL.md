---
name: achievements
description: Tracks investment milestones and achievements for motivation. Activates when the user asks "my achievements", "any milestones?", "badges", "what have I accomplished?", or after significant portfolio events (new high, streak milestone, goal reached). Also provides positive reinforcement during daily briefings.
allowed-tools: mcp__diamond__*, Read, Write
---

# Achievements — Investment Milestones & Badges

## Achievement Categories

### Consistency Badges
- **First Steps**: Checked in for the first time
- **Week Warrior**: 7-day streak
- **Monthly Master**: 30-day streak
- **Quarterly Crusher**: 90-day streak
- **Year of Discipline**: 365-day streak
- **Ironclad**: 100+ check-ins total

### Portfolio Milestones
- **First Trade**: Executed your first trade
- **Diversified**: Hold 10+ stocks across 5+ sectors
- **Fully Loaded**: Reached 18-stock target in God's Plan
- **Cash Deployed**: Less than 5% cash remaining (fully invested)
- **Six Figures**: Portfolio NAV crossed INR 1,00,000
- **Half Million**: NAV crossed INR 5,00,000
- **Seven Figures**: NAV crossed INR 10,00,000
- **Crorepati**: NAV crossed INR 1,00,00,000

### Performance Badges
- **First Green**: First profitable day
- **First Red**: Survived your first loss day (didn't panic sell)
- **10% Club**: Total returns exceeded 10%
- **Market Beater**: Outperformed Nifty 50 over 3+ months
- **Steady Hand**: Held through a >5% drawdown without selling
- **Diamond Hands**: Held through a >10% drawdown without selling
- **Recovery King**: Portfolio recovered from max drawdown to new high
- **Compounder**: CAGR exceeded 15% over 6+ months

### Knowledge Badges
- **Student**: Completed 5 /learn lessons
- **Scholar**: Completed 20 /learn lessons
- **Professor**: Completed all 10 topic categories

### Smart Decisions
- **Tax Saver**: Made a tax-loss harvesting trade
- **Trim Master**: Successfully trimmed an overweight position
- **Clean House**: Cleaned up a delisted stock
- **Paper First**: Paper traded for 30+ days before going live
- **Patience Pays**: Waited for DEPLOY signal before buying (ignored WAIT urge)

## Storage

Store in `data/achievements.json`:
```json
{
  "unlocked": [
    {"badge": "First Steps", "date": "2026-03-06", "detail": "First check-in recorded"},
    {"badge": "Six Figures", "date": "2026-03-07", "detail": "NAV hit 1,23,000"}
  ],
  "pending_checks": ["Week Warrior", "10% Club", "Market Beater"]
}
```

## Achievement Checking

On each interaction, silently check:
1. Streak milestones (from `daily_streak` MCP tool)
2. NAV milestones (from `portfolio_status`)
3. Performance milestones (from `portfolio_summary`)
4. Action-based badges (from context of current conversation)

When a new achievement unlocks:
"**Achievement Unlocked: Steady Hand**
You held through a 7% drawdown without panic selling. That's discipline."

## Display

When user asks "my achievements":
Show all unlocked badges grouped by category, with dates.
Show next closest unachieved badges: "Next up: 'Market Beater' — you need 2 more months of outperformance."

## Integration

- During `/morning`: If a new milestone was hit overnight, lead with it
- During sell discussions: Check for "Steady Hand" / "Diamond Hands" before proceeding
- After trades: Check for "First Trade", "Tax Saver", "Trim Master"
- Weekly: Check for performance badges (10% Club, Market Beater, Compounder)