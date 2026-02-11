# Alert Taxonomy

## EnergyRiskIQ Alert Intelligence System

### Version 2 | EnergyRiskIQ

---

## 1. What Is the Alert System?

The EnergyRiskIQ Alert System is the intelligence backbone of the platform. It ingests raw events from curated news and data sources, classifies them, enriches them with AI, scores their severity, and generates structured alerts that feed directly into the GERI, EERI, and EGSI indices — and are delivered to subscribers based on their plan tier.

The alert system answers one operational question:

> **"What just happened that matters for energy markets, and who needs to know?"**

Every index value, every risk score, and every intelligence delivery originates from this alert pipeline. Understanding the alert taxonomy is essential for interpreting what the indices are measuring and why they move.

---

## 2. Alert Architecture Overview

The alert system operates in four sequential phases:

### Phase A — Event Ingestion and Classification

Raw events are ingested from curated RSS feeds, classified by category and region, scored for severity, and enriched with AI analysis. This produces structured events in the database.

### Phase B — Alert Generation

Classified events that meet defined thresholds are converted into structured alert events. These are user-agnostic — they represent things that happened, not messages to specific people. Alert events are deduplicated using fingerprints to prevent redundancy.

### Phase C — Fanout Delivery

Alert events are fanned out to individual users based on their subscription plan, alert preferences, and delivery channel settings. Each user receives only the alert types their plan permits.

### Phase D — Index Consumption

Alert events feed directly into the GERI, EERI, and EGSI computation engines. Each index consumes specific alert types and uses them to calculate daily risk values. This is the critical link between raw intelligence and quantitative indices.

---

## 3. Event Categories

Every event ingested into the system is classified into a primary category that determines how it is weighted, routed, and interpreted across the platform.

### 3.1 Primary Classification Categories

Events are first classified into one of three broad categories based on keyword matching against their title and content:

| Category | Description | Typical Sources |
|----------|-------------|-----------------|
| **Energy** | Events directly related to energy production, pricing, infrastructure, commodities, and energy policy. This is the broadest category and captures the majority of energy-relevant intelligence. | OPEC announcements, production data, refinery outages, pipeline news, LNG terminal updates, power grid events, regulatory changes |
| **Geopolitical** | Events related to military conflict, territorial disputes, diplomatic crises, security threats, and political instability that may affect energy markets indirectly or directly. | Military operations, sanctions announcements, border disputes, diplomatic breakdowns, security incidents, intelligence reports |
| **Supply Chain** | Events affecting the physical movement of energy commodities — shipping, ports, freight, logistics, and trade routes. | Port closures, shipping disruptions, freight rate spikes, canal blockages, maritime incidents, cargo diversions, customs disputes |

### 3.2 Thematic Sub-Categories

After primary classification, events receive a more granular thematic category that determines their influence within specific indices (particularly EERI). The thematic hierarchy reflects empirical disruption potential:

| Thematic Category | Description | Disruption Profile |
|-------------------|-------------|-------------------|
| **War** | Active armed conflict, invasions, occupations, direct military strikes, airstrikes, bombings, and shelling events. | Highest — Direct physical threat to energy infrastructure, supply routes, and producing regions. Immediate market impact. |
| **Military** | Military movements, deployments, exercises, weapons systems, defence posturing, and NATO/alliance activities that have not yet escalated to active conflict. | Very High — Signals escalation risk and potential future disruption. Markets react to positioning even before conflict materialises. |
| **Conflict** | Active hostilities, clashes, fighting, and violence that fall short of full-scale war but indicate regional instability. | High — Indicates deteriorating security environment. Often precedes supply disruptions or transit restrictions. |
| **Strike** | Industrial action — worker strikes, walkouts, labour disputes, and industrial shutdowns affecting energy infrastructure. | High — Direct impact on production capacity, refinery operations, port handling, and pipeline maintenance. Often causes immediate supply constraints. |
| **Supply Disruption** | Physical supply interruptions — outages, shutdowns, production halts, blockades, congestion, and force majeure events. | High — Direct supply impact. The most operationally immediate category. Markets respond to confirmed supply loss faster than to geopolitical rhetoric. |
| **Sanctions** | Trade restrictions, embargoes, asset freezes, blacklists, tariffs, and regulatory trade barriers affecting energy flows. | Significant — Often has delayed but persistent effects on energy trade patterns, pricing, and supply availability. Creates structural market distortions. |
| **Energy** | Broad energy market developments — commodity pricing, OPEC decisions, production data, storage reports, renewable energy shifts, and infrastructure projects. | Significant — Captures the fundamental energy landscape. Individual events may have moderate impact but accumulation drives trend. |
| **Political** | Government decisions, elections, parliamentary votes, ministerial announcements, policy changes, and regulatory actions affecting energy markets. | Moderate — Policy changes can have profound long-term effects but typically unfold over weeks or months rather than hours. |
| **Diplomacy** | Negotiations, summits, peace talks, agreements, treaties, ceasefire discussions, and de-escalation signals. | Lower immediate impact — Diplomacy typically reduces near-term risk. However, failed diplomacy can trigger rapid escalation. |
| **Geopolitical** | Default category for events with geopolitical relevance that do not fit neatly into the above categories. | Variable — Serves as a catch-all for events that carry geopolitical significance but whose specific disruption mechanism is unclear. |

### 3.3 Classification Priority

When an event matches multiple thematic categories with equal keyword scores, a priority hierarchy resolves the tie:

**War → Military → Conflict → Strike → Sanctions → Supply Disruption → Energy → Political → Diplomacy**

This priority order ensures that the most operationally significant interpretation is selected. A headline mentioning both "military" and "energy" is classified as "military" because the military dimension carries higher immediate disruption potential.

---

## 4. Alert Types

The alert system generates four distinct alert types, each capturing a different dimension of the risk landscape.

### 4.1 HIGH_IMPACT_EVENT

**What it captures:** Individual events of exceptional severity that have the potential to cause significant, immediate disruption to energy markets.

**Trigger conditions:**
- Event severity score is 4 or higher (on a 1-5 scale)
- Event category is a recognised thematic category (war, military, conflict, sanctions, supply disruption, energy, political, diplomacy, or geopolitical)
- Event region is a monitored region
- Event occurred within the last 24 hours
- No duplicate alert has been generated for the same event

**Alert content includes:**
- Event headline and source attribution
- Severity rating (1-5 scale)
- Thematic category
- Affected region
- AI-generated analysis summary (when available)
- Source URL for verification

**Why it matters:**
High-Impact Events are the single strongest predictors of near-term energy market dislocation. A major pipeline explosion, a surprise OPEC production cut, or a military strike on energy infrastructure represents a discrete, identifiable shock. These events carry the highest weight in index calculations because they represent confirmed, material developments — not speculation.

**Index consumption:**
- **GERI:** High-Impact Events are the primary driver of the High-Impact Events pillar (the dominant GERI component)
- **EERI:** Feeds into the Regional Risk Backbone when the event affects Europe
- **EGSI-M:** Feeds into Theme Pressure and Chokepoint Factor when gas-related

### 4.2 REGIONAL_RISK_SPIKE

**What it captures:** Concentrated risk build-up within a specific geographic region, detected when the region's aggregate risk score crosses defined thresholds or shows rapid acceleration.

**Trigger conditions:**
- Regional 7-day risk score reaches or exceeds the spike threshold, OR
- Regional risk score has increased by 20% or more compared to the previous assessment

**Alert content includes:**
- Region identification
- Current risk level (0-100)
- Percentage change from previous assessment
- Trend direction (rising, falling, stable)
- Top 3 driver events contributing to the spike
- Asset risk summary for affected commodities (oil, gas, FX, freight)

**Why it matters:**
Regional Risk Spikes capture the phenomenon of risk accumulation — the gradual build-up of pressure in a region that often precedes a major disruption event. History shows that energy supply crises rarely occur without warning; they are preceded by a period of escalating regional tension. This alert type detects that pre-crisis pattern.

