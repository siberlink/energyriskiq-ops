# EGSI Methodology

## Europe Gas Stress Index

### Version 1 | EnergyRiskIQ

---

## 1. What Is EGSI?

The **Europe Gas Stress Index (EGSI)** is a proprietary dual-layer index system that measures the stress, fragility, and disruption exposure of the European natural gas system. It answers two critical questions simultaneously:

> **"How violently is risk transmitting through European gas markets right now?"**
> **"How structurally fragile is Europe's gas system today?"**

EGSI is unique in the EnergyRiskIQ platform because it operates as two complementary indices — **EGSI-M (Market/Transmission)** and **EGSI-S (System)** — each measuring a different dimension of gas stress. Together, they provide the most complete picture available of European gas vulnerability.

EGSI is designed for gas traders, LNG procurement teams, utility risk managers, energy desk analysts, infrastructure operators, policymakers, and hedge funds with European gas exposure. It translates complex multi-source intelligence — spanning geopolitical events, infrastructure chokepoints, physical storage data, market pricing, and policy signals — into an actionable daily stress reading.

---

## 2. The Two Layers: EGSI-M and EGSI-S

### 2.1 Why Two Indices?

European gas stress manifests in two fundamentally different ways:

1. **Market transmission stress** — How violently geopolitical and supply risk is flowing through gas markets today. This is reactive, fast-moving, and driven by the alert stream.

2. **System structural stress** — How fragile the underlying physical gas infrastructure is. This is slower-moving, driven by storage levels, refill rates, price volatility, and policy conditions.

A single index cannot capture both dimensions without compromising clarity. A day can have high market transmission stress (a pipeline disruption headline) but low system stress (storage is full, winter is months away). Conversely, system stress can be critically high (storage depletion, slow refill) while market transmission is temporarily calm (no new headlines).

EGSI solves this by providing both readings simultaneously.

### 2.2 EGSI-M (Market / Transmission)

**What it measures:** How intensely geopolitical and supply risk is transmitting through European gas markets on any given day.

**Character:** Reactive, event-driven, fast-moving. EGSI-M responds to the daily intelligence stream — new alerts, escalations, chokepoint hits, and asset stress signals.

**Analogy:** If the European gas system were a building, EGSI-M measures how hard the building is shaking right now.

**Primary audience:** Gas traders, commodity desks, short-term risk managers.

### 2.3 EGSI-S (System)

**What it measures:** How structurally fragile the European gas system is — its physical readiness, storage adequacy, price stability, and policy environment.

**Character:** Structural, data-driven, slower-moving. EGSI-S responds to physical fundamentals — storage levels vs seasonal targets, injection/withdrawal rates, TTF price movements, and supply-side pressures.

**Analogy:** If the European gas system were a building, EGSI-S measures how structurally sound the building is — regardless of whether it is currently shaking.

**Primary audience:** Utilities, LNG procurement teams, policymakers, infrastructure operators, institutional risk committees.

### 2.4 Reading EGSI-M and EGSI-S Together

| EGSI-M | EGSI-S | Interpretation |
|--------|--------|----------------|
| **Low** | **Low** | Gas system is calm and structurally sound. Normal operations. Minimal risk. |
| **High** | **Low** | Market is reacting to headlines, but the physical system is resilient. Likely a transient shock — watch for escalation but system buffers are intact. |
| **Low** | **High** | No immediate headlines, but the physical system is under structural strain. Storage may be depleting, refill rates lagging, or prices volatile. This is the quiet danger — the building is weakening even though it is not shaking. |
| **High** | **High** | Maximum concern. Active market transmission stress AND structural fragility. The system is both shaking and weakened. Historically associated with crisis conditions. Defensive positioning and contingency planning strongly indicated. |

This dual reading is one of EGSI's most powerful features — it separates headline noise from structural reality.

---

## 3. Scoring Range

Both EGSI-M and EGSI-S produce daily values on a **0 to 100** scale:

- **0** represents a theoretical state of zero gas stress
- **100** represents a theoretical state of maximum systemic gas crisis

The scale is calibrated so that normal operating conditions cluster in the lower ranges, while readings above 60 indicate historically unusual stress requiring active attention.

---

## 4. Risk Bands

