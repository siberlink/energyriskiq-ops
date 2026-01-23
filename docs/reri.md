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

## 3.5 Existing Alert Taxonomy (Already Ideal for RERI)

The app already collects 3 types of alerts that map perfectly to RERI:

### Layer A — Atomic Escalation Signals

**`HIGH_IMPACT_EVENT`**

This is the primary truth layer — raw geopolitical/energy shocks.

Example:
```
alert_type: HIGH_IMPACT_EVENT
scope_region: Middle East
severity: 5
headline: Kurdistan's Oil Lifeline at Risk as Baghdad Payments Fall Short Again
category: ENERGY
confidence: 0.950
```

These are what RERI fundamentally measures.

### Layer B — Regional Synthesis

**`REGIONAL_RISK_SPIKE`**

This is a proto-index — already aggregated, region-specific, multi-driver, multi-asset.

Example:
```
alert_type: REGIONAL_RISK_SPIKE
scope_region: Europe
severity: 5
headline: Europe Geo-Energy Risk Spike
Current Risk Level: 100/100
ASSETS AFFECTED: FREIGHT, FX, GAS, OIL
```

**Important:** RERI should NOT be computed from these. These should be *derived from* RERI, not the other way around. Great for UX, but the index must come from Layer A + C.

### Layer C — Asset Pressure Layer

**`ASSET_RISK_SPIKE`**

This is gold — provides asset overlap, direction, confidence, region coupling.

Example:
```
alert_type: ASSET_RISK_SPIKE
scope_region: Europe
scope_asset: ['gas']
severity: 5
headline: GAS Risk Rising in Europe
Risk Score: 100/100
```

This becomes the **Asset Overlap** component of RERI.

---

## 3.6 Mapping Existing Alerts → RERI Components

### Component 1 — Severity Pressure (S)

**Source:** `HIGH_IMPACT_EVENT` alerts

Formula:
```
event_score = severity * category_weight * confidence
```

**Category Weights:**

| Category | Weight |
|----------|--------|
| WAR / STRIKE / MILITARY | 1.6 |
| SUPPLY_DISRUPTION | 1.5 |
| ENERGY | 1.3 |
| SANCTIONS | 1.3 |
| POLITICAL | 1.0 |
| DIPLOMACY | 0.7 |

Example (Kurdistan crisis):
```
event_score = 5 * 1.3 * 0.95 ≈ 6.18
```

**RERI S = sum of all event_scores for region/day.**

### Component 2 — High-Impact Concentration (H)

**Source:** `HIGH_IMPACT_EVENT` + `REGIONAL_RISK_SPIKE` alerts

Count as high-impact if:
- `severity >= 4`
- OR `alert_type = HIGH_IMPACT_EVENT`
- OR `alert_type = REGIONAL_RISK_SPIKE`

```
H = number of high-impact alerts affecting region today
```

This captures:
- Clustering
- Escalation stacking
- Regime shifts

**One of the strongest predictive signals.**

### Component 3 — Asset Overlap (O)

**Source:** `ASSET_RISK_SPIKE` alerts

```
O = count(distinct assets with ASSET_RISK_SPIKE today)
```

Assets universe: `oil`, `gas`, `freight`, `fx`, `power`, `lng`

Example: If Europe has gas + oil + freight spikes today → O = 3

This captures: *"How many market channels are under pressure simultaneously"*

**Institutions LOVE this.**

### Component 4 — Escalation Velocity (V)

Already available from trend data.

```
V = today_S - avg(S over last 3 days)
```

This captures:
- Shock acceleration
- Regime breaks
- Surprise factor

**This turns RERI into an early warning index.**

---

## 3.7 Complete RERI Formula Using Existing Data

**No new pipelines needed.**

### Step 1 — Collect Alerts

For each region R, day D:
```
A = all HIGH_IMPACT_EVENT affecting R on D
B = all ASSET_RISK_SPIKE affecting R on D
C = all REGIONAL_RISK_SPIKE affecting R on D (for clustering only)
```

### Step 2 — Compute Components

```
Severity pressure:
S = Σ (severity * category_weight * confidence)

High-impact count:
H = count(A) + count(C)

Asset overlap:
O = count(distinct scope_asset in B)

Velocity:
V = S - avg(S last 3 days)
```

### Step 3 — Normalize Per Region (Rolling 180 Days)

**Very important: per region.**

```
S_norm = normalize(S, min_R, max_R)
H_norm = normalize(H, min_R, max_R)
O_norm = normalize(O, 0, max_assets)
V_norm = normalize(V, min_R, max_R)
```

### Step 4 — Final Index

**Production-grade formula:**

```
RERI =
  0.45 * S_norm
+ 0.30 * H_norm
+ 0.15 * O_norm
+ 0.10 * V_norm
```

