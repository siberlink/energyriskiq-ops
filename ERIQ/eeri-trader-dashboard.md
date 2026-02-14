# EERI Trader Dashboard — Tactical Intelligence Modules

## Overview
The EERI Trader Dashboard provides tactical risk intelligence modules designed for active energy market participants. Available to Trader, Pro, and Enterprise plan subscribers, these modules transform the EERI index into an actionable trading tool by answering: Is risk rising? Which asset reacts first? How strong is confirmation? What might happen next week? How fast do I need to act?

## Modules

### 1. Reaction Lag Panel
Shows how quickly each asset class historically reacts to EERI changes.

| Asset | Avg Reaction Lag | Note |
|-------|-----------------|------|
| TTF Gas | 1–2 days | Most sensitive to European risk shifts |
| Brent Oil | 3–5 days | Global supply/demand dampens reaction speed |
| VIX | Same day | Instantaneous risk-sentiment transmission |
| EUR/USD | 2–3 days | FX adjusts via macro channel with delay |
| EU Gas Storage | Structural | Physical flow adjustment, not traded |

**Why this matters:** Traders use reaction lag to time entries. If EERI spikes, TTF reacts in 1–2 days but Brent takes 3–5 days, giving a window for position adjustment.

### 2. 30-Day Rolling Correlation Panel
Shows Pearson correlation between EERI and each asset over the last 30 trading days.

- **Strong (≥0.70):** High co-movement, EERI reliably predicts asset direction
- **Moderate (0.40–0.69):** Partial co-movement, use alongside other signals
- **Weak (<0.40):** Limited relationship in current regime

**Interpretation:** Positive correlation with TTF/Brent/VIX means rising EERI = rising prices/volatility. Negative correlation with EUR/USD means rising EERI = weaker euro. Storage correlation is typically negative (higher risk = faster drawdowns).

Sample sizes are displayed for transparency. Minimum 7 overlapping data points required.

### 3. Regime Persistence Probability
Computed from actual historical EERI data. Shows the probability that the current risk band (LOW/MODERATE/ELEVATED/SEVERE/CRITICAL) will persist into next week.

- Calculated from week-over-week band transitions in the historical record
- Includes confidence level (Low/Medium/High) based on sample size
- Shows sample size (number of historical transitions analyzed)

**Example:** "Based on 25 historical week-transitions, the ELEVATED regime has a 63% probability of persisting next week."

### 4. Risk Shock Detector
Monitors for rapid EERI acceleration: Δ EERI ≥ +10 points within any 2-day window over the last 5 days.

When triggered, displays:
- Warning banner with the magnitude of the shock
- Start and end values with dates
- Alert message: "Rapid Acceleration Detected: EERI rose X points in 2 days"

**Why this matters:** Risk shocks often precede sustained directional moves in energy markets. Same-day VIX reaction, 1–2 day TTF reaction.

### 5. Key Energy Market Dates
Calendar of recurring market events that drive EERI volatility:

- **AGSI+ Weekly Storage Update** — Weekly (Wed)
- **OPEC+ JMMC / Full Meeting** — Monthly / Quarterly
- **EU Energy Council** — As scheduled
- **EU/US Sanctions Review Deadlines** — Periodic
- **TTF Front-Month Expiry** — Monthly
- **IEA Oil Market Report** — Monthly

### 6. Data Timestamps
Shows the latest update date for each data source:
- EERI index computation
- TTF Gas price
- Brent Oil price
- VIX close
- EUR/USD rate
- EU Gas Storage level

**Credibility note:** Traders require knowing data freshness. Prices are carried forward on non-trading days (weekends, holidays).

### 7. Asset Impact Ranking
Assets ranked by weekly sensitivity to EERI: `sensitivity_score = |weekly_move_pct| × 30d_correlation`.

Shows rank number, asset name, last known value, and weekly percentage move. The most sensitive asset this week should receive priority attention.

### 8. One-Line Trading Insight
A single shareable sentence summarizing the current risk-asset relationship. Generated from:
- Current EERI value and band
- 7-day trend direction
- Risk shock detection status
- Top correlated asset

**Examples:**
- "Risk shock detected: EERI surged 15 pts in 2 days — energy-linked assets face directional pressure."
- "EERI at 56 (Elevated) and accelerating — highest conviction for energy risk hedging."
- "Energy risk easing from SEVERE (56), but declines often stall — watch for reversal signals."

## Plan Tier Access
- **Trader (€29/mo):** All modules above
- **Pro (€49/mo):** All Trader modules + Component Attribution, Historical Analogs, Scenario Outlook
- **Enterprise (€129/mo):** All Pro modules + Multi-region spillover, Sector impact forecasting

## Technical Details
- API endpoint: `GET /api/v1/eeri-pro/trader-intel`
- Correlations computed using Pearson coefficient over 30-day aligned series
- Regime persistence uses week-over-week band transition analysis
- Risk shock threshold: Δ ≥ +10 in any 2-day window
- All computations use production database (real market data, not simulated)

## Weekend / Non-Trading Day Handling
Prices are carried forward (forward-filled) on non-trading days. This means weekend values reflect the last Friday close. The "Prices carried forward on non-trading days" note is displayed on the dashboard.
