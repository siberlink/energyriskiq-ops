# Asset Mapping Definitions

## EnergyRiskIQ Monitored Asset Classes and Index Relationships

### Version 1 | EnergyRiskIQ

---

## 1. What Is the Asset Map?

EnergyRiskIQ monitors five asset classes that together define the quantitative landscape of global energy risk. Each asset represents a distinct dimension of energy market stress — from the price of the world's most-traded crude oil benchmark to the physical volume of gas sitting in underground storage caverns across Europe.

The asset map serves two purposes:

1. **Measurement** — Each asset provides a quantitative signal that feeds into one or more of the platform's risk indices (GERI, EERI, EGSI-M, EGSI-S).
2. **Transmission** — Each asset acts as a transmission mechanism through which geopolitical and operational events convert into observable market effects.

Understanding what each asset measures, where its data comes from, and how it connects to the indices is essential for interpreting the intelligence the platform produces.

---

## 2. Asset Definitions

### 2.1 Brent Crude Oil

**Full Name:** ICE Brent Crude Oil Futures (front-month contract)

**Commodity Code:** BRENT_CRUDE_USD

**Unit of Measurement:** US dollars per barrel (USD/bbl)

**What It Measures:**
Brent Crude is the international benchmark for crude oil pricing. It is the reference price for approximately two-thirds of the world's internationally traded crude oil supply. Brent reflects the marginal cost of crude oil from the North Sea, adjusted by global supply-demand dynamics, geopolitical risk, and financial market positioning.

**Why It Matters for Energy Risk:**
Brent is the single most important price signal in global energy markets. Virtually every geopolitical event that threatens oil production, transit, or demand manifests as a movement in the Brent price. A missile strike on a Middle Eastern refinery, an OPEC production cut, a Suez Canal blockage, or a hurricane in the Gulf of Mexico will all register in the Brent price — often within minutes.

Brent is not merely a passive thermometer; it is a leading indicator of market stress. Sharp Brent moves frequently precede broader economic effects: inflation pressure, central bank responses, trade balance shifts, and downstream energy cost increases for consumers and industry.

**Additional Coverage — WTI Crude:**
The platform also captures West Texas Intermediate (WTI) crude oil prices (commodity code: WTI_USD, unit: USD/bbl). WTI is the primary benchmark for North American crude oil and is relevant for understanding US-centric supply dynamics and the Brent-WTI spread.

**Brent-WTI Spread:**
The difference between Brent and WTI prices is calculated and stored as a separate metric. This spread reflects the relative balance between Atlantic Basin and US domestic crude markets. A widening spread often signals logistics constraints, sanctions effects, or regional supply disruptions that affect one benchmark more than the other.

