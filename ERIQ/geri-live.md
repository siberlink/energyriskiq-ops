# GERI Live — Real-time Global Energy Risk Index

## Overview

GERI Live provides a real-time, intraday view of the Global Energy Risk Index that updates as news events and alerts are processed throughout the day. Unlike the official daily GERI (computed once per day and stored in `intel_indices_daily`), GERI Live recalculates continuously, giving Pro and Enterprise users an up-to-the-minute risk reading.

## Plan Gating

- **Available to:** Pro and Enterprise subscription tiers only
- **Nav visibility:** The "GERI Live" sidebar item is hidden for Free, Personal, and Trader plans
- **API enforcement:** Both REST and SSE endpoints verify plan via `user_plans.plan`

## Architecture

### Compute Pipeline

```
alert_events (today, UTC) → compute_components() → normalize_components() → calculate_geri_value()
                                                                                  ↓
                                                              geri_live table (INSERT per computation)
                                                                                  ↓
                                                              SSE broadcast → connected clients
```

1. **Data Source:** All `alert_events` created since midnight UTC today
2. **Component Computation:** Same `compute_components()` from `src/geri/compute.py` (regional weighting model, severity scoring)
3. **Normalization:** Uses 90-day historical baseline from `get_historical_baseline()`
4. **Final Value:** Weighted combination (high_impact 40%, regional_spike 25%, asset_risk 20%, region_concentration 15%)
5. **Band Assignment:** 0-20 LOW, 21-40 MODERATE, 41-60 ELEVATED, 61-80 SEVERE, 81-100 CRITICAL
6. **Trend:** Compared against yesterday's official daily GERI from `intel_indices_daily`

### Debounce

Recomputations are throttled to a minimum 60-second interval. If `compute_live_geri()` is called within 60 seconds of the last computation, it returns the cached latest value instead of recomputing.

### AI Interpretation

The interpretation is regenerated when:
- GERI value changes by ≥ 2 points
- Risk band changes (e.g., MODERATE → ELEVATED)
- No interpretation exists yet

Uses OpenAI gpt-4.1-mini with a prompt optimized for intraday analysis (1-2 paragraphs, present tense, references specific drivers and regions). Falls back to a template-based interpretation if OpenAI is unavailable.

## Database Schema

### `geri_live` table

```sql
CREATE TABLE geri_live (
    id SERIAL PRIMARY KEY,
    value INTEGER NOT NULL DEFAULT 0,
    band VARCHAR(20) NOT NULL DEFAULT 'LOW',
    trend_vs_yesterday NUMERIC(5,1),
    components JSONB DEFAULT '{}',
    interpretation TEXT DEFAULT '',
    alert_count INTEGER DEFAULT 0,
    last_alert_id INTEGER,
    top_drivers JSONB DEFAULT '[]',
    top_regions JSONB DEFAULT '[]',
    computed_at TIMESTAMP DEFAULT NOW()
);
```

Each computation inserts a new row, preserving the full intraday timeline. This enables the sparkline chart showing how GERI evolved throughout the day.

## API Endpoints

### REST: Get Latest Live GERI

```
GET /api/v1/indices/geri/live/latest
Headers: X-User-Token: <session_token>
```

Returns the latest computed live GERI value plus the full intraday timeline.

### SSE: Live Stream

```
GET /api/v1/indices/geri/live/stream?token=<session_token>
```

Server-Sent Events stream. Token passed as query parameter (EventSource API cannot set headers).

Event types:
- `initial`: Sent on connection with current state
- `update`: Sent when GERI is recomputed
- `heartbeat`: Sent every 30 seconds to keep connection alive

### Internal: Trigger Recomputation

```
POST /api/v1/indices/geri/live/compute
```

Called by the alerts engine after processing new alerts. Triggers recomputation and broadcasts to SSE clients.

## SSE Broadcast Mechanism

