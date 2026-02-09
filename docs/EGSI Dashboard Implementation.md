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

## 24. Probability Engine — Concept Model

### Primary Purpose

The EGSI Probability Engine answers:

> "Given current system stress conditions, what is the probability that specific gas market stress events occur within defined time horizons?"

The engine does **not** predict prices directly. It predicts **stress outcomes** that markets react to. This is far more robust and defensible.

### Strategic Positioning Statement

> EGSI does not predict prices directly. It models systemic gas stress conditions that historically precede price movements and supply disruptions.

---

### Core Event Set

| Event | Definition | Example |
|-------|-----------|---------|
| **A — TTF Price Spike** | Probability TTF gas price rises above statistical threshold | P(TTF moves +15% within 30 days) |
| **B — Storage Crisis Acceleration** | Probability storage draw exceeds seasonal norms | Storage deviation beyond 1.5 sigma |
| **C — Supply Disruption Escalation** | Probability pipeline/LNG flow reduction increases system-wide risk | Multi-source supply stress |
| **D — Market Panic Regime** | Probability system transitions into panic volatility state | VIX correlation + TTF volatility surge |
| **E — Infrastructure Stress Cascade** | Probability multiple chokepoints become simultaneously stressed | 2+ chokepoint flags active |

### Event Probability Taxonomy

| Horizon | Events |
|---------|--------|
| **Short Term (7-14 days)** | Price spike, volatility surge, LNG congestion |
| **Mid Term (30-60 days)** | Storage stress, supply deficit, infrastructure stress |
| **Structural (90-180 days)** | System imbalance, seasonal crisis risk |

---

### Engine Architecture (7 Layers)

#### Layer 1 — Feature Engineering

Transforms raw EGSI + asset data into predictive signals.

**Input Data Sources (already available):**

- EGSI historical values
- Storage levels
- TTF prices
- Brent prices
- VIX
- EUR/USD
- LNG & supply stress signals
- Chokepoint flags
- Alert classification outputs

**Core Feature Set:**

**1. Stress Level Metrics**

- EGSI Level
- EGSI Momentum
- EGSI Acceleration
- EGSI Volatility

**2. System Pressure Components**

- Storage deviation vs seasonal norm
- Supply shock intensity
- LNG congestion intensity
- Infrastructure disruption score

**3. Market Behavior Features**

- Rolling correlations: EGSI-TTF, EGSI-VIX, EGSI-Brent

**4. Divergence Residuals**

- `Residual = Actual Asset Movement - Expected Movement based on EGSI`
- Extremely powerful predictive signal

**5. Regime Classification Features**

- Binary and categorical regime flags: Normal, Structural Stress, Event Shock, Panic Mode

---

#### Layer 2 — Conditional Probability Modelling

Answers: "Historically, when system stress looked like THIS, what happened next?"

**Method 1 — Bucketed Historical Conditioning**

Create stress buckets (EGSI 0-25, 25-50, 50-75, 75-100) and compute event frequency over time horizons.

Example output when EGSI = 70-80:

| Event | 30D Probability |
|-------|----------------|
| TTF +10% | 46% |
| Storage crisis | 31% |
| Panic regime | 22% |

**Method 2 — Momentum Conditioning**

Probability increases when high stress combines with rising or accelerating momentum:

```
P(Event | EGSI Level, EGSI Momentum, EGSI Acceleration)
```

**Method 3 — Multi-Factor Conditional Tables**

Include storage stress, LNG congestion, and chokepoint risk:

```
P(TTF spike | EGSI > 65 AND Storage deviation > 1.2 sigma AND LNG congestion high)
```

---

#### Layer 3 — Logistic Probability Engine

Advanced model layer producing smooth probability curves.

**Model:**

```
Z = w1 * EGSI_Level
  + w2 * EGSI_Momentum
  + w3 * Storage_Stress
  + w4 * LNG_Congestion
  + w5 * Divergence_Residual
  + w6 * Regime_Flag

P(Event) = 1 / (1 + e^(-Z))
```

Produces smooth probability curves instead of step buckets.

---

#### Layer 4 — Probability Calibration

Makes the system professional-grade by calibrating probabilities against real outcomes.

**Techniques:**

