# EERI Weekly Snapshot — Public Section Design

## Overview

The EERI Weekly Snapshot is a public-facing section embedded on the `/eeri` page that provides weekly context for European energy risk. It sits between the Risk Level Bands section and the Daily Intelligence Narrative, answering the natural follow-up question: "Is this unusual or part of a broader pattern?"

## Strategic Value

- **Habit Formation:** Sunday reading ritual for analysts
- **Brand Authority:** Institutional-grade weekly intelligence
- **SEO Benefit:** Fresh structured content every week
- **Conversion Funnel:** Natural progression to Pro subscription
- **Social Sharing:** Divergence insights are highly shareable

---

## Placement (EXACT)

```
Risk Level Bands
↓
👉 INSERT WEEKLY SNAPSHOT HERE
↓
Daily Intelligence Narrative
```

### Why This Placement Is Ideal

The current flow explains:
1. What the index is today
2. Why it is high (drivers)
3. Where pressure exists (regions/assets)
4. What the bands mean

The user naturally asks next: "Is this unusual or part of a broader pattern?"
That is EXACTLY what Weekly Snapshot answers.

---

## Core Philosophy

The Weekly Snapshot must feel:
- Narrative
- Interpreted
- Calm
- Institutional

NOT:
- Analytical overload
- Data dump
- Trading dashboard

**Emotional Outcome:** After reading, user should feel: "I understand what kind of week this was."

---

## Data Sources (Production Database)

| Data | Table | Key Column |
|------|-------|-----------|
| EERI Values | `reri_indices_daily` (index_id = 'europe:eeri') | `value`, `band`, `trend_7d` |
| Brent Oil | `oil_price_snapshots` | `brent_price` |
| TTF Gas | `ttf_gas_snapshots` | `ttf_price` |
| EU Gas Storage | `gas_storage_snapshots` | `eu_storage_percent` |
| VIX | `vix_snapshots` | `vix_close` |
| EUR/USD | `eurusd_snapshots` | `rate` |

### Week Definition
- Monday through Sunday (ISO week)
- Data computed for the most recently completed week
- Refreshed after Sunday data becomes available

---

## Block Structure (7 Blocks)

### Block 1 — Weekly Risk Overview (Dark Card)

**Purpose:** Answers "Was this a shock week or a persistent stress week?"

**Display:**
- Weekly Average EERI
- Weekly High / Low (with day labels)
- Weekly Trend vs Prior Week (Rising/Falling/Stable)
- Weekly Risk Band

**Example:**
```
⚡ Weekly EERI Overview
Week: Jan 27 – Feb 2, 2026

Average Risk: 91 (CRITICAL)
High: 96 (Wed)
Low: 78 (Mon)
Trend vs Prior Week: ↑ Rising
```

**Interpretation Narrative (generated):**
> Risk remained elevated throughout the week, with escalation mid-week pushing EERI into Critical territory. Risk persistence suggests structural pressure rather than isolated events.

---

### Block 2 — Weekly Risk Regime Distribution (Light Panel)

**Purpose:** Answers "How stable or unstable was the risk environment?"

**Display:**
- Simple badges showing days in each band
- Color-coded visual bars

**Example:**
```
CRITICAL → 6 days
ELEVATED → 1 day
```

**Interpretation Logic:**
- Many band switches → unstable environment
- Same band all week → entrenched regime

---

### Block 3 — Cross-Asset Confirmation Panel (Core Insight)

**Purpose:** Answers "Did markets believe the risk?" — Most valuable public block.

**Layout:** Card grid or table

| Asset | Weekly Move | Risk Alignment | Historical Context |
|-------|-------------|---------------|-------------------|
| TTF Gas | +8.4% | ✅ Confirming | Gas markets strengthened alongside elevated risk |
| Brent Oil | +1.2% | 🟡 Neutral | Oil moved modestly, mixed interpretation |
| VIX | +6.0% | ✅ Confirming | Broader risk sentiment reacted to energy stress |
| EUR/USD | −1.3% | ✅ Confirming | Currency markets reflect European risk premium |
| EU Gas Storage | −0.8% | ✅ Confirming | Accelerated withdrawal validates supply concern |

**Risk Alignment Labels (3 options only):**
- ✅ Confirming
- 🟡 Neutral
- ⚠ Diverging

**Alignment Logic:**
- EERI high/rising + asset moves in risk-confirming direction → Confirming
- EERI high/rising + asset flat or mixed → Neutral
- EERI high/rising + asset moves against risk direction → Diverging

**Asset-Specific Risk Alignment Rules:**
- **TTF Gas:** Price UP when EERI UP = Confirming (supply stress = higher prices)
- **Brent Oil:** Price UP when EERI UP = Confirming (energy stress = higher prices)
- **VIX:** VIX UP when EERI UP = Confirming (risk sentiment alignment)
- **EUR/USD:** EUR DOWN when EERI UP = Confirming (European stress = weaker EUR)
- **EU Storage:** Storage DOWN/faster withdrawal when EERI UP = Confirming

---

### Block 4 — Mini Weekly Overlay Charts (Compact Row)

**Purpose:** Answers "How quickly did markets react to risk?"

**5 Charts:**
1. EERI vs Brent
2. EERI vs TTF
3. EERI vs Gas Storage
4. EERI vs VIX
5. EERI vs EUR/USD

**Chart Specifications:**
- X-axis: Mon → Sun timeline
- Y-axis: Indexed performance (start = 100)
- Two lines: EERI (blue) + Asset (asset-specific color)
- Small, compact size
- No analytics overlays
- Simple dual-line design
- Chart.js lightweight implementation

**What Users Learn Visually:**
- Lag patterns
- Overreaction
- Divergence

---

### Block 5 — Divergence Watch Badge (Signature Insight)

