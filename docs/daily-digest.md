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

---

# Quantitative Intelligence Blueprint

End-to-end quant + intelligence implementation using existing lifecycle data (GERI/EERI/EGSI + Brent, TTF, VIX, EURUSD, EU Storage).

---

## 1. Risk → Asset Modelling Formulas

### 1.1 Notation (Daily)

```
R_t = index level at day t (GERI, EERI, or EGSI)
A_t = asset price/level at day t (Brent, TTF, VIX, EURUSD, Storage)
rR_t = R_t - R_{t-1} (index daily change)
rA_t = ln(A_t / A_{t-1}) (asset log return)
```

### 1.2 Standardize (for comparability)

```
zX_t = (X_t - mean(X_{t-W..t-1})) / std(X_{t-W..t-1})
```

Where W is rolling window (e.g., 60 or 90 trading days).

### 1.3 Linear Sensitivity (Beta) — Rolling OLS

Model how asset returns respond to risk changes:

```
rA_t = alpha + beta * rR_t + epsilon_t
beta = cov(rA, rR) / var(rR)
```

**Interpretation:** Beta tells you the expected asset move for a 1-unit index change (in return terms if using log returns).

### 1.4 Multi-Factor Risk Transmission Model (Recommended)

Use multiple indices and storage (gas reacts to storage + EU risk):

```
rA_t = alpha + b1*rGERI_t + b2*rEERI_t + b3*rEGSI_t + b4*chgStorage_t + b5*rVIX_t + epsilon_t
```

Where:
```
chgStorage_t = Storage_t - Storage_{t-1} (or % change)
```

### 1.5 Nonlinear / Threshold Sensitivity (Piecewise Beta)

Markets often react only after risk crosses bands:

```
rA_t = alpha + beta1*rR_t*I(R_{t-1} < T1) + beta2*rR_t*I(T1 <= R_{t-1} < T2) + beta3*rR_t*I(R_{t-1} >= T2) + epsilon_t
```

Example thresholds: T1=40, T2=60 (Elevated/High breakpoints).

### 1.6 Event-Window Reaction (Shock Response)

Define "risk shock" days by percentile:

```
Shock_t = 1 if rR_t >= percentile(rR, 95%) else 0
CAR_A(k) = sum_{i=0..k} rA_{t+i} (cumulative abnormal return over k days after shock)
```

Compute average CAR_A(k) across all shock events.

### 1.7 Lead/Lag Model (Risk Leads Asset)

Test whether risk moves precede asset moves:

```
rA_t = alpha + sum_{k=0..K} beta_k * rR_{t-k} + epsilon_t
```

If beta_1/beta_2 significant → index leads.

### 1.8 Correlation + "Elasticity" for Level Series

For some relationships (risk vs VIX level), use changes in level:

```
dA_t = A_t - A_{t-1}
dA_t = alpha + beta * rR_t + epsilon_t
```

---

## 2. Probability Scoring Methodology

Data-backed probabilities, not "AI vibes".

### 2.1 Define Outcomes (Binary Targets)

Pick horizons (1D, 3D, 5D, 10D). Examples:

```
Y_spike_TTF_t(h) = 1 if max_{i=1..h}(TTF_{t+i}) >= TTF_t*(1+S) else 0
Y_vol_VIX_t(h) = 1 if VIX_{t+h} - VIX_t >= V else 0
Y_break_Brent_t(h) = 1 if |Brent_{t+h}/Brent_t - 1| >= B else 0
```

Where S, V, B are thresholds (e.g., 3%, 5 pts, 2%).

### 2.2 Feature Set (Model Inputs)

Use only existing data:

```
X_t = [
  R_t, rR_t, zR_t,
  EERI_t, rEERI_t, EGSI_t, rEGSI_t,
  zBrentRet_t, zTTFRet_t, zVIXchg_t, zEURUSDret_t,
  Storage_t, zStorage_t, chgStorage_t,
  Corr_rolling(R, Asset), Beta_rolling(R->Asset),
  DivergenceScore_t,
  RegimeID_t
]
```

### 2.3 Baseline Probability via Historical Conditioning (Fastest MVP)

Condition on current state buckets:

```
P(Y=1 | bucket) = count(Y=1 in history where state in same bucket) / count(history in bucket)
```

