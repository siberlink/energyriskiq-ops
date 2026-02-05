# Daily Geo-Energy Intelligence Digest

## Overview

The Daily Geo-Energy Intelligence Digest is an AI-powered daily briefing that synthesizes alert data into actionable intelligence for energy market participants. Unlike traditional news aggregation, the digest interprets systemic risk, connects alerts together, translates risk into asset impact, and highlights trend direction.

**Core Question Answered:**
> "What changed in global energy risk in the last 24 hours — and why does it matter?"

---

## Publishing Schedule

**Target Time:** 07:30 – 09:00 CET

This timing is strategically chosen for:
- Market preparation window for EU traders
- Overlap with Asia market close
- Coverage of US overnight developments

---

## Digest Structure

### Section 1: Executive Risk Snapshot

A concise, high-authority summary for quick consumption.

**Format:**
```
GLOBAL GEO-ENERGY RISK SNAPSHOT
Date: {Today}
Based on Alerts from: {Yesterday}

Global Risk Tone:
🟢 Stabilizing | 🟡 Elevated | 🔴 Escalating

Key Drivers:
• {Driver 1}
• {Driver 2}
• {Driver 3}

Net Systemic Impact:
{2–3 sentence AI interpretation}
```

**AI Tasks:**
- Cluster alerts into themes
- Determine trend direction
- Detect cross-region contagion
- Summarize systemic meaning

**Example Output:**
> Global risk remained elevated but stabilized, with supply-side concerns in Europe partially offset by improved LNG flow expectations. Freight volatility continues to signal hidden stress in supply routing.

---

### Section 2: Index Movement Summary

Proprietary index analysis that differentiates the digest from generic news.

**Indices Covered:**
- GERI (Global Energy Risk Index)
- EERI (Europe Energy Risk Index)
- EGSI (Europe Gas Stress Index)
- RERI (Regional Escalation Risk Index)

**Format:**
```
INDEX MOVEMENTS (24h)

GERI:
Current: {value} ({change})
Trend: Rising | Falling | Stable
Interpretation: {AI explanation}

EERI:
Current: {value} ({change})
Driver: {primary driver}

RERI – {Region}:
Current: {value} ({change})
Driver: {regional driver}
```

**AI Tasks:**
- Connect index movements to specific alerts
- Explain WHY each index moved (not just the numbers)
- Identify primary drivers for each movement

---

### Section 3: Top Risk Events of the Day

Curated selection of the most systemically significant alerts.

**Selection Criteria:**
- Limit to top 3–5 alerts
- Prioritize by systemic impact, not recency
- Focus on cross-market implications

**Format:**
```
1️⃣ {Alert Title}

Region: {region}
Category: {category}
Risk Severity: {severity}
Confidence Level: {confidence}

Why It Matters:
{AI interpretation of significance}

Possible Spillover:
{Affected assets / regions}
```

**Value Proposition:**
Transforms raw alerts into analyst-quality commentary.

---

### Section 4: Cross-Market Impact Map

Unique analysis connecting alerts to asset class implications.

**Format:**
```
LIKELY MARKET IMPACT

Oil:
{↑/↓/→} {Impact description}

Natural Gas:
{↑/↓/→} {Impact description}

Freight:
{↑/↓/→} {Impact description}

FX:
{↑/↓/→} {Impact description}

Power:
{↑/↓/→} {Impact description}
```

**Asset Classes:**
- Oil (Brent, WTI)
- Natural Gas (TTF, LNG)
- Freight (shipping, logistics)
- FX (USD, EUR)
- Power (European electricity)

**Implementation Note:**
Uses alert → asset sensitivity weights from existing architecture.

---

### Section 5: Risk Trend Context

Historical intelligence that builds cumulative value.

**Format:**
```
RISK TREND CONTEXT

Last 7 Days:
{Trend summary with primary drivers}

Last 30 Days:
{Broader pattern analysis}

Regime Status:
{Current risk regime classification}
```

**AI Tasks:**
- Compare yesterday vs rolling baseline
- Detect regime shifts
- Identify trend inflection points

---

### Section 6: Forward Risk Watchlist

Predictive intelligence for the next 48-72 hours.

**Format:**
```
WATCH LIST (Next 48-72h)

• {Event/indicator to monitor}
• {Event/indicator to monitor}
• {Event/indicator to monitor}
```

**Content Types:**
- Scheduled data releases (storage reports, production data)
- Geopolitical events (meetings, negotiations)
- Market events (contract expirations, auctions)
- Infrastructure developments (maintenance, capacity changes)

