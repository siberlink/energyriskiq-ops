# EGSI Dashboard Implementation

**Last Updated:** 2026-02-09

## Overview

The Europe Gas Stress Index (EGSI) dashboard provides a multi-layered view of European gas market stress through two complementary indices:

- **EGSI-M (Market/Transmission):** Measures how violently risk is transmitting through gas markets today.
- **EGSI-S (System):** Measures how fragile the European gas system is structurally.

The dashboard spans the landing page snapshot card, public SEO pages, and authenticated API endpoints with plan-tiered access.

---

## 1. Landing Page Snapshot Card (`/`)

### Location

`src/static/index.html` — Section ID: `egsi-section`

### Design

- Green accent color (`#10b981` / `rgba(16, 185, 129)`) consistent with gas/energy theming.
- Dark background gradient (`#0f172a` to `#1e293b`).
- Same card structure as GERI, EERI, and Digest sections: header → description → feature grid → snapshot card → CTA buttons → trust line.

### Data Loading

- JavaScript fetches `GET /api/v1/indices/egsi-m/public` on page load.
- Displays: index value (0-100), risk band, 7-day trend with directional arrow.
- Band-based CSS classes: `.egsi-band-LOW`, `.egsi-band-NORMAL`, `.egsi-band-MODERATE`, `.egsi-band-ELEVATED`, `.egsi-band-HIGH`, `.egsi-band-CRITICAL`.
- Data is **24-hour delayed** for public/free access.

### Feature Grid (4 cards)

1. **Dual-Layer Index** — EGSI-M tracks market signals while EGSI-S monitors system fundamentals.
2. **Chokepoint Monitoring** — Tracks 10+ European gas infrastructure chokepoints.
3. **Storage Intelligence** — Real EU gas storage data from AGSI+ with seasonal deviation analysis.
4. **Market Stress Signals** — Live TTF pricing and volatility integrated into stress calculations.

### CTA Buttons

- "View Today's EGSI" → links to `/egsi`
- "Explore EGSI History" → links to `/egsi/history`

---

## 2. Public SEO Pages

### File

`src/egsi/egsi_seo_routes.py`

### Routes

| URL | Function | Description |
|-----|----------|-------------|
| `/egsi` | `egsi_public_page()` | Main EGSI overview page with 24h delayed data |
| `/egsi/methodology` | `egsi_methodology_page()` | How EGSI-M and EGSI-S are calculated |
| `/egsi/history` | `egsi_history_page()` | Historical data overview with links to daily/monthly archives |
| `/egsi/updates` | `egsi_updates_page()` | Changelog of EGSI methodology updates |
| `/egsi/{date}` | `egsi_daily_snapshot()` | Single day snapshot (e.g., `/egsi/2026-02-08`) |
| `/egsi/{year}/{month}` | `egsi_monthly_archive()` | Monthly archive (e.g., `/egsi/2026/02`) |

### Public Page Features

- 24-hour delayed EGSI-M data via `get_egsi_m_delayed()`.
- SEO-optimized HTML with structured meta tags.
- Canonical URLs, breadcrumbs, internal linking.
- Daily AI-generated interpretations when available.
- Component breakdown display (RERI_EU, Theme Pressure, Asset Transmission, Chokepoint Factor).
- Sitemap integration (`sitemap.xml` and `sitemap.html`).

---

## 3. API Endpoints

### File

`src/egsi/routes.py` — Router prefix: `/api/v1/indices`

### EGSI-M Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/v1/indices/egsi-m/public` | GET | None | 24h delayed data for public display |
| `/api/v1/indices/egsi-m/latest` | GET | Pro+ | Real-time latest EGSI-M value |
| `/api/v1/indices/egsi-m/status` | GET | None | Module health check |
| `/api/v1/indices/egsi-m/history` | GET | None | Historical data (query: `days`, `limit`) |
| `/api/v1/indices/egsi-m/compute` | POST | Internal | Trigger computation (body: `{date, force}`) |
| `/api/v1/indices/egsi-m/{date}` | GET | None | Specific date data |