**Purpose:** Answers "Are markets underpricing or validating risk?"

**Display:** Single prominent badge with one of three states:

| State | Badge |
|-------|-------|
| All confirming | ✅ Markets Confirming Risk |
| Mixed results | 🟡 Markets Mixed |
| Mostly diverging | ⚠ Markets Diverging From Risk |

**Logic:**
- Count confirming vs diverging vs neutral
- 4-5 confirming → "Confirming"
- 2-3 confirming → "Mixed"
- 0-1 confirming → "Diverging"

**Example Output:**
> 🟡 Markets Mixed — Gas and volatility indicators confirmed elevated risk, while oil markets showed partial divergence.

---

### Block 6 — Historical Context Box (Light Panel)

**Purpose:** Provides credibility without revealing methodology.

**Display:**
> Historically, weeks where EERI spends multiple days in [BAND] territory are associated with:
> • Increased gas price volatility
> • Elevated freight disruption probability
> • Broader risk sentiment spillovers

**Band-Specific Context Templates:**

**CRITICAL (81-100):**
- Significant gas price volatility often follows
- Freight and logistics disruption probability elevated
- European FX markets typically show stress
- Cross-market risk sentiment tends to remain elevated

**ELEVATED/SEVERE (41-80):**
- Gas markets may show directional uncertainty
- Oil markets often display mixed signals
- Risk sentiment tends toward gradual normalization
- Supply-chain indicators warrant close monitoring

**LOW/MODERATE (0-40):**
- Markets typically operate within normal ranges
- Gas price volatility remains subdued
- Risk sentiment broadly stable
- Seasonal patterns dominate over geopolitical signals

---

### Block 7 — Next Week Historical Tendencies Panel

**Purpose:** Answers "What typically follows weeks like this?" (NOT a prediction)

**Title:** Next Week Historical Tendencies (Not Forecasts)

**Display:**

| Asset | Historical Tendency | Confidence |
|-------|-------------------|------------|
| TTF Gas | 60-70% probability of continued volatility | Medium |
| Brent Oil | Mixed directional bias | Low |
| VIX | 55-65% probability of elevated levels | Medium |
| EUR/USD | 55-65% probability of weaker EUR | Medium |
| EU Gas Storage | 55-65% probability of accelerated draws | Medium |

**Band-Based Tendency Logic:**

**After CRITICAL weeks:**
- TTF: 60-70% continued volatility (Medium confidence)
- Brent: 45-55% mixed (Low confidence)
- VIX: 55-65% elevated (Medium confidence)
- EUR/USD: 55-65% weaker EUR (Medium confidence)
- Storage: 55-65% accelerated draws (Medium confidence)

**After ELEVATED/SEVERE weeks:**
- TTF: 50-60% moderate volatility (Medium confidence)
- Brent: 45-55% mixed (Low confidence)
- VIX: 45-55% normalizing (Low confidence)
- EUR/USD: 50-55% stable (Low confidence)
- Storage: 50-60% seasonal norms (Medium confidence)

**After LOW/MODERATE weeks:**
- TTF: 40-50% stable (Low confidence)
- Brent: 45-55% stable (Low confidence)
- VIX: 40-50% stable (Low confidence)
- EUR/USD: 45-55% stable (Low confidence)
- Storage: 50-60% seasonal norms (Medium confidence)

---

## Visual Styling

| Element | Style |
|---------|-------|
| Overview Card | Dark gradient (matches main index card) |
| Asset Panel | Dark chips + labels |
| Context / Narrative | Light card |
| Probability Panel | Light but bordered |
| Charts | Small, indexed, dual-line |

---

## UX Psychology Flow

User journey with Weekly Snapshot:

1. See today's crisis (EERI value)
2. Understand drivers
3. Understand assets affected
4. Understand risk band
5. **Understand weekly context** ← NEW
6. Read daily narrative
7. Convert to Pro

---

## What MUST Remain Pro Only

Do NOT include in public Weekly Snapshot:
- Driver severity scores
- Component contributions
- Transmission math
- Correlation metrics
- Full historical comparisons
- Multi-week analog analysis

**Public = trust + education | Pro = edge**

---

## SEO Benefits

Every week this section provides:
- Fresh crawlable content
- Expanded keyword footprint (asset names, market terms)
- Added narrative text (long-form structured)
- Improved dwell time
- Signals site authority to Google

---

## API Endpoint

`GET /api/v1/eeri/weekly-snapshot`

Returns JSON with all 7 blocks of data computed from production database.

Response structure:
```json
{
  "week_start": "2026-01-27",
  "week_end": "2026-02-02",
  "overview": {
    "average": 91,
    "high": { "value": 96, "day": "Wed" },
    "low": { "value": 78, "day": "Mon" },
    "trend_vs_prior": "rising",
    "dominant_band": "CRITICAL"
  },
  "regime_distribution": {
    "CRITICAL": 6,
    "ELEVATED": 1
  },
  "cross_asset": [
    {
      "asset": "TTF Gas",
      "weekly_move_pct": 8.4,
      "alignment": "confirming",
      "context": "Gas markets strengthened alongside elevated risk"
    }
  ],
  "chart_data": { ... },
  "divergence_status": "mixed",
  "divergence_narrative": "...",
  "historical_context": "...",
  "tendencies": [ ... ]
}
```

---

## Implementation Notes

- Weekly snapshot data is computed server-side from the most recently completed week
- All market data sourced from production database tables
- Charts rendered client-side with Chart.js (inline, lightweight)
- Section is server-rendered HTML (no client-side API calls for SEO)
- Week boundary: Monday 00:00 UTC to Sunday 23:59 UTC
- If insufficient data for a complete week, display "Weekly snapshot will be available after the first complete week of data"
