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

## 13. MOST IMPORTANT | STRATEGY

> **This section contains the most critical strategic guidance for RERI development and commercialization.**

### 13.1 RERI Is Not an Index — It Is a "Decision Layer"

The biggest conceptual shift:

**You are NOT building:**
- A statistic
- A chart
- An alert system

**You ARE building:**
- A regional decision layer for energy, shipping, and risk allocation

**This implies:**

| Principle | Meaning |
|-----------|---------|
| Stability beats precision | Institutions prefer smooth indices, consistent behavior, predictable bands |
| Avoid excessive volatility | Smooth with 3–5 day rolling influence |
| No wild daily swings | Unless truly justified by events |

RERI must be:
- **Stable enough** to trust
- **Reactive enough** to warn early
- **Interpretable enough** to explain

---

### 13.2 Regime Detection Is the Hidden Gold Feature

Later (not v1), RERI can detect regime states:

| Regime | Description |
|--------|-------------|
| CALM | Baseline risk, no significant events |
| ELEVATED | Above-normal risk, monitoring advised |
| ESCALATING | Risk increasing, hedging recommended |
| CRISIS | Active disruption, immediate action needed |
| DE-ESCALATING | Risk decreasing from crisis |

**Example signal:**
> "Middle East entered ESCALATION regime 6 days ago"

**That's a €10k-level signal alone.**

Extremely valuable for:
- Hedging decisions
- Insurance pricing
- Supply chain decisions

---

### 13.3 Correlation With Prices Is Your Proof Engine

**Build correlation dashboards internally.** For each region:

| RERI Correlation | Use Case |
|------------------|----------|
| RERI vs Brent | Oil price sensitivity |
| RERI vs TTF gas | European gas exposure |
| RERI vs freight indices | Shipping disruption |
| RERI vs FX (EUR/USD, USD/CAD) | Currency risk |

This gives you:
- Proof of economic relevance
- Marketing charts
- Sales ammunition
- Model calibration

**Future pitch:**
> "When Middle East RERI > 70, Brent volatility rises 42% within 5 days"

**That is enterprise-grade selling power.**

---

### 13.4 RERI Can Become a Benchmark Index

**Very rare opportunity.** If you:
- Publish daily
- Keep methodology stable
- Build multi-year history

RERI can become a **benchmark index cited by others**, like:
- "Europe Energy Risk Index (EnergyRiskIQ)"
- "Middle East Escalation Index"

This gives you:
- Backlinks
- Citations
- Brand moat
- Acquisition leverage

**Almost no startups manage to create benchmark indices. You are in a perfect niche to do it.**

---

### 13.5 Versioning Strategy (Critical Long-Term)

**Formal index versioning discipline:**

| Rule | Implementation |
|------|----------------|
| Never rewrite past values silently | Immutable history |
| Any formula change = new version | `reri_v1` → `reri_v2` |
| Always store `index_version` | In every row |

**Example timeline:**
- `reri_v1` → first 18 months
- `reri_v2` → improved weights / regime logic

**In UI:**
- Default to latest version
- Allow enterprise to choose versions

**Institutions love this.** It signals:
- Professionalism
- Auditability
- Regulatory readiness

---

### 13.6 RERI Powers Multiple Derived Products

RERI is not one product — it is a **platform primitive**.

| Derived Product | Source | Buyer |
|-----------------|--------|-------|
| **Escalation Probability Index (EPI)** | RERI + velocity → "Probability of disruption in next 7 days (%)" | Insurers |
| **Shipping Disruption Index** | Red Sea RERI + Black Sea RERI + freight overlap | Shipping lines |
| **Sanctions Pressure Index** | RERI filtered by category = sanctions/political | Banks, compliance |
| **Energy Corridor Risk Index** | Regions tied to pipelines/straits/LNG routes | Shipping, insurers |

**Corridor-specific indices:**
- Suez Risk
- Hormuz Risk
- Bosphorus Risk

**These sell extremely well to shipping & insurers.**

---

### 13.7 Early-Warning Alerts (Future Feature)

**"Escalation Warning Alerts"** — Trigger when:
- RERI crosses 60
- OR velocity > threshold
- OR enters ESCALATING regime

**Example alert:**
```
⚠️ MIDDLE EAST ESCALATION WARNING
RERI crossed into SEVERE zone (+14 in 3 days)
Disruption probability rising
```

This becomes:
- Premium push alert
- SMS / Telegram signal
- Paid feature

**This is where stickiness comes from.**

---

### 13.8 Governance & Trust (Huge for Enterprise)

Institutions will eventually ask:
- How is this computed?
- Is it biased?
- Is it stable?
- Is it auditable?