**Index consumption:**
- **GERI:** Feeds directly into the Regional Risk Spikes pillar
- **EERI:** Primary contributor to the Regional Escalation Backbone when Europe is the affected region
- **EGSI-M:** Contributes to RERI_EU component when the region is Europe

### 4.3 ASSET_RISK_SPIKE

**What it captures:** Risk concentration around specific energy asset classes — individual commodities, infrastructure types, or supply chain elements showing elevated stress.

**Trigger conditions:**
- Asset-specific 7-day risk score reaches or exceeds the spike threshold for a given region-asset combination

**Alert content includes:**
- Asset identification (oil, gas, FX, freight)
- Affected region
- Asset risk score (0-100)
- Directional bias (up, down, risk-off, risk-on)
- Confidence level
- Top driver events

**Monitored asset classes:**
- **Oil** — Crude oil supply, pricing, and infrastructure risk
- **Gas** — Natural gas supply, storage, and pipeline risk (including EGSI-generated storage alerts)
- **FX** — Foreign exchange risk, particularly EUR/USD as a European macro confidence indicator
- **Freight** — Shipping, maritime logistics, and trade route risk

**Why it matters:**
Asset Risk Spikes capture risk at the most granular, tradeable level. While Regional Risk Spikes tell you where risk is concentrated geographically, Asset Risk Spikes tell you which specific commodities or markets are absorbing that stress. This is the most directly actionable alert type for traders and procurement teams.

**Special sub-type — Storage Risk:**
Gas storage alerts are a specialised form of Asset Risk Spike generated by the EGSI storage monitoring system. These are triggered when EU gas storage levels deviate significantly from seasonal norms, when withdrawal rates are unsustainable, or when winter supply security is threatened. Storage alerts are generated from structured data (GIE AGSI+ API), not from news intelligence, giving them a fundamentally different — and often more reliable — signal character.

**Index consumption:**
- **GERI:** Feeds into the Asset Risk pillar
- **EERI:** Primary contributor to Asset Transmission, with gas storage alerts carrying particular influence
- **EGSI-S:** Gas storage alerts directly reflect in the Storage Stress pillar

### 4.4 DAILY_DIGEST

**What it captures:** A consolidated summary of the day's risk landscape, providing a periodic overview rather than an event-by-event stream.

**Content includes:**
- Regional risk overview (7-day and 30-day scores)
- Trend assessment
- Asset risk summary across all monitored classes
- Top events of the day
- Index readings (GERI, EERI, EGSI) with AI interpretation

**Why it matters:**
Not all professionals need or want real-time alert streams. The Daily Digest provides a once-daily, structured briefing that captures the essential risk picture without alert fatigue. It is particularly valued by risk committees, portfolio managers, and senior decision-makers who need context rather than immediacy.

---

## 5. Region Mapping

Every event is assigned to a geographic region that determines its routing through the alert system, its influence on specific indices, and its delivery to users with region-based preferences.

### 5.1 Primary Regions