- Each connected client gets an `asyncio.Queue` (max 50 items)
- Global list of active client queues protected by `asyncio.Lock`
- `broadcast_live_update(data)` pushes to all queues; dead/full queues are removed
- Heartbeat every 30 seconds to detect disconnected clients
- Client-side auto-reconnect with exponential backoff (1s → 30s max)

## UI Components

Located in `src/static/users-account.html`, section `section-geri-live`.

### Layout
- **Main card:** Large GERI value (72px font), band badge, trend arrow
- **Yesterday comparison:** Side-by-side yesterday vs today live values
- **AI Interpretation card:** Dynamically updated interpretation with fade-in animation
- **Intraday Timeline:** Chart.js line chart showing all data points for today
- **Sidebar:**
  - Top Drivers: Top 5 events driving the current GERI value
  - Affected Regions: Regions with highest risk concentration
  - Activity Feed: Chronological log of GERI updates (max 20 items)

### Quick Insights Strip
- **Velocity Indicator:** Shows how fast GERI is moving (e.g., "+3 pts/hr"). Color-coded: red for rising, green for falling, grey for stable.
- **Band Proximity Warning:** Alerts users when GERI is within 5 points of a band threshold (e.g., "4 pts from ELEVATED"). Pulsing amber animation for urgency.
- **Peak/Low of the Day:** Shows today's highest and lowest GERI values with timestamps (e.g., "34 @ 14:30").

## Professional Intelligence Modules

The GERI Live dashboard includes 6 professional profile cards, each designed to house profile-specific intelligence features. These appear below the AI Analysis section in a single-column layout.

### Energy Commodity Trader Module — IMPLEMENTED

Backend: `src/geri/live_trader_intel.py`
API: `GET /api/v1/indices/geri/live/trader-intel` (requires `X-User-Token`, Pro/Enterprise only)
Live Refresh: All 5 features automatically re-fetch and re-render on every SSE GERI update.