**Data Source:**
- **Provider:** OilPriceAPI (https://docs.oilpriceapi.com/)
- **API Key:** OIL_PRICE_API_KEY
- **Update Frequency:** Daily (end-of-day close)
- **Capture Timing:** Prices are captured for the previous day (T-1), representing end-of-day settlement values
- **Data Stored:** Price, 24-hour change (absolute and percentage), Brent-WTI spread, source metadata
- **Storage Table:** `oil_price_snapshots`
- **Idempotency:** One record per date; duplicate fetches are safely merged via ON CONFLICT

**Data Captured per Snapshot:**

| Field | Description |
|-------|-------------|
| Date | Trading date for the price capture |
| Brent Price | ICE Brent front-month closing price (USD/bbl) |
| Brent 24h Change | Absolute price change vs previous trading day |
| Brent 24h Change % | Percentage change vs previous trading day |
| WTI Price | NYMEX WTI front-month closing price (USD/bbl) |
| WTI 24h Change | Absolute price change vs previous trading day |
| WTI 24h Change % | Percentage change vs previous trading day |
| Brent-WTI Spread | Brent minus WTI (USD/bbl) |
| Source | Data provider identifier |

---

### 2.2 TTF Natural Gas

**Full Name:** Dutch Title Transfer Facility Natural Gas Futures

**Commodity Code:** DUTCH_TTF_EUR

**Unit of Measurement:** Euros per megawatt-hour (EUR/MWh)

**What It Measures:**
TTF is Europe's primary natural gas benchmark. It is the virtual trading point for natural gas in the Netherlands and has become the de facto reference price for piped and LNG gas across the European continent. TTF reflects the European gas supply-demand balance, pipeline transit capacity utilisation, LNG cargo economics, and seasonal storage dynamics.

**Why It Matters for Energy Risk:**
TTF is the most volatile major energy commodity benchmark. During the 2021-2022 European energy crisis, TTF prices increased from approximately €15/MWh to over €300/MWh — a twenty-fold increase that fundamentally reshaped European energy policy, industrial competitiveness, and consumer welfare.

TTF responds to a uniquely wide range of risk factors:
- **Pipeline disruption** — Any interruption to Russian, Norwegian, or North African pipeline flows immediately affects TTF pricing
- **LNG cargo competition** — When Asian LNG prices rise, European TTF must rise to attract cargoes, creating intercontinental competition
- **Storage dynamics** — Storage fill rates, injection/withdrawal patterns, and winter readiness directly influence forward TTF pricing
- **Weather** — Cold snaps increase heating demand and drive TTF higher; mild winters suppress it
- **Regulatory changes** — EU gas storage mandates, price caps, and joint purchasing mechanisms all influence TTF dynamics

TTF is the primary market input for both EGSI-M (market stress) and EGSI-S (system stress), making it the most important quantitative signal in the gas-specific indices.

**Data Source:**
- **Provider:** OilPriceAPI (https://docs.oilpriceapi.com/)
- **API Key:** OIL_PRICE_API_KEY (shared with Brent/WTI)
- **Update Frequency:** Daily (end-of-day close)
- **Capture Timing:** Previous day (T-1) settlement values
- **Historical Backfill:** Available via `past_week` (free tier) or `past_year` (Production Boost+) endpoints. Multiple intraday prices are consolidated to the latest price per day.
- **Storage Table:** `ttf_gas_snapshots`
- **Idempotency:** One record per date

**Data Captured per Snapshot:**

| Field | Description |
|-------|-------------|
| Date | Trading date for the price capture |
| TTF Price | Front-month closing price (EUR/MWh) |
| Currency | Price currency (EUR) |
| Unit | Price unit (EUR/MWh) |
| Source | Data provider identifier |

---

### 2.3 CBOE Volatility Index (VIX)

**Full Name:** CBOE Volatility Index (ticker: ^VIX)

**Unit of Measurement:** Index points (dimensionless, typically ranging 10-80)

**What It Measures:**
The VIX measures the market's expectation of 30-day forward-looking volatility in the S&P 500, derived from options prices. It is widely known as the "fear gauge" of global financial markets. A high VIX indicates that options traders expect significant price movement — in either direction — over the coming month.

**Why It Matters for Energy Risk:**
The VIX is not an energy-specific indicator, but it captures a dimension of risk that energy-only metrics miss: **financial market contagion**. Energy crises do not occur in isolation. They interact with broader financial stress — credit conditions, equity volatility, currency movements, and sovereign risk — in ways that amplify or dampen their impact.

Key VIX-energy interactions:
- **Risk-off cascades** — When VIX spikes (typically above 30), capital flows to safe-haven assets. Energy commodities can experience simultaneous selling pressure from financial participants, even if physical supply fundamentals are tight.
- **Correlation amplification** — During high-VIX environments, traditionally uncorrelated asset classes begin moving together. Oil, gas, equities, and currencies can all decline simultaneously, creating compounding risk.
- **Hedging cost signal** — VIX levels directly influence the cost of hedging energy positions. A high VIX makes options more expensive, potentially leaving energy consumers and producers more exposed.
- **Macro stress indicator** — VIX above 25-30 often coincides with periods of elevated geopolitical tension, recession fears, or financial instability — all of which affect energy demand and investment flows.

**Data Sources (Dual-Provider with Automatic Fallback):**

**Primary — Yahoo Finance (yfinance):**
- **Ticker:** ^VIX
- **Data Type:** Full OHLC (Open, High, Low, Close) daily candles
- **API Key:** Not required (free public API)
- **Reliability:** Generally reliable but occasionally experiences service interruptions or data delays

**Fallback — FRED (Federal Reserve Bank of St. Louis):**
- **Series ID:** VIXCLS
- **Data Type:** Closing prices only (no OHLC)
- **API Key:** Not required (free CSV endpoint)
- **Endpoint:** `https://fred.stlouisfed.org/graph/fredgraph.csv?id=VIXCLS`
- **Reliability:** Extremely reliable as a government data source, though may have 1-2 day reporting lag

**Fallback Logic:**
The system attempts Yahoo Finance first. If yfinance returns no data (service outage, timeout, or data unavailability), it automatically falls back to FRED. When FRED data is used, only closing prices are available — open, high, and low values are recorded as zero to distinguish FRED-sourced records from full yfinance records.

**Storage Table:** `vix_snapshots`
**Idempotency:** One record per date; yfinance data (with full OHLC) takes precedence over FRED data (close only) if both are available for the same date.

**Data Captured per Snapshot:**

| Field | Description |
|-------|-------------|
| Date | Trading date |
| VIX Close | End-of-day VIX value |
| VIX Open | Opening VIX value (yfinance only; 0 from FRED) |
| VIX High | Intraday high (yfinance only; 0 from FRED) |
| VIX Low | Intraday low (yfinance only; 0 from FRED) |
| Source | Data provider identifier ("yfinance" or "fred") |

---

### 2.4 EUR/USD Exchange Rate

**Full Name:** Euro / US Dollar Spot Exchange Rate

**Currency Pair:** EUR/USD

**Instrument Code:** EUR_USD (Oanda instrument identifier)

**Unit of Measurement:** US dollars per euro (e.g., 1.0850 = €1 buys $1.085)

**What It Measures:**
The EUR/USD exchange rate is the world's most-traded currency pair. It reflects the relative economic strength, interest rate differential, trade balance, and capital flow dynamics between the Eurozone and the United States.

**Why It Matters for Energy Risk:**
EUR/USD is the critical macro confidence indicator for EnergyRiskIQ's European-centric risk framework. Because Brent crude oil and many LNG contracts are priced in US dollars, while European consumers and industry pay in euros, the exchange rate acts as a multiplier on energy costs for European buyers.

Key EUR/USD-energy interactions:
- **Dollar-denominated commodity amplifier** — When EUR weakens against USD, the same barrel of oil or cargo of LNG becomes more expensive in euro terms, even if the dollar price is unchanged. A 10% EUR depreciation effectively increases European energy import costs by 10%.
- **European macro stress signal** — EUR/USD below 1.00 (parity) historically coincides with periods of severe European economic stress, often driven by energy crises. The EUR/USD decline during the 2022 energy crisis reflected market concern about European industrial competitiveness and current account deterioration.
- **Risk sentiment proxy** — EUR/USD movement during geopolitical events signals how global capital views relative safety. USD strengthening (EUR/USD declining) during a Middle Eastern crisis indicates global risk aversion, while EUR strength signals confidence in European resilience.
- **Central bank divergence** — ECB/Fed policy divergence affects EUR/USD, which in turn affects European energy procurement costs and corporate hedging economics.

**Special FX Directional Conventions:**
Unlike commodities where "up" means price increase, FX risk uses sentiment-based directional language:
- **Risk-off** — EUR weakening / USD strengthening, indicating defensive positioning and typically coinciding with broader market stress
- **Risk-on** — EUR strengthening / USD weakening, indicating confidence and typically coinciding with improving risk appetite
- **Mixed** — Conflicting signals with no clear directional bias

**Data Source:**
- **Provider:** Oanda REST API v20 (https://developer.oanda.com/rest-live-v20/)
- **API Keys:** OANDA_API_KEY, OANDA_ACCOUNT_ID
- **Endpoint:** Production (api-fxtrade.oanda.com/v3)
- **Data Type:** Daily candles with mid-price OHLC (Open, High, Low, Close), precision to 5-6 decimal places
- **Capture Logic:** Uses the last completed daily candle. If the daily candle is incomplete (current trading day), falls back to the last completed 4-hour (H4) candle as an approximation.
- **Storage Table:** `eurusd_snapshots`
- **Idempotency:** One record per date

**Data Captured per Snapshot:**

| Field | Description |
|-------|-------------|
| Date | Trading date |
| Rate | EUR/USD mid-price closing rate (5-6 decimal precision) |
| Currency Pair | "EUR/USD" |
| Source | "oanda" (daily candle) or "oanda_4h_fallback" (4-hour approximation) |
| Open | Session opening mid-price |
| High | Session high mid-price |
| Low | Session low mid-price |
| Close | Session closing mid-price |
| Volume | Tick volume for the candle period |

---

### 2.5 EU Gas Storage (AGSI+)

**Full Name:** Aggregated Gas Storage Inventory (GIE AGSI+ Platform)

**Operator:** Gas Infrastructure Europe (GIE)

**Unit of Measurement:** Multiple metrics — percentage full (%), terawatt-hours (TWh), TWh/day (flow rates)

**What It Measures:**
AGSI+ tracks the physical volume of natural gas stored in underground storage facilities across the European Union. It reports EU-aggregate and country-level data on storage fill levels, daily injection and withdrawal volumes, and working gas capacity. This is the definitive source for European gas storage intelligence.

**Why It Matters for Energy Risk:**
Gas storage is Europe's primary buffer against supply disruption. Underground storage facilities hold gas injected during the summer months for withdrawal during winter heating season. The storage level at any given time — relative to seasonal norms and regulatory targets — is the single most important indicator of European gas supply security.

Key storage dynamics:
- **Seasonal cycle** — Europe follows a predictable injection/withdrawal pattern: injection from April through October (building reserves), withdrawal from November through March (consuming reserves for heating). Deviations from this pattern signal stress.
- **Regulatory mandates** — EU Regulation 2022/1032 requires member states to reach 90% storage fill by November 1st each year. Failure to meet this target triggers market anxiety and potential policy intervention.
- **Winter survival arithmetic** — Storage levels determine how many days of heating demand Europe can sustain if pipeline imports are disrupted. This "days of supply" calculation is a critical input to winter risk assessment.
- **Price signal** — Storage levels directly influence TTF gas prices. Low storage drives prices higher as the market prices in scarcity risk; high storage suppresses prices by reducing supply anxiety.
- **Refill speed** — The rate of injection during summer determines whether Europe will reach its November target. Slow refill rates in June-August signal potential winter shortfalls.

**Monitored Countries:**
While the platform reports EU-aggregate data, it also tracks storage at the country level for the ten largest EU storage operators: Germany (DE), Italy (IT), France (FR), Austria (AT), Netherlands (NL), Poland (PL), Czech Republic (CZ), Hungary (HU), Slovakia (SK), and Belgium (BE).

**Seasonal Norms:**
The system maintains monthly seasonal norm baselines against which current storage levels are compared:

| Month | Seasonal Norm (% Full) | Season Phase |
|-------|----------------------|--------------|
| January | 65% | Winter withdrawal |
| February | 50% | Late winter drawdown |
| March | 40% | End of withdrawal season |
| April | 45% | Early injection season |
| May | 55% | Injection ramp-up |
| June | 65% | Mid injection season |
| July | 75% | Peak injection |
| August | 82% | Approaching target |
| September | 88% | Near-target territory |
| October | 92% | Pre-winter peak |
| November | 90% | EU regulatory target (90% by Nov 1) |
| December | 80% | Early winter withdrawal |

**Winter Deviation Risk Levels:**
During winter months (November–March), storage is assessed against specific targets:

| Risk Level | Winter Condition |
|------------|-----------------|
| LOW | Storage at or above target |
| MODERATE | Storage within 20 points of target |
| ELEVATED | Storage within 10 points of target |
| CRITICAL | Storage below target |

During non-winter months, deviation risk is assessed against the November target minus seasonal offsets.

**Storage Alert Sub-Types:**
The storage monitoring system generates three distinct alert sub-types based on the triggering condition:

| Sub-Type | Trigger | Description |
|----------|---------|-------------|
| STORAGE_DEVIATION | Deviation from seasonal norm exceeds -15% | Current fill level significantly below where it should be for the time of year |
| WINTER_RISK | Winter deviation risk is ELEVATED or CRITICAL | Direct threat to winter heating supply security |
| STORAGE_LEVEL | Risk score threshold crossed | General storage stress alert when risk score reaches alertable levels |

**Data Source:**
- **Provider:** GIE AGSI+ Transparency Platform (https://agsi.gie.eu/)
- **API Documentation:** https://www.gie.eu/transparency-platform/GIE_API_documentation_v007.pdf
- **API Key:** GIE_API_KEY
- **Endpoint:** `https://agsi.gie.eu/api`
- **Update Frequency:** Daily (T-1 reporting lag — data published for the previous gas day)
- **Storage Table:** `gas_storage_snapshots`
- **Idempotency:** One record per date

**Data Captured per Snapshot:**

| Field | Description |
|-------|-------------|
| Date | Gas day (AGSI+ reporting date, typically T-1) |
| EU Storage % | EU-wide storage fill percentage |
| Gas in Storage (TWh) | Total gas volume in EU storage facilities |
| Working Gas Volume (TWh) | Total EU working gas capacity |
| Injection (TWh) | Daily injection volume |
| Withdrawal (TWh) | Daily withdrawal volume |
| Trend | Day-over-day change in fill level |
| Consumption (TWh) | EU daily gas consumption estimate |

**Derived Metrics (Computed from Snapshots):**

| Metric | Description |
|--------|-------------|
| Deviation from Norm | Current fill % minus seasonal norm % |
| Refill Speed (7d) | Average daily injection rate over the trailing 7 days |
| Withdrawal Rate (7d) | Average daily withdrawal rate over the trailing 7 days |
| Winter Deviation Risk | Categorical risk assessment (LOW/MODERATE/ELEVATED/CRITICAL) |
| Days to Target | Estimated days until storage drops below target at current withdrawal rate |
| Risk Score | Composite 0-100 risk score incorporating all storage metrics |
| Risk Band | Categorical band derived from risk score |

---

## 3. Freight (Baltic Dry Index)

**Full Name:** Baltic Dry Index (BDI)

**Status:** MONITORED BUT DATA UNAVAILABLE

**Unit of Measurement:** Index points

**What It Measures:**
The BDI measures the cost of shipping dry bulk commodities (coal, iron ore, grain) on major maritime routes. While not an energy commodity itself, it reflects maritime trade capacity, shipping lane stress, and global trade flow dynamics that directly affect energy logistics.

**Why It Is Monitored:**
Freight risk is a critical transmission mechanism for energy supply disruption. When the Suez Canal is blocked, when Houthi attacks disrupt Red Sea shipping, or when Baltic Sea trade routes are affected by military activity, freight costs spike and energy cargo economics shift. The platform tracks freight as a monitored asset class within its risk scoring framework.

**Why Data Is Currently Unavailable:**
The Baltic Dry Index is published by the Baltic Exchange, which requires a paid institutional subscription (approximately $500+/month). The platform's risk engine includes freight as a monitored asset class, and AI impact analysis produces freight directional assessments, but live BDI data is not ingested.

**Freight Risk Scoring:**
Despite the absence of live BDI data, freight risk is still computed through the AI enrichment pipeline. When events are analysed by AI, freight impact and directional assessment are generated alongside oil, gas, and FX. This intelligence-derived freight risk feeds into the GERI Asset Risk pillar and EERI Asset Transmission component.

**Future Availability:**
When a Baltic Exchange subscription is obtained, the platform is pre-built to ingest BDI data via the `freight_snapshots` table, using the same daily snapshot architecture as all other asset classes.

---

## 4. Asset-to-Index Mapping

Each asset feeds into specific indices through defined transmission channels. Understanding this mapping explains why indices move — and which assets are driving the movement.

### 4.1 GERI (Global Energy Risk Index)

GERI is the platform's headline index, measuring aggregate global energy risk on a 0-100 scale. Assets contribute to GERI primarily through the **Asset Risk** pillar, which is one of four GERI components.

| Asset | GERI Contribution | Transmission Mechanism |
|-------|-------------------|----------------------|
| **Brent Crude** | Asset Risk pillar — Oil component | AI-derived directional assessment and risk confidence from news events mentioning oil supply, pricing, and infrastructure. Sharp Brent moves amplify the GERI signal. |
| **TTF Gas** | Asset Risk pillar — Gas component | AI-derived gas risk assessment. Also indirectly contributes via storage-related events that generate High-Impact Event and Regional Risk Spike alerts. |
| **VIX** | Not a direct GERI input | VIX does not feed directly into GERI computation. Its influence is indirect — high VIX environments tend to coincide with periods of elevated geopolitical risk, which generates more high-severity events that do feed GERI. |
| **EUR/USD** | Asset Risk pillar — FX component | AI-derived FX risk assessment using risk-on/risk-off directional conventions. EUR weakness during energy crises amplifies the FX risk component. |
| **Storage** | Asset Risk pillar — Gas component (via storage alerts) | Storage risk alerts are classified as ASSET_RISK_SPIKE events and contribute to both the High-Impact Events and Asset Risk pillars. |
| **Freight** | Asset Risk pillar — Freight component | AI-derived freight directional assessment from maritime and trade events. Contributes even without live BDI data. |

**GERI Dashboard Asset Display:**
- **Free tier:** Simplified 3-category drivers (Geopolitical, Energy Supply, Market Stress) with 14-day Brent chart
- **Personal tier:** Expanded drivers with regions and severity, single asset selector
- **Trader tier:** Full history, 2 simultaneous overlays (e.g., Brent + TTF), smoothing options, regime markers, momentum panel
- **Pro tier:** 4 overlays, AI narrative access
- **Enterprise tier:** 5 overlays, team workspace

### 4.2 EERI (European Escalation Risk Index)

EERI measures Europe-specific escalation risk. Assets contribute through the **Asset Transmission** component, which captures how geopolitical events transmit into observable market stress for European-relevant assets.

| Asset | EERI Contribution | Transmission Mechanism |
|-------|-------------------|----------------------|
| **Brent Crude** | Asset Transmission — Oil stress | European oil supply disruption risk. Brent is the primary pricing reference for European crude imports. |
| **TTF Gas** | Asset Transmission — Gas stress (primary) | The single most important EERI asset input. TTF stress is the most direct indicator of European energy supply risk. Gas-related events carry elevated influence in EERI. |
| **VIX** | Not a direct EERI input | Indirect influence via market stress correlation. |
| **EUR/USD** | Asset Transmission — FX stress | EUR weakness signals European macro fragility and increases euro-denominated energy costs. |
| **Storage** | Asset Transmission — Gas stress (via storage alerts) | Storage risk directly feeds EERI's gas stress component. Below-norm storage and winter risk alerts are among the strongest EERI drivers. |
| **Freight** | Asset Transmission — Freight stress | Maritime logistics stress affecting European energy imports (LNG cargo competition, Baltic shipping disruption). |

### 4.3 EGSI-M (Europe Gas Stress Index — Market/Transmission)

EGSI-M measures how external geopolitical pressure transmits into European gas market stress. It is intelligence-driven, not market-data-driven.

| Asset | EGSI-M Contribution | Transmission Mechanism |
|-------|---------------------|----------------------|
| **Brent Crude** | Indirect (via oil-gas correlation) | Oil supply events that spill over into gas markets (e.g., OPEC cuts that shift LNG demand patterns). |
| **TTF Gas** | Theme Pressure, Chokepoint Factor | Gas-specific intelligence events that carry TTF implications. However, EGSI-M does not directly ingest TTF price data — it measures the intelligence pressure that drives TTF moves. |
| **VIX** | Not an EGSI-M input | Market volatility is outside EGSI-M's scope. |
| **EUR/USD** | Not an EGSI-M input | Currency dynamics are outside EGSI-M's scope. |
| **Storage** | Not a direct EGSI-M input | Storage is the domain of EGSI-S. EGSI-M captures the geopolitical events that may threaten storage (pipeline disruption, sanctions on gas exports). |
| **Freight** | Chokepoint Factor | Maritime chokepoint events (Strait of Hormuz, Bab el-Mandeb, Turkish Straits) that affect LNG or pipeline gas transit. |

### 4.4 EGSI-S (Europe Gas Stress Index — System)

EGSI-S measures structural gas system stress using quantitative market data rather than intelligence signals. This is where asset data feeds most directly into index computation.

| Asset | EGSI-S Contribution | Transmission Mechanism |
|-------|---------------------|----------------------|
| **Brent Crude** | Not a direct EGSI-S input | Oil pricing is outside EGSI-S's gas-specific scope. |
| **TTF Gas** | Market Stress pillar (primary input) | TTF price level, price volatility, and deviation from moving averages directly feed the Market Stress pillar. TTF is the primary market data input to EGSI-S. |
| **VIX** | Not a direct EGSI-S input | Financial volatility is outside EGSI-S's scope. |
| **EUR/USD** | Not a direct EGSI-S input | Currency dynamics are outside EGSI-S's scope. |
| **Storage** | Storage Stress pillar (primary input) | EU storage levels, deviation from seasonal norms, injection/withdrawal rates, and winter readiness assessments are the dominant EGSI-S inputs. Storage data is the single most important data source for EGSI-S. |
| **Freight** | Not a direct EGSI-S input | Maritime logistics are outside EGSI-S's scope (captured by EGSI-M). |

---

## 5. Cross-Asset Summary Matrix

| Asset | Primary Role | Data Source | Update Cadence | GERI | EERI | EGSI-M | EGSI-S |
|-------|-------------|-------------|----------------|------|------|--------|--------|
| Brent Crude | Global oil benchmark | OilPriceAPI | Daily (T-1) | Direct | Direct | Indirect | — |
| WTI Crude | North American oil benchmark | OilPriceAPI | Daily (T-1) | Direct | — | — | — |
| TTF Gas | European gas benchmark | OilPriceAPI | Daily (T-1) | Direct | Direct (primary) | Indirect | Direct (primary) |
| VIX | Financial volatility gauge | Yahoo Finance / FRED | Daily | Indirect | Indirect | — | — |
| EUR/USD | European macro confidence | Oanda | Daily (T-1) | Direct | Direct | — | — |
| EU Storage | Physical gas reserve level | GIE AGSI+ | Daily (T-1) | Direct | Direct | — | Direct (dominant) |
| Freight (BDI) | Maritime trade cost | Unavailable (Baltic Exchange) | N/A | AI-derived | AI-derived | Direct | — |

**Legend:**
- **Direct** — Asset data or AI-derived asset risk assessment feeds directly into index computation
- **Indirect** — Asset influences the index through correlated events or secondary effects, but is not a computation input
- **AI-derived** — No live market data available; risk contribution is computed from AI analysis of news events
- **—** — No meaningful contribution to this index

---

## 6. Data Collection Architecture

### 6.1 Daily Snapshot Model

All asset data is captured using a standardised daily snapshot architecture:

1. **Scheduled capture** — Data collection runs daily, triggered by the platform's orchestration system
2. **T-1 convention** — Most data sources report with a one-day lag (yesterday's data), ensuring final settlement values
3. **Idempotent storage** — Each snapshot uses ON CONFLICT (date) logic, ensuring that re-running collection for the same date safely updates rather than duplicates
4. **Source attribution** — Every record stores its data source identifier, enabling audit and quality tracking
5. **Raw data preservation** — API response payloads are stored alongside computed values, enabling retroactive recalculation if interpretation logic changes

### 6.2 Fallback Resilience

Each asset data pipeline includes fallback mechanisms to ensure continuity:

| Asset | Primary Source | Fallback Source | Fallback Behaviour |
|-------|---------------|-----------------|-------------------|
| Brent / WTI | OilPriceAPI | None (single source) | Returns error status; indices use most recent available snapshot |
| TTF Gas | OilPriceAPI | None (single source) | Returns error status; EGSI-S uses most recent available snapshot |
| VIX | Yahoo Finance (full OHLC) | FRED (close only) | Automatic fallback; FRED data marked with source="fred" and zero OHLC |
| EUR/USD | Oanda daily candle | Oanda 4H candle | If daily candle incomplete, uses last completed 4-hour candle as approximation |
| EU Storage | GIE AGSI+ API | Database (historical snapshots) | For backfills, uses previously stored snapshots before re-fetching from API |

### 6.3 Historical Backfill

Each asset supports historical data backfill for initialisation and gap-filling:

| Asset | Backfill Capability | Depth |
|-------|-------------------|-------|
| Brent / WTI | Via OilPriceAPI historical endpoints | 7 days (free), 30-365 days (paid tier) |
| TTF Gas | Via OilPriceAPI past_week/past_year | 7 days (free), up to 365 days (Production Boost+) |
| VIX | Via yfinance (primary) or FRED (specific date ranges) | Up to 5000 daily candles via yfinance; full FRED history since 1990 |
| EUR/USD | Via Oanda daily candles | Up to 5000 daily candles (~20 years at daily granularity) |
| EU Storage | Via GIE AGSI+ API date parameter | Daily queries per date; no bulk history endpoint |

---

## 7. Asset Risk Scoring in the Risk Engine

### 7.1 AI-Derived Asset Risk

When news events are ingested and processed by AI, the enrichment pipeline produces an asset impact assessment for each of the four monitored asset classes (oil, gas, FX, freight). This assessment includes:

| Field | Description |
|-------|-------------|
| Direction | Expected price/risk direction: up, down, mixed, unclear (or risk_on/risk_off for FX) |
| Confidence | AI confidence in the directional assessment (0.0-1.0) |

These AI-derived signals are the primary input for the risk engine's asset-level calculations.

### 7.2 Directional Voting System

The risk engine aggregates AI directional assessments across all events within a time window using a weighted voting system:

- Each event "votes" for a direction (up, down, mixed, unclear) with a weight proportional to its overall risk score multiplied by the AI confidence for that specific asset
- The direction with the highest total vote weight wins, subject to tiebreaking rules
- If the two strongest opposing directions (up vs down) are within 20% of each other, the result is classified as "mixed"
- FX uses special directional conventions: risk_on/risk_off instead of up/down

### 7.3 Asset Risk Score Normalisation

Raw asset risk scores are normalised to a 0-100 scale using a rolling maximum method:
- The system tracks the highest daily asset risk score observed over the trailing 90 days
- Current raw scores are divided by this rolling maximum and scaled to 100
- This ensures that asset risk scores are always contextualised against recent history

---

## 8. Asset Interpretation for Subscribers

### 8.1 Dashboard Visualisation

Assets are visualised on subscriber dashboards with plan-tiered access:

| Feature | Free | Personal | Trader | Pro | Enterprise |
|---------|------|----------|--------|-----|------------|
| Brent price chart | 14-day history | 90-day history | Full history | Full history | Full history |
| TTF price chart | — | — | Available | Available | Available |
| VIX overlay | — | — | Available | Available | Available |
| EUR/USD overlay | — | — | Available | Available | Available |
| Storage level chart | — | — | — | Available | Available |
| Simultaneous overlays | — | 1 asset | 2 assets | 4 assets | 5 assets |

### 8.2 Alert Content

When asset-related alerts are delivered to subscribers, they include:

- **Asset identification** — Which asset is affected (oil, gas, FX, freight)
- **Risk score** — Current asset risk score (0-100)
- **Directional bias** — AI-derived direction (up/down/risk_on/risk_off/mixed)
- **Confidence level** — AI confidence in the directional call
- **Driver events** — The specific news events driving the asset risk assessment
- **Regional context** — Which geographic region the asset stress originates from

### 8.3 Daily Digest Asset Summary

The Daily Digest includes a complete asset risk summary showing all four monitored asset classes with their current risk scores, directional biases, and contributing factors. This provides subscribers with a single-glance view of the entire asset risk landscape.

---

## 9. Data Governance

### 9.1 Data Quality Controls

- **Deduplication** — ON CONFLICT (date) ensures no duplicate snapshots
- **Source tracking** — Every record stores its data provider, enabling audit
- **Raw preservation** — Original API responses are stored alongside computed values
- **Fallback marking** — Records from fallback sources are clearly labelled (e.g., "oanda_4h_fallback", "fred")

### 9.2 Data Retention

All asset snapshots are retained indefinitely. Historical depth is essential for:
- Rolling baseline calculations (90-day windows)
- Trend analysis (7-day, 30-day comparisons)
- Seasonal pattern recognition (year-over-year storage comparisons)
- Model calibration and backtesting

### 9.3 API Cost Management

- **OilPriceAPI** — Shared key for Brent, WTI, and TTF. Respects rate limits and tier-appropriate endpoint access
- **Oanda** — Production REST API with per-request rate limits. Uses minimal candle counts (5 for daily capture, larger for backfills)
- **Yahoo Finance** — Free tier with no explicit rate limits but subject to throttling. FRED fallback ensures resilience
- **GIE AGSI+** — API key authenticated. Per-date queries for historical data to avoid bulk endpoint limitations

---

*The EnergyRiskIQ Asset Mapping system is a proprietary data architecture. This document is provided for transparency and educational purposes. It does not constitute financial advice.*

*Asset Mapping Version: v1 | Last Updated: February 2026*