| Region | Coverage | Key Energy Significance |
|--------|----------|------------------------|
| **Europe** | EU Member States, UK, Norway, Switzerland, non-EU Balkans | Largest energy consuming bloc. Primary gas import dependency. TTF benchmark. Critical pipeline and LNG infrastructure. |
| **Middle East** | Israel, Iran, Iraq, Saudi Arabia, UAE, Qatar, Kuwait, Bahrain, Oman, Yemen, Syria, Lebanon | Controls approximately 30% of global oil production. Key LNG exporter (Qatar). Strait of Hormuz chokepoint. Source of most geopolitical oil supply risk. |
| **Black Sea** | Turkey, Russia, Ukraine, Caucasus, and associated maritime zone. Russia-specific keywords override European classification to ensure proper routing. | Critical gas transit corridor (Ukraine, TurkStream). Major oil and gas producer (Russia). Historically the primary source of European gas supply disruption. |
| **North Africa** | Egypt, Libya, Algeria, Morocco, Tunisia, Suez Canal zone | Suez Canal chokepoint. Pipeline gas supply to Southern Europe (Algeria). Libyan oil production volatility. |
| **Asia** | China, Japan, South Korea, India, Singapore, Taiwan, ASEAN, Australia | World's largest energy import region (China). Major LNG demand centre. Key demand-side force for global commodity pricing. |
| **North America** | United States, Canada, Mexico, Gulf of Mexico | World's largest oil and gas producer. Major LNG exporter. Source of most energy-relevant sanctions and trade policy. |
| **South America** | Brazil, Venezuela, Guyana, Colombia, Argentina | Emerging deepwater oil production (Brazil, Guyana). Venezuelan supply volatility. Vaca Muerta shale development (Argentina). |
| **Global** | Events that cannot be attributed to a specific region or that affect multiple regions simultaneously | Default classification for events with worldwide implications. Receives neutral weighting in index calculations. |

### 5.2 Region Classification Logic

Events are classified into regions through a hierarchical process:

1. **Keyword Matching** — Event title and content are scanned against region-specific keyword lists. Each region has a curated set of geographic, institutional, and infrastructure keywords.

2. **Score Accumulation** — Multiple keyword matches for the same region strengthen the classification. An event mentioning "Germany", "EU", and "Netherlands" will strongly classify as Europe.

