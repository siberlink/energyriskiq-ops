# RERI - Regional Escalation Risk Index

Development reference for RERI implementation.

---

## 1. Core Concept (What RERI Really Is)

> **RERI = "Probability-weighted disruption pressure for a specific region"**

It answers one institutional question:

> "How dangerous is THIS REGION for energy, shipping, FX, and supply chains right now?"

Unlike GERI (global), RERI is:
- **Actionable**
- **Hedge-driven**
- **Procurement-driven**
- **Insurance-driven**

This is where real budgets live.

---

## 2. Canonical Regions (Lock These Early)

Do NOT let regions be dynamic or messy. You need stable, licensable region taxonomy.

### Tier 1 (Must Have)

| Region ID | Display Name | Type |
|-----------|--------------|------|
| `middle-east` | Middle East | conflict / energy |
| `europe` | Europe | energy |
| `black-sea` | Black Sea | shipping / conflict |
| `east-asia` | East Asia | energy / shipping |
| `south-china-sea` | South China Sea | shipping / conflict |
| `north-africa` | North Africa | energy |
| `ukraine-region` | Ukraine Region | conflict (high-value war zone) |
| `persian-gulf` | Persian Gulf | energy / shipping |

### Tier 2 (Add Later)

| Region ID | Display Name |
|-----------|--------------|
| `latin-america` | Latin America |
| `west-africa` | West Africa |
| `caucasus` | Caucasus |
| `central-asia` | Central Asia |
| `indian-ocean` | Indian Ocean |

**Store as controlled vocabulary, not free text.**

### Database Schema

```sql
regions (
  region_id TEXT PRIMARY KEY,     -- "middle-east"
  region_name TEXT,               -- "Middle East"
  region_type TEXT,               -- "conflict" | "energy" | "shipping"
  core_assets JSONB               -- ["oil","gas","freight","fx"]
)
```

This becomes part of your IP.

---

## 3. Event → Region Mapping Logic

Every alert/event should already have:
- `region_primary`
- `regions_secondary[]`
- `entities[]`
- `assets[]`

### Region Inclusion Rule

An event contributes to RERI if:

```
event.region_primary == this_region
OR this_region ∈ event.regions_secondary
OR event.entities map to region influence (pipeline, strait, exporter)
```

### Examples

| Event | Regions Counted |
|-------|-----------------|
| Iran unrest | `middle-east`, `persian-gulf` |
| Gaza escalation | `middle-east` |
| Black Sea port strike | `black-sea`, `europe` |
| Qatar LNG outage | `middle-east`, `europe` |

This gives **cross-regional spillover**, which institutions love.

---

## 4. RERI Computation Model (v1 – Production Safe)

### Step 1 — Daily Regional Event Set

For each region R on day D:
```
E(R,D) = all events mapped to region R on day D
```

If no events → decay logic applies.

### Step 2 — Metrics Per Region/Day

**A. Total Severity Pressure**
```
S = Σ event.severity_weighted
```

Where:
```
event.severity_weighted = base_severity * impact_multiplier
```

**Impact multipliers:**
| Event Type | Multiplier |
|------------|------------|
| War / strikes / shutdowns | 1.5 |
| Sanctions / embargo | 1.3 |
| Rhetoric / diplomacy | 0.7 |

**B. High-Impact Event Count**
```
H = count(events where severity >= 80 OR category in ["war","supply_disruption","sanctions"])
```

This captures escalation clustering.

**C. Asset Risk Overlap**

For region R:
```
O = number of distinct high-risk assets impacted today
```

Assets set: `oil`, `gas`, `freight`, `lng`, `fx`, `power`

Example: If events hit oil + gas + freight → O = 3

### Step 3 — Normalization (Rolling 180-Day Window)

**Very important:** Normalize per region, not globally.

For each region R:
```
S_norm = normalize(S, min_R_180d, max_R_180d)
H_norm = normalize(H, min_R_180d, max_R_180d)
O_norm = normalize(O, 0, max_assets)
```

This makes:
- Middle East volatility not distort Europe
- Europe calm days meaningful

### Step 4 — Final RERI Formula (v1)

```
RERI =
  0.45 * S_norm
+ 0.30 * H_norm
+ 0.15 * O_norm
+ 0.10 * escalation_velocity
```

Where:
```
escalation_velocity = Δ(RERI yesterday vs 3-day avg)
```

This captures sudden shocks — extremely valuable.

**Clamp to 0–100.**

---

## 5. Risk Bands (Institution-Friendly)

Use stable bands — these become contract language later.

| Value | Band | Meaning |
|-------|------|---------|
| 0–20 | LOW | Normal risk |
| 21–40 | GUARDED | Elevated monitoring |
| 41–60 | HIGH | Hedging advised |
| 61–80 | SEVERE | Disruption likely |
| 81–100 | CRITICAL | Immediate escalation risk |

These bands later appear in:
- Alerts
- Contracts
- SLA language
- Insurance annexes

---

## 6. Database Schema (Core Asset)

This table becomes one of your most valuable datasets.

