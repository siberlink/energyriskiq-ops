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

Returns the latest computed live GERI value plus the full intraday timeline:

```json
{
  "success": true,
  "data": {
    "value": 34,
    "band": "MODERATE",
    "trend_vs_yesterday": 2,
    "alert_count": 23,
    "top_drivers": [...],
    "top_regions": [...],
    "components": {...},
    "interpretation": "...",
    "computed_at": "2026-02-28T13:00:00Z",
    "timeline": [
      {"value": 30, "band": "MODERATE", "alert_count": 5, "time": "..."},
      {"value": 34, "band": "MODERATE", "alert_count": 23, "time": "..."}
    ]
  }
}
```

### REST: Get Timeline Only

```
GET /api/v1/indices/geri/live/timeline
Headers: X-User-Token: <session_token>
```

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

### Connection Status Bar
- Green dot + "Connected" — SSE stream active
- Yellow dot + "Reconnecting..." — Connection lost, retrying
- Red dot + "Disconnected" — Connection failed

### Animations
- Pulsing red LIVE badge (CSS keyframes)
- Value count-up/down animation (requestAnimationFrame, cubic easing)
- Interpretation fade-in on update
- Band color transitions

### Responsive Design
- 1024px breakpoint: Single column layout, sidebar becomes 2-column grid below main content
- 640px breakpoint: Smaller value font, stacked meta row, single-column sidebar

## Update Frequency

GERI Live recomputes with a 60-second debounce. After a computation, it will not recompute again for at least 60 seconds even if new alerts arrive. Outside of that cooldown, a recomputation is triggered when the alerts engine calls the `/compute` endpoint after processing new alerts. In practice, the update frequency depends on how often new alerts are being processed — it could update every minute during active news periods, or stay static during quiet periods. The displayed value always reflects the most recent computation based on all alerts processed that day.

## What Updates When GERI Live Refreshes

When GERI Live recomputes, all dashboard components update together in a single SSE broadcast:

- **GERI Value & Band:** The main score and risk band are recalculated from all alerts processed today.
- **Top Drivers:** The top 5 events driving the current GERI value are refreshed.
- **Affected Regions:** The regions with the highest risk concentration are recalculated.
- **Intraday Timeline:** A new data point is added to the sparkline chart showing how GERI evolved throughout the day.
- **AI Analysis:** The interpretation checks whether it needs to regenerate. It updates when the GERI value shifts by 2 or more points, or when the risk band changes (e.g., LOW to MODERATE). If the change is not significant enough, it carries forward the previous analysis.

## Edge Cases

- **No alerts today:** Shows yesterday's GERI value with `no_alerts_today: true` flag
- **No yesterday value:** Falls back to most recent `intel_indices_daily` entry
- **Midnight UTC reset:** Timeline resets, showing only post-midnight data
- **Alert storms:** Debounce prevents excessive recomputation (60s minimum interval)
- **SSE disconnection:** Client auto-reconnects with exponential backoff

## Future Intelligence Enhancements

### Quick Wins (Low Effort, High Impact) — IMPLEMENTED

- **Velocity Indicator:** Shows how fast GERI is moving (e.g., "+3 pts/hr"). Calculated from the intraday timeline by comparing the current value against the value from ~1 hour ago. Color-coded: red for rising, green for falling, grey for stable. Backend: `_compute_velocity()` in `live.py`. Frontend: `#geriLiveVelocityVal` in the quick insights strip.

- **Band Proximity Warning:** Alerts users when GERI is within 5 points of a band threshold (e.g., "4 pts from ELEVATED"). Band thresholds: LOW 0-20, MODERATE 21-40, ELEVATED 41-60, SEVERE 61-80, CRITICAL 81-100. Only visible when proximity condition is met; hidden otherwise. Pulsing amber animation for urgency. Backend: `_compute_band_proximity()` in `live.py`. Frontend: `#geriLiveBandProx` (conditionally shown).

- **Peak/Low of the Day:** Shows today's highest and lowest GERI values with timestamps (e.g., "34 @ 14:30"). Derived from the full intraday timeline. Displayed in the quick insights strip alongside velocity. Backend: `_compute_peak_low()` in `live.py`. Frontend: `#geriLivePeakVal`, `#geriLiveLowVal`.

### Medium Effort

- **Alert Heatmap by Hour:** A small grid showing alert density by hour of the day. Uses `alert_events.created_at` grouped by hour (0-23 UTC). Helps users see when activity spiked. Could be a simple row of colored cells (cool to hot).

- **Driver Category Breakdown:** A mini donut chart showing what's driving GERI by alert category (e.g., 45% geopolitical, 30% supply disruption, 25% market stress). Uses the existing `classification.category` field from alert_events. Built with Chart.js doughnut chart.

- **Cross-Index Snapshot:** Shows current EERI and EGSI values alongside GERI Live for a quick multi-index view. Pulls the latest values from `intel_indices_daily` for EERI and EGSI. Helps users see if risk is concentrated in one area or broad-based.

### Premium Feel (Higher Effort)

- **Historical Comparison Overlay:** "Today vs. yesterday" or "Today vs. last Monday" on the sparkline chart. Overlays a second line on the intraday Chart.js sparkline using data from the `geri_live` table for the comparison day. Lets users visually compare how the day is unfolding relative to a reference day.

- **Scenario Projection:** Based on current trajectory, shows where GERI might land by end of day. Uses simple linear regression or weighted projection from intraday data points. Displays a "projected close" value with confidence range. Adds a dashed projected line on the sparkline.

- **Alert Severity Distribution:** A stacked bar showing how many HIGH, MEDIUM, LOW severity alerts make up today's score. Grouped from `alert_events.classification.severity`. Useful context for whether the score is driven by one major event or many smaller ones.

## File Inventory

| File | Purpose |
|------|---------|
| `src/geri/live.py` | Compute engine, DB operations, SSE broadcast, AI interpretation |
| `src/geri/live_routes.py` | FastAPI REST + SSE endpoints, plan gating |
| `src/api/app.py` | Router registration, migration call |
| `src/static/users-account.html` | Frontend: CSS, HTML section, JavaScript |

## How to Trigger a Live Recomputation

```bash
curl -X POST http://localhost:5000/api/v1/indices/geri/live/compute
```

This is intended to be called by the alerts engine after processing new alerts. The debounce mechanism ensures it won't recompute more than once per 60 seconds.
