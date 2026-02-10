# EERI Methodology

## European Energy Risk Index

### Version 1 | EnergyRiskIQ

---

## 1. What Is EERI?

The **European Energy Risk Index (EERI)** is a proprietary composite index that measures Europe's daily exposure to energy disruption risk arising from geopolitical, supply, and market transmission forces. It answers one critical question:

> **"How dangerous is the European energy environment today, and where is the stress coming from?"**

EERI is the first regional index in the EnergyRiskIQ platform, built on top of the Regional Escalation Risk Index (RERI) framework. Where GERI provides a global risk temperature, EERI zooms into Europe specifically — the region most acutely sensitive to gas supply disruption, pipeline dependency, and geopolitical spillover from neighbouring conflict zones.

EERI is designed for energy traders, gas desk analysts, LNG procurement teams, European utility risk managers, freight planners, and institutional investors with European energy exposure. It translates complex, multi-source intelligence into an actionable daily signal that sits between raw news and formal market analysis.

---

## 2. Index Architecture

### 2.1 Scoring Range

EERI produces a daily value on a **0 to 100** scale:

- **0** represents a theoretical state of zero energy disruption risk for Europe
- **100** represents a theoretical state of maximum systemic energy crisis

The scale is normalised against a rolling historical baseline, ensuring that the 0-100 range remains calibrated to the conditions actually observed in the European energy landscape. This prevents the index from clustering at one end of the scale during prolonged periods of calm or sustained tension.

### 2.2 Risk Bands

Each daily EERI value maps to one of four risk bands:

| Risk Band | Range | Interpretation |
|-----------|-------|----------------|
| **LOW** | 0 - 25 | European energy environment is calm. No significant geopolitical or supply disruption signals are active. Standard operations can proceed without elevated monitoring. |
| **MODERATE** | 26 - 50 | Background risk is present. Some supply concerns, regional tensions, or policy uncertainties exist, but systemic disruption is not indicated. Routine monitoring is appropriate. |
| **ELEVATED** | 51 - 75 | Meaningful risk accumulation detected across European energy markets. Multiple stress vectors are contributing simultaneously. Active monitoring and hedging consideration are warranted. Gas, freight, or power markets may be showing early sensitivity. |
| **CRITICAL** | 76 - 100 | Severe systemic stress affecting European energy security. Risk signals are converging across supply, transit, and market channels. Historical precedent suggests high probability of price dislocation, supply tightening, or both. Defensive positioning and contingency planning are strongly indicated. |

### 2.3 Trend Indicators

Each daily EERI reading includes:

- **1-Day Trend** — Change from the previous day's value, showing immediate momentum
- **7-Day Trend** — Change from seven days prior, showing directional trajectory

These trends are essential for distinguishing between an EERI of 70 that is rising sharply (escalation phase) and an EERI of 70 that is falling from a recent peak (stabilisation phase). The same number carries very different operational implications depending on its trajectory.

---

## 3. The Four Pillars

EERI is constructed from four distinct pillars, each capturing a different dimension of European energy risk. This multi-pillar architecture ensures the index reflects the full spectrum of forces that can disrupt European energy markets.

### Pillar 1 — Regional Risk Backbone (RERI_EU)

This is the structural foundation of EERI. It measures the underlying severity, intensity, and acceleration of geopolitical and energy events directly affecting Europe.

**What it measures:**

The Regional Risk Backbone itself is composed of four sub-dimensions:

- **Severity Pressure** — The cumulative severity of high-impact events affecting Europe on a given day. Events are scored by their severity level and adjusted by event category (military and conflict events carry more weight than diplomatic developments, reflecting their higher disruption potential). Only direct high-impact events are included — derived or aggregated alerts are excluded to avoid double-counting.

- **High-Impact Concentration** — The count of significant events clustering around Europe on the same day. This captures escalation stacking — the phenomenon where multiple simultaneous events compound risk far beyond their individual severity. A day with five moderate events is qualitatively different from a day with one moderate event.

- **Asset Overlap** — The number of distinct energy asset classes simultaneously under stress (gas, oil, freight, FX, power, LNG). When risk propagates across multiple asset classes, it signals systemic transmission rather than isolated concern. This is one of the strongest institutional signals available.