**Value Proposition:**
Makes digest forward-looking and actionable for traders.

---

### Section 7: Strategic Interpretation

Human-like AI commentary representing EnergyRiskIQ's analytical voice.

**Format:**
```
EnergyRiskIQ Analyst Note:

{3-4 sentence strategic interpretation connecting current signals
to broader market implications and historical patterns}
```

**Example:**
> Current risk environment suggests localized escalation rather than global systemic shock. However, freight and gas indicators show early stress signals that historically precede oil market repricing.

---

## AI Generation Architecture

### Step 1: Data Pull

Query alerts from previous day:
```sql
SELECT *
FROM alert_events
WHERE created_at >= {yesterday_start}
  AND created_at < {today_start}
ORDER BY risk_score DESC
```

Include fields:
- severity
- confidence
- region
- category
- asset_impact
- risk_score

### Step 2: Alert Clustering

AI groups alerts into thematic clusters:
- EU supply stress
- Middle East geopolitical
- Logistics disruptions
- Production changes
- Demand signals

### Step 3: Risk Signal Calculation

Compute aggregate metrics:
- Alert density (count by region/category)
- Weighted severity (severity × confidence)
- Regional concentration (Herfindahl index)
- Asset exposure distribution

### Step 4: Narrative Generation

System prompt framework:
```
You are EnergyRiskIQ Intelligence Engine.
Interpret systemic geo-energy risk using provided alerts.
Avoid news repetition.
Focus on risk meaning and market impact.
Use professional, analytical tone.
```

---

## Output Formats

### Web Article
- SEO-optimized for organic discovery
- Published to `/digest/{date}` or `/intelligence/{date}`
- Includes structured data for search engines

### Email Newsletter
- Sent to subscribed users based on plan tier
- Formatted for email clients
- Links back to full web version

### Social Media Summary
- Short teaser content for Twitter/LinkedIn
- Highlights key risk tone and top driver
- Drives traffic to full digest

### Pro Dashboard Module
- Real-time access in user account
- Interactive elements
- Historical archive

---

## Access Tiers

### Free Users
- Executive snapshot only
- 2 alerts with commentary
- 24-hour delay on full digest

### Pro Users
- Full digest access
- Market impact analysis
- Forward watchlist
- Historical trend section
- Real-time access

### Enterprise (Future)
- Custom sector digests
- API feed access
- Early release (before market open)
- White-label options

---

## Advanced Features (Roadmap)

### AI Contagion Detection
Detect when unrelated alerts combine to form systemic risk patterns.

### Sentiment Momentum Tracking
Track whether risk is accelerating or fading based on alert velocity and severity trends.

### Regime Classification
Automatically classify current risk environment:
- Supply Shock
- Demand Shock
- Geopolitical Shock
- Logistics Shock
- Mixed/Transition

---

## Strategic Value

### Historical Intelligence Dataset
Each daily digest builds a structured dataset enabling:
- Backtesting of risk signals vs market movements
- Academic research partnerships
- Hedge fund marketing materials
- Data licensing opportunities

### Differentiation
Unlike news aggregators, the digest provides:
- Interpretation over repetition
- Forward-looking analysis
- Quantitative index integration
- Asset class translation

---

## Branding Options

Potential names for the digest:
- EnergyRiskIQ Morning Brief
- Global Energy Risk Intelligence Report
- Geo-Energy Risk Daily
- Risk Pulse Digest
- EnergyRiskIQ Intelligence Brief

---

## Implementation Status

| Component | Status | Notes |
|-----------|--------|-------|
| Alert data pipeline | Active | Feeds from `alert_events` table |
| Index integration | Active | GERI, EERI, EGSI available |
| AI generation | Planned | Requires prompt engineering |
| Web publishing | Planned | SEO route structure needed |
| Email delivery | Planned | Uses existing email infrastructure |
| Tier gating | Planned | Integrate with plan_settings |

---

## Related Documentation

- [Email Sending](./email-sending.md) - Email delivery infrastructure
- [GERI Specification](./geri.md) - Global Energy Risk Index
- [EERI Development](./eeri-development.md) - Europe Energy Risk Index
- [EGSI Specification](./EGSI.md) - Europe Gas Stress Index

---

## Tier-Based Feature Architecture

The Daily Digest is designed as a progressively deeper decision-intelligence tool. Each tier escalates from awareness to institutional-grade analytics:

**Tier Philosophy:**
- **Awareness** → **Insight** → **Trading Edge** → **Institutional Intelligence** → **Strategic Risk Infrastructure**

**Pricing Psychology:**
- $9.95 = Knowledge
- $29 = Trading edge
- $49 = Professional intelligence
- $129 = Business intelligence infrastructure

---

### FREE USER PLAN

**Purpose:** Lead generation, brand authority, SEO, funnel entry

Creates curiosity and trust without replacing paid plans.

**Features:**
- **Executive Risk Snapshot**
  - Global risk tone
  - 2-3 key drivers
  - 1 short interpretation paragraph
- **Limited Alert Commentary**
  - Top 1-2 alerts only
  - Very high-level explanation
  - No asset breakdown
- **Public Index Direction**
  - GERI movement only
  - Direction + daily change
  - No advanced context
- **24h Delay**
  - Free users should always feel slightly behind
- **Public Watchlist (Short)**
  - 1-2 forward signals
  - No probability scoring

**Not Included:**
- Historical comparisons
- Asset impact tables
- Regional deep analysis
- Data exports
- Custom alerts
- Index components
- Trend analytics

**Goal:** Make users think: *"This is impressive… but I need more detail."*

---

### PERSONAL PLAN — $9.95/month

**Purpose:** Serious enthusiasts + early professionals

Introduces personal intelligence and interpretation depth.

**Features (everything from FREE plus):**
- **Full Daily Digest Access**
  - All sections unlocked
  - Full alert commentary (Top 3-5)
- **Multi-Index Summary**
  - GERI
  - EERI
  - RERI regional highlights
  - EGSI summary
- **7-Day Risk Trend Context**
  - Short rolling trend analysis
  - Early pattern recognition
- **Basic Asset Impact Overview**
  - Directional impacts only: Oil ↑/↓, Gas ↑/↓, Freight ↑/↓, FX ↑/↓
  - No volatility modelling yet
- **Email Digest Delivery**
  - Retention engine
- **Access to Digest Archive**
  - Last 30 days

**Not Included:**
- Probability scoring
- Market timing signals
- Custom alerts
- Data exports
- Asset correlation tools

**Psychological Role:** *"I now understand global risk better."*

---

### TRADER PLAN — $29/month

**Purpose:** Active traders & tactical market participants

Digest becomes decision-support intelligence.

**Features (everything from Personal plus):**
- **Market Impact Probability Scores**
  - Example: Oil Volatility Probability: 68%, Gas Pricing Shock Probability: 74%
- **Cross-Asset Impact Matrix**
  - Shows alert cluster → asset sensitivity
- **Volatility Outlook Section**
  - AI predicts short-term volatility regimes and asset risk windows
- **Early Release Digest**
  - Published 2-3 hours earlier than lower tiers
  - Very powerful upgrade motivation
- **30-Day Historical Risk Pattern Analysis**
  - Helps traders identify regime transitions
- **Forward Watchlist With Risk Probability**
  - Example: OPEC Supply Decision - Impact Probability: 62%, Confidence: Medium
- **Digest Linked To Alert Detail Pages**
  - Deep research workflow

**Not Included:**
- Custom portfolio risk
- Raw data download
- API access
- Advanced index decomposition

**Psychological Role:** *"This helps me trade smarter."*

---

### PRO PLAN — $49/month

**Purpose:** Professional analysts, energy firms, institutional-style traders

Core premium identity tier.

**Features (everything from Trader plus):**
- **Full Index Decomposition Commentary**
  - GERI drivers: Supply stress, Transit stress, Freight stress, Storage stress contributions
- **Cross-Regional Contagion Analysis**
  - Shows how risk spreads between regions
  - Extremely rare and premium feature
- **Asset Sensitivity Scoring Tables**
  - Numerical sensitivity modelling: GERI vs Brent Beta, GERI vs TTF Elasticity
- **90-Day + 1-Year Risk Context**
  - Institutional time horizon
- **Historical Digest Library (Full)**
  - Hidden data goldmine
- **Scenario Forecast Narratives**
  - AI generates: Base case, Escalation case, De-escalation case
- **Advanced Visual Dashboards**
  - Digest integrates charts + overlays
- **Digest Download (PDF / Analyst Format)**
  - Huge professional value

**Psychological Role:** *"This is institutional intelligence."*

---

### ENTERPRISE PLAN — $129/month

**Purpose:** Companies, funds, trading desks, logistics firms, research teams

Digest becomes customizable intelligence infrastructure.

**Features (everything from PRO plus):**
- **Custom Digest Filtering**
  - By region, asset class, sector, risk type