**From day 1, always store:**
- `driver_event_ids`
- `components`
- `raw_scores`
- `model_version`

This allows you to:
- Explain every index point
- Pass internal audits
- Satisfy compliance

**Very few startups prepare this early — you already are.**

---

### 13.9 Naming Strategy (Extremely Important)

| Context | Name |
|---------|------|
| Internal (engineering, docs, schema) | RERI |
| External (product, marketing) | Regional names |

**External product names:**

| Region | External Name |
|--------|---------------|
| Middle East | "Middle East Escalation Index" |
| Europe | "Europe Energy Risk Index" |
| Black Sea | "Black Sea Conflict Index" |

These names:
- Rank on Google
- Are understandable
- Sound institutional
- Sell better

**Example:**
> "Europe Energy Risk Index by EnergyRiskIQ"

**That's a brand asset.**

---

### 13.10 SEO Strategy (Massive Opportunity)

RERI creates a rare SEO gold structure:

**Pages you can own:**
- `/indices/middle-east-escalation-index`
- `/indices/europe-energy-risk-index`
- `/indices/black-sea-conflict-index`

Each page:
- Daily updated
- Unique data
- Institutional keywords
- Very high authority potential

**Target keywords:**
- "Middle East risk index"
- "Europe energy risk today"
- "Black Sea conflict risk"

**Almost nobody competes here. This can make EnergyRiskIQ a category reference site.**

---

### 13.11 Pricing Power Strategy

RERI gives excellent pricing discrimination:

| Tier | Price | Features |
|------|-------|----------|
| **Low end** | €49–€149 | Live RERI, 3–6 regions, charts |
| **Mid** | €299–€999 | All regions, alerts, weekly reports |
| **Enterprise** | €10k–€120k | Per-region feeds, history, API, correlation data |

RERI scales extremely well with price because:
- Value increases with exposure size
- Institutional users pay from risk budgets
- Replacement cost is very high

---

### 13.12 Defensive Strategy (Protect Your Moat)

Three things you MUST protect:

| Asset | Protection |
|-------|------------|
| **History** | Never give full public history. This is your moat. |
| **Components & weights** | Never publish formulas, caps, weights. Only describe conceptually. |
| **Frequency** | Public: daily delayed. Paid: daily live. Enterprise: intraday later. Never give public intraday. |

---

### 13.13 Long-Term Exit Value

With 3–5 years of:
- RERI history
- Multiple regions
- Correlations
- Enterprise clients

EnergyRiskIQ becomes:
- Data acquisition target
- Terminal integration candidate
- Research provider

**Potential buyers:**
- Refinitiv
- Bloomberg
- S&P Global
- ICE
- Major commodity houses

**This is your personal exit strategy.**

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

## 14. Formulas Reference (Quick Reference)

Complete formula reference for RERI and all derived indices.

---

### 14.1 Core RERI Base Formula

```
RERI_R = 100 * clamp( 0.45 * S_norm + 0.30 * H_norm + 0.15 * O_norm + 0.10 * V_norm )
```

**Component definitions:**
```
S = sum( severity(e) * category_weight(e) * confidence(e) )
H = count( high_impact_events + regional_risk_spikes )
O = count( distinct_impacted_assets )
V = S_today - avg(S_last_3_days)
```

**Normalization:**
```
S_norm = clamp( S / 25 , 0 , 1 )
H_norm = clamp( H / 6 , 0 , 1 )
O_norm = clamp( O / 4 , 0 , 1 )
V_norm = clamp( ( V + 10 ) / 20 , 0 , 1 )
```

---

### 14.2 Generic Derived Index Formula

```
DerivedIndex_R_T = 100 * clamp(
    w1 * ( RERI_R / 100 ) +
    w2 * ThemePressure_R_T_norm +
    w3 * AssetTransmission_R_T_norm +
    w4 * ChokepointFactor_R_T_norm +
    w5 * Contagion_R_norm
)
```

---

### 14.3 Building Block Formulas

#### ThemePressure
```
ThemePressure_R_T = sum( severity(e) * confidence(e) * typeMultiplier(e) )
ThemePressure_R_T_norm = clamp( ThemePressure_R_T / ThemeCap_T , 0 , 1 )
```

#### AssetTransmission
```
AssetTransmission_R_T = count( distinct_assets_with_spike_for_theme_T )
AssetTransmission_R_T_norm = clamp( AssetTransmission_R_T / MaxAssets_T , 0 , 1 )
```

Weighted version:
```
AssetTransmission_R_T_weighted = ( 1 / NumAssets_T ) * sum( spike_present(a) * ( riskScore_a / 100 ) * confidence_a )
```

