# GERI Trader Dashboard — Tactical Intelligence Modules

## Overview
The GERI Trader Dashboard provides tactical risk intelligence modules designed for active energy market participants. Available to Trader, Pro, and Enterprise plan subscribers (plan_level >= 2), these modules transform the Global Energy Risk Index (GERI) into an actionable trading tool by answering: Is risk escalating or de-escalating? Are markets confirming the risk signal? Which assets lead or lag? How does gas storage compare to seasonal norms?

## Access
- **Trader tier (plan_level >= 2):** Full access to all 7 modules
- **Pro tier (plan_level >= 3):** Full access
- **Enterprise tier (plan_level >= 4):** Full access
- **Free and Personal tiers:** Not visible; upgrade prompts shown in GERI dashboard

## API Endpoint
`GET /api/v1/indices/geri/trader-intel`

Requires authentication via X-User-Token header. Returns JSON with all 7 intelligence modules.

## Modules

### 1. Risk Regime Status
Shows the current regime transition direction based on the last 3 GERI readings.

- **Escalating:** Risk rising — GERI moving up
- **De-escalating:** Risk falling — GERI moving down
- **Stable:** No significant directional change

Regime is determined by comparing average of last 2 readings vs the reading before them. A change of more than 1.0 points triggers escalating/de-escalating classification.

### 2. Cross-Asset Confirmation Score (0-100)
Measures whether energy markets are pricing risk consistently with GERI.

| Score Range | Label | Meaning |
|-------------|-------|---------|
| 80-100 | Strong confirmation | All major assets moving in GERI-predicted direction |
| 60-79 | Moderate | Most assets confirming, some divergence |
| 40-59 | Mixed signals | Significant disagreement between assets |
| 0-39 | Weak/Divergent | Markets not pricing the risk GERI sees |

**Calculation:** Percentage of tracked assets whose 7-day price change aligns with expected GERI direction. Positive correlation expected for Brent, TTF, VIX. Negative correlation expected for EUR/USD and gas storage.

**Why this matters:** A high confirmation score (>80) means the risk signal is broadly accepted by markets. A low score (<40) suggests either GERI is detecting an emerging risk markets haven't priced, or GERI is lagging a market move.

### 3. Divergence Indicator
Shows per-asset alignment with GERI direction over the trailing 7-day window.

| Status | Meaning |
|--------|---------|
| Aligned | Asset moving in GERI-predicted direction |
| Moderate divergence | Partial misalignment |
| Strong divergence | Asset moving opposite to GERI prediction |

Assets tracked: Brent Oil, TTF Gas, VIX, EUR/USD, EU Gas Storage.

### 4. Lead/Lag Intelligence
Identifies which assets react first to GERI risk changes using cross-correlation analysis.

| Timing | Meaning |
|--------|---------|
| Asset leads by N days | This asset moves before GERI updates |
| Risk leads by N days | GERI moves first, asset follows |
| Moves same-day | Simultaneous reaction |

**Maximum lag window:** 7 days. Requires minimum 14 overlapping daily data points.

**Trading application:** If GERI spikes and Brent historically lags by 2 days, traders have a positioning window. If VIX leads GERI, it can serve as an early warning.

### 5. EU Gas Storage Seasonal Context
Provides current EU gas storage levels compared to historical seasonal averages.

| Field | Description |
|-------|-------------|
| current_pct | Latest AGSI+ EU aggregate storage fill level (%) |
| seasonal_avg | Typical storage level for this time of year (%) |
| vs_seasonal | Difference from seasonal norm (percentage points) |
| status | "Above seasonal", "Near seasonal", or "Below seasonal" |

**Seasonal averages by month:** Based on 5-year historical norms. Below-seasonal storage during winter months (Oct-Mar) is a significant bullish signal for TTF gas prices.

### 6. Asset Reaction Summary
AI-generated narrative summarizing how key energy assets are responding to the current risk environment. Based on the most recent daily asset snapshots (Brent, TTF, VIX, EUR/USD, storage).

### 7. Alert Preview
Shows the 3 most recent risk alerts with headline, severity, and date. Provides quick context on what events are driving GERI movements.

Severity levels: Critical, High, Medium, Low.

## Data Sources
- **GERI values:** `intel_indices_daily` table (index_type = 'global:geo_energy_risk')
- **Asset prices:** `intel_asset_snapshots` table (Brent, TTF, VIX, EUR/USD, EU storage)
- **Alerts:** `alert_events` table (latest 5 by severity)
- **Minimum data requirement:** 14 days of overlapping GERI + asset data for correlation-based modules

## Frontend Integration
- Panels render inside `#geriTraderIntelSection` div in the GERI dashboard
- Plan gating: Only visible for Trader/Pro/Enterprise plans
- Loads asynchronously via `loadGeriTraderIntel()` function after main GERI chart renders
- Graceful degradation: Shows "insufficient data" messages when data history is limited

## Relationship to EERI Trader Dashboard
The GERI Trader Dashboard complements the EERI Trader Dashboard (see `eeri-trader-dashboard.md`). While EERI focuses on European escalation risk with correlation panels and regime persistence, GERI provides a global risk perspective with cross-asset confirmation scoring and lead/lag analysis. Together, they give traders both macro-global and region-specific tactical intelligence.
