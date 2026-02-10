# Indices Bible

Development reference for EnergyRiskIQ index architecture and implementation guidance.

---

## 1. Difference Between GERI and RERI (Conceptual & Commercial)

Think of them as two layers of the same intelligence stack.

---

### GERI — Global Geo-Energy Risk Index

**What it answers:**
> "How risky is the global geopolitical & energy environment today?"

| Attribute | Description |
|-----------|-------------|
| **Scope** | Entire world |
| **Output** | One single number per day |
| **Nature** | Macro / regime-level, Strategic, Slow-moving but powerful |

**What it measures:**
- Global escalation pressure
- Systemic instability
- Cross-regional contagion

**Who uses it:**
- Macro traders
- CIOs / risk committees
- Asset allocators
- Strategists
- Media / research

**Typical decisions driven by GERI:**
- Reduce global exposure
- Increase volatility hedges
- Rotate into energy / defense
- De-risk portfolios

**Mental model:**
> GERI = "Global Risk Temperature"
> Like VIX, but for geopolitics & energy.

---

### RERI — Regional Escalation Risk Index

**What it answers:**
> "How dangerous is THIS REGION specifically for markets & supply chains right now?"

| Attribute | Description |
|-----------|-------------|
| **Scope** | One index per region |
| **Output** | Multiple numbers per day |
| **Nature** | Tactical, Actionable, Fast-moving |

**What it measures:**
- Regional escalation pressure
- Probability of disruption
- Spillover risk into assets

**Who uses it:**
- Energy traders
- LNG desks
- Shipping planners
- Insurers
- Procurement teams
- Hedging desks

**Typical decisions driven by RERI:**
- Hedge Middle East exposure
- Reroute shipping
- Secure alternative suppliers
- Adjust gas / oil books
- Price insurance

**Mental model:**
> RERI = "Regional Early-Warning Radar"

---

## 2. The Key Strategic Difference

This is extremely important:

| Index | Role | Purpose |
|-------|------|---------|
| **GERI** | Narrative & Brand Index | Builds authority, SEO, citations, "EnergyRiskIQ Index" brand |
| **RERI** | Commercial Engine | Sells feeds, dashboards, APIs, enterprise contracts |

**In real institutions:**
- GERI is what the board sees
- RERI is what desks pay for

---

## 3. How They Work Together

They should always be presented as:

```
GLOBAL LAYER (GERI)
        ↓
REGIONAL LAYERS (RERI per region)
        ↓
ASSET LAYERS (future indices)
```

**Meaning:**
- GERI explains **why** risk is rising globally
- RERI explains **where** it is dangerous
- Asset indices explain **what** is impacted

This layered architecture is exactly how institutional intelligence systems are built.

---

## 4. What Should the PUBLIC Output of RERI Be?

RERI is too valuable to fully expose publicly.

If you publish it wrong:
- You destroy enterprise value
- You give away your moat
- You reduce pricing power

So we design:
- **Public** = signal teaser
- **Paid** = intelligence
- **Enterprise** = data

### Public RERI Output (Recommended Strategy)

**Principle:** Public RERI should:
- Build SEO
- Build authority
- Build habit
- **NOT** allow reconstruction
- **NOT** give trading advantage

**Rule:** Show only today's value + band + trend, delayed, no history, no components.

### Public RERI Format (Homepage / Region Pages)

Example:
```
Middle East Escalation Index

Value: 88 (CRITICAL)
Trend: +12 vs 7-day average
Status: Escalation risk elevated

Drivers:
• Iran unrest intensifies
• Gaza escalation expands
• Red Sea shipping threats

⚠️ Informational only. Not financial advice.
🔒 Full history, charts, and signals available to subscribers.
```

### What NOT to Show Publicly

Very important — do NOT show:
- Time series
- 7/30/90 day charts
- Component values (S, H, O, V)
- Exact formula
- Asset overlaps
- Intraday updates
- Confidence metrics

**Why?** With history + daily points, someone can rebuild your index for free. That kills your moat.

### Paid RERI Output (Pro Users)

This is where RERI becomes very powerful. For logged-in Pro users:

**Per Region Dashboard - Show:**
- Current value
- Band
- Trend
- 90-day curve
- Band history
- Escalation warnings

**Example widgets:**
- "Days in CRITICAL (last 30d): 7"
- "Escalation velocity: FAST"
- "Asset pressure: Gas + Freight"

**Still do NOT show:**
- Raw components
- Weights
- Internal caps

### Enterprise RERI Output (Licensable)

This is your real gold. Enterprise clients get:
- Full historical daily series
- Raw component columns
- Asset overlaps
- Velocity
- Driver IDs
- API

**Pricing guidance:**
- €10k–€50k / region / year
- €50k–€120k full pack

---

## 5. Public Positioning (Brand Strategy)

Present the two indices differently:

### GERI — Public Flagship

On homepage:
```
🔥 Today's Global Energy Risk Index (GERI): 71 — ELEVATED
Trend: +9 vs 7-day average
```

This becomes:
- Your brand index
- SEO anchor
- Citation object

### RERI — Public Regional Radar

On region pages:
```
🌍 Middle East Escalation Index: 88 — CRITICAL
Trend: +12
Key escalation signals detected
```

This builds:
- Region SEO
- Institutional credibility
- Subscription funnel

---

## 6. Strategic Truth

In real markets:
- Global indices are **branding tools**
- Regional indices are **revenue engines**

Almost all big data providers make money from:
- Regional risk
- Country risk
- Sector risk

**Not** from global aggregates.

By building GERI (global) + RERI (regional), you are positioning EnergyRiskIQ as:

> "The reference geopolitical & energy risk layer"

Which is exactly where these players operate:
- Verisk
- Eurasia Group
- Stratfor
- Refinitiv
- ICE Data

---

## 7. Final Recommendation (Access Tiers)

### Public (Free)
Publish:
- GERI daily (24h delayed)
- RERI daily per region (24h delayed)

Show only:
- Value
- Band
- Trend
- Top 2–3 drivers

**No charts. No history. No components.**

### Pro (€49–€149)
- Live GERI
- Live RERI
- Charts (90 days)
- Band history
- Escalation warnings

### Enterprise
- Feeds
- APIs
- History
- Components
- Asset overlaps

---

## 8. Core Questions Each Index Answers

| Index | Question |
|-------|----------|
| **GERI** | "Is the world dangerous today?" |
| **RERI** | "Where will my money / cargo / gas / insurance break first?" |

**In institutions:**
- GERI builds **reputation**
- RERI builds **revenue**

---

## Implementation Status

| Index | Status | Location |
|-------|--------|----------|
| GERI v1 | ✅ Complete | `src/geri/` |
| RERI | 🔜 Planned | TBD |
| Asset Indices | 📋 Future | TBD |

---

*Last updated: January 2026*
