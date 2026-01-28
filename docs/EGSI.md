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

## Related Documents

- [RERI/EERI Documentation](./reri.md) - Regional/Europe Energy Risk Index
- [Indices Bible](./indices-bible.md) - Overall index strategy and access tiers

---

*Last updated: January 2026*