#### 1. Price-Risk Correlation Signal
Shows latest prices for Brent Crude, WTI Crude, TTF Gas, and VIX with day-over-day percentage changes. Detects divergence between GERI risk trajectory and price direction — flags when risk is rising but prices are flat (market hasn't priced in risk) or when risk and prices move in opposite directions (potential trading opportunity). Includes a 7-day Pearson correlation between GERI and Brent, displayed as a strength badge (Strong/Moderate/Weak).

Data sources: `oil_price_snapshots`, `ttf_gas_snapshots`, `vix_snapshots`, `geri_live` (daily aggregation).

#### 2. Trading Risk Heatmap
Four-cell grid showing risk intensity (0-100%) for Oil, Natural Gas, Freight/Shipping, and Power/Electricity. Intensity is computed from today's alert events — combines average severity with alert count for each commodity. Alerts are mapped to commodities via `scope_assets` array and headline keyword matching. Color-coded severity bars with regional attribution. Risk levels: critical (>75%), high (>50%), moderate (>25%), low (>0%), none (0%).

Data sources: `alert_events` (today, severity ≥1, types: HIGH_IMPACT_EVENT, REGIONAL_RISK_SPIKE, ASSET_RISK_SPIKE).

#### 3. Position Risk Alerts
Actionable warnings for traders, sorted by severity (critical first). Alert types:
- **Band Proximity:** Warning when GERI is ≤5 points from escalating to the next band (e.g., "3 pts from SEVERE"). Critical if ≤2 pts.
- **Velocity:** Warning when GERI is moving ≥3 pts/hr. Critical if ≥5 pts/hr.
- **Commodity Exposure:** Flags when top GERI drivers are oil-related or gas-related (severity ≥4). Shows driver count, max severity, and top headline.
- **Overall Risk:** Warning when GERI is in ELEVATED/SEVERE/CRITICAL band.

Each alert includes a title, message, and actionable recommendation (e.g., "Consider stop-loss tightening").

Data sources: Live GERI value/band, velocity, band proximity, top drivers.

#### 4. Intraday Risk Windows
Four trading session cards mapped to market hours:
- Asia (01:00–08:00 UTC)
- London (08:00–14:00 UTC)
- New York (14:00–21:00 UTC)
- After Hours (21:00–01:00 UTC, wraps midnight)

Each session shows: GERI average, GERI delta (start→end), alert count, max severity, risk level, and the top headline from that session. The currently active session has a green "LIVE" badge and highlighted border. Session boundaries use proper UTC datetime comparison to prevent cross-day data mixing.

Data sources: `geri_live` (intraday timeline), `alert_events` (today).

#### 5. Flash Headline Feed
Scrollable feed of the 20 most recent severity ≥4 alerts from today. Each entry shows:
- Timestamp (HH:MM UTC)
- Headline text
- Severity badge (CRITICAL red / HIGH amber)
- Region label
- Asset tags (Oil, Gas, Freight — derived from headline keyword matching)
- GERI impact indicator (delta between timeline points before/after the alert, via binary search)

Impact lookup uses `_bisect_timeline()` for O(log n) performance.

Data sources: `alert_events` (severity ≥4, today), `geri_live` (timeline for impact calculation).

### Remaining Profile Cards — Placeholder

The following cards show "Features coming soon" and have container IDs ready for future implementation:
- **Energy Risk Managers** (`geriLiveProRiskBody`)
- **Hedge Fund & Asset Managers** (`geriLiveProHedgeBody`)
- **Commodity Analysts & Strategists** (`geriLiveProAnalystBody`)
- **Corporate Energy Procurement** (`geriLiveProProcurementBody`)
- **Insurance & Reinsurance Underwriters** (`geriLiveProInsuranceBody`)

## Update Frequency

GERI Live recomputes with a 60-second debounce. After a computation, it will not recompute again for at least 60 seconds even if new alerts arrive. Outside of that cooldown, a recomputation is triggered when the alerts engine calls the `/compute` endpoint after processing new alerts. In practice, the update frequency depends on how often new alerts are being processed — it could update every minute during active news periods, or stay static during quiet periods. The displayed value always reflects the most recent computation based on all alerts processed that day.

## What Updates When GERI Live Refreshes

When GERI Live recomputes, all dashboard components update together in a single SSE broadcast:

- **GERI Value & Band:** The main score and risk band are recalculated from all alerts processed today.
- **Top Drivers:** The top 5 events driving the current GERI value are refreshed.
- **Affected Regions:** The regions with the highest risk concentration are recalculated.
- **Intraday Timeline:** A new data point is added to the sparkline chart showing how GERI evolved throughout the day.
- **AI Analysis:** The interpretation checks whether it needs to regenerate. It updates when the GERI value shifts by 2 or more points, or when the risk band changes (e.g., LOW to MODERATE). If the change is not significant enough, it carries forward the previous analysis.
- **Trader Intelligence:** All 5 trader features (Price-Risk Correlation, Heatmap, Position Alerts, Risk Windows, Flash Feed) automatically re-fetch and re-render on every SSE update.

## Edge Cases

- **No alerts today:** Shows yesterday's GERI value with `no_alerts_today: true` flag
- **No yesterday value:** Falls back to most recent `intel_indices_daily` entry
- **Midnight UTC reset:** Timeline resets, showing only post-midnight data
- **Alert storms:** Debounce prevents excessive recomputation (60s minimum interval)
- **SSE disconnection:** Client auto-reconnects with exponential backoff

## File Inventory

| File | Purpose |
|------|---------|
| `src/geri/live.py` | Compute engine, DB operations, SSE broadcast, AI interpretation |
| `src/geri/live_routes.py` | FastAPI REST + SSE endpoints, plan gating, trader-intel route |
| `src/geri/live_trader_intel.py` | Trader Intelligence Module: 5 professional features |
| `src/api/app.py` | Router registration, migration call |
| `src/static/users-account.html` | Frontend: CSS, HTML section, JavaScript |