Clamp 0–100. Band from table.

---

## 3.8 Driver Storage (Already Perfect)

Alert bodies already contain KEY DRIVERS. Store in RERI row:

```json
{
  "drivers": [
    {
      "event_id": 16173,
      "headline": "Kurdistan's Oil Lifeline at Risk...",
      "category": "energy",
      "region": "middle-east"
    },
    {
      "event_id": 15709,
      "headline": "Cracks Emerging in Iran's Oil Sector",
      "category": "energy",
      "region": "middle-east"
    }
  ]
}
```

This gives:
- Explainability
- Auditability
- Licensing value

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

## 12. Frequently Asked Questions

### Q1: Should RERI be saved daily, same as GERI?

**Yes.** Same discipline, same "time moat" logic.

**Why:**
- Daily storage gives you credibility and auditability
- It enables trend regimes (weeks/months) that buyers care about
- It creates exportable datasets (feeds/APIs) later

**Rule of thumb:**
- Compute RERI from "yesterday's alerts" and store it permanently
- Never "rewrite history" unless you explicitly version it (e.g., `reri_v1`, `reri_v2`)

---

### Q2: Can RERI data create graphics that can be made into products?

**Yes** — RERI is made for productized visuals. The strongest ones:

**A) Regional Risk Curve (Time-Series)**
- 30 / 90 / 365 day line chart
- Band shading (LOW → CRITICAL)
- *Core Pro feature*

**B) "Risk Map" (Region Tiles Heatmap)**
- A grid of regions, each tile shows: value, band, trend arrow
- *Killer homepage widget (public delayed) + dashboard (paid live)*

**C) Escalation Velocity Sparkline**
- Small sparkline + "FAST / SLOW" tag
- *Extremely "terminal-like" and sticky*

**D) "Days in Critical" Meter**
- A simple bar: "Days in CRITICAL (last 30d): 7"
- *Sells to procurement/risk committees*

**E) Weekly / Monthly Regional Brief (PDF)**
- Auto-generated report: last 7/30 day curve, biggest drivers, top affected assets
- *Standalone product: "Europe Energy Risk Weekly"*

**RERI → graphics → monetizable products very naturally.**

---

### Q3: What are the most important Regions for RERI?

Pick regions that map to real exposure buckets (energy flows, chokepoints, sanctions zones, shipping lanes). Start with 6–8.

**Tier 1 (Start Here)**

| Region | Why It Matters |
|--------|----------------|
| Middle East / Persian Gulf | Oil + LNG + conflict escalation |
| Europe | Gas + power + sanctions + winter sensitivity |
| Black Sea | Grain + shipping + Russia/Ukraine spillover |
| Red Sea / Suez | Shipping disruption is directly monetizable |
| East Asia | China demand + coal/LNG + macro energy shifts |
| South China Sea / Taiwan Strait | Tail risk that insurers & supply chains price |

**Tier 2 (Add Next)**

| Region | Why It Matters |
|--------|----------------|
| North Africa / Med | Pipeline/LNG + migration + regional instability |
| Caucasus / Caspian | Corridors, pipelines, geopolitics |
| West Africa / Gulf of Guinea | Oil + piracy/shipping |
| Latin America | Supply shocks, politics (lower immediate pricing power) |

**Practical note:** Don't start with 20 regions. Start with the regions where buyers instantly say: "Yes, I need that."

---

### Q4: If I have past Alerts, should I generate RERI from them or start fresh?

**Do both, but label it correctly.**

**Best practice:**
- A) Backfill from past alerts (so you don't waste time already accumulated)
- B) Start fresh daily from now on (your "true" operational index stream)

**The key is labeling.** Backfilled data may differ from live process because:
- Alert model may have improved over time
- Sources changed
- Classification logic evolved

**Labeling approach:**
- Backfill output: `reri_v1_backfill`
- Live output: `reri_v1`

In raw_input, store:
```json
{
  "backfilled": true,
  "computed_at": "2026-01-23T10:00:00Z",
  "model_version": "reri_v1"
}
```

**Should you publish backfill publicly?**
- Keep backfill internal at first
- Use it to validate charts/UX
- Later expose paid history (not public)

**If past alerts are messy:**
If older alerts lack consistent fields (assets/confidence), you can still backfill with fallbacks:
- Default confidence
- Treat missing assets as zero overlap
- Still compute S + H reliably

**Recommended Move:**
1. Start saving RERI daily immediately (yesterday → today onward)
2. Backfill last 30–90 days first (fast validation + immediate charts)
3. If stable, backfill further (6–12 months), but keep it labeled

This gives you:
- Immediate product visuals
- A growing moat
- Clean operational dataset

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
