# EGSI Trader Intelligence Dashboard

## Overview
The EGSI Trader Intelligence module provides tactical analytics for Trader-tier subscribers (plan_level >= 2) on the EGSI (Europe Gas Stress Index) dashboard. It adds 9 interactive intelligence modules beyond the base EGSI dashboard.

## Plan Gating
- **Free/Personal (plan_level 0-1):** See upgrade prompt, no trader intel
- **Trader (plan_level 2):** All 9 modules, 90-day asset overlay history
- **Pro (plan_level 3):** All Trader + 365-day asset overlay history
- **Enterprise (plan_level 4):** All Pro features

## API Endpoint
`GET /api/v1/indices/egsi/trader-intel`
- Authentication: X-User-Token header (server-side plan enforcement)
- Returns: JSON with all 9 module datasets

## 9 Intelligence Modules

### 1. Stress Momentum Gauge
RSI-like indicator (0-100) for EGSI-M stress momentum over 14 days.
- Labels: OVERBOUGHT (>=70), BUILDING (>=55), NEUTRAL, EASING (<=45), OVERSOLD (<=30)
- Uses: Average gain/loss ratio over lookback window
- Source: `egsi_m_daily.index_value`

### 2. TTF vs EGSI Divergence Indicator
Z-score spread between normalized TTF price and EGSI-M stress level.
- Signals: OVERPRICED (>1.5σ), UNDERPRICED (<-1.5σ), SLIGHT_PREMIUM, SLIGHT_DISCOUNT, ALIGNED
- Uses 90-day normalization window
- Source: `egsi_m_daily` JOIN `ttf_gas_snapshots`

### 3. Biggest Risk Driver of the Week
Top driver headline from the past 7 days by score/severity.
- Source: `egsi_drivers_daily` WHERE `index_family = 'egsi_m'`
- Shows: headline, severity, confidence, type, source

### 4. Risk Radar (30-Day Outlook)
Heuristic bias indicators across 4 factors:
- Stress Momentum: Based on trend_1d and trend_7d
- Storage Draw Risk: Current vs seasonal norm
- Price Volatility: TTF coefficient of variation
- Supply Disruption: Current stress band level
- Overall bias: RISK_ON, LEANING_UP, NEUTRAL, LEANING_DOWN, RISK_OFF

### 5. Scenario Impact Analysis
Forward scenario ranges for 2-week horizon based on current momentum:
- If stress accelerates (high range)
- Base case (trend continues)
- If stress reverses (low range)
- Each scenario shows EGSI range, implied band, and TTF impact direction

### 6. Regime History (12 months)
Bar chart showing days spent in each stress band (LOW/NORMAL/ELEVATED/HIGH/CRITICAL).
- Includes percentage breakdown and transition count
- Source: `egsi_m_daily.band` GROUP BY

### 7. EGSI vs Assets Overlay Chart
Interactive line chart with EGSI-M and selectable asset overlays:
- TTF gas price, Brent crude, VIX, EUR/USD, EU Storage %
- Checkbox toggles for each asset
- Date-aligned with EGSI-M as primary axis
- Sources: `ttf_gas_snapshots`, `oil_price_snapshots`, `vix_snapshots`, `eurusd_snapshots`, `gas_storage_snapshots`

### 8. EU Gas Storage vs Seasonal Average
Line chart comparing current storage trajectory against seasonal norms.
- Shows deficit/surplus from seasonal target
- Source: `gas_storage_snapshots.eu_storage_percent` and `seasonal_norm`

### 9. Analog Event Finder
Pattern matching algorithm finding historical periods similar to the current 14-day EGSI-M pattern.
- Uses normalized Pearson correlation (threshold: 0.7)
- Shows top 5 matches with similarity score, dates, band, and 7-day outcome
- Source: Full `egsi_m_daily` history

## Data Sources
| Module | Tables Used |
|--------|------------|
| Momentum | egsi_m_daily |
| Divergence | egsi_m_daily, ttf_gas_snapshots |
| Weekly Driver | egsi_drivers_daily |
| Risk Radar | egsi_m_daily, gas_storage_snapshots, ttf_gas_snapshots |
| Alert Impact | egsi_m_daily |
| Regime History | egsi_m_daily |
| Asset Overlay | egsi_m_daily, ttf_gas_snapshots, oil_price_snapshots, vix_snapshots, eurusd_snapshots, gas_storage_snapshots |
| Storage Seasonal | gas_storage_snapshots |
| Analog Finder | egsi_m_daily |

## Files
- Backend: `src/egsi/trader_intel.py`
- API Route: `src/egsi/routes.py` (endpoint: `/egsi/trader-intel`)
- Frontend: `src/static/users-account.html` (EGSI Trader Intelligence section)