### EGSI-S Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/v1/indices/egsi-s/status` | GET | None | Module status + data source info |
| `/api/v1/indices/egsi-s/latest` | GET | None | Latest EGSI-S value |
| `/api/v1/indices/egsi-s/history` | GET | None | Historical data (query: `days`) |
| `/api/v1/indices/egsi-s/compute` | POST | Internal | Trigger computation |
| `/api/v1/indices/egsi-s/{date}` | GET | None | Specific date data |

### Internal Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/internal/run/egsi-compute` | POST | `INTERNAL_RUNNER_TOKEN` | Workflow trigger for EGSI-M |
| `/internal/run/egsi-s-compute` | POST | `INTERNAL_RUNNER_TOKEN` | Workflow trigger for EGSI-S |

### Public API Response Format (EGSI-M)

```json
{
  "success": true,
  "value": 42,
  "band": "ELEVATED",
  "trend_1d": -3,
  "trend_7d": 5,
  "date": "2026-02-07",
  "explanation": "...",
  "top_drivers": [],
  "chokepoint_watch": [],
  "is_delayed": true,
  "delay_hours": 24
}
```

---

## 4. EGSI-M Computation

### Files

- `src/egsi/compute.py` — Formula and component calculations
- `src/egsi/service.py` — Orchestration layer
- `src/egsi/types.py` — Dataclasses, constants, risk bands, chokepoint config

### Formula

```
EGSI-M = 100 * (
    0.35 * (RERI_EU / 100) +
    0.35 * ThemePressure_norm +
    0.20 * AssetTransmission_norm +
    0.10 * ChokepointFactor_norm
)
```

### Risk Bands

| Band | Range | Color |
|------|-------|-------|
| LOW | 0-20 | Green |
| NORMAL | 21-40 | Light Green |
| ELEVATED | 41-60 | Yellow |
| HIGH | 61-80 | Orange |
| CRITICAL | 81-100 | Red |

### Chokepoints v1

10 monitored European gas infrastructure entities: Ukraine Transit (1.0), TurkStream (0.9), Nord Stream (0.8), Norway Pipelines (0.8), Gate LNG NL (0.7), Zeebrugge LNG (0.7), Dunkerque LNG (0.6), Montoir LNG (0.6), Swinoujscie LNG (0.6), Revithoussa LNG (0.5).

---

## 5. EGSI-S Computation

### Files

- `src/egsi/compute_egsi_s.py` — Formula and component calculations
- `src/egsi/service_egsi_s.py` — Orchestration with data source integration
- `src/egsi/data_sources.py` — Pluggable data source architecture

### Formula

```
EGSI-S = 100 * (
    0.25 * SupplyPressure +
    0.20 * TransitStress +
    0.20 * StorageStress +
    0.20 * PriceVolatility +
    0.15 * PolicyRisk
)
```

### Data Sources

Configured via `EGSI_S_DATA_SOURCE` environment variable:

| Source | Description |
|--------|-------------|
| `mock` | Synthetic seasonal data (default) |
| `agsi` | Real EU gas storage from AGSI+ (GIE API) |
| `ttf` | Real TTF gas prices from OilPriceAPI |
| `composite` | AGSI+ storage + OilPriceAPI TTF combined |

---

## 6. Database Schema

### EGSI-M Tables

| Table | Purpose |
|-------|---------|
| `egsi_m_daily` | Main index values (date, value, band, trend, explanation) |
| `egsi_components_daily` | Component breakdown per day |
| `egsi_drivers_daily` | Top drivers per day |
| `egsi_signals_daily` | Individual signals detected |
| `egsi_norm_stats` | Normalization statistics for percentile-based calculation |

### EGSI-S Table

| Table | Purpose |
|-------|---------|
| `egsi_s_daily` | System index values with JSONB components, data_sources array |

---

## 7. Data Retrieval Services

### File

