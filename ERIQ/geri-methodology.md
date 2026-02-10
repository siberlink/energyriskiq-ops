# GERI Methodology

## Global Geo-Energy Risk Index

### Version 1.1 | EnergyRiskIQ

---

## 1. What Is GERI?

The **Global Geo-Energy Risk Index (GERI)** is a proprietary composite index that measures the overall level of geopolitical and energy supply risk affecting global energy markets on any given day. It distills a complex, multi-source intelligence pipeline into a single, interpretable daily value that answers one question:

> **"How dangerous is the global geopolitical and energy environment today?"**

GERI functions as a macro-level risk thermometer — analogous to the VIX for financial volatility, but purpose-built for geopolitical and energy risk. It is designed for macro traders, risk committees, asset allocators, strategists, and energy professionals who need a reliable, quantitative signal to inform portfolio decisions, hedging strategies, and risk exposure management.

---

## 2. Index Architecture

### 2.1 Scoring Range

GERI produces a daily integer value on a **0 to 100** scale, where:

- **0** represents a theoretical state of zero geopolitical or energy risk
- **100** represents a theoretical state of maximum systemic crisis

In practice, the index oscillates within the middle range, with extreme values reserved for genuinely extraordinary conditions. The scale is calibrated so that moderate, everyday risk environments cluster in the 30-50 range, while sustained readings above 75 indicate historically unusual stress.

### 2.2 Risk Bands

The GERI value maps to five distinct risk bands, providing an immediate qualitative interpretation:

| Risk Band | Range | Interpretation |
|-----------|-------|----------------|
| **LOW** | 0 - 20 | Benign geopolitical environment. Energy supply risks are minimal. Markets are operating under normal conditions with no significant escalation signals. |
| **MODERATE** | 21 - 40 | Background risk is present but manageable. Some regional tensions or supply concerns exist, but systemic contagion is not indicated. Standard monitoring posture. |
| **ELEVATED** | 41 - 60 | Meaningful risk accumulation detected. Multiple regions or risk vectors are contributing to a heightened threat environment. Active monitoring and hedging consideration warranted. |
| **SEVERE** | 61 - 80 | Severe disruption pressure across multiple regions. Risk signals are converging with high probability of market dislocation. Active hedging and contingency planning strongly advised. |
| **CRITICAL** | 81 - 100 | Critical systemic stress. Risk signals have converged across regions and asset classes. Historical precedent indicates imminent or active market disruption and supply chain compromise. Defensive positioning and emergency protocols indicated. |

### 2.3 Trend Indicators

Each daily GERI reading is accompanied by two trend indicators:

- **1-Day Trend** — Change from the previous day's value, indicating immediate momentum
- **7-Day Trend** — Change from the value seven days prior, indicating directional trajectory

These trends provide critical context: a GERI value of 60 that has risen 15 points in a week carries a very different implication than a GERI of 60 that has fallen 10 points over the same period.

---

## 3. The Four Pillars

GERI is constructed from four distinct risk pillars, each capturing a different dimension of the global risk landscape. This multi-pillar architecture ensures the index is not dominated by any single event type and provides a balanced view of systemic conditions.

### Pillar 1 — High-Impact Events (40%)

This is the dominant pillar and the primary driver of GERI movements. It captures events that have the potential to cause significant, immediate disruption to global energy supply or pricing.

**What it measures:**
- Major geopolitical escalations (military conflicts, sanctions, diplomatic crises)
- Critical infrastructure incidents (pipeline disruptions, refinery outages, port closures)
- Supply shock events (production cuts, export bans, force majeure declarations)
- Policy shifts with systemic implications (regulatory changes, trade restrictions)

**How it works:**
Events are scored by severity on a 1-5 scale, where 1 represents a minor development and 5 represents a major systemic event. Each event's contribution is weighted by its source credibility and regional influence (see Regional Weighting Model below). The pillar aggregates the cumulative severity-weighted impact of all qualifying events within the measurement window.

**Why it carries the highest weight:**
In empirical observation, single high-severity events (e.g., a major pipeline attack, an OPEC emergency cut, a military escalation in a key producing region) are the strongest predictors of near-term energy market dislocation. The 40% allocation reflects this reality.

### Pillar 2 — Regional Risk Spikes (25%)

This pillar detects concentrated risk build-up within specific geographic regions, even when individual events may not reach the high-impact threshold.