- **Reliability Curves:** When model predicts 70% probability, did event occur ~70% of the time?
- **Brier Score:** Measures overall probability accuracy.
- **Rolling Recalibration:** Update weights periodically based on new data.

---

#### Layer 5 — Confidence Scoring

Probability alone is dangerous. Each prediction includes signal reliability.

**Confidence depends on:**

- Data completeness
- Regime clarity
- Model agreement
- Historical sample size

**Example output:**

```
TTF Spike Probability: 58%
Signal Confidence: HIGH
```

---

#### Layer 6 — Forward Stress Radar

Visual flagship feature showing probability curves over time horizons:

```
7 Day Risk Curve
30 Day Risk Curve
60 Day Risk Curve
```

Displayed as an expanding risk cone.

---

#### Layer 7 — Scenario Simulation Integration

Users modify inputs and recompute probabilities.

Example: User toggles "Norway pipeline outage" → engine recomputes all event probabilities with modified stress assumptions.

---

### Dashboard Output Format

**Probability Panel:**

```
TTF Price Spike
  Probability (30D): 42%
  Confidence: Medium
  Historical Baseline: 27%
```

**Risk Radar Panel:**

```
Storage Crisis Risk:
  7D  → 12%
  30D → 35%
  60D → 58%
```

**Narrative Panel:**

AI-generated explanation:

> "Current stress configuration historically precedes storage crisis acceleration within 30-60 days."

---

### Backtesting Engine

Critical for credibility. Each event prediction must be trackable.

**Metrics generated:**

- Hit rate
- False positive rate
- Calibration curves
- Regime performance

These metrics become marketing assets.

---

### Daily Compute Flow

| Step | Action |
|------|--------|
| 1 | Update EGSI + components |
| 2 | Compute feature set |
| 3 | Compute event probabilities |
| 4 | Run calibration checks |
| 5 | Generate UI outputs + alerts |

---

### Commercial Differentiation

| Plan | Probability Engine Access |
|------|--------------------------|
| Free | Stress level only |
| Personal | Historical conditional tables |
| Trader | Probability outputs |
| Pro | Full probability modelling + scenario simulations |
| Enterprise | Custom event modelling |

---

### Advanced Feature: Probability Change Tracking (Pro+)

Shows probability movement over time:

> "Probability increased from 28% → 41% in last 3 days"

---

### Competitive Advantage: Secret Weapon

The combination of three capabilities provides dramatically improved prediction power:

1. **Divergence residuals** — detect when markets misprice stress
2. **Regime detection** — classify stress state for conditional modelling
3. **Storage seasonality modelling** — leverage seasonal patterns most competitors ignore

---

## 25. Feature Engineering Specification

### Scope

Daily frequency (end-of-day). All features computed for date `t` using only data up to `t`.

### Core Inputs (Daily)

| Input | Range | Description |
|-------|-------|-------------|
| `EGSI_t` | 0-100 | Composite EGSI score |
| `EGSI_storage_t` | 0-100 | Storage component |
| `EGSI_supply_t` | 0-100 | Supply component |
| `EGSI_lng_t` | 0-100 | LNG component |
| `EGSI_market_t` | 0-100 | Market component |
| `EGSI_chokepoint_t` | 0-100 | Chokepoint component |
| `TTF_t` | — | TTF gas price |
| `BRENT_t` | — | Brent crude price |
| `VIX_t` | — | Volatility index |
| `EURUSD_t` | — | EUR/USD exchange rate |
| `STOR_pct_t` | 0-100 | EU gas storage % fullness |

### Constants & Parameters

| Parameter | Default Values |
|-----------|---------------|
| Returns windows `w` | {7, 14, 30, 90} |
| Moving average `ma` | {7, 14} |
| Z-score windows `z` | {30, 90, 180} |
| Seasonality `season_window` | 5 days around day-of-year |
| Winsorization | Cap z-scores to [-4, +4] |
| `eps` | 1e-9 (avoid division by zero) |

### Helper Functions

```
ln(x)         — natural log
SMA(x,n)      — simple moving average of last n values
STD(x,n)      — rolling standard deviation of last n values
EMA(x,n)      — exponential moving average (optional)
Z(x,n)        — (x - SMA(x,n)) / (STD(x,n) + eps)
CLAMP(x,a,b)  — clamp to range [a,b]
I(condition)  — indicator 1/0
PCTL(x,n)     — percentile rank of x_t within last n values
DOY(t)        — day-of-year (1..365)
```