`src/egsi/egsi_history_service.py`

### Functions

| Function | Description |
|----------|-------------|
| `get_all_egsi_m_dates()` | All dates with EGSI-M data |
| `get_egsi_m_available_months()` | Available monthly archives |
| `get_egsi_m_by_date(date)` | Full data for a specific date |
| `get_egsi_m_components_for_date(date)` | Component breakdown for a date |
| `get_egsi_m_drivers_for_date(date)` | Top drivers for a date |
| `get_egsi_m_monthly_data(year, month)` | All data for a month |
| `get_egsi_m_adjacent_dates(date)` | Previous/next navigation |
| `get_egsi_m_monthly_stats()` | Monthly aggregated statistics |
| `get_egsi_m_delayed(delay_hours)` | 24h delayed data for public display |
| `get_latest_egsi_m_public()` | Latest public-safe EGSI-M value |

---

## 8. Workflow Integration

EGSI computation runs via GitHub Actions in `alerts-engine-v2.yml`:

1. **EGSI-M** runs after alert delivery, alongside GERI and EERI.
2. **EGSI-S** runs every 10 minutes via the same workflow.

Both are triggered via internal endpoints requiring `INTERNAL_RUNNER_TOKEN`.

---

## 9. Feature Flag

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_EGSI` | `true` | Enables/disables the entire EGSI module |

When disabled, all EGSI API endpoints return HTTP 503.

---

## 10. AI Interpretations

### File

`src/egsi/interpretation.py`

Daily AI-generated interpretations are produced via `generate_egsi_interpretation()` using OpenAI (gpt-4.1-mini). These provide contextual analysis of current gas market stress levels and are displayed on:

- EGSI public SEO pages (`/egsi`, `/egsi/{date}`)
- Daily digest emails (when EGSI data is included)

---

## 11. Integration Points

- **Landing page** (`src/static/index.html`): EGSI snapshot card with live data loading.
- **Daily Digest** (`src/api/daily_digest_routes.py`): `get_egsi_snapshot()` provides EGSI data for daily intelligence digests.
- **EERI relationship**: EGSI feeds into EERI via AssetTransmission component.
- **Contextual linking** (`src/utils/contextual_linking.py`): EGSI keywords trigger links to EGSI pages from alert content.
- **Sitemap**: All EGSI pages included in `sitemap.xml` and `sitemap.html`.

---

## 12. Product Monetization Architecture

### Strategic Positioning

EGSI = **Operational Stress Intelligence** (not just an index value).

EGSI answers four critical questions:

1. "How stressed is the European gas system RIGHT NOW?"
2. "Where is stress coming from?"
3. "What markets are exposed next?"
4. "What is the probability of disruption?"

### Commercial Strengths

- Gas stress is directly tradable.
- Highly relevant to the European market.
- Strong narrative clarity for all audiences.
- Full lifecycle historical asset + storage + price data provides a significant competitive moat.

---

## 13. Intelligence Layers

The EGSI dashboard progressively unlocks five intelligence layers across plan tiers:

| Layer | Name | Description |
|-------|------|-------------|
| 1 | Headline Intelligence | Current EGSI score, stress classification, trend direction |
| 2 | Drivers & Decomposition | Storage stress, supply disruption risk, LNG congestion, market volatility, chokepoint risk |
| 3 | Market Impact Intelligence | Asset correlations, divergence detection, market regime classification |
| 4 | Predictive Intelligence | Forward probability modelling, scenario stress simulations, early warning signals |
| 5 | Decision Support & Automation | Alerts, AI interpretation, backtesting, custom alerts |

---

## 14. Plan-Tiered Feature Ladder

### FREE — "Awareness & Curiosity"

**Goal:** Hook users. Build trust. Show value exists but is incomplete.

**Dashboard Features:**

- **EGSI Snapshot:** Current value + stress category (Normal / Elevated / High / Crisis)
- **Basic Trend Indicator:** 7-day directional arrow + mini sparkline chart
- **Daily EGSI Narrative Summary:** AI-generated plain language explanation (e.g., "Gas system stress remains elevated due to storage drawdown and LNG congestion.")
- **Stress Driver Highlights (Partial):** Top 2 drivers only (e.g., Storage Pressure, LNG Import Congestion)
- **Public Historical Chart:** Full history but limited interaction, no asset overlays
- **Alerts:** Major stress spike alerts only, delayed delivery

**Locked (Visible but blurred):**

- Driver decomposition
- Asset overlays
- Probabilities
- Forward signals
- Divergence detection

**Upgrade Trigger:** "Unlock market impact intelligence"

---

### PERSONAL — $9.95 — "Serious Observer / Analyst / Research User"

Adds context + interpretation depth.

**Everything in Free PLUS:**

- **Full Stress Driver Decomposition:** Weighted contribution view (Storage stress, Supply disruptions, LNG congestion, Market volatility, Infrastructure risk)
- **Interactive Historical Charts:** Zoom, range select, compare periods
- **Asset Overlay (Limited):** 2 simultaneous assets from: TTF Gas, EU Storage, Brent Oil, EUR/USD, VIX
- **Basic Correlation Metrics:** Rolling 30D + 90D correlation
- **Risk Trend Interpretation Panel:** Classifies stress as Structural / Event-driven / Seasonal / Market sentiment-driven
- **Faster Alerts:** Near real-time, email + dashboard
- **Weekly Gas Stress Report:** Auto-generated narrative PDF

**Locked:**

- Probability modelling
- Divergence residual analytics
- Regime detection
- Predictive alerts
- AI trading intelligence

**Upgrade Trigger:** "See how stress historically moved markets — Upgrade to Trader"

---

### TRADER — $29 — "Market Intelligence & Trading Signal Layer"

Intelligence becomes actionable.

**Everything in Personal PLUS:**

- **Full Asset Impact Intelligence:** Unlimited asset overlays
- **Divergence Detection Engine:** Shows when assets deviate from expected EGSI behavior (e.g., "TTF Gas underpricing current stress by 18%")
- **Regime Classification:** Identifies Panic / Supply Shock / Storage Crisis / Normal Seasonal regimes
- **Probability Forecasting:** Probability of supply disruption, price spikes, storage depletion risk (7D / 30D horizons)
- **Early Warning Stress Signals:** Pre-crisis stress pattern detection
- **Backtesting Panel:** "How did markets behave during past EGSI spikes?"
- **Advanced Alerts:** Asset-linked (TTF breakout probability, LNG congestion stress, storage acceleration)
- **Export Data (Limited):** CSV export for charts

**Locked:**

- Scenario modelling
- AI trade narratives
- Full signal automation
- Portfolio stress modelling
- Institutional data exports

**Upgrade Trigger:** "Run forward scenario simulations & AI trading playbooks — Upgrade to Pro"

---

### PRO — $49 — "Professional Decision Intelligence"

Flagship monetization tier with strongest price-value balance.

**Everything in Trader PLUS:**

- **Scenario Simulation Engine:** Simulate LNG outage, pipeline shutdown, storage draw shock, weather shock — see EGSI forward projection
- **AI Trade & Risk Narrative Generator:** AI explains historical pattern implications (e.g., "Current stress suggests upward price skew for TTF within 10-20 trading days.")
- **Full Probability Engine:** Multi-factor conditional modelling, probability bands, risk severity curves
- **Signal Confidence Scoring:** Reliability level for each signal
- **Cross-Index Intelligence:** EGSI integrated with GERI and EERI, shows contagion risk
- **Professional Daily Gas Intelligence Digest:** Stress snapshot, market outlook, risk radar, trading bias summary
- **Custom Alert Builder:** User-defined stress thresholds, asset relationships, trigger logic
- **Full Historical Dataset Access:** For research and modelling

---

### ENTERPRISE — $129 — "Operational Risk Intelligence Platform"

Target audience: Utilities, LNG operators, hedge funds, energy consultancies, government risk teams.

**Everything in Pro PLUS:**

- **Portfolio Stress Modelling:** Upload asset exposure, see portfolio vulnerability to gas stress events
- **API Access:** Direct EGSI feed integration
- **Multi-Region Gas Stress Dashboard:** Europe, Black Sea, Global LNG routing risk
- **Custom Risk Models:** Enterprise weighting customization
- **Real-Time Data Frequency:** Higher refresh cadence
- **Institutional Reporting Engine:** Auto-generated risk board reports, regulatory summaries, internal decision briefings
- **Team Collaboration:** Shared dashboards and alerts

---

## 15. Cross-Tier Feature: EGSI Stress Timeline Replay

Available across all paid tiers as a strategic monetization tool.

Allows users to replay past crises:

- 2022 European gas crisis
- Ukraine transit disruptions
- LNG winter shortages

Powerful storytelling and educational tool that reinforces platform credibility.

---

## 16. Strategic Upgrade Funnel

| Transition | Emotional Driver | Value Unlock |
|------------|-----------------|--------------|
| Free → Personal | Awareness → Understanding | Context + interpretation depth |
| Personal → Trader | Understanding → Advantage | Market intelligence + trading signals |
| Trader → Pro | Advantage → Decision Power | Predictive intelligence + scenario simulation |
| Pro → Enterprise | Decision Power → Control | Operational risk infrastructure |

---

## 17. Competitive Moat: Real Data Assets

EnergyRiskIQ's full lifecycle data provides unique capabilities:

| Data Asset | Capability Enabled |
|------------|-------------------|
| Full lifecycle storage data | Reliable backtesting |
| Full asset price history | Real divergence analytics |
| Full EGSI history | Credible probability modelling |
| Combined historical dataset | Historical regime learning |

---

## 18. Dashboard UI Feature Map

### Master Layout

```
HEADER
  EGSI Dashboard | Plan Badge | Last Update | Alert Status | Upgrade CTA