#### ChokepointFactor
```
ChokepointFactor_R_T = max( severity(e) * confidence(e) )
ChokepointFactor_R_T_norm = clamp( ChokepointFactor_R_T / ChokepointCap , 0 , 1 )
```

#### Contagion
```
Contagion_R = sum( ( RERI_neighbor / 100 ) * alpha_neighbor_to_R )
Contagion_R_norm = clamp( Contagion_R , 0 , 1 )
```

---

### 14.4 Europe Indices

#### Europe Energy Risk Index (EERI)
```
EERI = 100 * clamp(
    0.45 * ( RERI_EU / 100 ) +
    0.25 * ThemePressure_EU_Energy_norm +
    0.20 * AssetTransmission_EU_Energy_norm +
    0.10 * Contagion_EU_norm
)
```

#### Europe Gas Stress Index (EGSI)
```
EGSI = 100 * clamp(
    0.35 * ( RERI_EU / 100 ) +
    0.35 * ThemePressure_EU_Gas_norm +
    0.20 * AssetTransmission_EU_Gas_norm +
    0.10 * ChokepointFactor_EU_Gas_norm
)
```

#### Europe Sanctions & Policy Shock Index (ESPSI)
```
ESPSI = 100 * clamp(
    0.30 * ( RERI_EU / 100 ) +
    0.50 * ThemePressure_EU_Sanctions_norm +
    0.20 * AssetTransmission_EU_Sanctions_norm
)
```

---

### 14.5 Middle East Indices

#### Middle East Escalation Index (MEEI)
```
MEEI = RERI_ME
```

#### Middle East Oil Supply Risk Index (MOSRI)
```
MOSRI = 100 * clamp(
    0.40 * ( RERI_ME / 100 ) +
    0.30 * ThemePressure_ME_Oil_norm +
    0.20 * AssetTransmission_ME_Oil_norm +
    0.10 * ChokepointFactor_ME_Oil_norm
)
```

#### Middle East LNG Disruption Index (MELDI)
```
MELDI = 100 * clamp(
    0.30 * ( RERI_ME / 100 ) +
    0.35 * ThemePressure_ME_LNG_norm +
    0.25 * AssetTransmission_ME_LNG_norm +
    0.10 * ChokepointFactor_ME_LNG_norm
)
```

#### Hormuz & Persian Gulf Chokepoint Index (HPCI)
```
HPCI = 100 * clamp(
    0.20 * ( RERI_ME / 100 ) +
    0.55 * ChokepointFactor_ME_Hormuz_norm +
    0.15 * ThemePressure_ME_ShippingThreat_norm +
    0.10 * AssetTransmission_ME_Freight_norm
)
```

---

### 14.6 Black Sea Indices

#### Black Sea Conflict Risk Index (BCRI)
```
BCRI = 100 * clamp(
    0.55 * ( RERI_BS / 100 ) +
    0.25 * ThemePressure_BS_Conflict_norm +
    0.10 * ChokepointFactor_BS_Ports_norm +
    0.10 * Contagion_BS_norm
)
```

#### Black Sea Shipping Disruption Index (BSSDI)
```
BSSDI = 100 * clamp(
    0.25 * ( RERI_BS / 100 ) +
    0.25 * ThemePressure_BS_Shipping_norm +
    0.35 * ChokepointFactor_BS_Ports_norm +
    0.15 * AssetTransmission_BS_Freight_norm
)
```

#### Black Sea Energy Corridor Risk Index (BSECRI)
```
BSECRI = 100 * clamp(
    0.35 * ( RERI_BS / 100 ) +
    0.35 * ThemePressure_BS_EnergyCorridor_norm +
    0.20 * ChokepointFactor_BS_Corridors_norm +
    0.10 * AssetTransmission_BS_Energy_norm
)
```

---

## 15. How RERI Is Created Technically

This section documents the technical implementation of RERI and derived indices.

---

### 14.1 Data Flows Into RERI

Three data layers feed into RERI:

#### A) Atomic Events (Truth Layer)
- **Alert type:** `HIGH_IMPACT_EVENT`
- **Carries:** `scope_region`, `severity` (1–5), `category`, `confidence`, `driver_event_ids`, `headline`, `created_at`

#### B) Asset Pressure (Transmission Layer)
- **Alert type:** `ASSET_RISK_SPIKE` (or `ASSET_RISK_ALERT`)
- **Carries:** `scope_region`, `scope_assets` (e.g., `["gas"]`), `risk_score`, `direction`, `confidence`, `driver_event_ids`