---

### F0 — Normalization & Base Transform Features

| ID | Feature | Formula |
|----|---------|---------|
| F0.1 | EGSI Level (0-1) | `f_egsi_level = EGSI_t / 100` |
| F0.2 | Component Levels (0-1) | `f_storage_level = EGSI_storage_t / 100` (same for supply, lng, market, chokepoint) |
| F0.3 | Stress Category (ordinal 0-3) | `0 if EGSI<25, 1 if 25-50, 2 if 50-75, 3 if >=75` |

---

### F1 — EGSI Dynamics (Momentum, Acceleration, Volatility)

| ID | Feature | Formula |
|----|---------|---------|
| F1.1 | 1-day Change | `f_egsi_d1 = EGSI_t - EGSI_(t-1)` |
| F1.2 | 7-day Change | `f_egsi_d7 = EGSI_t - EGSI_(t-7)` |
| F1.3 | 14-day Change | `f_egsi_d14 = EGSI_t - EGSI_(t-14)` |
| F1.4 | 7-day Momentum | `f_egsi_mom7 = (EGSI_t - EGSI_(t-7)) / 7` |
| F1.5 | 14-day Momentum | `f_egsi_mom14 = (EGSI_t - EGSI_(t-14)) / 14` |
| F1.6 | Acceleration | `f_egsi_accel7 = f_egsi_mom7 - ((EGSI_(t-7) - EGSI_(t-14)) / 7)` |
| F1.7 | Volatility (30D/90D) | `f_egsi_vol30 = STD(EGSI,30)` / `f_egsi_vol90 = STD(EGSI,90)` |
| F1.8 | Z-Score (anomaly) | `f_egsi_z90 = CLAMP(Z(EGSI,90),-4,4)` / `f_egsi_z180 = CLAMP(Z(EGSI,180),-4,4)` |
| F1.9 | Percentile (rarity) | `f_egsi_pct180 = PCTL(EGSI,180)` |

---

### F2 — Storage Features (Seasonality + Drawdown Stress)

#### 2A — Storage Level vs Seasonal Norm

| ID | Feature | Formula |
|----|---------|---------|
| F2.1 | Seasonal Mean | `STOR_seas_mean_t = mean(STOR_pct_d)` for all past dates where `abs(DOY(d)-DOY(t)) <= season_window` |
| F2.2 | Seasonal Std | `STOR_seas_std_t = std(STOR_pct_d)` for same window |
| F2.3 | Storage Seasonal Z (core) | `f_stor_seas_z = CLAMP((STOR_pct_t - STOR_seas_mean_t) / (STOR_seas_std_t + eps), -4, 4)` — negative = below normal (stress) |
| F2.4 | Storage Deficit (0-1) | `f_stor_deficit = CLAMP((STOR_seas_mean_t - STOR_pct_t) / 100, 0, 1)` — positive = worse |

#### 2B — Storage Drawdown Speed

| ID | Feature | Formula |
|----|---------|---------|
| F2.5 | 7-day Storage Change | `f_stor_d7 = STOR_pct_t - STOR_pct_(t-7)` |
| F2.6 | Drawdown Rate | `f_stor_draw7 = CLAMP((STOR_pct_(t-7) - STOR_pct_t) / 7, 0, 5)` — positive = drawing |
| F2.7 | Drawdown Z | `f_stor_draw_z90 = CLAMP(Z(f_stor_draw7,90), -4, 4)` — rare fast drawdowns |

#### 2C — Storage Pressure Composite

```
f_storage_pressure = CLAMP(0.6 * f_stor_deficit + 0.4 * CLAMP(f_stor_draw_z90/4, 0, 1), 0, 1)
```

---

### F3 — Supply & LNG Features (Stress Pulse Detection)