3. **Hint Resolution** — When the source feed provides a region hint (from the feed's known geographic focus), this is used as a tiebreaker when keyword scores are close.

4. **Russia Override** — Events containing Russia-specific keywords (Gazprom, Kremlin, Nord Stream, Yamal, etc.) are classified as Black Sea regardless of other regional signals. This prevents Russian gas events from being under-weighted by routing to Europe.

5. **Global Fallback** — Events that cannot be attributed to any specific region default to Global.

### 5.3 Region-to-Cluster Mapping (GERI)

For GERI computation, the seven primary regions are mapped to influence clusters that determine their contribution weight to the global index:

| Region | GERI Cluster | Energy Influence |
|--------|-------------|-----------------|
| Middle East | Middle East | Highest — swing production, chokepoints |
| Black Sea | Russia / Black Sea | Very High — pipeline gas, oil exports |
| Asia | China | High — demand-side force |
| North America | United States | High — production, policy, LNG exports |
| Europe | Europe Internal | Moderate — consuming region, regulatory |
| North Africa | Emerging Supply Regions | Lower — developing supply base |
| South America | Emerging Supply Regions | Lower — developing supply base |
| Global | Neutral (no cluster) | Events contribute without regional amplification |

Additionally, keyword overrides route specific events to specialised clusters:
- **LNG Exporter Keywords** (Qatar, Australia, Norway, specific facility names) → LNG Exporters cluster
- **Russia Keywords** (Gazprom, Kremlin, Yamal, etc.) → Russia / Black Sea cluster

---

## 6. Severity Scoring

Every event receives a severity score that determines whether it qualifies for alert generation, how it is weighted in index calculations, and its priority in delivery.

### 6.1 Event Severity Scale (1-5)

| Score | Level | Description | Examples |
|-------|-------|-------------|----------|
| **1** | Minimal | Routine development with marginal energy relevance. Background noise level. | Minor policy statement, routine production data, scheduled maintenance announcement |
| **2** | Low | Notable development that registers on the intelligence radar but carries limited immediate market implications. | Moderate diplomatic exchange, minor shipping delay, routine regulatory update |
| **3** | Medium | Significant development with clear potential for market impact. Warrants monitoring and may trigger hedging consideration. | Supply disruption report, regional tension escalation, notable price movement, OPEC discussion leak |
| **4** | High | Major development with high probability of market impact. Represents a material change in the risk environment. | Military escalation in energy-producing region, major infrastructure outage, sanctions announcement, OPEC production cut |
| **5** | Critical | Exceptional development with near-certain market impact. Represents a systemic shock or crisis-level event. | Major armed conflict in chokepoint region, critical infrastructure attack, emergency production halt, force majeure on major supply route |

### 6.2 Severity Classification Factors

Severity is determined by analysing the event text for signal keywords:

**High-Severity Signals** — Keywords indicating maximum disruption potential:
- Attack, missile, explosion, shutdown, blockade, sanctions, crisis, turmoil, halt, suspend, collapse, war, conflict, seize, capture, embargo, invasion, emergency, critical

**Medium-Severity Signals** — Keywords indicating significant but not extreme disruption:
- Strike, disruption, outage, congestion, shortage, delay, spike, surge, plunge, threat, risk, warning, tension

**Special Amplifiers:**
- OPEC-related keywords (production cut, output cut, supply cut) add severity due to the organisation's outsized market influence

### 6.3 Alert Severity Scale (1-10)

Alert events (as opposed to raw events) use an expanded severity scale that incorporates the magnitude of the triggering condition:

**For Regional Risk Spikes:**

| Risk Score | Alert Severity |
|------------|---------------|
| 90 - 100 | 5 (Critical) |
| 80 - 89 | 4 (High) |
| 70 - 79 | 3 (Medium) |

**For Asset Risk Spikes:**

| Risk Score | Alert Severity |
|------------|---------------|
| 90 - 100 | 5 (Critical) |
| 80 - 89 | 4 (High) |
| 70 - 79 | 3 (Medium) |

**For High-Impact Events:**
Alert severity directly inherits the event's severity score (4 or 5, since only events with severity ≥ 4 qualify).

**For Gas Storage Alerts:**

| Storage Risk Score | Alert Severity |
|-------------------|---------------|
| 75 - 100 | 5 (Critical) |
| 60 - 74 | 4 (High) |
| 45 - 59 | 3 (Medium) |
| Below 45 | 2 (Low) |

---

## 7. Signal Quality Assessment

Beyond basic severity scoring, every event undergoes a comprehensive signal quality assessment that determines its contribution strength to index calculations.

### 7.1 Quality Dimensions

| Dimension | What It Measures |
|-----------|-----------------|
| **Source Credibility** | The trustworthiness and institutional authority of the source. Institutional data providers (EIA, OPEC, government agencies) score highest. Professional market intelligence (Reuters, ICIS) scores high. Specialist trade publications score moderately. General sources score lower. |
| **Energy Relevance** | How directly the event relates to energy markets. Events mentioning specific commodities, infrastructure, or energy entities score highest. General geopolitical events with indirect energy implications score lower. |
| **Entity Specificity** | Whether the event mentions specific, identifiable entities — named pipelines, terminals, producers, chokepoints, or organisations. Events referencing "Strait of Hormuz" or "Gazprom" carry more signal than generic "Middle East tensions". |
| **Freshness** | How recent the event is relative to the current moment. Fresh intelligence carries more signal than stale information. Signal strength decays over time using a half-life model. |
| **Noise Penalty** | Whether the event contains indicators of low-value content — opinion pieces, editorials, podcasts, book reviews, lifestyle content, or other non-intelligence material. Noise indicators reduce signal quality. |
| **Market Relevance** | The composite likelihood that the event will produce observable market effects, derived from severity, regional energy exposure, thematic category, and entity specificity. |

### 7.2 Signal Quality Bands

After assessment, events are assigned to quality bands:

| Band | Interpretation |
|------|----------------|
| **High** | Strong, actionable intelligence from credible sources with clear energy market relevance. These events drive index calculations. |
| **Medium** | Meaningful intelligence that contributes to the risk picture but may lack the specificity or source authority of high-quality signals. |
| **Low** | Marginal intelligence with limited direct relevance. Contributes minimally to calculations. |
| **Noise** | Content identified as non-intelligence material. Excluded from index calculations. |

### 7.3 GERI Driver Qualification

Events that achieve sufficient signal quality and market relevance are flagged as "GERI drivers" — meaning they are eligible to appear as named contributors in GERI's top driver analysis. This is a quality gate that ensures only credible, relevant intelligence is surfaced to users as explanatory context for index movements.

---

## 8. Named Entity Recognition

The signal quality system maintains a registry of named entities that, when detected in event text, significantly increase signal specificity and quality assessment.

### 8.1 Entity Categories

| Category | Description | Examples |
|----------|-------------|---------|
| **Chokepoints** | Maritime straits, canals, and transit bottlenecks where disruption would have outsized supply implications | Strait of Hormuz, Bab el-Mandeb, Suez Canal, Panama Canal, Bosphorus, Malacca Strait, Red Sea, Danish Straits, Cape of Good Hope |
| **Pipelines** | Named pipeline infrastructure carrying significant energy commodity flows | Nord Stream, TurkStream, Yamal, Druzhba, Trans-Adriatic (TAP), Trans-Anatolian (TANAP), Keystone, Colonial Pipeline, Blue Stream, South Stream |
| **LNG Terminals** | Named liquefaction and regasification facilities critical to global LNG trade | Sabine Pass, Cameron LNG, Freeport LNG, Corpus Christi, Ras Laffan, Yamal LNG, Gate Terminal, Dunkerque LNG, Montoir, Zeebrugge, Swinoujscie |
| **Producers** | Major national and international oil and gas companies whose operations affect global supply | Saudi Aramco, Gazprom, Rosneft, QatarEnergy, ADNOC, Equinor, Shell, BP, TotalEnergies, ExxonMobil, Chevron, PetroChina, Sinopec, Petrobras |
| **High-Risk Countries** | Nations with elevated energy-relevant geopolitical risk | Iran, Russia, Ukraine, Yemen, Libya, Iraq, Syria, Venezuela, Nigeria, Sudan, Myanmar |
| **Organisations** | International bodies whose decisions directly affect energy markets and policy | OPEC, OPEC+, IEA, EIA, NATO, EU Commission, UN Security Council |

### 8.2 Why Entity Recognition Matters

Events that mention specific named entities carry fundamentally more signal than generic events. "Tensions rise in the Middle East" is vague and difficult to act on. "Iran threatens to close the Strait of Hormuz" is specific, verifiable, and has clear supply implications. The entity recognition system quantifies this distinction and ensures that specific, actionable intelligence receives higher quality scores than generic commentary.

---

## 9. Source Credibility Architecture

The alert system assigns credibility ratings to intelligence sources based on their institutional authority, track record, and specialisation.

### 9.1 Source Tiers

| Tier | Description | Credibility Range | Examples |
|------|-------------|-------------------|---------|
| **Tier 0** | Primary institutional data providers — government agencies, intergovernmental organisations, and official statistical bodies | 0.90 - 0.95 | EIA (US Energy Information Administration), OPEC Press Releases, European Commission Energy, Norwegian Offshore Directorate |
| **Tier 1** | Professional market intelligence — established wire services, specialised energy intelligence providers, and industry-standard information platforms | 0.85 - 0.95 | Reuters Energy, ICIS Energy News, Energy Intelligence |
| **Tier 2** | Specialist trade publications — focused industry media covering specific sectors (maritime, offshore, commodities) with professional editorial standards | 0.75 - 0.85 | FreightWaves, Rigzone, Maritime Executive, Oil & Gas Journal, Hellenic Shipping News |
| **Tier 3** | Quality regional and general sources — major international media and regional news services with energy coverage | 0.65 - 0.80 | Al Jazeera, Xinhua Business, China Daily Business, Politico Europe |
| **Tier 4** | General energy media — broader energy news platforms with variable editorial depth | 0.60 - 0.65 | OilPrice.com, Energy Live News, Power Technology |

### 9.2 Source Curation Philosophy

The EnergyRiskIQ source portfolio follows strict curation principles:

- **Institutional sources first** — Reuters, EIA, ICIS, OPEC, and government agencies form the credibility backbone
- **Trade and industry sources second** — FreightWaves, Rigzone, Maritime Executive provide specialised domain intelligence
- **Regional sources third** — Xinhua, China Daily, Norwegian Offshore Directorate provide geographic coverage
- **No noise sources** — General news aggregators, opinion blogs, social media, and financial spam feeds are excluded by design

This hierarchy ensures that the intelligence stream is dominated by authoritative, verifiable information rather than speculation, commentary, or noise.

---

## 10. Noise Filtering

The alert system actively filters out content that degrades signal quality.

### 10.1 Noise Indicators

Content is penalised when it contains indicators of non-intelligence material:

| Indicator Type | Examples |
|---------------|---------|
| **Opinion content** | Opinion, editorial, comment, column |
| **Non-intelligence formats** | Podcast, review, interview transcript, book review |
| **Irrelevant content** | Celebrity, entertainment, sports, lifestyle, recipe, horoscope, weather forecast, travel guide |
| **Non-market obituaries** | Obituary (unless energy industry figure) |

### 10.2 Why Noise Filtering Matters

Without noise filtering, high-volume sources would flood the intelligence stream with irrelevant content, diluting signal quality and inflating index values with false inputs. A single source might publish 50 items per day, of which only 5 are genuinely energy-relevant. The noise filter ensures that only the 5 relevant items contribute to risk calculations.

---

## 11. Alert Delivery and Plan Access

### 11.1 Plan-Tiered Alert Access

Not all alert types are available to all subscription tiers. Access is progressively unlocked as users upgrade:

| Plan | Allowed Alert Types | Max Alerts/Day | Max Regions |
|------|-------------------|----------------|-------------|
| **Free** | HIGH_IMPACT_EVENT | 2 | 1 |
| **Personal** | HIGH_IMPACT_EVENT, REGIONAL_RISK_SPIKE | 4 | 2 |
| **Trader** | HIGH_IMPACT_EVENT, REGIONAL_RISK_SPIKE, ASSET_RISK_SPIKE | 8 | 3 |
| **Pro** | HIGH_IMPACT_EVENT, REGIONAL_RISK_SPIKE, ASSET_RISK_SPIKE, DAILY_DIGEST | 15 | 4 |
| **Enterprise** | HIGH_IMPACT_EVENT, REGIONAL_RISK_SPIKE, ASSET_RISK_SPIKE, DAILY_DIGEST | 30 | All |

### 11.2 Delivery Channels

Alerts are delivered through multiple channels based on user preferences and plan capabilities:

| Channel | Description | Availability |
|---------|-------------|-------------|
| **Email** | HTML-formatted alert emails with full event context, driver analysis, and asset impact summary | All plans |
| **Telegram** | Instant message delivery via Telegram bot for real-time notification | All plans (requires account linking) |
| **Dashboard** | In-app alert history and real-time notification within the user dashboard | All plans |

### 11.3 Delivery Timing

| Plan | Delivery Speed |
|------|---------------|
| **Free** | Delayed (60 minutes for events, 24 hours for index data) |
| **Personal** | Near real-time for events |
| **Trader** | Real-time |
| **Pro** | Real-time with priority routing |
| **Enterprise** | Real-time with priority routing |

---

## 12. Alert Safety and Deduplication

### 12.1 Fingerprint-Based Deduplication

Every alert event is assigned a unique fingerprint based on its type, region, and temporal context. This fingerprint prevents the same alert from being generated multiple times:

- **HIGH_IMPACT_EVENT:** Fingerprint based on the source event ID — each unique event can only generate one alert
- **REGIONAL_RISK_SPIKE:** Fingerprint based on region and date — one regional spike alert per region per day
- **ASSET_RISK_SPIKE:** Fingerprint based on region, asset, and date — one asset spike per region-asset combination per day
- **Storage Risk:** Fingerprint based on storage data date — one storage alert per data reporting day

### 12.2 Severity Floor

Alert events must meet a minimum severity threshold to be created. Events below this threshold are filtered at generation time, preventing low-significance developments from consuming delivery capacity.

### 12.3 Production Safety Mechanisms

The alert delivery system employs multiple safety mechanisms to ensure reliable operation:

- **Advisory locks** — Prevent concurrent delivery runs from creating duplicate messages
- **Unique constraints** — Database-level enforcement of delivery deduplication
- **Skip-locked queries** — Ensure that parallel delivery workers don't process the same alerts
- **Retry and backoff** — Failed deliveries are retried with exponential backoff
- **Circuit breakers** — Delivery is paused if error rates exceed defined thresholds
- **User allowlisting** — Production delivery can be restricted to specific users during testing or rollout

---

## 13. Alert-to-Index Relationship

### 13.1 How Alerts Feed Indices

| Alert Type | GERI | EERI | EGSI-M | EGSI-S |
|-----------|------|------|--------|--------|
| **HIGH_IMPACT_EVENT** | High-Impact Events pillar (dominant) | Regional Risk Backbone (when Europe-relevant) | Theme Pressure, Chokepoint Factor (when gas-relevant) | Supply Pressure, Transit Stress (when gas infrastructure-relevant) |
| **REGIONAL_RISK_SPIKE** | Regional Risk Spikes pillar | Regional Risk Backbone (when region is Europe) | RERI_EU component (when region is Europe) | — |
| **ASSET_RISK_SPIKE** | Asset Risk pillar | Asset Transmission (gas, oil, freight, FX) | Asset Transmission (gas-specific) | Policy Risk (supply-related alert pressure) |
| **Storage Risk (sub-type)** | Asset Risk pillar | Asset Transmission (gas asset) | — | Storage Stress pillar (primary input) |

### 13.2 Why This Matters

Understanding which alerts feed which indices explains index movements. If GERI rises sharply, looking at the High-Impact Events generated that day reveals the specific cause. If EERI rises but GERI doesn't, the driver is likely a Europe-specific Regional Risk Spike or Asset Risk event. If EGSI-S rises without EGSI-M movement, the cause is structural (storage depletion, price volatility) rather than geopolitical.

---

## 14. Regional Energy Exposure

Regions are assigned energy exposure ratings that influence how events from that region are weighted in severity calculations and index contributions.

| Region | Energy Exposure | Rationale |
|--------|----------------|-----------|
| **Middle East** | Highest | Controls approximately 30% of global oil production, key LNG exporter, Strait of Hormuz chokepoint |
| **Black Sea** | Very High | Major oil and gas exporter (Russia), critical pipeline infrastructure, historically the primary source of European gas supply disruption |
| **Europe** | High | Largest energy consuming bloc, critical import dependency, TTF benchmark, extensive pipeline and LNG infrastructure |
| **North Africa** | High | Suez Canal chokepoint, pipeline gas supply to Southern Europe, Libyan oil production volatility |
| **Asia** | Significant | World's largest energy import region, major demand-side force, key LNG consumer |
| **North America** | Significant | Largest oil and gas producer, major LNG exporter, source of most energy-relevant sanctions and policy |
| **Global** | Moderate | Default for events that cannot be regionally attributed |

---

## 15. Taxonomy Governance

### 15.1 Version Control

The alert taxonomy operates under version control. The current production version is **Alerts Engine v2**. All historical alerts are tagged with their generation parameters, ensuring auditability.

### 15.2 Category Evolution

New thematic categories may be added as the intelligence landscape evolves. Any additions follow a formal process: the category must demonstrate distinct disruption characteristics that are not adequately captured by existing categories, and its addition must not degrade classification accuracy for existing events.

### 15.3 Source Updates

The source portfolio is reviewed and updated periodically. New sources must demonstrate:
- Consistent publication of energy-relevant content
- Editorial standards that meet the minimum credibility threshold for their proposed tier
- Geographic or topical coverage that fills a gap in the existing portfolio
- Absence of noise characteristics that would degrade signal quality

---

*The EnergyRiskIQ Alert Taxonomy is a proprietary classification system. This document is provided for transparency and educational purposes. It does not constitute financial advice.*

*Taxonomy Version: v2 | Last Updated: February 2026*