#### C) Regional Synthesis (Narrative Layer)
- **Alert type:** `REGIONAL_RISK_SPIKE`
- **Carries:** region + top drivers + implied multi-asset stress
- **Use as:** corroboration signal (not the core truth)

---

### 14.2 Where AI Is Used (and Where It Should NOT Be)

**AI should be upstream, not inside the index math.**

#### AI Components (Upstream)
- Event classification (category, region_primary, entities, severity, confidence)
- Asset tagging (oil, gas, freight, fx, lng, power)
- Dedup / clustering (same story across sources)
- Driver extraction (top driver events)

#### Index Computation (Downstream)
- **Deterministic math** (stable + auditable + enterprise-friendly)

> This separation is key for trust and licensing.

---

### 14.3 Daily Compute Pipeline

**Simple + reliable process:**

1. Choose `target_day` = yesterday (Europe/Amsterdam day boundary)

2. For each region:
   - Pull that day's `HIGH_IMPACT_EVENT`
   - Pull that day's `ASSET_RISK_SPIKE`
   - Optionally pull `REGIONAL_RISK_SPIKE` as corroboration

3. Compute components:
   - **S** = Severity Pressure
   - **H** = High-impact Concentration
   - **O** = Asset Overlap
   - **V** = Velocity (vs last 3 days)

4. Normalize (caps / rolling windows)

5. Output: RERI value 0–100, band, trend, top drivers

6. Persist (Phase 0, no schema change):
   ```sql
   INSERT INTO alert_events (alert_type, ...) 
   VALUES ('RERI_DAILY', ...) -- details in raw_input
   ```

---

## 15. Derived Indices Architecture

RERI serves as the regional baseline escalation signal. Derived indices are specialized lenses over the same underlying alert/event stream.

---

### 15.1 Core Formula (Secret Sauce Architecture)

Each derived index follows this pattern:

```
DerivedIndex(R, T, D) = 100 × clamp(
    w1 × RERI_hat(R, D) +
    w2 × ThemePressure_hat(R, T, D) +
    w3 × AssetTransmission_hat(R, T, D) +
    w4 × ChokepointFactor_hat(R, T, D) +
    w5 × Contagion_hat(R, D)
)
```

Where:
- **R** = region (Europe, Middle East, Black Sea)
- **T** = theme/product (Energy, Gas, Shipping, LNG, Sanctions, etc.)
- **D** = day
- **_hat** = normalized to 0..1 (caps or rolling)

This makes every derived index:
- Auditable
- Tunable
- Versionable
- Licensable

---

### 15.2 Building Blocks (Computed Per Region/Day)

#### 1) RERI Baseline
```
RERI_hat = RERI / 100
```

#### 2) ThemePressure (from HIGH_IMPACT_EVENT)

Filter events by category set relevant to theme T:

```
ThemePressure(R, T) = Σ[e ∈ Events(R, D) ∩ Theme(T)] severity(e) × confidence(e) × typeMultiplier(e)
```

Normalize with a cap (v1) per theme:
```
ThemePressure_hat = clamp(ThemePressure / Tcap, 0, 1)
```

#### 3) AssetTransmission (from ASSET_RISK_SPIKE)

Simple v1:
```
AssetTransmission(R, T) = Σ[a ∈ Assets(T)] 1[asset spike present]
AssetTransmission_hat = clamp(AssetTransmission / |Assets(T)|, 0, 1)
```

Better v1.1 (if you store asset risk score 0–100):
```
AssetTransmission = (1 / |Assets(T)|) × Σ[a ∈ Assets(T)] 1[spike] × (riskScore_a / 100) × confidence_a
```

#### 4) ChokepointFactor (Optional but Powerful)

If region/day includes events mentioning key corridors/straits/pipelines, boost:
```
ChokepointFactor(R, T) = max_e(1[entity ∈ chokepoints] × severity × confidence)
```
Normalize with a cap and clamp.

#### 5) Contagion (Spillover)

Regional risk can be influenced by linked regions:
```
Contagion(R, D) = Σ[r' ∈ Neighbors(R)] RERI_hat(r', D) × α(r' → R)
```
Normalize/clamp to 0..1.

**Contagion examples:**
- For Europe, contagion comes from Middle East + Black Sea
- For Black Sea, contagion comes from Europe + Russia/Ukraine region
- For Middle East, contagion comes from global sanctions regime / Red Sea shipping

---

## 16. Derived Indices Catalog

### 16.1 Europe Indices

#### Europe Energy Risk Index (EERI)

**Purpose:** "How exposed is Europe to energy disruption risk today?"