Bucket example:
```
bucket = (RiskBand(R_t), StorageQuartile(Storage_t), VolRegime(VIX_t))
```

### 2.4 Logistic Probability Model (Clean, Explainable)

```
p_t = 1 / (1 + exp(-(w0 + w1*R_t + w2*rR_t + w3*zStorage_t + w4*DivergenceScore_t + w5*RegimeShock_t)))
```

Train one model per target/horizon (TTF spike 5D, Brent breakout 3D, etc).

### 2.5 Reliability Calibration (Important)

After training, calibrate so "70%" actually means ~70%:

- Platt scaling or isotonic regression
- Or simple binning:
```
CalibratedP = mean(Y) within predicted-probability bins
```

### 2.6 Output Score Format (What Users See)

Show:
- **Probability (horizon):** 0–100%
- **Confidence:** based on sample size + stability
- **Drivers:** top contributing features (explainability)

Confidence proxy:
```
Confidence = min(1, sqrt(N_bucket / N_ref)) * (1 - model_error)
```

---

## 3. Divergence Detection Algorithms

Divergence = "risk signal says stress, market not pricing it (or vice versa)".

### 3.1 Simple Standardized Divergence

```
Div_t = zR_t - zA_t
```

Where zA_t could be z(rolling return) or z(level change) depending on asset.

### 3.2 Beta-Expected vs Realized (Best Practical Version)

Use rolling beta model:

```
Expected_rA_t = alpha_hat + beta_hat * rR_t
DivergenceResidual_t = rA_t - Expected_rA_t
```

Then normalize:
```
DivScore_t = (DivergenceResidual_t - mean(resid_{t-W..t-1})) / std(resid_{t-W..t-1})
```

**Interpretation:**
- `DivScore_t << 0`: market underreacting to risk (risk up, asset not moving)
- `DivScore_t >> 0`: market overreacting / pricing ahead

### 3.3 Multi-Asset Divergence (Systemic "Pricing Gap")

Compute residual divergence for each asset, then aggregate with weights:

```
SystemDiv_t = wBrent*DivScoreBrent_t + wTTF*DivScoreTTF_t + wVIX*DivScoreVIX_t + wEURUSD*DivScoreEURUSD_t
```

Weights can be fixed (e.g., gas heavy for EERI/EGSI days) or data-driven.

### 3.4 Trigger Rules (Alerts)

```
UnderpricingTrigger_t = 1 if zR_t >= 1.5 and SystemDiv_t <= -1.0 else 0
OverpricingTrigger_t = 1 if zR_t <= -1.0 and SystemDiv_t >= 1.5 else 0
```

---

## 4. Regime Classification Framework

Regimes that are interpretable to traders and explainable in the digest.

### 4.1 Regime Features

```
f1 = zR_t
f2 = zVolAsset_t (e.g., rolling stdev of returns)
f3 = zStorage_t (and/or storage slope)
f4 = Corr_rolling(R, asset)
f5 = SystemDiv_t
f6 = TrendR_t = slope(R_{t-L..t}) (simple linear slope)
```

### 4.2 Rule-Based Regimes (MVP, Fast, Explainable)

Example regimes:

```
Regime = "Calm" if zR_t < 0.5 and zVolAsset_t < 0.5
Regime = "Risk Build" if zR_t >= 0.5 and TrendR_t > 0 and zVolAsset_t < 0.7
Regime = "Shock" if zR_t >= 1.5 and zVolAsset_t >= 1.0
Regime = "Gas-Storage Stress" if zEERI_t >= 1.0 and zStorage_t <= -1.0
Regime = "Contagion" if zR_t >= 1.0 and Corr_rolling(R, VIX) >= 0.5 and Corr_rolling(R, TTF) >= 0.5
Regime = "Divergence / Underpriced Risk" if zR_t >= 1.0 and SystemDiv_t <= -1.0
```

### 4.3 Unsupervised Clustering (v2)

Use k-means / GMM on [f1..f6], then label clusters with human-friendly names using AI.

### 4.4 Regime Transition Signal

```
RegimeShift_t = 1 if Regime_t != Regime_{t-1} else 0
```

In digest: "Regime shift detected: Risk Build → Shock".

---

## 5. Backtesting Engine Architecture

Simple, reproducible, and fast.

### 5.1 Data Layer

