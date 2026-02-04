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
