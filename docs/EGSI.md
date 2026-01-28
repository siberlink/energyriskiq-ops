# EGSI - EU Gas Storage Index

## Overview

EGSI (EU Gas Storage Index) is EnergyRiskIQ's quantitative gas storage monitoring system, powered by the GIE AGSI+ API. It provides real-time risk assessment of European gas storage levels, refill rates, and winter supply security.

EGSI integrates with the alerts pipeline to generate `ASSET_RISK_SPIKE` alerts for the `gas` asset when storage conditions warrant concern.

---

## 1. Data Inputs

EGSI requires three core storage metrics:

| Metric | Description | Source |
|--------|-------------|--------|
| **EU Gas Storage Level** | Current storage as % of capacity vs seasonal norm | GIE AGSI+ API |
| **Refill Speed** | 7-day average injection/withdrawal rate (TWh/day) | GIE AGSI+ API |
| **Winter Deviation Risk** | Current level vs target trajectory for winter security | Computed |

---

## 2. Primary Data Source: GIE AGSI+ API

**GIE AGSI+ (Aggregated Gas Storage Inventory)** is the official EU gas storage transparency platform operated by Gas Infrastructure Europe.

| Property | Value |
|----------|-------|
| **URL** | https://agsi.gie.eu/ |
| **API Docs** | https://www.gie.eu/transparency-platform/GIE_API_documentation_v007.pdf |
| **Update Frequency** | Twice daily (19:30 CET and 23:00 CET) |
| **Coverage** | 18 EU Member States |
| **Historical Data** | From 2011 onwards |
| **Access** | Free (API key required) |

### API Key Setup

1. Register at https://agsi.gie.eu/account
2. Receive personal API key via email
3. Set environment variable: `GIE_API_KEY=your_key_here`

### Module Location

`src/ingest/gie_agsi.py`

### GitHub Actions

The `GIE_API_KEY` secret must be added to your GitHub repository secrets for the scheduled alerts engine workflow to fetch storage data. The workflow file `.github/workflows/alerts-engine-v2.yml` is configured to pass this key to the runner.

---

## 3. RSS Feeds for News/Analysis

Four high-quality RSS feeds provide supplementary European gas storage news:

| Source | URL | Focus | Weight |
|--------|-----|-------|--------|
| **ICIS Energy News** | `https://icisenergynews.podomatic.com/rss2.xml` | European gas markets, LNG, storage analysis | 0.9 |
| **EU Energy Commission** | `https://energy.ec.europa.eu/news_en/rss.xml` | EU policy, storage regulations | 0.9 |
| **Energy Intelligence** | `https://www.energyintel.com/rss-feed` | European energy policy analysis | 0.85 |
| **Oil & Gas Journal** | `https://www.ogj.com/rss` | Gas infrastructure, storage, LNG | 0.8 |

**Config Location:** `src/config/feeds.json`

---

## 4. Seasonal Norms Reference

EU gas storage seasonal targets used for deviation calculation:

| Month | Seasonal Norm (%) | Context |
|-------|-------------------|---------|
| January | 65% | Mid-winter withdrawal |
| February | 50% | End of heating season approach |
| March | 40% | Seasonal low point |
| April | 45% | Refilling begins |
| May | 55% | Refilling ramp-up |
| June | 65% | Active injection season |
| July | 75% | Peak refilling |
| August | 82% | Approaching targets |
| September | 88% | Pre-winter buffer |
| October | 92% | Near peak |
| November | 90% | **EU regulatory target (Nov 1)** |
| December | 80% | Early withdrawal season |

### EU Regulatory Targets

- **November 1 Target:** 90% storage (EU Gas Storage Regulation)
- **February 1 Target:** 45% storage (winter security floor)

---

## 5. Risk Score Computation

The EGSI risk score (0-100) is computed from:

```
Risk Score = 
    (100 - storage_percent) × 0.5     # Base: lower storage = higher risk
  + deviation_penalty                  # Negative deviation from norm adds risk
  + seasonal_factor                    # Winter months add +15
  + flow_factor                        # High withdrawals add +5-10
```

### Risk Bands

| Score | Band | Meaning |
|-------|------|---------|
| 0-25 | LOW | Normal storage conditions |
| 26-50 | MODERATE | Monitor refill progress |
| 51-75 | ELEVATED | Supply concerns, hedging advised |
| 76-100 | CRITICAL | Winter security at risk |

### Deviation Penalty

- Negative deviation from seasonal norm increases risk
- Deviation > 15% above norm reduces risk by 10 points

### Seasonal Factor

- Winter months (Nov-Mar): +15 points base risk
- Summer months: No seasonal adjustment

### Flow Factor

- Withdrawal rate > 2.0 TWh/day: +10 points
- Withdrawal rate > 1.5 TWh/day: +5 points

---

## 6. Alert Generation

### Trigger Conditions

Storage alerts are generated when:
- `risk_score >= 40` OR
- `winter_deviation_risk` is ELEVATED or CRITICAL

### Alert Types

| Type | Trigger | Description |
|------|---------|-------------|
| **STORAGE_DEVIATION** | Deviation < -15% | Storage significantly below seasonal norm |
| **WINTER_RISK** | Winter risk elevated | Winter supply security concerns |
| **STORAGE_LEVEL** | Risk score >= 40 | General low storage alert |

