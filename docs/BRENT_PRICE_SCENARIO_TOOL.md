# Brent Price Scenario Tool — Product & Design Reference

Working document consolidating all strategy, positioning, timing, forecast-horizon, and monetization decisions for the Brent Price Scenario Tool (and the broader Forecast Desk vision). Use this as the source of truth when developing and building the tool.

---

## 1. Positioning

- **Do NOT position this as a price forecaster.** Position it as a **Brent Market Reaction Simulator** — it models how the market could *react* to today's risk conditions, not the intrinsic future value of oil.
- Core public question the tool answers:
  > "If geopolitical and market conditions changed today, how could Brent react over the next 24–48 hours?"
- This aligns with EnergyRiskIQ's "Risk Moves First" positioning and leverages the platform's unique assets: **GERI (daily + Live), VIX, Intelligence Alerts, Daily Intelligence Report**.
- Avoid long-horizon single-price claims (e.g. "Brent in 90 days: $86.40") — experienced traders find these non-credible.

## 2. Forecast Horizon Ladder (the product structure)

Short horizons (hours/days) are strongly preferred over 7/30/90 days because they match the platform's data strengths and real trader behavior ("How will X affect Brent tomorrow?").

| Horizon | Access | Data Used | Confidence | Purpose |
|---|---|---|---|---|
| **24–48h Market Reaction Scenario** | Public (free) | Daily GERI + VIX + latest daily intelligence | High | Lead generation / SEO |
| **0–24h Live Forecast** | Premium | GERI Live + Intelligence Alerts + intraday Brent + intraday VIX + event severity + historical analogs | Very High | Active traders — the product people will actually pay for |
| **72h Tactical Outlook** | Premium | Daily + Live + event-persistence assumptions | Medium | Tactical positioning |
| **7-Day Strategic Outlook** | Premium | Full analyst model (narrative, probabilities, drivers) | Medium | Weekly planning |

Each layer answers a different question:
- **Free (24–48h):** "If current conditions persist, how might Brent react?"
- **0–24h Live:** "What is most likely to happen before tomorrow?"
- **72h Tactical:** "How could this event develop over the next few trading sessions?"
- **7-Day Strategic:** "What are the key risks, scenarios, and probabilities for the coming week?"

### Naming rules
- Public tier is called **"24–48 Hour Market Reaction Scenario"** — never plain "forecast".
- Use **"Market Reaction Horizon"** rather than "Time Horizon" in the UI.
- If longer ranges are ever offered, label them honestly: "7-Day Scenario Impact", "30-Day Scenario Projection", "90-Day Risk Path" — never "90-Day Brent Forecast".

## 3. Output Format Rules

- **Ranges, not point prices**, with uncertainty bands that widen with horizon:
  - ~±2% for short (24–72h / 7D-class), ±5% for 30D-class, ±10% for 90D-class projections.
- Confidence **decreases** as horizon grows and must be displayed (High → Medium → Low).
- Example premium 0–24h output block:
  - GERI Live value + intraday change since London open
  - Latest alerts with GERI-point contributions (e.g. "Missile strike +12 GERI points")
  - Current Brent
  - Expected 24h range (e.g. $76.80–78.10) + Confidence (e.g. 82%)
- 7-Day Outlook must be more than a number: **Bias** (Bullish/Bearish), **Expected Range**, **Probability**, **Primary Drivers** (bullets), **Main Risk**.
- Longer-horizon display language:
  > "90-Day Scenario Range — If this risk environment persists: $78–$92. Directional Bias: Bullish. Confidence: Low / scenario-based."

## 4. Freshness Indicator (differentiator)

Show a "Forecast Freshness" element competitors lack:
- "Updated 3 minutes ago"
- "Based on 127 intelligence events"
- Current GERI Live value
- Optionally "Next update in ~12 minutes"

The 24h premium forecast should be **dynamic** — re-run whenever GERI Live / VIX change materially. The 48h is a moderate extension; 72h is the longest tactical horizon.

## 5. Best-Time-To-Use Guidance (page copy)