EGSI uses a five-band classification system specifically designed for gas stress measurement. The band labels are intentionally distinct from GERI and EERI to reflect the different nature of gas system risk:

| Risk Band | Range | Interpretation |
|-----------|-------|----------------|
| **LOW** | 0 - 20 | Minimal gas stress. The European gas system is operating under normal conditions with no significant supply, storage, or market disruption signals. Standard monitoring posture. |
| **NORMAL** | 21 - 40 | Baseline market conditions. Some background stress may be present — routine maintenance, seasonal patterns, or minor supply variations — but nothing warrants elevated concern. Normal operational awareness. |
| **ELEVATED** | 41 - 60 | Heightened stress detected across the gas system. Multiple stress vectors are contributing simultaneously. Active monitoring is warranted. Gas, freight, or power markets may be showing early sensitivity. Procurement teams and traders should be alert. |
| **HIGH** | 61 - 80 | Significant stress affecting the European gas system. Risk signals are converging across supply, storage, transit, and market channels. Active hedging and contingency planning are strongly advised. Price dislocation or supply tightening probability is meaningful. |
| **CRITICAL** | 81 - 100 | Severe systemic stress. The European gas system is under extreme pressure across multiple dimensions. Historical precedent indicates imminent or active supply disruption, storage crisis, or market dislocation. Emergency protocols, defensive positioning, and immediate contingency activation are strongly indicated. |

### 4.1 Why EGSI Uses Different Band Labels

GERI and EERI use a five-band system with SEVERE as the fourth band. EGSI intentionally uses HIGH instead of SEVERE because gas system stress has a different operational character:

- Gas stress is more directly tied to physical infrastructure and commodity flows than geopolitical risk
- The language of "HIGH stress" is more natural for physical systems, industrial operations, and commodity markets
- It aligns with how gas traders, utilities, and procurement teams naturally describe system conditions

This is a deliberate design choice, not an inconsistency.

### 4.2 Trend Indicators

Each daily EGSI reading includes:

- **1-Day Trend** — Change from the previous day's value, showing immediate momentum
- **7-Day Trend** — Change from seven days prior, showing directional trajectory

These trends are critical for distinguishing between an EGSI of 55 that is rising sharply (stress is building) and an EGSI of 55 that is falling from a recent peak (stress is subsiding). The same number carries very different operational implications.

---

## 5. EGSI-M Architecture: The Four Pillars

EGSI-M is constructed from four distinct pillars, each capturing a different dimension of how risk transmits through European gas markets.

### Pillar 1 — Regional Escalation Backbone (RERI_EU)

This is the structural foundation of EGSI-M. It measures the underlying severity and intensity of geopolitical and energy events directly affecting Europe's gas system.

**What it measures:**
- The cumulative impact of high-severity events affecting European energy security
- Escalation patterns — rising event frequency, increasing severity, and building pressure
- The overall "temperature" of the European geopolitical risk environment as it relates to gas

**Why it matters:**
Gas market stress does not emerge in a vacuum. It is rooted in geopolitical reality — sanctions, conflicts, diplomatic crises, and policy shifts. The Regional Escalation Backbone captures this ground-level reality. When this pillar is elevated, the European gas system is operating in a dangerous environment regardless of what spot prices are doing.

**Relationship to EERI:**
This pillar draws from the same regional risk intelligence that powers EERI (European Energy Risk Index), but filters it specifically for gas-relevant signals. This ensures EGSI-M reflects the geopolitical context without duplicating EERI's broader energy scope.

### Pillar 2 — Theme Pressure

This pillar measures the nature, breadth, and intensity of gas-specific stress narratives in the intelligence stream.

**What it measures:**
- The type of events driving gas stress: supply disruptions, pipeline issues, transit disputes, LNG congestion, maintenance outages, or policy interventions
- The breadth of thematic coverage — whether stress is concentrated in one narrative or spread across multiple themes
- The persistence of stress themes — repeated events in the same category signal deep structural pressure

**Why it matters:**
Theme Pressure answers: "What kind of gas stress is this?" A supply disruption crisis requires different responses than a transit dispute or a policy intervention. This pillar helps professionals understand the character of current stress and calibrate their response accordingly. When multiple gas-specific themes are active simultaneously, compounding pressure builds — even if individual events remain moderate.