### Alert Severity Mapping

| Risk Score | Severity |
|------------|----------|
| 75-100 | 5 (Critical) |
| 60-74 | 4 (High) |
| 45-59 | 3 (Medium) |
| < 45 | 2 (Low) |

---

## 7. Integration with Alerts Pipeline

> **Status:** Fully integrated into the alerts engine v2 (Phase A).

Gas storage metrics are checked during every alerts engine run and feed into the pipeline as `ASSET_RISK_SPIKE` events for the `gas` asset.

### Integration Architecture

```
Alerts Engine v2 (Phase A)
    ├── generate_regional_risk_spike_events()
    ├── generate_asset_risk_spike_events()
    ├── generate_high_impact_event_alerts()
    └── generate_storage_risk_events()  ◄── EGSI
            │
            ├── Fetch from GIE AGSI+ API
            ├── Compute risk metrics
            ├── Persist to gas_storage_snapshots table
            └── Create ASSET_RISK_SPIKE alert if warranted
```

### Behavior

- Daily storage snapshot persisted to `gas_storage_snapshots` table
- If `risk_score >= 40` or `winter_deviation_risk` is ELEVATED/CRITICAL, an alert is generated
- Alert type: `ASSET_RISK_SPIKE` with `scope_assets = ['gas']`, `scope_region = 'Europe'`
- Storage alerts contribute to EERI via AssetTransmission weight

### Delivery

Storage alerts are delivered to users on:
- **Trader Plan** (allows ASSET_RISK_SPIKE)
- **Pro Plan** (allows ASSET_RISK_SPIKE)
- **Enterprise Plan** (allows ASSET_RISK_SPIKE)

---

## 8. Database Schema

### Table: `gas_storage_snapshots`

Stores daily EU storage metrics with risk scores.

```sql
CREATE TABLE gas_storage_snapshots (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL UNIQUE,
    eu_storage_percent NUMERIC(5,2) NOT NULL,
    seasonal_norm NUMERIC(5,2) NOT NULL,
    deviation_from_norm NUMERIC(6,2) NOT NULL,
    refill_speed_7d NUMERIC(8,4),
    withdrawal_rate_7d NUMERIC(8,4),
    winter_deviation_risk TEXT,
    days_to_target INT,
    risk_score INT NOT NULL,
    risk_band TEXT NOT NULL,
    interpretation TEXT,
    raw_data JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

### Indexes

- `idx_gas_storage_date` - Date-based queries (DESC)
- `idx_gas_storage_risk` - Risk score queries (DESC)

---

## 9. Usage

### Fetch Current Metrics

```python
from src.ingest.gie_agsi import run_storage_check

alert = run_storage_check()
if alert:
    print(f"Alert: {alert['headline']}")
```

### Fetch Raw Data

```python
from src.ingest.gie_agsi import fetch_eu_storage_data, fetch_historical_storage

current = fetch_eu_storage_data()
history = fetch_historical_storage(days=7)
```

### Compute Metrics Manually

```python
from src.ingest.gie_agsi import (
    fetch_eu_storage_data,
    fetch_historical_storage,
    compute_storage_metrics
)

current = fetch_eu_storage_data()
history = fetch_historical_storage(days=7)
metrics = compute_storage_metrics(current, history)

print(f"Storage: {metrics.eu_storage_percent}%")
print(f"Deviation: {metrics.deviation_from_norm:+.1f}%")
print(f"Risk: {metrics.risk_score} ({metrics.risk_band})")
```

---

## 10. Relationship to EERI

EGSI feeds into EERI (Europe Energy Risk Index) through the **AssetTransmission** component:

```
EERI = 0.45×RERI_EU + 0.25×ThemePressure + 0.20×AssetTransmission + 0.10×Contagion
                                                ↑
                                    Includes gas storage risk from EGSI
```

When storage conditions are concerning:
- EGSI generates `ASSET_RISK_SPIKE` alerts for `gas` asset
- These alerts contribute to EERI's AssetTransmission weight
- High withdrawal rates during winter increase ThemePressure

---

## Related Documents

- [RERI/EERI Documentation](./reri.md) - Regional/Europe Energy Risk Index
- [Indices Bible](./indices-bible.md) - Overall index strategy and access tiers

---

## 11. Strategic Vision: Europe Gas Stress Index

> **Note:** This section outlines the future evolution of EGSI from a storage-focused index to a comprehensive multi-dimensional gas stress system.

### Concept

EGSI (Europe Gas Stress Index) measures:

**"How stressed, fragile, and risk-exposed the European natural gas system is right now — across supply, transit, storage, prices, and geopolitics."**

It answers one killer question:

**"How close is Europe to a gas shock?"**

This is extremely valuable for:
- Gas traders
- Utilities
- Energy companies
- Industrial buyers
- Policymakers
- Hedge funds

### Positioning in EnergyRiskIQ Architecture

In the index ecosystem:

| Index | Scope |
|-------|-------|
| **GERI** | Global macro energy risk |
| **RERI** | Regional multi-asset energy + geopolitical risk |
| **EGSI** | Asset-specific system stress index |

```
EnergyRiskIQ
 ├── GERI (Global)
 ├── RERI (Regional)
 └── EGSI (System / Asset level)