| ID | Feature | Formula |
|----|---------|---------|
| F3.1 | Supply Stress Level | `f_supply = f_supply_level` |
| F3.2 | LNG Stress Level | `f_lng = f_lng_level` |
| F3.3 | Supply Stress Spike Flag | `I((EGSI_supply_t - SMA(EGSI_supply,30)) > 1.5 * STD(EGSI_supply,30))` |
| F3.4 | LNG Stress Spike Flag | `I((EGSI_lng_t - SMA(EGSI_lng,30)) > 1.5 * STD(EGSI_lng,30))` |
| F3.5 | Combined Flow Stress (0-1) | `f_flow_stress = CLAMP(0.5 * f_supply + 0.5 * f_lng, 0, 1)` |
| F3.6 | Flow Stress Momentum | `f_flow_mom7 = ((EGSI_supply_t + EGSI_lng_t) - (EGSI_supply_(t-7) + EGSI_lng_(t-7))) / 7 / 200` |

---

### F4 — Market Stress Features (Volatility & Fragility)

| ID | Feature | Formula |
|----|---------|---------|
| F4.1 | Market Stress Level | `f_market = f_market_level` |
| F4.2 | Market Stress Z | `f_market_z90 = CLAMP(Z(EGSI_market,90), -4, 4)` |
| F4.3 | Market Stress Spike Flag | `I((EGSI_market_t - SMA(EGSI_market,30)) > 2 * STD(EGSI_market,30))` |

---

### F5 — Chokepoint/Infrastructure Features (Tail Risk)

| ID | Feature | Formula |
|----|---------|---------|
| F5.1 | Chokepoint Level | `f_chokepoint = f_chokepoint_level` |
| F5.2 | Chokepoint Spike | `I((EGSI_chokepoint_t - SMA(EGSI_chokepoint,30)) > 2 * STD(EGSI_chokepoint,30))` |
| F5.3 | Tail Risk Composite (0-1) | `f_tail_risk = CLAMP(0.7 * f_chokepoint + 0.3 * I(EGSI_t >= 75), 0, 1)` |

---

### F6 — Asset Return Features (TTF, Brent, VIX, EURUSD)

#### 6A — Log Returns

| ID | Feature | Formula |
|----|---------|---------|
| F6.1 | TTF Return 1D | `r_ttf_1d = ln(TTF_t / TTF_(t-1))` |
| F6.2 | Brent Return 1D | `r_brent_1d = ln(BRENT_t / BRENT_(t-1))` |
| F6.3 | VIX Change 1D | `r_vix_1d = ln(VIX_t / VIX_(t-1))` |
| F6.4 | EURUSD Return 1D | `r_eurusd_1d = ln(EURUSD_t / EURUSD_(t-1))` |

#### 6B — Rolling Realized Volatility

| ID | Feature | Formula |
|----|---------|---------|
| F6.5 | TTF Vol 30D | `vol_ttf_30 = STD(r_ttf_1d, 30) * sqrt(252)` |
| F6.6 | Brent Vol 30D | `vol_brent_30 = STD(r_brent_1d, 30) * sqrt(252)` |
| F6.7 | EURUSD Vol 30D | `vol_eurusd_30 = STD(r_eurusd_1d, 30) * sqrt(252)` |

---

### F7 — EGSI-Asset Coupling (Correlation, Beta)

Market impact intelligence features.

#### 7A — Rolling Correlation

| ID | Feature | Formula |
|----|---------|---------|
| F7.1a | EGSI-TTF Corr 30D | `corr_egsi_ttf_30 = corr(EGSI, r_ttf_1d) over last 30 days` |
| F7.1b | EGSI-TTF Corr 90D | `corr_egsi_ttf_90 = corr(EGSI, r_ttf_1d) over last 90 days` |

(Similar for Brent, VIX, EURUSD)

#### 7B — Rolling Beta

```
dEGSI_1d = EGSI_t - EGSI_(t-1)
beta_ttf_90 = cov(r_ttf_1d, dEGSI_1d) over 90 / (var(dEGSI_1d) over 90 + eps)
```

(Similar for other assets)

---

### F8 — Divergence Residual Features (Differentiation Weapon)

Identify mispricing vs stress.