**Gas-specific themes monitored:**
- Supply disruption (production outages, force majeure, export restrictions)
- Pipeline issues (maintenance, flow reductions, infrastructure damage)
- Transit disputes (Ukraine corridor, TurkStream, regulatory conflicts)
- LNG congestion (terminal capacity, cargo diversions, shipping delays)
- Storage concerns (drawdown rates, refill targets, regulatory mandates)
- Market stress (price spikes, volatility events, trading anomalies)

### Pillar 3 — Asset Transmission

This pillar measures whether gas stress is actually propagating into energy markets — bridging the gap between intelligence signals and financial reality.

**What it measures:**
- The number and breadth of energy asset classes showing stress linked to gas events
- Cross-asset transmission — whether stress is isolated to gas or spreading to oil, freight, FX, and power
- The strength of the connection between current intelligence signals and market-observable stress

**Why it matters:**
Asset Transmission answers: "Is this stress real or theoretical?" When gas stress transmits across multiple asset classes simultaneously, it signals systemic disruption rather than isolated concern. This is where headlines become money. A high EGSI-M driven by geopolitical events but with low Asset Transmission suggests markets are discounting the threat. A high EGSI-M with high Asset Transmission means markets are actively responding — a fundamentally different situation.

**Asset classes monitored:**
- **Gas (TTF)** — The primary European gas benchmark, most sensitive to supply disruption
- **Oil (Brent)** — Global benchmark reflecting broader energy supply concerns
- **Freight** — Physical logistics stress, often the earliest confirmation of real disruption
- **FX (EUR/USD)** — European macro confidence and capital positioning

### Pillar 4 — Chokepoint Factor

This pillar captures risk signals emanating from specific European gas infrastructure chokepoints — high-value, low-redundancy nodes in the gas supply network where disruption has outsized consequences.

**What it measures:**
- Direct mentions of monitored chokepoint entities in the intelligence stream
- The severity and frequency of alerts referencing specific infrastructure
- The concentration of risk around critical gas transit and import facilities

**Why it matters:**
The European gas system has identifiable single points of failure — infrastructure nodes where disruption cannot be easily rerouted or compensated. When intelligence signals cluster around these nodes, disruption probability increases disproportionately. The Chokepoint Factor ensures EGSI-M is sensitive to these high-signal, high-consequence risks.

**Monitored chokepoints include:**
- **Ukraine Transit Corridor** — Historically the primary Russian gas transit route to Europe, with ongoing geopolitical vulnerability
- **TurkStream / Blue Stream** — Southern corridor for Russian gas to Turkey and Southeast Europe
- **Nord Stream Infrastructure** — Northern corridor (currently compromised), with implications for future capacity
- **Norway Pipeline System** — Langeled, Europipe, and associated infrastructure supplying Northwestern Europe
- **Key LNG Import Terminals** — Gate (Netherlands), Zeebrugge (Belgium), Dunkerque (France), Montoir (France), Swinoujscie (Poland), Revithoussa (Greece)

Each chokepoint carries a signal weight reflecting its systemic importance to European gas supply security.

---

## 6. EGSI-S Architecture: The Five Pillars

EGSI-S is constructed from five distinct pillars measuring the physical, market, and policy dimensions of European gas system fragility.

### Pillar 1 — Supply Pressure (Winter Readiness)

This pillar measures how fragile European gas supply is — the physical availability and reliability of gas flowing into the system.

**What it measures:**
- LNG terminal outages, maintenance events, and capacity constraints
- Pipeline disruptions, compressor outages, and flow reductions
- Force majeure events and export restrictions affecting European supply
- The alignment between current supply capacity and seasonal demand requirements

**Why it matters:**
Supply Pressure answers: "Can Europe get the gas it needs?" When supply is constrained — through outages, disruptions, or insufficient import capacity — the entire gas system becomes more fragile. Even moderate demand increases or weather events can trigger crisis conditions when supply buffers are thin. This pillar measures that buffer adequacy.

### Pillar 2 — Transit Stress (Injection / Withdrawal Rate Stress)

This pillar measures the physical flow dynamics of the European gas system — how gas is moving through the network and whether injection or withdrawal patterns indicate stress.