Do **not** advise a single fixed time (e.g. "best at 11:30"). Brent is a global market.

Recommended usage window:

| Time (UTC) | Recommendation |
|---|---|
| 08:00–10:00 | ⭐⭐⭐⭐⭐ Best time to run the forecast |
| 10:00–13:00 | Very good |
| After major geopolitical news | Run immediately |
| After OPEC/OPEC+ announcements | Run immediately |
| After major EIA/IEA reports | Run immediately |

Rationale: Asia has digested overnight developments, European energy trading is underway, overnight geopolitics is reflected in GERI, previous US session VIX/Brent context is available.

**Exact page copy to use:**
> "Best used daily after the latest EnergyRiskIQ Daily Intelligence update (typically from 08:00 UTC onward), and again after major geopolitical or OPEC-related developments."

Intended daily workflow: read Daily Intelligence Report → open Brent tool → run own scenario. Refresh the tool immediately after the Daily Intelligence Report and GERI calculation are published.

## 6. Freemium Conversion Design

Make the free 24–48h scenario **intentionally useful but incomplete**:

**Show free:**
- Expected Brent range
- Bullish/Bearish bias
- Confidence level
- One-line explanation

**Blur/lock (premium):**
- Driver contributions (GERI vs. VIX vs. other factors)
- Historical analogs
- Probability distribution
- AI reasoning
- Alternative scenarios

Locking the *depth of explanation* converts better than locking extra time horizons — visitors see the model works, but the professional-grade reasoning is behind the paywall.

## 7. Business Model — Forecast Desk (bundling strategy)

Do **not** sell four separate forecasters (Brent €9, WTI €9, LNG €9, NatGas €9). Sell **one professional forecasting workspace**: **EnergyRiskIQ Forecast Desk** (~€29/month framing).

Why bundle:
1. **Higher perceived value** — "Is a forecast platform worth €29?" beats "Is Brent worth €9?".
2. **Every public tool becomes a lead magnet** ending in "Unlock the full Forecast Desk". One destination, one subscription.
3. **Retention** — multi-tool daily-workflow users are far less likely to cancel than single-tool users.
4. **Branding** — a platform (Bloomberg/Refinitiv/Kpler feel), not a collection of calculators.

### Pricing ladder
1. **Free (public):** public tools, limited scenarios, public intelligence, SEO pages.
2. **Free Account:** basic Forecast Desk, limited horizons, saved recent scenarios, daily snapshots.
3. **Forecast Desk Pro (one subscription):** all four forecasters, unlimited scenarios, Historical Analog Engine, Scenario Library, Daily Intelligence, watchlists, saved forecasts, PDF exports, AI explanations, intraday GERI integration.

### Forecast Desk dashboard structure (modules, not "tools")
- **Oil:** Brent Forecast, WTI Forecast
- **Gas:** TTF Forecast, JKM LNG Forecast
- **Scenarios:** Scenario Library, AI Scenario Builder
- **Risk:** GERI, EERI, EGSI
- **Analysis:** Daily Intelligence, Historical Analogs, Market Commentary
- Plus: Market Stress Dashboard, Saved Scenarios, My Watchlist, Forecast History

Goal mindset shift: from "I'm paying for a Brent calculator" to "I'm subscribing to an Energy Market Intelligence Platform."

## 8. Modeling Principles

- Short-horizon model asks only: *"If today's conditions remain unchanged over the next 24/48/72 hours, what is the likely market reaction?"* — far more defensible than long-range prediction.
- 72h model assumes **event persistence**: "If today's situation continues over the next three days, how might Brent evolve?"
- Inputs the visitor can adjust in scenarios: GERI change (e.g. +40%), VIX change (e.g. +20%) → expected price, likely move %, confidence per horizon.
- Confidence pattern example: 24h High, 48h Medium, 72h Medium (declining).

## 9. Public Tool Ecosystem (lead magnets)

Public tools that funnel into Forecast Desk:
- Brent Scenario Tool (this tool)
- WTI Scenario Tool
- LNG Scenario Tool
- Gas Storage Calculator
- Risk Correlation Explorer