```sql
regional_indices (
  index_id TEXT,                  -- "region:middle-east"
  region_id TEXT,                 -- "middle-east"
  date DATE,
  value INTEGER,                  -- 0–100
  band TEXT,                      -- LOW / HIGH / CRITICAL
  trend_1d INTEGER,               -- +12
  trend_7d INTEGER,
  severity_pressure FLOAT,
  high_impact_count INTEGER,
  asset_overlap INTEGER,
  escalation_velocity FLOAT,
  drivers JSONB,                  -- top 3 events/themes
  model_version TEXT,             -- "reri_v1"
  created_at TIMESTAMP
)
```

**Index on:**
- `(region_id, date)`
- `(date)`
- `(band, region_id)`

---

## 7. Product UX

### Public (Free, Delayed, Marketing)

On region pages:
```
🔥 Middle East Escalation Index: 88 (CRITICAL)
Trend: +12 vs 7d avg
Drivers:
• Iran unrest intensifies
• Gaza escalation expands
• Shipping threats in Red Sea
```

**NO charts, no history.**

Pure SEO magnet:
- "Middle East risk index"
- "Europe energy risk today"
- "Black Sea conflict index"

### Pro Users (€49–€149)

For selected regions:
- 90-day curve
- Band history
- Asset overlays
- Escalation warnings

**Example widgets:**
- "Days in CRITICAL (last 30d): 7"
- "Escalation velocity: +4.2 (fast)"

### Enterprise (€5k–€50k+)

Per region:
- Full historical export
- API
- Intraday updates later
- Correlation with prices

---

## 8. API Design (Future Gold Mine)

Design now, even if you don't expose it yet.

### Endpoint Examples

```
GET /api/v1/index/region/middle-east/latest
GET /api/v1/index/region/europe/history?from=2025-01-01
GET /api/v1/index/region/black-sea/drivers/today
```

### Response Format

```json
{
  "region": "middle-east",
  "date": "2026-01-16",
  "value": 88,
  "band": "CRITICAL",
  "trend_1d": 12,
  "drivers": [
    "Iran unrest intensifies",
    "Gaza escalation expands",
    "Red Sea shipping threats"
  ]
}
```

This is exactly what trading desks consume.

---

## 9. Monetization Matrix

### A. SaaS Plans

| Plan | Regions |
|------|---------|
| Free | 1 region, delayed |
| Pro €99 | 3 regions, live |
| Pro+ €149 | 6 regions + history |
| Desk €299 | All regions + overlays |

### B. Enterprise Feeds

Typical pricing in market:

| Product | Price |
|---------|-------|
| 1 region daily feed | €10k–€20k / year |
| 3 regions bundle | €25k–€40k / year |
| Full regions pack | €50k–€120k / year |

**Buyers:**
- Oil majors
- LNG traders
- Reinsurers
- Shipping lines
- Defense analysts

### C. Reports & Consulting

Because you own the index:
- "Europe Energy Risk Outlook 2026"
- "Middle East Escalation Curve since 2024"

These sell for:
- €2k–€15k per report
- €5k–€50k per consulting engagement

---

## 10. Strategic Moat

This index gives you four moats:

### 1. Time Moat (Irreversible)

Once you store daily RERI:
- Nobody can recreate your history
- Nobody can backfill escalation dynamics
- Nobody can prove regime changes

This becomes: *"Only dataset covering regional escalation daily since 2025"*

That alone is acquisition-grade IP.

### 2. Calibration Moat

Over 6–24 months you can:
- Tune weights
- Learn which signals lead prices
- Improve predictive power

Institutions value consistency more than accuracy.

### 3. Cross-Index Moat

Later you will build:
- Asset Risk Index
- Shipping Index
- Sanctions Index

All of them can reference GERI and RERI.

Which means: **EnergyRiskIQ becomes the core reference layer.**

### 4. Brand Moat

You are not "an app". You become:
- "Middle East Escalation Index by EnergyRiskIQ"
- "Europe Energy Risk Index"

These become quoted in reports, blogs, terminals.

That's how Refinitiv / Verisk / Stratfor were built.

---

## 11. Execution Plan

### Step 1 — Lock Region Taxonomy
- Create `regions` table
- Define 6–8 Tier-1 regions

### Step 2 — Extend Alert Mapping
Ensure every alert has:
- `region_primary`
- `regions_secondary[]`
- `assets[]`

### Step 3 — Daily Batch Job
Every day (D):
```python
for each region R:
  events = all alerts from D-1 mapped to R
  compute S, H, O, velocity
  compute RERI
  store row
```

### Step 4 — Store Forever
- **No deletions, no rewrites**
- Only append
- This is financial-grade time series discipline

---

## Strategic Truth

What you are building is not:
- An alert system
- A dashboard
- A SaaS

You are building:
> **A proprietary geopolitical & energy risk time-series database**

That is:
- Licensable
- Defensible
- Acquirable
- Compounding

If you execute only two indices well (GERI + RERI), you already have:
- A core product
- 3 monetization channels
- Institutional credibility
- Long-term exit optionality

---

## Implementation Status

| Component | Status | Notes |
|-----------|--------|-------|
| Region taxonomy | 📋 Planned | Define controlled vocabulary |
| Event-region mapping | 📋 Planned | Extend alert_events schema |
| RERI compute engine | 📋 Planned | Similar to GERI architecture |
| Public display (24h delay) | 📋 Planned | Region pages |
| Pro dashboard | 📋 Planned | User account section |

---

## Related Documents

- [Indices Bible](./indices-bible.md) - Overall index strategy and access tiers

---

*Last updated: January 2026*