- **Escalation Velocity** — The rate of change in severity pressure compared to the recent historical average. This captures sudden shocks and regime breaks — days when risk accelerates significantly beyond its recent trajectory. Velocity is what transforms EERI from a retrospective measure into an early warning signal.

**Why it matters:**
The Regional Risk Backbone answers: "How dangerous is the European geopolitical and energy environment right now?" If this pillar is elevated, EERI cannot be calm regardless of what markets are doing. This is the ground shaking beneath Europe's energy infrastructure.

### Pillar 2 — Theme Pressure

This pillar measures the nature and breadth of stress narratives dominating the European risk landscape.

**What it measures:**
- The type of events driving risk: military conflict, supply disruption, sanctions, energy policy, trade logistics, or diplomatic developments
- The breadth of thematic coverage — whether risk is concentrated in one narrative (e.g., a single pipeline dispute) or spread across multiple stress themes simultaneously
- The structural persistence of narratives — repeated events in the same theme category signal deep structural risk rather than episodic noise

**Why it matters:**
Theme Pressure answers: "What kind of crisis is this?" It separates a sanctions-driven risk environment from a military-escalation-driven one, or a supply-disruption crisis from a policy-uncertainty period. This distinction is critical for professionals because different crisis types require different hedging strategies, different asset exposures, and different time horizons. Many medium-severity events in the same theme build pressure that a single high-severity event may not — and Theme Pressure captures this accumulation.

**Event Category Hierarchy:**
Events are classified into categories that reflect their empirical disruption potential for European energy markets. Military conflicts, strikes, and active supply disruptions carry higher influence than diplomatic developments or political rhetoric, based on the observed relationship between event types and subsequent market reactions.

### Pillar 3 — Asset Transmission

This pillar measures whether risk is actually propagating into European energy markets — bridging the gap between geopolitical headlines and financial reality.

**What it measures:**
- The number and breadth of energy asset classes showing stress signals linked to current events
- Cross-asset transmission patterns — whether stress is isolated to gas or spreading across oil, freight, FX, and power simultaneously
- The alignment between risk events and market-observable stress

**Core asset classes monitored:**
- **Gas** — The primary European vulnerability indicator, most sensitive to supply disruption
- **Oil** — Global benchmark reflecting broader supply concerns
- **Freight** — Physical logistics and shipping route stress, often the earliest confirmation of systemic disruption
- **FX (EUR/USD)** — European macro confidence indicator
- **Power** — Downstream electricity market stress
- **LNG** — Alternative supply channel pressure

**Why it matters:**
Asset Transmission answers: "Is this risk actually reaching markets?" When multiple asset classes react simultaneously, risk is no longer theoretical — it is being priced. This pillar is the bridge between headlines and money. A high EERI driven primarily by geopolitical events but with low Asset Transmission suggests markets are discounting the threat. A high EERI with high Asset Transmission means markets are actively responding — a fundamentally different situation for anyone with European energy exposure.

### Pillar 4 — Contagion (Reserved for v2)

This pillar will measure cross-regional spillover risk — the degree to which energy-relevant crises in neighbouring regions are threatening to spread into Europe.

**What it will measure:**
- Risk transmission from the Middle East (the primary oil and LNG supply region for Europe)
- Risk transmission from the Black Sea / Caucasus region (historically the source of major European gas supply disruptions)
- Second-order effects from conflicts or disruptions in adjacent regions that could affect European energy routes, prices, or supply chains

**Current status:**
In EERI v1, the Contagion pillar is structurally present but set to zero. Its allocated influence has been proportionally redistributed across the other three pillars. This design decision was made because reliable contagion measurement requires mature regional indices for the Middle East and Black Sea — indices that are planned for future development. When activated in v2, the Contagion pillar will complete the picture by capturing fire jumping to the next building — risk that originates outside Europe but threatens to reach it.

**Why it matters (for v2):**
Europe's most devastating energy crises have historically originated externally. The 2022 gas crisis was driven by Russia/Ukraine conflict. Red Sea shipping disruptions affect LNG delivery routes to Europe. Middle East escalation directly impacts oil and LNG prices. Contagion is the pillar that will capture these external transmission channels.