ROW 1 — HEADLINE INTELLIGENCE
  [ EGSI Score Gauge ] [ Stress Classification ] [ Trend Momentum Panel ]

ROW 2 — DRIVERS & SYSTEM PRESSURE
  [ Driver Decomposition Chart ] [ Storage Stress Panel ]
  [ LNG / Supply Stress Panel ] [ Infrastructure / Chokepoint Panel ]

ROW 3 — MARKET IMPACT INTELLIGENCE
  [ Asset Overlay Chart ] [ Correlation & Divergence Panel ]
  [ Regime Classification Panel ]

ROW 4 — PREDICTIVE INTELLIGENCE
  [ Probability Forecast Panel ] [ Forward Stress Radar ]
  [ Scenario Simulation Panel ]

ROW 5 — DECISION SUPPORT
  [ AI Intelligence Narrative ] [ Backtesting Explorer ]
  [ Alert Builder ] [ Portfolio Stress Panel ]

FOOTER
  Stress Timeline Replay | Methodology | Export Tools
```

### Widget Visibility Per Plan

#### FREE

| Row | Widget | Status |
|-----|--------|--------|
| 1 | EGSI Score Gauge | Visible |
| 1 | Stress Classification | Visible |
| 1 | 7-Day Momentum Arrow | Visible |
| 2 | Top 2 Stress Drivers (Simplified Bars) | Visible |
| 3 | Entire row | Locked (blurred preview) |
| 4 | Entire row | Locked |
| 5 | AI Daily Summary (Simplified) | Visible |
| 5 | Backtesting | Locked |
| 5 | Alert Builder | Locked |
| 5 | Portfolio Panel | Locked |
| Footer | Stress Timeline Replay (Limited Episodes) | Visible |

#### PERSONAL

| Row | Widget | Status |
|-----|--------|--------|
| 1 | Full Headline Intelligence | Visible |
| 2 | Full Driver Decomposition | Visible |
| 2 | Storage Stress Panel | Visible |
| 2 | LNG / Supply Panel | Visible |
| 2 | Chokepoint Advanced Analytics | Locked |
| 3 | Asset Overlay Chart (Max 2 Assets) | Visible |
| 3 | Correlation Panel (30D / 90D only) | Visible |
| 3 | Divergence Engine | Locked |
| 3 | Regime Classification | Locked |
| 4 | Entire row | Locked |
| 5 | Weekly AI Intelligence Report | Visible |
| 5 | Backtesting | Locked |
| 5 | Alert Builder | Locked |
| 5 | Portfolio Panel | Locked |
| Footer | Full Stress Timeline Replay | Visible |

#### TRADER

| Row | Widget | Status |
|-----|--------|--------|
| 1 | Full access | Visible |
| 2 | Full System Pressure Panels | Visible |
| 3 | Unlimited Asset Overlay | Visible |
| 3 | Correlation + Divergence Panel | Visible |
| 3 | Regime Classification Panel | Visible |
| 4 | Probability Forecast Panel (7D + 30D) | Visible |
| 4 | Scenario Simulation | Locked |
| 4 | Forward Radar | Locked |
| 5 | Backtesting Explorer | Visible |
| 5 | Advanced Alert Builder (Preset rules only) | Visible |
| 5 | Portfolio Stress | Locked |

#### PRO

| Row | Widget | Status |
|-----|--------|--------|
| 1 | Full | Visible |
| 2 | Full + Advanced Chokepoint Analytics | Visible |
| 3 | Full Market Intelligence Layer | Visible |
| 4 | Probability Engine Full Horizons | Visible |
| 4 | Forward Stress Radar | Visible |
| 4 | Scenario Simulation Engine | Visible |
| 5 | AI Trade Intelligence Narratives | Visible |
| 5 | Full Backtesting | Visible |
| 5 | Custom Alert Builder | Visible |
| 5 | Portfolio Stress | Locked |

#### ENTERPRISE

Everything unlocked, plus:

| Row | Widget | Status |
|-----|--------|--------|
| 5 | Portfolio Stress Panel | Visible |
| 5 | Custom Risk Models | Visible |
| 5 | Multi-Region Gas Stress Layer | Visible |
| 5 | API Monitoring Panel | Visible |

---

## 19. Feature Flag JSON Schema

Backend enforcement schema controlling UI visibility and logic permissions:

```json
{
  "egsi_features": {

    "headline": {
      "score_gauge": ["free", "personal", "trader", "pro", "enterprise"],
      "stress_classification": ["free", "personal", "trader", "pro", "enterprise"],
      "momentum_panel": ["free", "personal", "trader", "pro", "enterprise"]
    },

    "drivers": {
      "driver_decomposition": ["personal", "trader", "pro", "enterprise"],
      "storage_panel": ["personal", "trader", "pro", "enterprise"],
      "lng_supply_panel": ["personal", "trader", "pro", "enterprise"],
      "chokepoint_analytics": ["pro", "enterprise"]
    },

    "market_impact": {
      "asset_overlay_basic": ["personal", "trader", "pro", "enterprise"],
      "asset_overlay_unlimited": ["trader", "pro", "enterprise"],
      "correlation_panel": ["personal", "trader", "pro", "enterprise"],
      "divergence_engine": ["trader", "pro", "enterprise"],
      "regime_classification": ["trader", "pro", "enterprise"]
    },

    "predictive": {
      "probability_basic": ["trader", "pro", "enterprise"],
      "probability_advanced": ["pro", "enterprise"],
      "forward_stress_radar": ["pro", "enterprise"],
      "scenario_simulation": ["pro", "enterprise"]
    },

    "decision_support": {
      "ai_summary_basic": ["free", "personal", "trader", "pro", "enterprise"],
      "ai_trade_narrative": ["pro", "enterprise"],
      "backtesting_basic": ["trader", "pro", "enterprise"],
      "backtesting_full": ["pro", "enterprise"],
      "alert_builder_basic": ["trader"],
      "alert_builder_advanced": ["pro", "enterprise"],
      "portfolio_stress": ["enterprise"]
    },

    "exports": {
      "csv_export": ["trader", "pro", "enterprise"],
      "data_api": ["enterprise"]
    }
  }
}
```

---

## 20. Upgrade Prompt Strategy

Psychological conversion triggers used contextually throughout the dashboard:

### Type A — Insight Teasing

> "You are seeing headline stress levels. Unlock driver decomposition to understand WHY stress is rising."

### Type B — Missed Opportunity Messaging

Triggered when divergence is detected:

> "TTF Gas is deviating from stress model expectations. Upgrade to Trader to access divergence intelligence."

### Type C — Risk Anxiety Trigger

Triggered when stress enters elevated range:

> "Stress escalation detected. Professional users monitor probability projections during these phases."

### Type D — Tool Ownership Trigger

Triggered when user clicks a locked scenario tool:

> "Run forward gas crisis simulations and anticipate price movements."

### Type E — Data Depth Trigger

Triggered when user attempts to export:

> "Export full historical stress dataset for modelling and trading research."

---

## 21. Alert Tiering Architecture

### FREE

- Major Stress Spike Alerts only
- Delayed delivery
- Dashboard notification only

### PERSONAL

- Daily Stress Change Alerts
- Storage acceleration alerts
- Email delivery

### TRADER

- Asset divergence alerts
- Price breakout probability alerts
- LNG congestion alerts
- Real-time delivery
- Email + SMS / Telegram

### PRO

- Predictive stress escalation alerts
- Scenario-based alerts
- Custom threshold alerts
- Signal confidence ranking
- Multi-index correlation alerts

### ENTERPRISE

- Portfolio exposure alerts
- Infrastructure disruption alerts
- Custom weighted risk alerts
- API alert streaming
- Team alert routing

---

## 22. Sales Messaging Stack

### Hero Positioning

**Headline:** Europe Gas Stress Intelligence — Before Markets React

**Subheadline:** Track systemic gas pressure, identify market impact, and anticipate disruption risk using EGSI — Europe's operational gas stress intelligence index.

### Value Pillars

1. **Understand System Pressure** — Monitor storage, supply disruption, LNG congestion, and infrastructure risk in one unified intelligence model.
2. **Detect Market Impact Early** — Identify asset mispricing and stress contagion across gas, oil, FX, volatility, and freight markets.
3. **Anticipate Disruption Risk** — Probability modelling and scenario simulations help users anticipate crisis phases before market pricing adjusts.

### Plan Positioning Stack

| Plan | Positioning Statement |
|------|----------------------|
| Free | "Track stress visibility" |
| Personal | "Understand stress drivers" |
| Trader | "Trade stress intelligence" |
| Pro | "Anticipate stress events" |
| Enterprise | "Operate on stress intelligence" |

### Social Proof Angle

> EGSI models gas system stress using full lifecycle storage and market data across multiple European crisis cycles.

### High-Conversion CTA Block

> Markets react to headlines. Infrastructure reacts to pressure. EGSI tracks the pressure.

**CTA Buttons:**

- View Live EGSI
- Explore Stress Drivers
- Run Scenario Simulation

### Recommended Add-On

**Comparison Slider:** "Market price vs Gas system stress" — high conversion booster showing the relationship between EGSI stress levels and actual market pricing.

---

## 23. Pricing Perception Matrix

| Plan | Price | Perceived Value |
|------|-------|----------------|
| Personal | $9.95 | Research Tool |
| Trader | $29 | Trading Signal |
| Pro | $49 | Professional Risk Platform |
| Enterprise | $129 | Institutional Intelligence |

---

## Related Documentation

- `docs/EGSI.md` — Original EGSI specification and strategic vision
- `docs/egsi-development.md` — Development status and technical architecture
- `docs/indices-bible.md` — Overall index strategy and access tiers