```

This creates a multi-layer risk stack: **Macro → Regional → Asset System**

### Core Stress Pillars (Future Dimensions)

EGSI v2 will be built from 5 stress pillars:

#### A) Supply Stress (Weight ~25%)

Measures how fragile supply is.

**Inputs:**
- LNG terminal outages / maintenance
- Pipeline disruptions (Norway, Algeria, Russia residual flows)
- Force majeure events
- Export restrictions

**Signals:**
- Number of supply alerts
- Severity of disruptions
- % of EU supply affected

#### B) Transit & Geopolitical Stress (Weight ~20%)

Measures geopolitical and transit fragility.

**Inputs:**
- Ukraine transit risk
- Black Sea / Turkey corridor risk
- Middle East LNG tensions
- Sanctions, threats, conflicts

**Signals:**
- High-impact geopolitical alerts
- Transit-route mentions
- Conflict proximity to infrastructure

#### C) Storage Stress (Weight ~20%)

*Currently implemented via GIE AGSI+ integration.*

**Inputs:**
- EU gas storage level vs seasonal norm
- Refill speed
- Winter deviation risk

**Signals:**
- Storage below seasonal percentile
- Refill velocity slowing
- Policy interventions

#### D) Market Stress (Price & Volatility) (Weight ~20%)

Measures how stressed markets already are.

**Inputs:**
- TTF volatility
- Extreme daily moves
- Backwardation / contango signals
- Correlation with power prices

**Signals:**
- Volatility spikes
- Price shock events
- Market dislocations

#### E) Policy & Regulation Stress (Weight ~15%)

Very underused — but extremely valuable in Europe.

**Inputs:**
- Price caps
- Emergency measures
- Demand curtailments
- Subsidies / rationing discussions

**Signals:**
- Policy alerts
- Emergency declarations
- Market interventions

### EGSI v2 Output Format (Public-Facing)

```
Europe Gas Stress Index (EGSI)

Current Level: 72 / 100  (HIGH STRESS)
Trend: +8 vs 7-day average

STRESS DRIVERS:
- Supply fragility elevated (LNG outages, Norway maintenance)
- Transit risk rising (Ukraine corridor uncertainty)
- Storage below seasonal norm (-6%)

SYSTEM STATUS:
Supply:        HIGH
Transit:       ELEVATED
Storage:       ELEVATED
Market:        HIGH
Policy:        NORMAL