---

## 4. Source Intelligence

### 4.1 Regional Focus

EERI ingests events classified as affecting Europe, the European Union, or European energy infrastructure. The classification uses both explicit geographic tagging and entity recognition — events mentioning European pipelines, terminals, storage facilities, or regulatory bodies are included even if tagged to a broader region.

### 4.2 Alert Types

EERI consumes three categories of structured alerts from the EnergyRiskIQ intelligence pipeline:

- **High-Impact Events** — Individual events with significant severity scores representing direct geopolitical or energy shocks (military escalations, infrastructure incidents, sanctions announcements, policy shifts)
- **Regional Risk Spikes** — Synthesised alerts generated when a region's aggregate risk level rises meaningfully above its recent baseline, indicating clustering or escalation
- **Asset Risk Alerts** — Asset-specific alerts triggered when individual energy commodities or infrastructure show stress linked to European risk events

Each alert type contributes to different pillars of the EERI computation, ensuring that the index captures both individual event severity and systemic patterns.

### 4.3 Event Categories

Events are classified into thematic categories that determine their influence within the index:

| Category | Disruption Profile |
|----------|-------------------|
| **War / Military / Conflict** | Highest disruption potential — direct physical threat to energy infrastructure, supply routes, or producing regions |
| **Supply Disruption** | High disruption potential — production outages, pipeline stoppages, facility shutdowns, force majeure events |
| **Energy** | Significant — broad energy market developments with pricing or supply implications |
| **Sanctions** | Significant — trade restrictions affecting energy flows, often with delayed but persistent effects |
| **Political** | Moderate — government decisions, elections, or policy changes affecting energy policy |
| **Diplomacy** | Lower immediate impact — negotiations, agreements, or de-escalation signals that may reduce future risk |

This hierarchy reflects empirical observation: military conflicts and active supply disruptions are far more likely to cause immediate European energy market dislocation than diplomatic developments, even when both receive similar media coverage.

---

## 5. Normalisation Strategy

### 5.1 Why Normalisation Matters

Raw risk metrics (event counts, severity sums, asset overlaps) vary enormously depending on the global news cycle and event clustering. Without normalisation, the 0-100 scale would be meaningless — a quiet week could produce values near zero while a single crisis could push values far beyond 100.

EERI uses a multi-phase normalisation approach that adapts as the index matures:

### 5.2 Bootstrap Phase (Early Days)

During the initial period when insufficient historical data exists, EERI uses conservative fallback caps for each component. These caps are set based on reasonable assumptions about the range of observable conditions, preventing extreme values while the system accumulates operational history.

### 5.3 Rolling Baseline Phase (Mature Operation)

Once sufficient history has accumulated (approximately 30+ days), EERI switches to a rolling baseline computed from the most recent 90 days of component values. This baseline dynamically adjusts the normalisation range using statistical percentiles of historical data.

The rolling approach ensures that:
- The 0-100 scale remains meaningful as the risk environment evolves
- A period of sustained high risk does not permanently compress the scale
- New periods of unusual calm or unusual stress are properly reflected
- The index adapts to structural changes in the risk landscape over time

---

## 6. Computation Cadence

### 6.1 Daily Computation

EERI is computed once per day, producing a single authoritative daily value. The computation runs after all alerts for the previous day have been finalised, ensuring complete data coverage.

### 6.2 Scheduled Execution

The daily EERI computation is triggered automatically at **01:00 UTC** each day via a scheduled workflow. This timing ensures that the full previous day's intelligence has been processed before the index is calculated.

### 6.3 Publication Schedule

| Audience | Timing | Content |
|----------|--------|---------|
| **Paid subscribers** | Real-time on computation | Full EERI value, band, trend, component breakdown, top drivers, asset stress, and AI interpretation |
| **Free users** | 24-hour delay | EERI value and band with limited context |
| **Public / SEO pages** | 24-hour delay | EERI value, band, trend indicator, and top 2-3 driver headlines |

### 6.4 What Is Shown vs. What Is Protected

EERI operates a strict information tiering policy to protect intellectual property while providing genuine value at every access level:

**Publicly visible (delayed):**
- Index value (0-100)
- Risk band (LOW / MODERATE / ELEVATED / CRITICAL)
- Trend direction (RISING / FALLING / STABLE)
- AI-generated interpretation narrative
- Top 2-3 risk driver headlines
- Affected asset classes (names only)

**Protected (paid subscribers only):**
- Component contributions and relative dominance
- Historical time series and charts
- Asset stress panel with directional bias
- Full driver intelligence with severity, confidence, and theme classification
- Regime statistics and persistence analysis
- Weekly snapshot intelligence

**Never exposed at any tier:**
- Raw component scores
- Internal normalisation parameters
- Proprietary scaling logic
- Component formulas or calculation methodology

---

## 7. Interpretation Framework

### 7.1 EERI as a Regional Decision Layer

EERI is not a price forecast or trading signal. It is a regional risk context layer that tells professionals where European energy stress is concentrated and how it is evolving. The distinction is important:

- **EERI rising** means European energy risk inputs are increasing — it does not guarantee energy prices will rise
- **EERI falling** means risk inputs are subsiding — it does not guarantee market calm
- **EERI in CRITICAL** means the concentration and severity of risk signals matches historical periods associated with significant energy market disruption

### 7.2 Asset Stress Interpretation

One of EERI's most valuable features is its ability to show which specific energy asset classes are absorbing geopolitical stress:

| Asset | Role in European Energy Risk |
|-------|------------------------------|
| **Gas** | Europe's primary vulnerability indicator. Gas is the first responder in European energy crises — it reacts fastest and most severely to supply disruption signals. When gas stress is elevated, downstream power prices, industrial costs, and consumer energy bills are all at risk. |
| **Oil** | Global benchmark reflecting broader supply concerns. Oil typically reacts to European risk when events have global implications (Middle East spillover, sanctions on major producers). Oil stress alongside gas stress signals systemic rather than regional disruption. |
| **Freight** | Physical logistics and shipping route stress. Freight is where geopolitical risk becomes physical reality — when ships are rerouted, insurance costs spike, or ports are disrupted. Elevated freight stress often precedes broader market transmission and is one of the earliest confirmation signals. |
| **FX (EUR/USD)** | European macro confidence indicator. Currency stress reflects capital positioning and investor confidence in European economic resilience. Elevated FX stress means capital is cautious about European exposure. |

**Cross-asset patterns professionals watch for:**

| Pattern | Interpretation |
|---------|----------------|
| Gas + Freight elevated together | Physical supply chain stress — disruptions are real, not theoretical |
| Oil + FX elevated together | Macro spillover — risk is affecting broader European economic outlook |
| All four asset classes elevated | Systemic shock — risk has permeated the entire European energy ecosystem |
| Gas elevated but others calm | Isolated supply concern — markets believe disruption is containable |

### 7.3 Component Dominance

For paid subscribers, EERI provides visibility into which pillar is driving the current reading. This is one of the most powerful features for professional users:

- **RERI_EU dominant:** The raw regional risk environment is dangerous. Structural geopolitical forces are the primary concern — sanctions, military escalation, or infrastructure threats.
- **Theme Pressure dominant:** The narrative landscape is intensifying. Multiple stress themes are compounding. Risk may be building toward a regime shift even if individual events remain moderate.
- **Asset Transmission dominant:** Markets are actively pricing risk. Supply chain and energy trading desks are responding. This is often the confirmation phase, indicating that risk has moved from intelligence to markets.

Understanding dominance helps users determine whether EERI is measuring emerging risk (RERI_EU and Theme Pressure) or confirmed market stress (Asset Transmission).

### 7.4 Regime Recognition

EERI's historical trajectory can be divided into recognisable risk regimes:

| Regime | Characteristics | Typical Duration |
|--------|----------------|------------------|
| **Calm** | EERI in LOW/MODERATE bands, stable trend, minimal driver activity | Weeks to months |
| **Escalation** | EERI rising, crossing from MODERATE to ELEVATED, increasing driver count and severity | Days to weeks |
| **Crisis** | EERI in ELEVATED/CRITICAL, multiple asset classes stressed, high driver concentration | Days to weeks |
| **De-escalation** | EERI falling from CRITICAL/ELEVATED, driver intensity decreasing, asset stress easing | Days to weeks |
| **Recovery** | EERI returning to LOW/MODERATE, normalisation of asset stress, driver count declining | Weeks |