**Theme filters:**
- Categories: `ENERGY`, `SUPPLY_DISRUPTION`, `SANCTIONS`, `WAR/MILITARY`
- Assets: gas, power, oil, lng, freight, fx

**Formula (v1):**
```
EERI = 100 × clamp(
    0.45 × RERI_hat(EU) +
    0.25 × ThemePressure_hat(EU, Energy) +
    0.20 × AssetTransmission_hat(EU, Energy) +
    0.10 × Contagion(EU)
)
```

**Neighbors for contagion:** Middle East (0.6), Black Sea (0.4)

---

#### Europe Gas Stress Index (EGSI)

**Purpose:** Traders + utilities + storage planners

**Theme filters:**
- Events mentioning: LNG, pipeline, storage, sanctions on gas, outages
- Assets: gas, lng, power (power included because gas → power)

**Formula (v1):**
```
EGSI = 100 × clamp(
    0.35 × RERI_hat(EU) +
    0.35 × ThemePressure_hat(EU, Gas) +
    0.20 × AssetTransmission_hat(EU, Gas) +
    0.10 × ChokepointFactor(EU, Gas)
)
```

**Chokepoints:** LNG terminals, major pipelines, key interconnectors

---

#### Europe Sanctions & Policy Shock Index (ESPSI)

**Purpose:** Banks, compliance, corporates

**Theme filters:**
- Categories: `SANCTIONS`, `POLITICAL`, `REGULATORY`, plus "EU embargo" entities
- Assets: fx, freight, oil, gas

**Formula (v1):**
```
ESPSI = 100 × clamp(
    0.30 × RERI_hat(EU) +
    0.50 × ThemePressure_hat(EU, Sanctions) +
    0.20 × AssetTransmission_hat(EU, Sanctions)
)
```

---

### 16.2 Middle East Indices

#### Middle East Escalation Index (MEEI)

This is RERI Middle East branded product:
```
MEEI = RERI(ME)
```
(Can add velocity/cluster boost later, keep v1 clean)

---

#### Middle East Oil Supply Risk Index (MOSRI)

**Purpose:** Oil traders, O&G, insurers

**Theme filters:**
- Categories: `ENERGY`, `WAR/MILITARY`, `SUPPLY_DISRUPTION`, `SANCTIONS`
- Assets: oil, freight, fx

**Formula (v1):**
```
MOSRI = 100 × clamp(
    0.40 × RERI_hat(ME) +
    0.30 × ThemePressure_hat(ME, Oil) +
    0.20 × AssetTransmission_hat(ME, Oil) +
    0.10 × ChokepointFactor(ME, Oil)
)
```

**Chokepoints:** Hormuz, Persian Gulf ports, key export terminals, pipelines

---

#### Middle East LNG Disruption Index (MELDI)

**Purpose:** LNG desks, Europe supply planners

**Theme filters:**
- LNG facilities, export outages, shipping threats, sanctions
- Assets: lng, gas, freight

**Formula (v1):**
```
MELDI = 100 × clamp(
    0.30 × RERI_hat(ME) +
    0.35 × ThemePressure_hat(ME, LNG) +
    0.25 × AssetTransmission_hat(ME, LNG) +
    0.10 × ChokepointFactor(ME, LNG)
)
```

---

#### Hormuz & Persian Gulf Chokepoint Index (HPCI)

Premium "corridor index" — chokepoint-dominant:

**Formula (v1):**
```
HPCI = 100 × clamp(
    0.20 × RERI_hat(ME) +
    0.55 × ChokepointFactor_hat(ME, Hormuz) +
    0.15 × ThemePressure_hat(ME, ShippingThreat) +
    0.10 × AssetTransmission_hat(ME, Freight)
)
```

---

### 16.3 Black Sea Indices

#### Black Sea Conflict Risk Index (BCRI)

**Purpose:** Insurers, shipping, grain/supply chain

**Theme filters:**
- Categories: `WAR/MILITARY`, `STRIKES`, `SANCTIONS`, `SUPPLY_DISRUPTION`
- Assets: freight, oil, fx (optionally grain later)

**Formula (v1):**
```
BCRI = 100 × clamp(
    0.55 × RERI_hat(BS) +
    0.25 × ThemePressure_hat(BS, Conflict) +
    0.10 × ChokepointFactor(BS, Ports) +
    0.10 × Contagion(BS)
)
```

**Neighbors:** Europe (0.5), Middle East (0.2), "Ukraine region" (0.3)

---

#### Black Sea Shipping Disruption Index (BSSDI)

**One of the most sellable niche feeds.**