| ID | Feature | Formula |
|----|---------|---------|
| F8A | Expected Return | `rhat_ttf_1d = beta_ttf_90 * dEGSI_1d` |
| F8B | Residual | `resid_ttf_1d = r_ttf_1d - rhat_ttf_1d` |
| F8C | Residual Z-score (divergence intensity) | `resid_ttf_z90 = CLAMP(Z(resid_ttf_1d, 90), -4, 4)` |
| F8D | Divergence Flag | `div_ttf_flag = I(abs(resid_ttf_z90) >= 2)` |
| F8E | Divergence Direction | `div_ttf_dir = 1*I(resid_ttf_z90>0) - 1*I(resid_ttf_z90<0)` |

**Interpretation:**

- Positive residual = asset moving more than expected (overreaction)
- Negative residual = asset moving less than expected (underreaction)

---

### F9 — Regime Features (Rule-Based, Deterministic)

Deterministic first (high trust), then ML later.

| ID | Regime | Rule |
|----|--------|------|
| F9.1 | Normal | `I(EGSI_t < 40 AND f_egsi_vol30 < 8)` |
| F9.2 | Structural Stress | `I(EGSI_t >= 50 AND f_storage_pressure >= 0.35 AND f_egsi_mom14 >= 0)` |
| F9.3 | Event Shock | `I(f_supply_spike == 1 OR f_lng_spike == 1 OR f_chokepoint_spike == 1)` |
| F9.4 | Panic | `I(EGSI_t >= 75 AND (f_market_spike == 1 OR f_egsi_vol30 >= 12 OR r_vix_1d > 0.05))` |
| F9.5 | Regime ID | `0=Normal, 1=Structural, 2=Event, 3=Panic` (priority: panic > event > structural > normal) |

---

### F10 — Probability-Ready Composite Features (0-1 Inputs)

Clean inputs for the logistic probability engine.

| ID | Feature | Formula |
|----|---------|---------|
| F10.1 | System Stress | `CLAMP(0.5 * f_egsi_level + 0.5 * CLAMP(f_egsi_z180/4, 0, 1), 0, 1)` |
| F10.2 | Pressure | `CLAMP(0.6 * f_storage_pressure + 0.4 * f_flow_stress, 0, 1)` |
| F10.3 | Market Fragility | `CLAMP(0.5 * CLAMP(f_market_z90/4, 0, 1) + 0.5 * CLAMP(vol_ttf_30/0.8, 0, 1), 0, 1)` |
| F10.4 | Tail Risk | `f_tail_risk` |
| F10.5 | Divergence (TTF-centric) | `CLAMP(abs(resid_ttf_z90)/4, 0, 1)` |
| F10.6 | Regime One-Hots | `f_reg_normal, f_reg_struct, f_reg_event, f_reg_panic` |

---

### F11 — Event Definition Features (Labeling Outcomes)

Define events for training and backtesting.

**TTF Spike Event:**

```
event_ttf_spike_30d = I((TTF_(t+30) - TTF_t) / TTF_t >= 0.15)
```

Threshold variants: 10%, 15%, 20%

**Storage Crisis Event:**

```
event_stor_crisis_30d = I(f_stor_deficit_(t+30) - f_stor_deficit_t >= 0.10)
```

**Panic Regime Event:**

```
event_panic_14d = I(max(reg_panic over t+1..t+14) == 1)
```

---

### Minimal Feature Set (Lean MVP)

The smallest high-power set for strong probability outputs:

| Feature | Purpose |
|---------|---------|
| `f_egsi_level` | Current stress state |
| `f_egsi_mom14` | Trend direction |
| `f_egsi_z180` | Stress anomaly |
| `f_storage_pressure` | Storage risk |
| `f_flow_stress` | Supply/LNG risk |
| `f_market_z90` | Market fragility |
| `resid_ttf_z90` | Divergence signal |
| `regime_id` | System regime |

---

### Feature Plan Gating (Strategic)

| Plan | Features Exposed |
|------|-----------------|
| Personal | `f_storage_pressure`, `f_flow_stress`, `f_market_z90` (as "drivers") |
| Trader | Correlations + divergence `resid_ttf_z90` |
| Pro | Probability model outputs using composites `f_system_stress`, `f_pressure`, `f_fragility`, `f_tail`, `f_divergence` |
| Enterprise | Custom events + custom weights |

---

## Related Documentation

- `docs/EGSI.md` — Original EGSI specification and strategic vision
- `docs/egsi-development.md` — Development status and technical architecture
- `docs/indices-bible.md` — Overall index strategy and access tiers