INTERPRETATION:
European gas system is under increasing stress. 
High sensitivity to geopolitical or weather shocks.
```

This is professional, readable, and monetizable.

---

## 12. EGSI-S vs EGSI-M: Understanding the Two Layers

### What EGSI-S (System) Is

The full Europe Gas Stress Index described in this document is **EGSI-S (System)**:

* Measures physical + structural gas system stress
* Built on 5 pillars: Supply, Transit, Storage, Market, Policy
* Answers: **"How close is Europe to a gas shock?"**

It sits cleanly in the index stack:

| Index | Scope |
|-------|-------|
| GERI | Global macro risk |
| RERI | Regional regime risk |
| EGSI-S | Asset / system risk (gas) |

**EGSI-S is the flagship institutional index** — methodologically defensible, licensable, and can stand alone without GERI/RERI.

### Why EGSI-M (Market) Exists

EGSI-M was introduced as a **tactical, fast-launch variant**:

* Anchored to RERI_EU
* Uses the existing alert engine
* No dependency (initially) on structured storage/refill/weather data
* Optimized for speed, daily cadence, and market sensitivity

**EGSI-M was added as a tactical layer, not a replacement.**

### The Clean Mental Model

| Index | What It Is | Role |
|-------|------------|------|
| **EGSI-S** | The real Europe Gas Stress Index | Structural / institutional / licensing |
| **EGSI-M** | Gas market-stress transmission indicator | Fast, reactive, trader-oriented |

Or in one sentence:

> **EGSI-S tells you how fragile the gas system is.**
> **EGSI-M tells you how violently risk is transmitting today.**

### Why EGSI-S Matters Most

Everything in this document describes what:
* Utilities
* Policymakers
* Procurement teams
* Regulators
* Serious institutional clients

will ultimately care about.

EGSI-S:
* Is methodologically defensible
* Is licensable
* Can stand alone without GERI/RERI
* Is what goes on a Methodology PDF and sells via API

**EGSI-M cannot replace that — it complements it.**

### Branding Options for EGSI-M

Future naming considerations:
* "EGSI-Market"
* "EGSI Signal"
* "EGSI Transmission Index"

This is layering like an institutional platform would.

---

## 13. EGSI-S Core Formula

### Normalized Components

Let:

* **S** = SupplyStressNormalized
* **T** = TransitStressNormalized
* **G** = StorageStressNormalized
* **M** = MarketStressNormalized
* **P** = PolicyStressNormalized

All normalized to 0–1

### Final EGSI Formula

```
EGSI = 100 * (0.25*S + 0.20*T + 0.20*G + 0.20*M + 0.15*P)
```

This gives 0–100 index.

---

## 14. Component Computation (Engine Level)

### A) Supply Stress

```
S = min(1 , (HighImpactSupplyAlerts * 0.6 + AffectedSupplyPercent * 0.4))
```

Where:
* **HighImpactSupplyAlerts** = count weighted by severity
* **AffectedSupplyPercent** = % of EU daily supply at risk

### B) Transit Stress

```
T = min(1 , (TransitAlertCount * 0.5 + GeopoliticalSeverityMean * 0.5))
```

### C) Storage Stress

Let:
* **D** = max(0 , (SeasonalNorm - CurrentStorageLevel) / SeasonalNorm )
* **V** = max(0 , (ExpectedRefillRate - ActualRefillRate) / ExpectedRefillRate )

```
G = min(1 , (0.7*D + 0.3*V))
```

### D) Market Stress

Let:
* **V** = VolatilityNormalized
* **P** = PriceShockNormalized

```
M = min(1 , (0.6*V + 0.4*P))
```

### E) Policy Stress

```
P = min(1 , (EmergencyPolicyCount * 0.6 + MarketInterventionSeverity * 0.4))
```

---

## 15. Categorization Bands

| Score | Band | Color |
|-------|------|-------|
| 0–20 | LOW STRESS | Green |
| 21–40 | NORMAL | Light Green |
| 41–60 | ELEVATED | Yellow |
| 61–80 | HIGH STRESS | Orange |
| 81–100 | CRITICAL | Red |

This aligns with:
* Traders intuition
* Risk dashboards
* Media readability

---

## 16. Monetization Strategy

### Public (Delayed, Marketing)

On homepage:
* Yesterday's EGSI
* Level + Trend only
* No components
* No history

**Purpose:** SEO + branding + backlinks. "EnergyRiskIQ Gas Index" becomes a reference.

### Pro Users (Paid Tier)

They get:
* Today's EGSI (real-time or T-1)
* 90 / 365 day history
* Component breakdown
* Driver explanations
* Correlation with TTF

### Institutional / API (Premium Tier)

They get:
* Raw component feeds
* Daily EGSI values
* Shock alerts ("Gas System Stress Spike")
* Country overlays (Germany, Italy, France)
* Licensing rights

This is **index licensing territory**.

---

## 17. Strategic Advantage

### Asset-Specific Authority

Most competitors only do:
* News
* Prices
* Generic volatility

Very few do:
* System stress indices

EnergyRiskIQ will own:
* **Global** (GERI)
* **Regional** (RERI)
* **System** (EGSI)

That's a **full institutional stack**.

---

## 18. Recommendations

EGSI should be:
* One of the first 3 branded indices
* Public on homepage (delayed)

With its own:
* Methodology page
* SEO landing page
* API future endpoint

**Future Expansion:**
* **NGSI** — Nordics Gas Stress
* **MGSI** — Mediterranean Gas Stress
* **UGSI** — Ukraine Transit Stress

---

## 19. EGSI-S Full Specification

### Purpose

Measure physical + policy + market fragility of Europe's gas system.

**Audience:** utilities, risk teams, procurement, policymakers, serious traders.

**Core output:** "How close is Europe to a gas shock?"

### A) Conceptual Model

EGSI-S is a weighted blend of 5 normalized pillars (0–1):

**S** Supply + **T** Transit/Geo + **G** Storage + **M** Market + **P** Policy

```
EGSI_S = 100 * clamp(0.25*S + 0.20*T + 0.20*G + 0.20*M + 0.15*P)
```

### B) Data Inputs

EGSI-S mixes two data types:

#### 1) Structured "state" data (recommended)

These feed Storage + Market, and improve Supply/Transit:

* Storage level (EU % full, country % full)
* Seasonal norm / percentile (e.g., 5y/10y average or percentile band)
* Injection/withdrawal (refill speed)
* Weather risk proxy (HDD forecast anomalies, or "winter deviation risk" proxy)
* Market data (TTF spot/nearby, implied/realized vol, spreads if available)

#### 2) Unstructured alert stream (already in engine)

These feed Supply/Transit/Policy and can also support Market:

* LNG terminal outages, maintenance, force majeure
* Pipeline disruptions, compressor outages
* Sanctions, conflict escalation, threats to transit routes
* Policy measures: caps, emergency declarations, rationing talk, subsidy shifts
* Market shock events: "TTF jumps X%", "extreme volatility"

### C) Computation Architecture (EnergyRiskIQ-native)

#### Layer 1 — Event ingestion

* RSS/news ingestion → ingestions
* Structured storage/market ingestion (daily) → signals_daily

#### Layer 2 — Alert generation

Each news item becomes an alert with:
* region=Europe
* theme=gas
* category={energy, geopolitical, policy, market}
* severity, confidence
* extracted entities (country, asset, terminal, pipeline, hub)

#### Layer 3 — Pillar aggregators (daily)

Compute 5 pillar scores per day (0–1), then EGSI-S.

**Recommended internal objects:**
* `egsi_s_components_daily`
* `egsi_s_daily`

#### Layer 4 — Explanation engine (UI/SEO)

For each pillar, attach:
* top drivers (top 3 alerts + top structured signals)
* interpretation line (1–2 sentences)

### D) Pillar Definitions (Practical, Implementable)

#### 1) Supply pillar (S)

**What it measures:** EU supply fragility from outages/disruptions.

**Inputs:**
* HighImpactSupplyAlerts (count weighted by severity*confidence)
* AffectedSupplyPercent (if available; else proxy by "major asset impacted")

**Implementation:**

```
S = clamp01(0.6*HighImpactSupplyAlerts_norm + 0.4*AffectedSupplyPercent_norm)
```

**How to build HighImpactSupplyAlerts_norm:**
* Filter alerts: theme=gas AND (lng OR norway OR algeria OR pipeline OR production OR outage)
* Score each: alert_score = severity * confidence * source_weight
* Daily sum → normalize with rolling window (e.g., 90d min/max or robust percentile)

#### 2) Transit/Geopolitical pillar (T)

**Measures:** transit corridor risk (Ukraine, Black Sea, Turkey, Middle East LNG lanes).

```
T = clamp01(0.5*TransitAlertCount_norm + 0.5*GeoSeverityMean_norm)
```

* TransitAlertCount_norm: alerts tagged with route/corridor entities
* GeoSeverityMean_norm: average severity*confidence of those alerts

#### 3) Storage pillar (G)

**Measures:** storage below seasonal norm + refill underperformance.

Let:
* D = max(0, (SeasonalNorm - CurrentStorageLevel) / SeasonalNorm)
* V = max(0, (ExpectedRefillRate - ActualRefillRate) / ExpectedRefillRate)

```
G = clamp01(0.7*D + 0.3*V)
```

**Winter deviation risk overlay:**

Add as an overlay factor to storage, not a separate pillar (cleaner):
* WinterRisk_norm derived from weather outlook anomalies + policy warnings + "cold snap" alert pressure

```
G = clamp01(0.65*D + 0.25*V + 0.10*WinterRisk_norm)
```

If weather data unavailable, proxy WinterRisk from news alerts.

#### 4) Market pillar (M)

**Measures:** market stress (vol + shock).

```
M = clamp01(0.6*Volatility_norm + 0.4*PriceShock_norm)
```

* Volatility_norm: realized volatility of TTF (rolling 7d/14d)
* PriceShock_norm: magnitude of daily move vs historical distribution

#### 5) Policy pillar (P)

**Measures:** intervention risk (caps, emergency measures, rationing talk).

```
P = clamp01(0.6*EmergencyPolicyCount_norm + 0.4*MarketInterventionSeverity_norm)
```

### E) EGSI-S UI Output

* EGSI-S number + band + trend
* 5 mini-bars for pillars (S/T/G/M/P)
* "Drivers" list (alerts + structured stats)
* One "Interpretation" line
* Optional: "Sensitivity" note (high when G or T is high)

---

## 20. EGSI-M Full Specification

### Purpose

Measure gas market stress transmission inside the risk ecosystem.

**Audience:** traders, market watchers, anyone already using RERI/GERI.

### Formula

```
EGSI_M = 100 * clamp(
  0.35*(RERI_EU/100) +
  0.35*ThemePressure_EU_Gas_norm +
  0.20*AssetTransmission_EU_Gas_norm +
  0.10*ChokepointFactor_EU_Gas_norm
)
```

### A) Conceptual Model

EGSI-M is "gas stress as a function of":

* broader Europe risk regime (RERI_EU)
* gas-specific pressure (ThemePressure)
* how strongly that pressure transmits into gas asset (AssetTransmission)
* chokepoint / corridor amplification (ChokepointFactor)

It's fast, alert-driven, and doesn't require structured storage data to launch.

### B) Component Definitions

#### 1) Anchor: RERI_EU

Use existing daily reri_eu (0–100).

This gives regime context: "Europe already risky → gas stress amplifies"

#### 2) ThemePressure_EU_Gas_norm

**Definition:** How intense are "gas-related" alerts today in Europe?

**Implementation:**
* Filter alerts: region=Europe AND theme=gas
* Compute weighted sum:

```
pressure_raw = Σ(severity * confidence * freshness_weight * source_weight)
```

* Normalize with rolling window → ThemePressure_norm in 0–1

#### 3) AssetTransmission_EU_Gas_norm

**Definition:** How strongly do today's Europe alerts imply a gas impact?

**Implementation:**
* For each EU alert (not only gas alerts), compute:
  * impact_prob_gas from classifier (0–1)
  * impact_score = severity * confidence * impact_prob_gas
* Sum daily, normalize

High means "non-gas events are still bleeding into gas risk."

This is what makes EGSI-M "market transmission," not just "gas headlines volume."

#### 4) ChokepointFactor_EU_Gas_norm

**Definition:** Are key corridors/infra nodes implicated today?

**Corridor entity list (start minimal):**
* Ukraine transit
* TurkStream/Black Sea
* LNG terminals (names)
* Norway pipelines
* Algeria/Med pipelines

**Compute:**

```
choke_raw = Σ(severity*confidence) for alerts mentioning chokepoint entities
```

Normalize 0–1

### C) EGSI-M Output

* EGSI-M number + band + trend
* "Top Gas Transmission Drivers" (top 3 alerts by impact_score)
* Small badges:
  * "Regime: RERI_EU high"
  * "Transmission: strong/weak"
  * "Chokepoint: active/quiet"

---

## 21. EGSI-S vs EGSI-M Comparison Matrix

| Dimension | EGSI-S (System) | EGSI-M (Market) |
|-----------|-----------------|-----------------|
| **What it measures** | Physical + structural stress (storage/refill/winter readiness + supply + policy + market) | Risk-signal transmission into gas (news/alerts regime + transmission + chokepoints) |
| **Data dependency** | Needs structured storage & refill data to be truly credible | Can run today using existing alerts + RERI |
| **Stability** | Smoother, "stateful" (storage changes daily but not wildly) | Reactive, can spike hard on breaking events |
| **Credibility** | Stronger for utilities/procurement/institutional licensing | Stronger for traders / "market regime" watchers |
| **SEO angle** | Great for "EU gas storage stress / winter readiness" keywords | Great for "gas risk index today / breaking risk" keywords |
| **Product fit** | Flagship system index that can stand alone publicly | Child index of alert engine + RERI stack |

---

## 22. Implementation Priority

### Implement EGSI-M first

**Why (practical + strategic):**
* Can ship immediately with current alert pipeline + RERI_EU
* Creates a gas-branded index fast (marketing + homepage card + daily cadence)
* Gives daily history accumulation now, which is priceless
* EGSI-S becomes "v2 premium" once structured storage/refill/winter inputs are reliable

### Recommended Rollout Plan

#### Phase 1 (now): EGSI-M

* Compute daily
* Publish delayed on homepage
* Show drivers + chokepoint badge
* Start accumulating history

#### Phase 2 (next): EGSI-S "System"

* Add structured storage/refill pipeline
* Add winter deviation risk proxy (weather or model)
* Launch as "EGSI System Edition" for Pro + API

### Result

Two indices that don't cannibalize each other:

* **EGSI-M** = "today's stress signal"
* **EGSI-S** = "system condition / winter readiness"

---

## 23. Database Schema (Postgres)

### 23.1 Core Daily Index Tables

#### EGSI-M (Market / Transmission) Daily Index

```sql
CREATE TABLE IF NOT EXISTS egsi_m_daily (
  id BIGSERIAL PRIMARY KEY,
  index_date DATE NOT NULL,
  region VARCHAR(32) NOT NULL DEFAULT 'Europe',
  index_value NUMERIC(6,2) NOT NULL,            -- 0..100
  band VARCHAR(16) NOT NULL,                    -- LOW/NORMAL/ELEVATED/HIGH/CRITICAL
  trend_1d NUMERIC(6,2),                        -- vs prior day
  trend_7d NUMERIC(6,2),                        -- vs 7d avg
  components_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  explanation TEXT,                             -- 1-2 sentence interpretation
  computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(index_date, region)
);

