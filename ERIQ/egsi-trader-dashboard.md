# EGSI Trader Intelligence Dashboard

## Overview
The EGSI Trader Intelligence module provides plan-tiered tactical analytics on the EGSI (Europe Gas Stress Index) dashboard. Each upgraded plan inherits all features from lower tiers plus unique tier-specific capabilities.

## Plan Gating (Feature Cascading)
- **Free/Personal (plan_level 0-1):** See upgrade prompt, no trader intel
- **Trader (plan_level 2):** 9 base modules, 90-day asset overlay history, upgrade prompt for Pro
- **Pro (plan_level 3):** All 9 Trader modules + 3 Pro-exclusive modules (rolling correlations, component decomposition, regime transition probability), 365-day asset overlay history, upgrade prompt for Enterprise
- **Enterprise (plan_level 4):** All Pro features + 1 Enterprise-exclusive module (cross-index contagion analysis), no upgrade prompt

## API Endpoint
`GET /api/v1/indices/egsi/trader-intel`
- Authentication: X-User-Token header (server-side plan enforcement)
- plan_level defaults to 0, auth failure returns error (no fallback to paid access)
- Returns: JSON with modules based on plan_level

## Trader Modules (plan_level >= 2)

### 1. Stress Momentum Gauge
RSI-like indicator (0-100) for EGSI-M stress momentum over 14 days.
- Labels: OVERBOUGHT (>=70), BUILDING (>=55), NEUTRAL, EASING (<=45), OVERSOLD (<=30)
- Source: `egsi_m_daily.index_value`

### 2. TTF vs EGSI Divergence Indicator
Z-score spread between normalized TTF price and EGSI-M stress level.
- Signals: OVERPRICED (>1.5σ), UNDERPRICED (<-1.5σ), SLIGHT_PREMIUM, SLIGHT_DISCOUNT, ALIGNED
- Source: `egsi_m_daily` JOIN `ttf_gas_snapshots`

### 3. Biggest Risk Driver of the Week
Top driver headline from the past 7 days by score/severity.
- Source: `egsi_drivers_daily` WHERE `index_family = 'egsi_m'`

### 4. Risk Radar (30-Day Outlook)
Heuristic bias indicators across 4 factors:
- Stress Momentum, Storage Draw Risk, Price Volatility, Supply Disruption
- Overall bias: RISK_ON, LEANING_UP, NEUTRAL, LEANING_DOWN, RISK_OFF

### 5. Scenario Impact Analysis
Forward scenario ranges for 2-week horizon based on current momentum.

### 6. Regime History (12 months)
Bar chart showing days spent in each stress band with transition count.

### 7. EGSI vs Assets Overlay Chart
Interactive line chart with toggleable overlays: TTF, Brent, VIX, EUR/USD, Storage.
- spanGaps enabled for continuous lines across weekends

### 8. EU Gas Storage vs Seasonal Average
Line chart comparing current storage trajectory against seasonal norms.

### 9. Analog Event Finder
Pattern matching via Pearson correlation finding similar historical stress periods.

## Pro-Exclusive Modules (plan_level >= 3)

### 10. Rolling Correlations (30-Day)
30-day rolling Pearson correlations between EGSI-M and 5 assets (TTF, Brent, VIX, EUR/USD, Storage).
- Shows latest 30d correlation, full-period correlation, correlation strength label
- Sorted by absolute correlation strength

### 11. Stress Component Decomposition
Breakdown of EGSI-M stress drivers by component type over last 30 days.
- Shows each component's weight percentage, average score, max score, event count
- Source: `egsi_drivers_daily` GROUP BY component_key, driver_type

### 12. Regime Transition Probability
Historical probability of transitioning between stress bands based on full history.
- Shows current band highlighted with next-day probability for each possible band
- Full transition matrix available
- Source: `egsi_m_daily.band` with LAG window function

## Enterprise-Exclusive Module (plan_level >= 4)

### 13. Cross-Index Contagion Analysis
Correlation and lead/lag analysis between EGSI-M and other risk indices (GERI, EERI).
- Shows correlation coefficient, lead/lag correlation, and directional insight
- Detects whether EGSI leads or lags other indices
- Source: `egsi_m_daily` cross-joined with `risk_indices`

## Frontend Sections
- `#egsiTraderIntelSection` - Contains all Trader modules (9 cards)
- `#egsiProSection` - Contains Pro-exclusive modules (3 cards), hidden for Trader
- `#egsiEnterpriseSection` - Contains Enterprise-exclusive module (1 card), hidden for Pro
- `#egsiTraderProUpgradePrompt` - Contextual upgrade prompt (shows Pro upgrade for Trader, Enterprise upgrade for Pro)
- Section title dynamically updates to reflect tier: "Trader Intelligence", "Pro Intelligence", or "Enterprise Intelligence"

## Files
- Backend: `src/egsi/trader_intel.py`
- API Route: `src/egsi/routes.py` (endpoint: `/egsi/trader-intel`)
- Frontend: `src/static/users-account.html` (EGSI intelligence sections)