Tables/views:
- `indices_daily(date, geri, eeri, egsi, ...)`
- `assets_daily(date, brent, ttf, vix, eurusd, storage, ...)`
- `features_daily(date, ...computed features...)`
- `signals_daily(date, divergence_triggers, regime_id, prob_scores...)`
- `tests_results(run_id, config_json, metrics_json, created_at)`

### 5.2 Pipeline (Daily)

1. Ingest / update assets + indices
2. Compute features (rolling stats, betas, correlations, regimes)
3. Generate signals (divergence triggers, shock days)
4. Train/update probability models (weekly is enough)
5. Write digest outputs + store "digest snapshot" record

### 5.3 Backtest Modes

**A) Event Study Backtest (best for product claims)**

When `UnderpricingTrigger_t=1`, measure forward moves:
```
Return_{t->t+h} = ln(A_{t+h}/A_t)
```
Aggregate: mean, median, hit rate.

**B) Threshold Strategy Backtest (Trader Plan)**

Example: long volatility proxy when risk shock triggers.
Track performance stats: hit rate, average move, max adverse, time-to-peak.

### 5.4 Metrics

```
HitRate = mean(Y=1 on signal days)
Lift = HitRate_signal / HitRate_baseline
AvgMove = mean(Return_{t->t+h} on signal days)
Sharpe_like = mean(Return)/std(Return) (informational only)
Drawdown = min cumulative
```

### 5.5 Validation Discipline

Walk-forward split:
- Train: older window
- Test: next window
- Roll forward

This keeps credibility when publishing results.

---

## 6. AI Prompt Templates Using Real Data

### 6.1 Digest Generator (System + User Template)

**SYSTEM PROMPT:**
```
You are EnergyRiskIQ Intelligence Engine.
You must NOT repeat raw news.
You must interpret yesterday's alerts + indices + real market data.
You must be concise, trader-oriented, and quantify relationships when data is provided.
If you state a probability, it must come from provided model outputs, not guesses.
Always separate: Facts / Interpretation / Watchlist.
```

**USER PROMPT (fill variables):**
```
DATE_TODAY: {YYYY-MM-DD}
DATE_YESTERDAY: {YYYY-MM-DD}

ALERTS_YESTERDAY (top 10 by severity, include region/category/severity/confidence):
{...}

INDEX_SNAPSHOT:
GERI: {level} ({delta})
EERI: {level} ({delta})
EGSI: {level} ({delta})

ASSET_MOVES_YESTERDAY:
Brent: {close} ({%})
TTF: {close} ({%})
VIX: {close} ({delta})
EURUSD: {close} ({%})
EU Storage: {level} ({delta})

QUANT_FEATURES:
Rolling betas (60d):
beta_GERI_to_Brent: {x}
beta_EERI_to_TTF: {x}
beta_GERI_to_VIX: {x}
Rolling correlations (60d):
corr_GERI_Brent: {x}
corr_EERI_TTF: {x}
corr_GERI_VIX: {x}

DIVERGENCE:
SystemDiv: {zscore}
UnderpricingTrigger: {0/1}
OverpricingTrigger: {0/1}

REGIME:
RegimeName: {string}
RegimeShift: {0/1}

MODEL_PROBABILITIES (must be used verbatim):
P_TTF_spike_5d: {0-100}%
P_Brent_breakout_3d: {0-100}%
P_VIX_jump_5d: {0-100}%

TASK:
Write the "EnergyRiskIQ — Daily Geo-Energy Intelligence Digest" for traders.
Include:
1) Executive snapshot (5 lines max)
2) What changed (3 bullets max)
3) Market reaction vs risk signal (quantified)
4) Top 3 systemic drivers (from alerts) with 1-line impact each
5) Probabilities + why (drivers from features)
6) 48–72h watchlist with triggers (levels to watch)
Tone: analyst-grade, not promotional. Avoid disclaimers except one line at the end.
```

### 6.2 Plan-Based Output Prompt (for Gating)

Add at top of USER prompt:
```
USER_PLAN: {FREE|PERSONAL|TRADER|PRO|ENTERPRISE}
Only include sections allowed for that plan:
FREE: (1,2 only) + asset moves line
PERSONAL: add (3,4) but no probabilities
TRADER: include all sections + probabilities
PRO: add regime detail + divergence deep dive + beta table
ENTERPRISE: add portfolio mapping section (if portfolio provided)
```