**Theme filters:**
- Port closures, attacks, mine threats, insurance rate spikes, rerouting
- Assets: freight, oil (freight dominates)

**Formula (v1):**
```
BSSDI = 100 × clamp(
    0.25 × RERI_hat(BS) +
    0.25 × ThemePressure_hat(BS, Shipping) +
    0.35 × ChokepointFactor_hat(BS, Ports) +
    0.15 × AssetTransmission_hat(BS, Freight)
)
```

---

#### Black Sea Energy Corridor Risk Index (BSECRI)

**Theme filters:**
- Pipeline/corridor incidents, sanctions impacting flows, infrastructure attacks
- Assets: oil, gas, freight

**Formula (v1):**
```
BSECRI = 100 × clamp(
    0.35 × RERI_hat(BS) +
    0.35 × ThemePressure_hat(BS, EnergyCorridor) +
    0.20 × ChokepointFactor_hat(BS, Corridors) +
    0.10 × AssetTransmission_hat(BS, Energy)
)
```

---

## 17. Enterprise-Grade Implementation Notes

### 17.1 Make Every Derived Index Deterministic
- No LLM calls inside the compute step
- AI only supplies tags/scores upstream

### 17.2 Use Caps + Versioning Early
- Caps prevent wild values before you have 6–12 months history
- Store `index_version` in the synthetic alert `raw_input`

### 17.3 Store Explainability

In each derived index synthetic alert `raw_input`, include:
- `top_driver_event_ids`
- `top_driver_headlines`
- `components_used` (ThemePressure, AssetTransmission, Chokepoint, Contagion)

This makes enterprise audits easy.

### 17.4 Keep Public Output as a Teaser

| Tier | What They Get |
|------|---------------|
| Public | value + band + trend + 2–3 drivers |
| Paid | history + charts |
| Enterprise | feeds + components |

---

## 18. Recommended First Implementation (Minimal, High ROI)

Start with exactly 3 derived indices (fast to ship, high commercial value):

1. **Europe Energy Risk Index (EERI)**
2. **Middle East Oil Supply Risk Index (MOSRI)** (or MEEI if simpler)
3. **Black Sea Shipping Disruption Index (BSSDI)**

These three cover:
- Energy planning (Europe)
- Oil supply shock (Middle East)
- Logistics/insurance niche (Black Sea)

They're also very SEO-friendly as named pages.

---

---

## 19. Strategic Implementation Decisions (January 2026)

This section documents all strategic decisions made before RERI/EERI development.

### 19.1 Data Source Decisions

| Question | Decision | Rationale |
|----------|----------|-----------|
| **Region Format** | Normalize to canonical set: `europe`, `middle-east`, `black-sea` | Fixed vocabulary enables clean filtering, indexing, and joins |
| **Category Extraction** | Extract from `body` text (not stored column) | `category` column not populated; parse `Category: X` from alert body |
| **Confidence Source** | Use `confidence` column from `alert_events` | Column is populated in production |

### 19.2 Architecture Decisions

| Question | Decision | Rationale |
|----------|----------|-----------|
| **Contagion Component** | **Option B:** Start without contagion | First build stable single-region RERI (Europe), add contagion after Middle East and Black Sea RERIs exist |
| **Storage Table** | Separate `reri_indices_daily` table | RERI-specific columns (region, theme, components) differ from GERI structure |
| **Normalization** | Fallback caps (days 1-14), rolling normalization (days 30-90+) | Preserves methodological integrity, no artificial history |
| **Compute Frequency** | Daily v1, intraday-ready architecture | Design for future intraday but only enable daily official values initially |
| **Feature Flag** | `ENABLE_EERI` (similar to `ENABLE_GERI`) | Controlled rollout, silent production testing, staged activation |

### 19.3 EERI v1 Formula (Without Contagion)

Since `Contagion_EU_norm = 0` in v1, the effective formula is:

```
EERI_v1 = 100 * clamp(
    0.50 * ( RERI_EU / 100 ) +
    0.28 * ThemePressure_EU_Energy_norm +
    0.22 * AssetTransmission_EU_Energy_norm
)
```

Weight redistribution from original:
- `RERI_EU`: 0.45 → 0.50 (+0.05)
- `ThemePressure`: 0.25 → 0.28 (+0.03)
- `AssetTransmission`: 0.20 → 0.22 (+0.02)
- `Contagion`: 0.10 → 0.00 (disabled)

### 19.4 Canonical Regions (Tier 1 Focus)

| Region ID | Display Name | Type | Priority |
|-----------|--------------|------|----------|
| `europe` | Europe | energy | v1 (EERI) |
| `middle-east` | Middle East | conflict/energy | v2 |
| `black-sea` | Black Sea | shipping/conflict | v2 |