**What it measures:**
- Injection rates during refill season vs expected targets
- Withdrawal rates during heating season vs sustainable depletion trajectories
- The deviation between actual flow rates and seasonal expectations
- Transit corridor disruptions and rerouting pressures

**Why it matters:**
Transit Stress captures the physical pulse of the gas system. Injection rates that fall behind schedule during summer indicate potential winter vulnerability months before it materialises. Withdrawal rates that exceed sustainable trajectories during winter signal accelerating depletion. This is one of the most forward-looking pillars — it detects emerging problems before they become headlines.

### Pillar 3 — Storage Stress

This pillar measures the adequacy and trajectory of European gas storage — the physical buffer that determines Europe's resilience to supply shocks and demand surges.

**What it measures:**
- Current EU gas storage level as a percentage of total capacity
- Deviation from seasonal storage norms — whether storage is above or below where it should be for this time of year
- Refill velocity — whether storage is being replenished at an adequate rate
- Winter deviation risk — the gap between current storage trajectory and the level needed for winter security

**Data source:**
Storage data is sourced from **GIE AGSI+ (Aggregated Gas Storage Inventory)**, the official EU gas storage transparency platform operated by Gas Infrastructure Europe. This provides daily storage levels across 18 EU Member States with data from 2011 onwards.

**Key regulatory targets:**
- **November 1:** 90% storage (EU Gas Storage Regulation mandate)
- **February 1:** 45% storage (winter security floor)

**Why it matters:**
Storage is Europe's insurance policy against supply disruption. When storage is above seasonal norms, the system can absorb shocks. When storage is below norms — particularly approaching winter — every additional risk factor is amplified. The Storage pillar quantifies this insurance margin and tracks whether it is growing or shrinking.

**Seasonal context:**
Storage stress is inherently seasonal. A storage level of 60% in August (when it should be 82%) carries very different implications than 60% in January (when 65% is the seasonal norm). The pillar adjusts for this seasonality, measuring deviation from where storage should be — not just where it is.

### Pillar 4 — Market Stress (Price Volatility)

This pillar measures financial market stress in European gas — the degree to which gas pricing and trading conditions indicate systemic concern.

**What it measures:**
- TTF (Title Transfer Facility) spot price movements and volatility
- The magnitude of daily price changes relative to historical norms
- Realised volatility over rolling measurement windows
- Price shock events — sudden, outsized moves that indicate market dislocation

**Data source:**
TTF gas price data is sourced from **OilPriceAPI**, providing real-time and historical European gas benchmark pricing.

**Why it matters:**
Markets aggregate information from thousands of participants. When TTF prices are volatile or experiencing outsized moves, it reflects collective concern about supply adequacy, demand uncertainty, or systemic risk. Market Stress captures this collective intelligence. Importantly, price volatility often precedes physical disruption — markets react to rumour, positioning, and hedging flows before physical supply is actually disrupted. This makes the Market pillar a valuable early warning signal.

### Pillar 5 — Policy Risk (Alert Pressure)

This pillar measures the degree to which government and regulatory interventions signal systemic concern about European gas security.

**What it measures:**
- Emergency policy declarations and market intervention announcements
- Price cap discussions, rationing proposals, and demand curtailment measures
- Regulatory changes affecting gas storage mandates, import requirements, or market rules
- Subsidy programmes, emergency procurement, and strategic reserve actions

**Why it matters:**
Policy interventions are a lagging but powerful stress indicator. When governments intervene in gas markets — through price caps, emergency measures, or rationing discussions — it confirms that the situation has exceeded normal market-managed parameters. The Policy pillar captures this "official concern" signal. Paradoxically, policy interventions can both reduce and increase market stress: emergency measures may stabilise supply but simultaneously signal that authorities believe conditions warrant extraordinary action.

---

## 7. Normalisation Strategy

### 7.1 Why Normalisation Matters

Raw stress metrics (event counts, severity sums, storage deviations, price movements) vary enormously depending on the global news cycle, seasonal patterns, and market conditions. Without normalisation, the 0-100 scale would be meaningless — a quiet week could produce values near zero while a single crisis could push values far beyond 100.

Both EGSI-M and EGSI-S use adaptive normalisation that evolves as the indices mature.