- **Portfolio Risk Mapping**
  - "How yesterday's alerts impact YOUR portfolio"
  - Huge enterprise value
- **Custom Watchlists**
  - Company selects: pipelines, regions, shipping lanes, suppliers
- **API Access To Digest Data**
  - Massive upsell opportunity
- **Early Institutional Release**
  - Delivered before public platform update
- **Multi-User Team Access**
- **Custom Analyst Notes**
  - AI + optional human layer in future
- **White-Label Report Option (Future)**
  - Extremely premium B2B feature

**Psychological Role:** *"EnergyRiskIQ is our external intelligence partner."*

---

## Feature Escalation Matrix

| Capability | Free | Personal | Trader | Pro | Enterprise |
|------------|------|----------|--------|-----|------------|
| Executive snapshot | ✔ | ✔ | ✔ | ✔ | ✔ |
| Full alert analysis | ❌ | ✔ | ✔ | ✔ | ✔ |
| Multi-index interpretation | ❌ | ✔ | ✔ | ✔ | ✔ |
| Risk trend analytics | ❌ | ✔ | ✔ | ✔ | ✔ |
| Probability scoring | ❌ | ❌ | ✔ | ✔ | ✔ |
| Early digest release | ❌ | ❌ | ✔ | ✔ | ✔ |
| Index decomposition | ❌ | ❌ | ❌ | ✔ | ✔ |
| Contagion analysis | ❌ | ❌ | ❌ | ✔ | ✔ |
| Scenario forecasting | ❌ | ❌ | ❌ | ✔ | ✔ |
| Custom portfolio risk | ❌ | ❌ | ❌ | ❌ | ✔ |
| API / data licensing | ❌ | ❌ | ❌ | ❌ | ✔ |

---

## Data-Driven Quantitative Intelligence

Having full lifecycle historical asset data synchronized with indices (GERI / EERI / EGSI) enables:

- Statistical credibility
- Predictive modeling
- Backtesting
- Real probability scoring (not narrative AI)
- Institutional differentiation
- Pricing justification for higher tiers

**Key Advantage:** Most geopolitical analytics platforms do NOT have synchronized asset + risk datasets.

### Transformation: Qualitative → Quantitative Intelligence

With historical data for Brent, TTF gas, VIX, EUR/USD, EU Storage levels, and risk indices, the digest upgrades from qualitative intelligence to quantitative intelligence + predictive analytics.

---

## New Quantitative Capabilities

### 1. Risk → Asset Sensitivity Models

```
When GERI rises 10 points:
• Brent moves avg +2.4%
• TTF volatility rises +5.8%
• VIX rises +3.1%
```

Extremely monetizable intelligence.

### 2. Regime Detection

- Early stress signals
- Lag relationships
- Risk shock propagation
- Structural vs temporary risk differentiation

### 3. Forward Probability Forecasting

```
Based on historical patterns:
Current GERI level implies:

TTF volatility spike probability: 67%
Brent directional breakout probability: 52%
```

This is trader gold.

### 4. Divergence Detection

**Massive differentiator:**
- Risk rising but oil not reacting
- Storage rising but gas volatility increasing

These are institutional trading signals.

### 5. Backtesting Intelligence

```
Historically when EU Storage < 45% AND EERI > 60:
TTF experienced price spikes 72% of cases.
```

Hedge-fund-grade intelligence.

---

## Data-Driven Tier Enhancements

### FREE PLAN (with Real Data)

**Add:**
- **Basic Asset Movement Summary**
  ```
  Yesterday's Market Reaction:
  Brent: +0.8%
  TTF: +1.5%
  VIX: +2.1%
  ```

**Exclude:**
- No interpretation correlation
- No statistical context

**Purpose:** Show credibility without giving trading edge.

---

### PERSONAL PLAN ($9.95) — Data Enhancements

Introduces educational quantitative insight.

**Add:**
- **Risk vs Asset Relationship Commentary**
  ```
  Historically, rising EERI tends to increase TTF volatility.
  Yesterday's move aligns with historical patterns.
  ```
- **7-Day Asset Reaction Context**
  ```
  Last 7 days correlation:
  GERI vs Brent: 0.41
  GERI vs VIX: 0.62
  ```
- **Storage Context Commentary**
  ```
  EU Storage levels currently sit in the lower historical
  quartile for this time of year.
  ```

**Still Exclude:**
- No forecasting
- No probabilities

---

### TRADER PLAN ($29) — Data Enhancements