CREATE INDEX IF NOT EXISTS idx_egsi_m_daily_date ON egsi_m_daily(index_date);
CREATE INDEX IF NOT EXISTS idx_egsi_m_daily_region ON egsi_m_daily(region);
```

#### EGSI-S (System) Daily Index

```sql
CREATE TABLE IF NOT EXISTS egsi_s_daily (
  id BIGSERIAL PRIMARY KEY,
  index_date DATE NOT NULL,
  region VARCHAR(32) NOT NULL DEFAULT 'Europe',
  index_value NUMERIC(6,2) NOT NULL,            -- 0..100
  band VARCHAR(16) NOT NULL,
  trend_1d NUMERIC(6,2),
  trend_7d NUMERIC(6,2),
  components_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  explanation TEXT,
  computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(index_date, region)
);

CREATE INDEX IF NOT EXISTS idx_egsi_s_daily_date ON egsi_s_daily(index_date);
CREATE INDEX IF NOT EXISTS idx_egsi_s_daily_region ON egsi_s_daily(region);
```

### 23.2 Component Tables (Normalized + Raw)

Shared table for both index families:

```sql
CREATE TABLE IF NOT EXISTS egsi_components_daily (
  id BIGSERIAL PRIMARY KEY,
  index_family VARCHAR(16) NOT NULL,  -- 'EGSI_M' or 'EGSI_S'
  index_date DATE NOT NULL,
  region VARCHAR(32) NOT NULL DEFAULT 'Europe',

  component_key VARCHAR(64) NOT NULL, -- e.g. 'RERI_EU', 'ThemePressure', 'Supply', 'Storage'
  raw_value NUMERIC(18,6),
  norm_value NUMERIC(18,6),           -- 0..1
  weight NUMERIC(10,6),               -- weight used in final formula
  contribution NUMERIC(18,6),         -- weight * norm (or weight * raw scaled), pre-100
  meta JSONB NOT NULL DEFAULT '{}'::jsonb,

  computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(index_family, index_date, region, component_key)
);