### 7.2 Bootstrap Phase

During the initial period when insufficient historical data exists (approximately the first 14 days), both indices use conservative cap-based fallback values for each component. These caps are set based on reasonable assumptions about the range of observable conditions, preventing extreme values while the system accumulates operational history.

### 7.3 Rolling Baseline Phase

Once sufficient history has accumulated (approximately 30+ days), both indices transition to percentile-based normalisation using rolling historical baselines. This approach:

- Keeps the 0-100 scale meaningful as conditions evolve
- Prevents prolonged periods of high or low stress from permanently compressing the scale
- Adapts to structural changes in the risk landscape over time
- Ensures new periods of unusual calm or stress are properly reflected

---

## 8. Data Sources

EGSI integrates both structured data feeds and unstructured intelligence signals:

### 8.1 Structured Data Sources

| Source | Data Provided | Used By |
|--------|---------------|---------|
| **GIE AGSI+** | EU gas storage levels, injection/withdrawal rates, capacity data across 18 Member States | EGSI-S (Storage pillar) |
| **OilPriceAPI** | TTF spot/near-month gas prices, historical pricing | EGSI-S (Market pillar) |

### 8.2 Intelligence Signal Sources

Both EGSI-M and EGSI-S consume structured alerts from the EnergyRiskIQ intelligence pipeline:

- **High-Impact Events** — Major geopolitical escalations, infrastructure incidents, supply shocks
- **Regional Risk Spikes** — Clustering of events indicating regional escalation
- **Asset Risk Alerts** — Asset-specific stress signals, including gas storage alerts generated by the EGSI storage monitoring system

These alerts are ingested from a curated portfolio of institutional, trade, and regional intelligence sources spanning Reuters, ICIS, EU Commission feeds, maritime intelligence, and specialised energy publications.

---

## 9. Computation Cadence

### 9.1 Daily Computation

Both EGSI-M and EGSI-S are computed daily, producing authoritative daily values. Computation runs after the day's intelligence has been processed and structured data has been updated.

### 9.2 Scheduled Execution

EGSI computation is triggered automatically via scheduled workflows:

- **EGSI-M** runs alongside GERI and EERI computation, after alert delivery
- **EGSI-S** runs on a higher-frequency schedule to incorporate the latest structured data as it becomes available

### 9.3 Publication Schedule

| Audience | Timing | Content |
|----------|--------|---------|
| **Paid subscribers** | Real-time on computation | Full EGSI-M and EGSI-S values, bands, trends, component breakdown, top drivers, chokepoint watch, and AI interpretation |
| **Free users** | 24-hour delay | EGSI value and band with limited context |
| **Public / SEO pages** | 24-hour delay | EGSI value, band, trend indicator, and top driver headlines |

---

## 10. Chokepoint Monitoring

### 10.1 Philosophy

The European gas system has identifiable critical nodes — infrastructure where disruption has consequences far beyond the facility itself. These chokepoints represent low-redundancy, high-throughput points in the gas supply network. EGSI maintains a monitored chokepoint registry that feeds directly into the EGSI-M Chokepoint Factor pillar.

### 10.2 Monitored Infrastructure

EGSI tracks ten key European gas infrastructure chokepoints across three categories:

**Transit corridors:**
- Ukraine Transit System (Sudzha entry, Urengoy-Pomary-Uzhgorod pipeline)
- TurkStream / Blue Stream (southern corridor)
- Nord Stream infrastructure (northern corridor, currently compromised)

**Pipeline systems:**
- Norway export pipelines (Langeled, Europipe, Troll infrastructure, Equinor network)

**LNG import terminals:**
- Gate Terminal (Rotterdam, Netherlands)
- Zeebrugge LNG (Fluxys, Belgium)
- Dunkerque LNG (France)
- Montoir-de-Bretagne LNG (Elengy, France)
- Swinoujscie LNG (Poland)
- Revithoussa LNG (Greece)

Each chokepoint carries a signal weight reflecting its systemic importance — transit corridors and major pipeline systems carry higher weights than individual LNG terminals, reflecting their greater potential for cascading disruption.

---

## 11. Integration with the EnergyRiskIQ Index Ecosystem

### 11.1 Position in the Index Stack