**What it measures:**
- Clusters of moderate-severity events in a single region
- Accelerating event frequency within a region (escalation velocity)
- Regional risk scores that deviate significantly from recent baselines

**Why it matters:**
History shows that energy supply disruptions rarely occur without warning. They are typically preceded by a period of regional risk accumulation — rising tensions, increasing event frequency, and building pressure. This pillar is designed to detect that pre-crisis build-up before it manifests as a high-impact event.

### Pillar 3 — Asset Risk (20%)

This pillar captures risk signals emanating from direct asset-level stress — specific infrastructure, commodities, or supply chain elements under threat.

**What it measures:**
- Threats to specific energy assets (pipelines, terminals, shipping lanes)
- Commodity-specific supply/demand imbalances flagged by intelligence
- Critical infrastructure vulnerability alerts

**Why it matters:**
Some risks are best understood at the asset level rather than the regional or event level. A targeted attack on a key LNG terminal, for example, may not register as a major geopolitical event but has profound implications for gas supply. This pillar ensures asset-specific intelligence feeds into the composite index.

### Pillar 4 — Region Concentration (15%)

This pillar measures the geographic diversity (or lack thereof) of the current risk environment.

**What it measures:**
- How concentrated risk is in a single region versus distributed globally
- The dominance of any single region in the total risk picture
- Geographic breadth of simultaneous risk signals

**Why it matters:**
A world where risk is concentrated in one region (e.g., 80% of risk emanating from the Middle East) is qualitatively different from a world where the same total risk is distributed across four regions. Concentrated risk implies higher disruption probability because a single escalation can trigger cascading effects. Distributed risk implies a more resilient but broadly stressed environment. This pillar penalises concentrated risk by adding to the GERI score when geographic diversity is low.

---

## 4. Regional Weighting Model (v1.1)

### 4.1 Philosophy

Not all geopolitical events carry equal weight for global energy markets. A military escalation in the Strait of Hormuz has fundamentally different implications for energy pricing than an equivalent escalation in a region with no energy infrastructure. The Regional Weighting Model ensures that GERI reflects this reality.

The model applies pre-aggregation multipliers to raw risk scores based on the region-cluster from which the event originates. Events in regions with higher structural influence on global energy flows receive proportionally greater weight in the index calculation.

### 4.2 Region Clusters and Influence Weights

GERI groups the world into seven region clusters, each assigned a base influence weight reflecting its structural importance to global energy markets:

| Region Cluster | Influence Weight | Rationale |
|----------------|-----------------|-----------|
| **Middle East** | 25% | Controls approximately 30% of global oil production, key chokepoints (Strait of Hormuz), and is the primary source of swing production capacity. Geopolitical instability here directly impacts global crude benchmarks. |
| **Russia / Black Sea** | 20% | Major global oil and gas exporter, critical pipeline infrastructure to Europe, historically the single largest source of European gas supply. Sanctions, conflicts, and transit disruptions in this cluster have outsized effects on European energy security. |
| **China** | 15% | The world's largest energy importer and a decisive demand-side force. Chinese economic activity, stockpiling behaviour, and trade policy directly influence LNG, crude oil, and commodity pricing globally. |
| **United States** | 15% | The world's largest oil and gas producer, a major LNG exporter, and the issuer of most energy-relevant sanctions. US policy, production shifts, and strategic reserve actions have global pricing implications. |
| **Europe Internal** | 10% | A major consuming region with limited domestic production. European regulatory decisions, storage policy, and demand patterns affect TTF gas pricing and broader energy security dynamics. |
| **LNG Exporters** | 10% | A dedicated cluster for Qatar, Australia, and Norway — the three largest LNG exporters outside the US. Disruptions to any major LNG export facility can rapidly tighten global gas markets. Keywords related to specific facilities (e.g., North Field, Gorgon, Snohvit) trigger classification into this cluster. |
| **Emerging Supply Regions** | 5% | Covers North Africa, South America, and other developing energy supply regions. While individually less influential, emerging supply disruptions can exacerbate tight market conditions during periods of elevated stress. |

### 4.3 Classification Logic

Events are classified into region clusters through a hierarchical process:

1. **Keyword Override (Russia):** If an event's text contains Russia-specific keywords (e.g., Gazprom, Nord Stream, Kremlin, Yamal), it is classified as Russia / Black Sea regardless of its tagged region. This prevents European-tagged events about Russian gas from being under-weighted.