CREATE INDEX IF NOT EXISTS idx_egsi_components_daily_date ON egsi_components_daily(index_date);
CREATE INDEX IF NOT EXISTS idx_egsi_components_daily_family ON egsi_components_daily(index_family);
CREATE INDEX IF NOT EXISTS idx_egsi_components_daily_key ON egsi_components_daily(component_key);
```

### 23.3 Drivers Tables

Top alerts + top structured signals for UI explainability:

```sql
CREATE TABLE IF NOT EXISTS egsi_drivers_daily (
  id BIGSERIAL PRIMARY KEY,
  index_family VARCHAR(16) NOT NULL,     -- 'EGSI_M' or 'EGSI_S'
  index_date DATE NOT NULL,
  region VARCHAR(32) NOT NULL DEFAULT 'Europe',

  driver_type VARCHAR(16) NOT NULL,      -- 'ALERT' or 'SIGNAL'
  driver_rank INT NOT NULL,              -- 1..N
  component_key VARCHAR(64),             -- which component this driver supports

  -- For ALERT drivers
  alert_id BIGINT,                       -- FK to alerts.id
  headline TEXT,
  source VARCHAR(128),
  severity NUMERIC(6,2),
  confidence NUMERIC(6,3),
  score NUMERIC(18,6),                   -- internal driver score

  -- For SIGNAL drivers (storage, refill, weather, TTF vol)
  signal_key VARCHAR(64),                -- e.g. 'EU_STORAGE_PCT', 'EU_REFILL_SPEED', 'TTF_VOL_7D'
  signal_value NUMERIC(18,6),
  signal_unit VARCHAR(32),

  -- Common
  meta JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  UNIQUE(index_family, index_date, region, driver_type, driver_rank)
);