EGSI occupies the asset/system layer in EnergyRiskIQ's multi-level risk architecture:

| Level | Index | Scope | Question Answered |
|-------|-------|-------|-------------------|
| **Macro** | GERI | Global | "Is the world dangerous for energy markets?" |
| **Regional** | EERI | European | "Is Europe's energy security threatened?" |
| **Asset / System** | EGSI | European Gas | "How close is Europe to a gas shock?" |

This creates a complete risk stack: **Macro → Regional → Asset System**.

### 11.2 EGSI and GERI

GERI measures global geopolitical and energy risk. EGSI measures European gas-specific stress. Reading them together reveals whether global risk is concentrated in gas, or whether gas stress is a regional phenomenon disconnected from global conditions.

### 11.3 EGSI and EERI

EGSI feeds directly into EERI through the Asset Transmission component. When EGSI detects elevated gas stress — particularly through storage alerts and supply disruption signals — these contribute to EERI's composite reading. However, EGSI provides far more granular gas-specific intelligence than EERI alone.

**Reading EGSI alongside EERI:**
- **EERI high + EGSI high:** European energy stress is gas-led. Gas is the primary vulnerability vector.
- **EERI high + EGSI moderate:** European stress is driven by non-gas factors (oil, geopolitics, broader energy policy). Gas system is relatively insulated.
- **EERI moderate + EGSI high:** Gas-specific stress that hasn't yet reached broader European energy risk thresholds. This is a sectoral warning — critical for gas professionals, less urgent for broader energy risk managers.

---

## 12. Interpretation Framework

### 12.1 EGSI as Operational Intelligence

EGSI is not a gas price forecast or trading signal. It is an operational stress intelligence layer that tells professionals where European gas system stress is concentrated, how it is evolving, and what dimensions are driving it. The distinction is important:

- **EGSI rising** means gas system stress inputs are increasing — it does not guarantee gas prices will rise
- **EGSI falling** means stress inputs are subsiding — it does not guarantee market calm
- **EGSI in CRITICAL** means the concentration and severity of stress signals matches historical periods associated with significant gas market disruption
- **The relationship between EGSI and gas prices** is mediated by storage buffers, LNG availability, demand conditions, weather forecasts, and market positioning

### 12.2 Component Dominance

For paid subscribers, EGSI provides visibility into which pillars are driving the current reading. This is one of the most powerful features for professional users:

**EGSI-M dominance patterns:**
- **RERI_EU dominant:** Geopolitical forces are the primary driver. The risk environment around Europe is deteriorating.
- **Theme Pressure dominant:** Gas-specific narratives are intensifying. Multiple stress themes are compounding.
- **Asset Transmission dominant:** Markets are actively pricing gas stress. This is the confirmation phase.
- **Chokepoint Factor dominant:** Risk is concentrated around specific infrastructure. High-consequence disruption probability is elevated.

**EGSI-S dominance patterns:**
- **Supply Pressure dominant:** Physical supply fragility is the primary concern. Outages, maintenance, or capacity constraints are driving stress.
- **Transit Stress dominant:** Flow dynamics are abnormal. Injection or withdrawal rates deviate significantly from expectations.
- **Storage dominant:** Storage levels are the primary vulnerability. The physical buffer is inadequate for current risk conditions.
- **Market Stress dominant:** Price volatility and trading conditions indicate systemic concern.
- **Policy Risk dominant:** Government interventions signal that authorities view conditions as beyond normal market management.

### 12.3 Regime Recognition

EGSI's historical trajectory can be divided into recognisable stress regimes:

| Regime | Characteristics | Typical Duration |
|--------|----------------|------------------|
| **Calm** | EGSI in LOW/NORMAL bands, stable trends, minimal driver activity. System is operating well within safe parameters. | Weeks to months |
| **Stress Build-Up** | EGSI rising, crossing from NORMAL to ELEVATED. Storage may be lagging, supply concerns emerging, or market volatility increasing. Early warning phase. | Days to weeks |
| **Active Stress** | EGSI in HIGH/CRITICAL range. Multiple pillars contributing. Markets volatile, storage under pressure, or supply disruptions active. Maximum vigilance required. | Days to weeks |
| **De-escalation** | EGSI falling from HIGH/CRITICAL. Stress drivers subsiding, storage improving, or supply normalising. Caution still warranted — false recoveries are common. | Days to weeks |
| **Recovery** | EGSI returning to LOW/NORMAL. System buffers rebuilding, market conditions normalising. | Weeks |