### 19.5 Category Weights for RERI

Extracted from alert body text using regex pattern `Category:\s*(\w+)`:

| Category | Weight | Multiplier for ThemePressure |
|----------|--------|------------------------------|
| `war`, `military`, `strike` | 1.6 | High escalation signal |
| `supply_disruption` | 1.5 | Direct market impact |
| `energy` | 1.3 | Core domain |
| `sanctions` | 1.3 | Policy shock |
| `political` | 1.0 | Baseline |
| `diplomacy` | 0.7 | Lower urgency |
| `unknown` (default) | 1.0 | Conservative fallback |

### 19.6 Module Structure

```
src/reri/
├── __init__.py           # Module exports
├── types.py              # RERIResult, EERIComponents, constants
├── compute.py            # Pure compute functions
├── normalize.py          # Rolling normalization logic
├── repo.py               # Database operations
├── service.py            # Orchestration layer
├── routes.py             # API endpoints (future)
└── tests/
    └── test_compute.py   # Unit tests
```

### 19.7 Database Schema

**Table: `reri_indices_daily`**

```sql
CREATE TABLE reri_indices_daily (
    id SERIAL PRIMARY KEY,
    index_id TEXT NOT NULL,           -- "europe:eeri", "middle-east:reri"
    region_id TEXT NOT NULL,          -- "europe", "middle-east", "black-sea"
    date DATE NOT NULL,
    value INTEGER NOT NULL,           -- 0-100 index value
    band TEXT NOT NULL,               -- LOW|MODERATE|ELEVATED|CRITICAL
    trend_1d INTEGER,                 -- Change vs yesterday
    trend_7d INTEGER,                 -- Change vs 7-day avg
    components JSONB NOT NULL,        -- Raw component values
    drivers JSONB,                    -- Top 3-5 driver headlines
    model_version TEXT NOT NULL,      -- "eeri_v1", "reri_v1"
    computed_at TIMESTAMP NOT NULL,
    UNIQUE(index_id, date)
);

CREATE INDEX idx_reri_lookup ON reri_indices_daily(index_id, date DESC);
CREATE INDEX idx_reri_region ON reri_indices_daily(region_id, date DESC);
```

**Table: `reri_canonical_regions`**

```sql
CREATE TABLE reri_canonical_regions (
    region_id TEXT PRIMARY KEY,       -- "europe"
    region_name TEXT NOT NULL,        -- "Europe"
    region_type TEXT NOT NULL,        -- "energy", "conflict", "shipping"
    aliases TEXT[] NOT NULL,          -- ["EU", "European", "Western Europe"]
    core_assets TEXT[],               -- ["gas", "oil", "power", "fx"]
    is_active BOOLEAN DEFAULT TRUE
);
```

### 19.8 Implementation Phases

| Phase | Scope | Duration | Deliverable |
|-------|-------|----------|-------------|
| **Phase 1** | EERI v1 (Europe only, no contagion) | 1-2 weeks | Working EERI with daily computation |
| **Phase 2** | RERI Middle East + Black Sea | 2 weeks | All 3 base RERIs |
| **Phase 3** | Contagion component | 1 week | Cross-regional spillover |
| **Phase 4** | Additional derived indices | Ongoing | EGSI, MOSRI, BSSDI |

### 19.9 Feature Flag Configuration

```python
# Environment variable
ENABLE_EERI = os.getenv("ENABLE_EERI", "false").lower() == "true"

# Behavior when disabled:
# - Compute engine does not run
# - API returns 503 or empty results
# - No entries written to reri_indices_daily
```

---

## 20. EU Gas Storage Data Integration (EGSI)

> **See also:** [EGSI.md](./EGSI.md) for the full EGSI (EU Gas Storage Index) documentation.

This section documents the data sources for EU gas storage monitoring, which provides key inputs for EERI and energy risk assessment.

### 20.1 Data Inputs Required

EERI and energy risk alerts require three core storage metrics:

| Metric | Description | Source |
|--------|-------------|--------|
| **EU Gas Storage Level** | Current storage as % of capacity vs seasonal norm | GIE AGSI+ API |
| **Refill Speed** | 7-day average injection/withdrawal rate (TWh/day) | GIE AGSI+ API |
| **Winter Deviation Risk** | Current level vs target trajectory for winter security | Computed |

### 20.2 Primary Data Source: GIE AGSI+ API

**GIE AGSI+ (Aggregated Gas Storage Inventory)** is the official EU gas storage transparency platform.