Unlocks true quant intelligence.

**Add:**
- **Probability-Based Asset Impact Forecast**
  ```
  TTF price spike probability (7-day horizon): 64%
  Brent volatility expansion probability: 58%
  ```
- **Lag & Lead Signal Analysis**
  ```
  GERI typically leads VIX by 2 trading days.
  ```
  Incredibly valuable for timing.
- **Risk-Adjusted Volatility Outlook**
  - Combines risk index + asset volatility
- **Storage Stress Signal Indicator**
  ```
  Storage Stress Level: Elevated
  Historical price spike probability: 61%
  ```

---

### PRO PLAN ($49) — Data Enhancements

Dataset becomes institutional intelligence.

**Add:**
- **Multi-Asset Sensitivity Dashboard**
  ```
  GERI Beta vs Assets:
  Brent: 0.42
  TTF: 0.71
  VIX: 0.55
  EUR/USD: -0.34
  ```
- **Regime Classification Engine**
  ```
  Current Regime:
  Logistics + Supply Shock Hybrid
  ```
- **Divergence Alert System**
  ```
  Risk increasing but freight + oil not reacting
  → historically precedes sharp repricing.
  ```
- **Historical Scenario Simulation**
  ```
  Current risk resembles:
  Jan 2022 Pre-Ukraine Risk Phase
  ```
  Extremely powerful for institutional clients.

---

### ENTERPRISE PLAN ($129) — Data Enhancements

Real data becomes B2B infrastructure.

**Add:**
- **Custom Asset Exposure Mapping**
  - Users upload or select assets
  - Digest shows impact score on THEIR portfolio
- **API Access to Correlation Models**
- **Custom Backtesting Engine**
  ```
  Users test: "What happens when EERI > 70?"
  ```
- **Early Stress Trigger Warnings**
  - Predict risk + asset structural break probability

---

## Data-Driven Feature Escalation Matrix

| Capability | Free | Personal | Trader | Pro | Enterprise |
|------------|------|----------|--------|-----|------------|
| Basic asset moves | ✔ | ✔ | ✔ | ✔ | ✔ |
| Risk correlation commentary | ❌ | ✔ | ✔ | ✔ | ✔ |
| Probability forecasting | ❌ | ❌ | ✔ | ✔ | ✔ |
| Lag/lead signal analytics | ❌ | ❌ | ✔ | ✔ | ✔ |
| Sensitivity modelling | ❌ | ❌ | ❌ | ✔ | ✔ |
| Regime classification | ❌ | ❌ | ❌ | ✔ | ✔ |
| Divergence detection | ❌ | ❌ | ❌ | ✔ | ✔ |
| Portfolio mapping | ❌ | ❌ | ❌ | ❌ | ✔ |
| Backtesting tools | ❌ | ❌ | ❌ | ❌ | ✔ |
| API data feeds | ❌ | ❌ | ❌ | ❌ | ✔ |

---

## NEW Digest Section: Market Reaction vs Risk Signal

**Recommended elite-tier intelligence section:**

```
RISK vs MARKET REACTION

Risk Level: Rising
Market Reaction: Muted

Interpretation:
Historically this pattern precedes delayed volatility expansion.
```

---

## Strategic Dataset Opportunity

Full lifecycle synchronized data creates a proprietary research dataset:
- Licensing gold
- Investor pitch gold
- Hedge fund partnership gold
- Academic partnership gold

---

## TRUE Long-Term Differentiator

Not alerts. Not dashboards.

**The differentiator is: Risk → Asset Transmission Intelligence**

This is extremely rare in the industry.

---

## Recommended Platform Positioning

Brand EnergyRiskIQ as:

> **Geo-Energy Risk Intelligence + Market Transmission Analytics Platform**

This is unique positioning globally.

---

## Smart Upgrade Hooks (UI Implementation)

Add these upgrade prompts throughout the UI:

```
🔒 Trader Insight Available
Upgrade to unlock probability scoring

🔒 Contagion Analysis is Pro Only

🔒 Portfolio Impact Available in Enterprise
```

These significantly increase conversion rates.

---

## Strategic Differentiators

Long-term strongest differentiators that MUST stay in higher tiers:
- Contagion analysis
- Probability modelling
- Scenario forecasting
- Portfolio risk mapping

---

## MVP Recommendation

For fastest monetization, consider launching with 3 active tiers initially:
- **Free**
- **Trader**
- **Pro**

Then introduce Personal and Enterprise later. This often converts better in early stages.