2. **Keyword Override (LNG Exporters):** If an event mentions specific LNG export facilities or exporter countries (e.g., Qatar, Gorgon, Hammerfest), it is classified as LNG Exporters regardless of geographic tagging.

3. **Standard Region Mapping:** Events not caught by keyword overrides are mapped to their cluster based on their tagged region (e.g., Middle East maps directly, North America maps to United States, Asia maps to China).

4. **Global / Unattributed Events:** Events that cannot be attributed to a specific region receive a neutral weight of 1.0x, ensuring they contribute to the index without distortion.

### 4.4 Scale Preservation

The regional multipliers are scaled so that their average equals 1.0. This means the Regional Weighting Model reshapes the distribution of risk across regions without inflating or deflating the overall index level. A period with identical events occurring in every region simultaneously would produce the same GERI as a model without regional weighting.

---

## 5. Source Intelligence Architecture

### 5.1 Source Philosophy

GERI's signal quality depends directly on the quality, credibility, and diversity of its intelligence sources. The platform follows a strict curation philosophy:

- **Institutional sources first:** Reuters, EIA, ICIS, OPEC, and government agencies form the credibility backbone
- **Trade and industry sources second:** FreightWaves, Rigzone, Maritime Executive, Hellenic Shipping provide specialised domain intelligence
- **Regional sources third:** Xinhua, China Daily, Norwegian Offshore Directorate, EU Commission feeds provide geographic coverage
- **No noise sources:** General news aggregators, opinion blogs, social media, and financial spam feeds are excluded by design

### 5.2 Source Credibility Tiers

Each source is assigned a credibility tier that influences its contribution weight:

| Tier | Description | Examples |
|------|-------------|----------|
| **Tier 0** | Primary institutional data | EIA, OPEC, government agencies |
| **Tier 1** | Professional market intelligence | Reuters, ICIS, Platts |
| **Tier 2** | Specialist trade publications | FreightWaves, Rigzone, Maritime Executive |
| **Tier 3** | Quality regional/general sources | Al Jazeera, Xinhua, EU Commission |

### 5.3 Signal Domain Balance

The source portfolio is designed to cover six core signal domains in approximate proportion to their influence on energy risk:

| Signal Domain | Target Coverage | What It Captures |
|---------------|----------------|------------------|
| **Supply** | 25% | Production disruptions, capacity changes, reserves |
| **Transit** | 20% | Shipping routes, pipeline flows, chokepoint security |
| **Geopolitics** | 20% | Military conflicts, sanctions, diplomatic escalations |
| **Demand** | 15% | Consumption shifts, economic indicators, stockpiling |
| **Policy** | 15% | Regulatory changes, trade restrictions, energy policy |
| **Infrastructure** | 5% | Facility construction, maintenance, technical failures |

---

## 6. Event Processing Pipeline

### 6.1 Ingestion

Events are ingested continuously from curated RSS feeds across the source portfolio. Each event undergoes:

- **Deduplication** — Identical or near-identical events from multiple sources are consolidated
- **Classification** — Events are categorised by type (geopolitical, energy, supply chain, market, environmental) using keyword-based classification
- **Region Tagging** — Events are assigned to geographic regions based on content analysis

### 6.2 AI Enrichment

Classified events are enriched using AI analysis to produce:

- **Impact Assessment** — Structured evaluation of the event's potential effect on energy markets
- **Severity Scoring** — Quantitative severity assignment on a 1-5 scale
- **Asset Linkage** — Identification of specific energy assets, commodities, or infrastructure affected
- **Contextual Summary** — Concise narrative explaining why the event matters for energy risk

### 6.3 Alert Generation

Enriched events that meet minimum severity and relevance thresholds are converted into structured alerts. These alerts feed directly into the GERI computation engine. Three alert types are generated:

- **HIGH_IMPACT_EVENT** — Individual events with severity 4-5 or risk scores above the high-impact threshold
- **REGIONAL_RISK_SPIKE** — Regional risk accumulation alerts triggered when a region's aggregate score exceeds its recent baseline
- **ASSET_RISK_ALERT** — Asset-specific alerts triggered when individual infrastructure or commodity risk exceeds thresholds

---

## 7. Computation Cadence

### 7.1 Daily Computation

GERI is computed once per day, producing a single authoritative daily value. The computation window considers alerts generated within the trailing 24-hour period, ensuring the index reflects the most current intelligence.

### 7.2 Publication Schedule