| Property | Value |
|----------|-------|
| **URL** | https://agsi.gie.eu/ |
| **API Docs** | https://www.gie.eu/transparency-platform/GIE_API_documentation_v007.pdf |
| **Update Frequency** | Twice daily (19:30 CET and 23:00 CET) |
| **Coverage** | 18 EU Member States |
| **Historical Data** | From 2011 onwards |
| **Access** | Free (API key required) |

**API Key Setup:**
1. Register at https://agsi.gie.eu/account
2. Receive personal API key via email
3. Set environment variable: `GIE_API_KEY=your_key_here`

**Module Location:** `src/ingest/gie_agsi.py`

### 20.3 RSS Feeds for News/Analysis

Four high-quality RSS feeds added for European gas storage news:

| Source | URL | Focus | Weight |
|--------|-----|-------|--------|
| **ICIS Energy News** | `https://icisenergynews.podomatic.com/rss2.xml` | European gas markets, LNG, storage analysis | 0.9 |
| **EU Energy Commission** | `https://energy.ec.europa.eu/news_en/rss.xml` | EU policy, storage regulations | 0.9 |
| **Energy Intelligence** | `https://www.energyintel.com/rss-feed` | European energy policy analysis | 0.85 |
| **Oil & Gas Journal** | `https://www.ogj.com/rss` | Gas infrastructure, storage, LNG | 0.8 |

**Config Location:** `src/config/feeds.json`

### 20.4 Seasonal Norms Reference

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

### 20.5 Risk Score Computation

The storage risk score (0-100) is computed from:

```
Risk Score = 
    (100 - storage_percent) × 0.5     # Base: lower storage = higher risk
  + deviation_penalty                  # Negative deviation from norm
  + seasonal_factor                    # Winter months add +15
  + flow_factor                        # High withdrawals add +5-10
```

**Risk Bands:**
| Score | Band | Meaning |
|-------|------|---------|
| 0-25 | LOW | Normal storage conditions |
| 26-50 | MODERATE | Monitor refill progress |
| 51-75 | ELEVATED | Supply concerns, hedging advised |
| 76-100 | CRITICAL | Winter security at risk |

### 20.6 Alert Generation

Storage alerts are generated when:
- `risk_score >= 40` OR
- `winter_deviation_risk` is ELEVATED/CRITICAL

Alert types:
- **STORAGE_DEVIATION**: Storage significantly below seasonal norm
- **WINTER_RISK**: Winter supply security concerns
- **STORAGE_LEVEL**: General low storage alert

### 20.7 Integration with Alerts Pipeline

> **Status:** Fully integrated into the alerts engine v2 (Phase A).

Gas storage metrics are checked during every alerts engine run and feed into the pipeline as `ASSET_RISK_SPIKE` events for the `gas` asset.

**Integration architecture:**

```
Alerts Engine v2 (Phase A)
    ├── generate_regional_risk_spike_events()
    ├── generate_asset_risk_spike_events()
    ├── generate_high_impact_event_alerts()
    └── generate_storage_risk_events()  ◄── NEW
            │
            ├── Fetch from GIE AGSI+ API
            ├── Compute risk metrics
            ├── Persist to gas_storage_snapshots table
            └── Create ASSET_RISK_SPIKE alert if warranted
```

**Behavior:**
- Daily storage snapshot persisted to `gas_storage_snapshots` table
- If `risk_score >= 40` or `winter_deviation_risk` is ELEVATED/CRITICAL, an alert is generated
- Alert type: `ASSET_RISK_SPIKE` with `scope_assets = ['gas']`, `scope_region = 'Europe'`
- Storage alerts contribute to EERI via AssetTransmission weight

**Database table:** `gas_storage_snapshots`
- Stores daily EU storage metrics with risk scores
- Unique constraint on date (one snapshot per day)
- Indexed for efficient date-based queries

**Note:** RSS feeds with `tags` field are ingested but tag filtering is not yet implemented in the ingestion pipeline.

### 20.8 Usage

**Fetch current metrics:**
```python
from src.ingest.gie_agsi import run_storage_check

alert = run_storage_check()
if alert:
    # Store in alert_events or trigger delivery
    print(f"Alert: {alert['headline']}")
```

**Fetch raw data:**
```python
from src.ingest.gie_agsi import fetch_eu_storage_data, fetch_historical_storage

current = fetch_eu_storage_data()
history = fetch_historical_storage(days=7)
```

---

## Related Documents

- [EGSI Documentation](./EGSI.md) - EU Gas Storage Index (GIE AGSI+ integration)
- [Indices Bible](./indices-bible.md) - Overall index strategy and access tiers

---

*Last updated: January 2026*