Regime transitions are the most actionable signals in the index. The shift from Calm to Escalation is the early warning. The shift from Escalation to Crisis is the confirmation. The shift from Crisis to De-escalation is the turning point.

---

## 8. Relationship to Other EnergyRiskIQ Indices

### 8.1 EERI and GERI

GERI (Global Geo-Energy Risk Index) and EERI operate at different scales and serve different purposes:

| Dimension | GERI | EERI |
|-----------|------|------|
| **Scope** | Global | European |
| **Question** | "Is the world dangerous?" | "Is Europe's energy security threatened?" |
| **Audience** | CIOs, strategists, allocators | Energy traders, gas desks, European risk managers |
| **Decision type** | Strategic portfolio allocation | Tactical hedging and procurement |
| **Sensitivity** | Broad geopolitical environment | Europe-specific supply, transit, and market stress |

**Reading them together:**
- **GERI high + EERI high:** Global risk is concentrated in or affecting Europe. Maximum concern for European energy exposure.
- **GERI high + EERI moderate:** Global risk exists but Europe is buffered (strong storage, diversified supply, or risk concentrated in non-European regions).
- **GERI moderate + EERI high:** Europe-specific risk (internal policy, localised disruption, or transit issues) that hasn't reached global systemic levels.

### 8.2 Future Regional Indices

EERI is the first implementation of the RERI (Regional Escalation Risk Index) framework. The same architecture is designed to support:

- **Middle East RERI** — Measuring escalation risk in the world's primary oil and LNG producing region
- **Black Sea RERI** — Measuring shipping, pipeline, and conflict risk in the Russia/Ukraine/Caucasus corridor

When these indices are operational, the EERI Contagion pillar will activate, measuring spillover risk from these adjacent regions into European energy markets.

---

## 9. What EERI Does Not Do

- **EERI is not a gas price forecast.** It measures the risk environment, not the price outcome.
- **EERI is not a trading signal.** It provides risk context for decision-making, not buy/sell instructions.
- **EERI does not cover non-energy European risks.** It focuses on geopolitical and energy supply disruption risk. Banking crises, public health emergencies, or sovereign debt concerns are outside its scope unless they directly affect energy markets.
- **EERI is not intraday.** It is a daily index. Events occurring during the day will be reflected in the following day's computation.
- **EERI does not measure European energy demand.** It focuses on supply disruption risk and geopolitical stress, not seasonal consumption patterns or economic growth dynamics.
- **EERI is not a substitute for market analysis.** It is a complementary intelligence layer designed to sit alongside traditional energy trading and risk management tools.

---

## 10. Model Governance

### 10.1 Version Control

EERI operates under strict version control. The current production model is **v1**, with the Contagion pillar reserved for v2 activation. All historical data is tagged with its model version, ensuring full auditability and reproducibility.

### 10.2 Feature Flag

EERI computation is controlled by a feature flag (`ENABLE_EERI`), allowing the index to be activated or deactivated without code changes. This ensures operational safety during maintenance or if data quality issues are detected.

### 10.3 Planned Evolution

- **v2 — Contagion Activation:** Enable cross-regional spillover measurement from Middle East and Black Sea indices, redistributing pillar influences to their original design allocation
- **Velocity Normalisation:** Transition the escalation velocity sub-component to rolling baseline normalisation once sufficient historical data has accumulated (90+ days)
- **Weekly Snapshot Intelligence:** Structured weekly summary with plan-tiered depth, including cross-asset alignment analysis, historical analogue matching, regime persistence probabilities, and scenario outlooks

### 10.4 Independence and Objectivity

EERI is computed algorithmically from structured intelligence inputs. There is no editorial override, manual adjustment, or subjective intervention in the daily index value. The methodology is fixed for each model version, with changes implemented only through formal version upgrades.

---

*European Energy Risk Index (EERI) is a proprietary index of EnergyRiskIQ. This methodology document is provided for transparency and educational purposes. It does not constitute financial advice.*

*Model Version: v1 | Last Updated: February 2026*