CREATE INDEX IF NOT EXISTS idx_egsi_drivers_daily_date ON egsi_drivers_daily(index_date);
CREATE INDEX IF NOT EXISTS idx_egsi_drivers_daily_family ON egsi_drivers_daily(index_family);
CREATE INDEX IF NOT EXISTS idx_egsi_drivers_daily_alert ON egsi_drivers_daily(alert_id);
```

### 23.4 Structured Signals Table

Daily "facts" table for storage/refill/winter/market:

```sql
CREATE TABLE IF NOT EXISTS egsi_signals_daily (
  id BIGSERIAL PRIMARY KEY,
  signal_date DATE NOT NULL,
  region VARCHAR(32) NOT NULL DEFAULT 'Europe',

  signal_key VARCHAR(64) NOT NULL,      -- 'EU_STORAGE_PCT', 'EU_STORAGE_SEASONAL_NORM', etc.
  value NUMERIC(18,6) NOT NULL,
  unit VARCHAR(32),
  source VARCHAR(128),
  meta JSONB NOT NULL DEFAULT '{}'::jsonb,

  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(signal_date, region, signal_key)
);

CREATE INDEX IF NOT EXISTS idx_egsi_signals_daily_date ON egsi_signals_daily(signal_date);
CREATE INDEX IF NOT EXISTS idx_egsi_signals_daily_key ON egsi_signals_daily(signal_key);
```

---

## 24. Normalization Rules

### 24.1 Percentile-Based Robust Scaling (Recommended)

Best for noisy alert streams.

**Step A: Compute rolling distribution**
* Window: 90 days minimum, 180 days once history available
* For each component_key: compute p10, p50, p90, p95

**Step B: Map raw → 0..1 using winsorized percentile**

```
norm = clamp01( (raw - p10) / (p90 - p10) )
```

If p90 == p10, fallback:
* norm = 0.5 (neutral) or norm = clamp01(raw / small_constant)

**Why this wins:**
* Avoids "one crazy day" breaking scaling
* Works well early even with limited history

### 24.2 Rolling Min/Max (Bounded Signals Only)

Use only when measure is naturally bounded and stable.

**Good examples:**
* storage % full (0..100) → scale directly: `storage_pct_norm = storage_pct / 100`

**Not great for:** alert counts (max changes)

### 24.3 Hybrid Approach (Best Practice)

| Component Type | Scaling Method |
|----------------|----------------|
| Storage level | Direct bounded scaling + seasonal deviation formula |
| Alert-based pressure | Percentile scaling |
| Volatility and price shock | Percentile scaling (fat tails) |

### 24.4 Persist Percentiles

```sql
CREATE TABLE IF NOT EXISTS egsi_norm_stats (
  id BIGSERIAL PRIMARY KEY,
  component_key VARCHAR(64) NOT NULL,
  index_family VARCHAR(16) NOT NULL,       -- 'EGSI_M' or 'EGSI_S' or 'BOTH'
  region VARCHAR(32) NOT NULL DEFAULT 'Europe',
  as_of_date DATE NOT NULL,                -- stats computed up to this date
  window_days INT NOT NULL DEFAULT 90,

  p10 NUMERIC(18,6),
  p50 NUMERIC(18,6),
  p90 NUMERIC(18,6),
  p95 NUMERIC(18,6),

  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(component_key, index_family, region, as_of_date)
);
```

---

## 25. Daily Compute Job Specification

### 25.1 Schedule (Europe/Amsterdam timezone)

"Today's index" computed from yesterday's completed data:

| Time | Task |
|------|------|
| 02:10 | Ingest structured signals (AGSI/storage, prices, etc.) |
| 02:30 | Finalize alert scoring aggregation for D-1 |
| 02:40 | Compute EGSI-M and EGSI-S for D-1 |
| 02:45 | Publish to homepage/API (public uses delayed logic) |

### 25.2 Inputs

#### For EGSI-M

* RERI_EU (already computed daily)
* Alerts table for D-1:
  * region=Europe
  * theme=gas (ThemePressure)
  * all EU alerts with impact_prob_gas (AssetTransmission)
  * corridor/chokepoint entity hits (ChokepointFactor)

#### For EGSI-S

* Alerts table for D-1:
  * supply disruption alerts (S)
  * transit/geopolitical alerts (T)
  * policy alerts (P)
* Structured signals for D-1:
  * EU_STORAGE_PCT
  * EU_STORAGE_SEASONAL_NORM
  * EU_REFILL_SPEED (injection rate)
  * EU_EXPECTED_REFILL_SPEED (seasonal expected)
  * TTF_VOL_7D, TTF_PRICE_SHOCK
  * optional: WINTER_RISK_PROXY

### 25.3 Transforms (High-Level)

**Step 1 — Aggregate alert pressures**

Create daily raw metrics:
* ThemePressure_raw (gas alerts in EU)
* AssetTransmission_raw (EU alerts weighted by impact_prob_gas)
* Chokepoint_raw (EU gas chokepoint entity mentions)
* Supply_raw / Transit_raw / Policy_raw (for EGSI-S pillars)

**Step 2 — Compute structured raw signals**

Storage deviation D raw:
```
D = max(0, (SeasonalNorm - CurrentStorageLevel)/SeasonalNorm)
```

Refill deficit V raw:
```
V = max(0, (Expected - Actual)/Expected)
```

Market raw: vol_raw, shock_raw

**Step 3 — Update normalization stats (rolling)**

For each component:
* Compute rolling percentiles up to D-1
* Store in egsi_norm_stats

**Step 4 — Normalize**

* Percentile scaling for alert-based and market components
* Bounded scaling or formula outputs for storage components (then clamp)

**Step 5 — Compute components + contributions**

Insert into egsi_components_daily for each index family.

**Step 6 — Compute final index values**

EGSI-M:
```
0.35*(RERI_EU/100) + 0.35*ThemePressure_norm + 0.20*AssetTransmission_norm + 0.10*Chokepoint_norm
```

EGSI-S:
```
0.25*S + 0.20*T + 0.20*G + 0.20*M + 0.15*P
```

Multiply by 100, clamp 0..100.

**Step 7 — Banding**

| Range | Band |
|-------|------|
| 0–20 | LOW |
| 21–40 | NORMAL |
| 41–60 | ELEVATED |
| 61–80 | HIGH |
| 81–100 | CRITICAL |

**Step 8 — Trends**

* trend_1d = today - yesterday
* trend_7d = today - avg(last 7 days)

**Step 9 — Drivers**

Pick top drivers:
* For EGSI-M: top 3 alerts by impact_score + top chokepoint alert
* For EGSI-S: top 2 alerts for Supply/Transit/Policy + top 2 signals (storage deviation, refill deficit)

Insert into egsi_drivers_daily.

**Step 10 — Write daily tables**

Upsert into egsi_m_daily and egsi_s_daily.

---

## 26. Homepage Cards (Public + Pro)

### 26.1 EGSI-M Card (Public, Delayed)

```
Title: Europe Gas Stress (Market Signal)
Main line: EGSI-M: {value} / 100 — {band}
Subline: Trend: {trend_7d:+} vs 7-day avg
Tiny line: Updated: {index_date} (24h delayed)