Regime transitions are the most actionable signals. The shift from Calm to Stress Build-Up is the early warning. The shift from Stress Build-Up to Active Stress is the confirmation. The shift from Active Stress to De-escalation is the turning point.

---

## 13. Seasonal Context

European gas stress is inherently seasonal, and EGSI accounts for this in several ways:

### 13.1 Storage Seasonality

Gas storage follows a predictable annual cycle: drawdown during winter heating season (November through March), refill during injection season (April through October). EGSI-S measures storage relative to seasonal norms — not absolute levels — ensuring that a storage level of 50% in March (normal) is treated differently from 50% in September (concerning).

**Key seasonal benchmarks:**

| Period | Expected Storage | Significance |
|--------|-----------------|--------------|
| November 1 | 90% | EU regulatory mandate for winter readiness |
| Mid-winter (January) | ~65% | Normal mid-winter drawdown level |
| Seasonal low (March) | ~40% | Expected post-winter minimum |
| February 1 | 45% | Winter security floor target |
| Peak refill (August) | ~82% | Pre-autumn acceleration target |

### 13.2 Winter Risk Amplification

During winter months (November through March), all gas stress signals carry amplified significance because:
- Demand is at its highest (heating load)
- Storage is being depleted rather than replenished
- Supply disruptions cannot be compensated by accelerated injection
- The consequences of miscalculation are immediate and severe

EGSI-S incorporates this seasonal amplification directly into its stress calculations.

---

## 14. What EGSI Does Not Do

For transparency and proper use, it is important to understand the boundaries of the index:

- **EGSI is not a gas price forecast.** It measures the stress environment, not the price outcome.
- **EGSI is not a trading signal.** It provides stress context for decision-making, not buy/sell instructions.
- **EGSI does not cover non-gas European energy risks.** It focuses specifically on the natural gas system. Oil-specific, power-specific, or renewables-specific risks are outside its scope unless they directly affect gas markets.
- **EGSI is not intraday.** It is a daily index. Events occurring during the day will be reflected in subsequent computations.
- **EGSI does not model weather directly.** While weather affects gas demand and storage trajectories, EGSI captures weather impact through its downstream effects on storage deviation, withdrawal rates, and market volatility — not through direct meteorological modelling.
- **EGSI does not replace fundamental gas market analysis.** It is a complementary intelligence layer designed to sit alongside traditional gas trading and procurement tools.

---

## 15. Model Governance and Evolution

### 15.1 Version Control

EGSI operates under strict version control. The current production models are **EGSI-M v1** and **EGSI-S v1**. All historical data is tagged with its model version, ensuring full auditability and reproducibility.

### 15.2 Feature Flag

EGSI computation is controlled by a feature flag (`ENABLE_EGSI`), allowing both indices to be activated or deactivated without code changes. This ensures operational safety during maintenance or if data quality issues are detected.

### 15.3 Planned Evolution

- **EGSI-S v2 — Enhanced Pillar Architecture:** Expansion of supply and transit pillars with additional structured data sources, including pipeline flow data and LNG terminal utilisation rates
- **Country-Level Decomposition:** Sub-national storage and stress analysis for major consuming countries (Germany, Italy, France, Netherlands)
- **Weather Integration:** Direct weather forecast anomaly data to enhance winter deviation risk modelling
- **Cross-Index Contagion:** When EERI activates its Contagion pillar (v2), EGSI will receive cross-regional spillover signals from Middle East and Black Sea gas-relevant developments

### 15.4 Independence and Objectivity

EGSI is computed algorithmically from structured data inputs and intelligence signals. There is no editorial override, manual adjustment, or subjective intervention in the daily index values. The methodology is fixed for each model version, with changes implemented only through formal version upgrades with documented rationale.

---

*Europe Gas Stress Index (EGSI) is a proprietary index of EnergyRiskIQ. This methodology document is provided for transparency and educational purposes. It does not constitute financial advice.*

*Model Version: EGSI-M v1, EGSI-S v1 | Last Updated: February 2026*