### 6.3 "Explain Divergence Without Leaking Sauce" Prompt

```
Explain the divergence in plain language without describing the exact formula, thresholds, or model parameters.
Use phrasing like: "historically", "based on past episodes", "risk signal vs market pricing gap".
Do not reveal z-score cutoffs, window lengths, or beta equations.
```

---

## 7. Trader-Grade Daily Digest Output Examples

### Example A — Risk Rising, Market Muted (Underpriced Risk)

```
ENERGYRISKIQ — DAILY GEO-ENERGY INTELLIGENCE DIGEST
Date: 2026-02-05 | Based on Alerts: 2026-02-04

EXECUTIVE SNAPSHOT
Global risk: Elevated, drifting higher (GERI 58 +4).
Europe stress firmed (EERI 63 +7) while market pricing stayed relatively muted.
Regime: Risk Build → early Divergence (underpriced risk signal).

WHAT CHANGED (24H)
- Europe risk accelerated on supply/transit uncertainty signals.
- Systemic risk broadened across regions (higher multi-region alert density).
- Freight/volatility channels showed early sensitivity, spot prices lagged.

MARKET REACTION vs RISK SIGNAL
- GERI +4 vs Brent +0.2% (muted vs historical sensitivity).
- EERI +7 vs TTF +0.3% (below typical reaction for similar risk jumps).
- System divergence: -1.3σ (risk signal > market pricing).

TOP SYSTEMIC DRIVERS (FROM ALERTS)
1) Europe | Energy | High severity: Supply/transit stress rising → gas sensitivity elevated.
2) Middle East | Geopolitical | Medium-high: escalation risk → volatility premium bias.
3) Global | Supply chain | Medium: routing/flows noise → freight stress tail risk.

PROBABILITIES (MODEL-BASED)
- TTF spike risk (5D): 64% | Drivers: EERI level, low storage quartile, divergence gap.
- Brent breakout (3D): 52% | Drivers: rising GERI + volatility regime stabilizing.
- VIX jump risk (5D): 58% | Drivers: GERI→VIX correlation strengthening, regime shift.

48–72H WATCHLIST (TRIGGERS)
- If EERI holds > 60 with storage still weakening: gas volatility bias stays upward.
- Watch any multi-region escalation cluster: increases probability of delayed repricing.
- Divergence resolves either via risk easing or market catch-up; monitor VIX sensitivity.

Informational only. Not financial advice.
```

### Example B — Risk Falling, Market Still Stressed (Overpriced Risk / Unwind Risk)

```
ENERGYRISKIQ — DAILY GEO-ENERGY INTELLIGENCE DIGEST
Date: 2026-02-06 | Based on Alerts: 2026-02-05

EXECUTIVE SNAPSHOT
Global risk: Cooling (GERI 49 -6), Europe stress stabilizing (EERI 57 -3).
Markets remain stressed relative to risk signal (volatility not easing yet).
Regime: Shock → Stabilization (potential unwind window).

WHAT CHANGED (24H)
- Risk signals eased across regions (alert density down 40%).
- Gas/storage concerns moderated with improved flow expectations.
- VIX remains elevated despite risk cooling — overpricing signal.

MARKET REACTION vs RISK SIGNAL
- GERI -6 vs Brent -0.1% (asset not unwinding with risk).
- EERI -3 vs TTF +0.5% (gas still bid despite lower EU risk).
- System divergence: +1.6σ (market > risk signal).

TOP SYSTEMIC DRIVERS (FROM ALERTS)
1) Europe | Energy | Moderate: Transit flows improving → near-term pressure easing.
2) Middle East | Geopolitical | Lower: Escalation signals fading.
3) Global | Macro | Stable: No new systemic triggers.

PROBABILITIES (MODEL-BASED)
- TTF spike risk (5D): 38% | Drivers: EERI cooling, storage stable.
- Brent breakout (3D): 29% | Drivers: GERI dropping, volatility regime shifting.
- VIX mean-reversion (5D): 62% | Drivers: Overpricing gap, risk cooling.

48–72H WATCHLIST (TRIGGERS)
- If GERI stabilizes < 50 with no new escalation cluster: unwind bias confirmed.
- Watch for VIX normalization — lagging indicator of market stress release.
- Any surprise regional alert could reverse stabilization narrative.

Informational only. Not financial advice.
```