Drivers (2 bullets max):
• "Transmission rising: {top_driver_headline_short}"
• "Chokepoint watch: {top_chokepoint_label}"

Interpretation (1 line):
"Gas market stress is {rising/falling/stable} as Europe risk regime 
and gas-linked events transmit into TTF sensitivity."

CTA: "See components (Pro)"
```

### 26.2 EGSI-M Card (Pro)

Everything above, plus:
* Mini component bars: RERI anchor, Theme Pressure, Transmission, Chokepoint
* "Top 5 Drivers" expandable list
* 90-day chart
* CTA: "Open EGSI-M dashboard"

### 26.3 EGSI-S Card (Public, Delayed)

```
Title: Europe Gas Stress (System Condition)
Main line: EGSI-S: {value} / 100 — {band}
Subline: Storage vs norm: {storage_delta}% | Refill pace: {refill_status}
Tiny line: Updated: {index_date} (24h delayed)

Drivers (2 lines):
• "Storage: {storage_pct}% (vs norm {norm_pct}%)"
• "Refill: {actual_refill} vs expected {expected_refill}"

Interpretation (1 line):
"System stress is driven by storage deviation and refill pace, 
with supply/transit risk contributing to winter sensitivity."

CTA: "See pillars (Pro)"
```

### 26.4 EGSI-S Card (Pro)

Everything above, plus:
* 5 pillar bars: Supply / Transit / Storage / Market / Policy
* 365-day history + seasonal overlay
* "Winter Deviation Risk" badge (Low/Med/High)
* Downloadable daily values (CSV/API)
* CTA: "Open EGSI-S dashboard"

---

## 27. Implementation Order Summary

1. **Ship EGSI-M first** (fast, uses existing alerts + RERI)
2. **Then ship EGSI-S** once structured signals ingestion is stable (storage/refill/winter/market)

---

## Related Documents

- [RERI/EERI Documentation](./reri.md) - Regional/Europe Energy Risk Index
- [Indices Bible](./indices-bible.md) - Overall index strategy and access tiers

---

*Last updated: January 2026*