| Audience | Timing | Content |
|----------|--------|---------|
| **Paid subscribers** | Real-time on computation | Full GERI value, band, trend, components, and AI interpretation |
| **Free users** | 24-hour delay | GERI value and band only, limited historical context |
| **Public / SEO pages** | 24-hour delay | GERI value, band, and top-level trend indicator |

### 7.3 Historical Baseline

The index maintains a rolling historical baseline for normalization purposes. This baseline tracks the minimum and maximum observed values for each pillar over a rolling window, ensuring that the 0-100 scale remains calibrated to the range of conditions actually observed in the data. This prevents the index from clustering at one end of the scale during prolonged periods of high or low risk.

---

## 8. Interpretation Framework

### 8.1 GERI as Risk Thermometer

GERI is not an asset price prediction tool. It is a risk context layer that answers: "What is the current state of the geopolitical and energy risk environment?" The distinction is critical:

- **GERI rising** means risk inputs are increasing — it does not guarantee asset prices will move in any specific direction
- **GERI falling** means risk inputs are subsiding — it does not guarantee market calm
- **The relationship between GERI and asset prices** is mediated by market positioning, liquidity, storage buffers, and participant expectations

### 8.2 Cross-Asset Context

GERI is designed to be read alongside energy market data for maximum insight:

| Cross-Reference | What It Reveals |
|-----------------|----------------|
| **GERI vs Brent Crude** | Whether supply disruption fear is priced into oil markets |
| **GERI vs TTF Gas** | European vulnerability to geopolitical gas risk |
| **GERI vs VIX** | Whether energy/geopolitical risk is spilling into broader financial markets |
| **GERI vs EUR/USD** | European macro vulnerability to energy shocks |
| **GERI vs EU Gas Storage** | Whether Europe's physical buffer is adequate for the current risk level |

### 8.3 Regime Recognition

GERI's historical trajectory can be divided into recognisable regimes:

| Regime | Characteristics |
|--------|----------------|
| **Risk Accumulation** | GERI rising gradually, assets react slowly. Risk is building but markets are discounting. Early warning phase. |
| **Shock** | GERI spikes sharply, assets overshoot. A high-impact event has materialised. Maximum volatility phase. |
| **Stabilisation** | GERI begins to fall, but assets remain volatile. Markets are repricing and uncertainty is still elevated. |
| **Recovery** | GERI returns to low/moderate bands, assets normalise. Risk has dissipated and markets have found equilibrium. |

---

## 9. What GERI Does Not Do

For transparency and proper use, it is important to understand the boundaries of the index:

- **GERI is not a trading signal.** It is a risk context layer, not a buy/sell indicator.
- **GERI does not predict asset prices.** It measures risk inputs, not market outcomes.
- **GERI does not cover all risk types.** It focuses on geopolitical and energy supply risk. It does not measure financial systemic risk, credit risk, or natural disaster risk except insofar as they affect energy markets.
- **GERI is not real-time intraday.** It is a daily index. Intraday events will be reflected in the following day's computation.
- **GERI is not a substitute for fundamental analysis.** It is a complementary intelligence layer designed to sit alongside traditional energy market analysis.

---

## 10. Model Governance and Evolution

### 10.1 Version Control

GERI operates under strict version control. The current production model is **v1.1**, which introduced the Regional Weighting Model. All historical data is tagged with its computation model version, ensuring full reproducibility and auditability.

### 10.2 Planned Enhancements

- **Source Weighting Calibration** — An adaptive system that will calibrate individual source weights based on measured contribution to predictive power, uniqueness, timeliness, and false-positive control. This is dependent on accumulating sufficient historical data (60+ days of scored events and daily GERI values).
- **Semantic Deduplication** — Moving beyond title-based deduplication to AI-powered semantic clustering, reducing noise from multiple sources reporting the same underlying event.
- **Temporal Event Detection** — Distinguishing between developing events and resolved events, preventing stale intelligence from inflating the index.

### 10.3 Independence and Objectivity

GERI is computed algorithmically from structured intelligence inputs. There is no editorial override, manual adjustment, or subjective intervention in the daily index value. The methodology is fixed for each model version, and changes are implemented only through formal version upgrades with documented rationale.

---

*Global Geo-Energy Risk Index (GERI) is a proprietary index of EnergyRiskIQ. This methodology document is provided for transparency and educational purposes. It does not constitute financial advice.*

*Model Version: v1.1 | Last Updated: February 2026*
