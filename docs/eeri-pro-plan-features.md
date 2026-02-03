# EERI Pro Plan Dashboard Features (Recommended)

## 1. Core Pro Charts (the backbone)

These are must-have — the backbone of the Pro experience.

### Correlation & Overlay Charts

Each chart should allow overlay + toggle + zoom.

| Chart | Purpose |
|-------|---------|
| **EERI vs Brent Crude** | Spot regime shifts (risk → oil response lag) |
| **EERI vs TTF Gas** | Europe-specific stress signal (very strong value) |
| **EERI vs European Gas (front-month)** | Direct gas market correlation |
| **EERI vs VIX** | Macro risk vs energy-specific divergence |
| **EERI vs Freight Index** | Supply-chain & logistics transmission |

**Pro insight:** Most platforms show price → risk. We show risk → price.

---

## 2. Advanced Time Controls (Pro-only)

Give users control, not just charts.

**Time ranges:**
- 7D / 30D / 90D / Since Launch

**Toggle:**
- Index only
- Asset only
- Overlay mode

**Smoothing:**
- Raw
- 3-day MA
- 7-day MA

This makes the dashboard feel analyst-grade, not retail.

---

## 3. Component Transparency (Pro-exclusive)

This is where Pro really earns its price.

### EERI Component Breakdown

Show normalized values only (never raw):
- RERI_EU contribution
- Theme Pressure
- Asset Transmission
- (Later) Contagion

**Visualize as:**
- Stacked bar
- Donut
- Waterfall

➡️ Users see *why* today is 83, not just *that* it is.

---

## 4. Asset Stress Panel (Highly Valuable)

A compact but powerful module.

### Asset Stress Snapshot

| Asset | Status |
|-------|--------|
| Gas | High |
| Oil | Elevated |
| Freight | Severe |
| FX | Elevated |

**Optional:**
- Directional bias (↑ ↓ ~)
- Color-coded risk bands

This is extremely attractive to traders and analysts.

---

## 5. Top Drivers — Full Version (Pro)

Public sees 2–3 headlines. Pro sees the real engine.

**For each driver:**
- Headline
- Driver class (high impact / spike)
- Theme (geopolitical, energy, supply chain)
- Severity
- Confidence
- Assets affected

**Sort by:**
- Severity
- Confidence
- Asset overlap

This is decision support, not news.

---

## 6. Historical Intelligence (Pro-only)

This is one of the strongest moats.

### Historical Views

- EERI history (daily)
- Risk band history (% of time in CRITICAL, HIGH, etc.)

**Compare:**
- This week vs last week
- This month vs last month

**Optional advanced view:**
- "Last time EERI ≥ 80, what happened next?"

---

## 7. Alerts & Thresholds (Pro)

Let users interact with the index.

**Notify when:**
- EERI crosses 60 / 70 / 80
- Sharp day-over-day change (Δ ≥ X)

**Delivery:**
- In-app
- Email
- Telegram (later)

This alone justifies a monthly subscription.

---

## 8. Daily EERI Intelligence Summary (Pro)

A daily auto-generated brief, tied to the index value.

**Example:**
> "EERI closed at 83 (CRITICAL), driven by war escalation and aviation disruption. Gas and freight remain the most exposed assets. Risk remains elevated compared to the 30-day baseline."

This is:
- Shareable
- Sticky
- High perceived value
- Cheap to generate (data already available)

---

## Optional Pro Add-Ons (for later tiers)

- EERI vs GERI comparison
- EERI vs Middle East RERI (when available)
- "What changed since yesterday?" delta view
- CSV / API export (Enterprise tier)

---

## Minimal Pro Feature Set (v1 lean start)

If starting with the tightest possible Pro v1:

- ✅ EERI vs Brent
- ✅ EERI vs TTF Gas
- ✅ EERI vs VIX
- ✅ EERI vs Freight
- ✅ Component Breakdown
- ✅ Top Drivers (full)
- ✅ Historical chart
- ✅ Daily summary text

**That alone is absolutely worth $49/month.**

---

## Strategic Pricing Insight

What we're offering is not data — it's:
- Context
- Interpretation
- Early signal
- Cross-asset intelligence

Most users cannot build this themselves.

The Pro dashboard should feel like:
> "I can't afford *not* to check this every day."

---

# Component Transparency — Deep Dive

## Why Component Transparency Exists

Most indices do this:
> "The index is 83."

That's it. No explanation. No context. No trust.

**EERI Pro does something different:**
> "The index is 83 — and here is why."

This is the moment where EnergyRiskIQ stops being a number and becomes **decision intelligence**.

---

## The Mental Model for Users

Users should intuitively understand EERI as:
> "A weighted combination of regional risk, themes, and market transmission."

Not formulas. Not math. **Forces.**

Each component answers a different question.

---

## The Four Conceptual Components

### 1. RERI_EU — Regional Risk Backbone

**Question it answers:**
> "How dangerous is the European geopolitical & energy environment right now?"

This is the structural layer:
- Captures war, sanctions, regional escalation
- Aggregates severity, clustering, velocity
- Slow-moving, but powerful
- Hard to fake, hard to ignore

**Conceptually:** This is the ground shaking under Europe.

If RERI_EU is high, EERI cannot be calm — no matter what markets do.

---

### 2. Theme Pressure — Narrative & Structural Stress

**Question it answers:**
> "What types of stress are dominating the risk landscape?"

**Themes include:**
- Geopolitical conflict
- Energy supply disruption
- Trade / logistics stress
- Policy & sanctions

Theme Pressure captures **breadth**, not just intensity:
- Many medium events → pressure builds
- Repeated narratives → structural risk
- Shows what *kind* of crisis this is

**Conceptually:** This is the story the world keeps telling you — louder and louder.

---

### 3. Asset Transmission — Market Reality Check

**Question it answers:**
> "Is this risk actually propagating into markets?"

This connects risk to:
- Gas
- Oil
- Freight
- FX

When multiple asset classes react together, risk is no longer theoretical.

**Conceptually:** This is the bridge between headlines and money.

It tells users: *"Markets are starting to feel it."*

---

### 4. Contagion (v2) — Spillover Risk

**Question it answers:**
> "Is risk spreading beyond Europe?"

- Middle East
- Black Sea
- Global trade corridors

This is about second-order effects.

**Conceptually:** This is fire jumping to the next building.

It's powerful, but only meaningful once regional indices mature — which is why it's v2.

---

## Why Show Normalized Values Only

This is extremely important.

**You are NOT showing:**
- Raw counts
- Internal math
- Proprietary scaling

**You ARE showing:**
> "Relative contribution to today's risk."

Normalized values answer:
- Which force mattered most today
- What changed since yesterday
- Where attention should go

Users don't care about raw math — they care about **dominance**.

---

## Visualization Options

### Stacked Bar — Composition View

**Best for:** "What is today made of?"

**Visually:**
- Each component occupies part of the bar
- Larger section = bigger influence

**User takeaway:**
> "Today's risk is mostly regional + market transmission."

---

### Donut — Balance View

**Best for:** "Which force dominates?"

**Visually:**
- Clean, intuitive
- Easy to compare proportions

**User takeaway:**
> "Theme pressure is unusually high today."

---

### Waterfall — Build-up View

**Best for:** "How did we get to 83?"

**Visually:**
- Start from baseline
- Each component pushes risk higher
- Ends at today's level

**User takeaway:**
> "Even if markets calm, regional risk alone keeps EERI elevated."

This is extremely powerful for analysts.

---

## The Key Psychological Shift for Pro Users

**Without this feature, users think:**
> "83 feels high."

**With this feature, users think:**
> "83 is high because regional escalation + gas + freight are all aligned."

That difference is everything.

---

## Why This Justifies Pro Pricing

This feature gives users:
- Explainability
- Confidence
- Trust
- Actionability

It answers:
- Can I trust this number?
- What should I watch today?
- Is this noise or systemic?

Most platforms hide this. **We monetize insight instead.**

---

## Dashboard UX Goal

The correct UX emotion is:
> "Ah. That makes sense."

**Not:**
- "How is this calculated?"
- "Is this arbitrary?"
- "Why should I trust this?"

---

## Strategic Note

We are not just explaining EERI. **We are educating users how to think about risk.**

Over time:
- They will stop checking prices first
- They will check EERI first
- Prices become confirmation, not signal

**That's how indices become indispensable.**

---

# Asset Stress Panel — Deep Dive

## Why the Asset Stress Panel Exists

Most users do this every day:
1. Scan news
2. Check charts
3. Guess which assets are affected
4. Decide where risk matters

That's slow. That's subjective. That's error-prone.

**The Asset Stress Panel answers one question instantly:**
> "Which markets are under stress today because of energy risk?"

Not tomorrow. Not in theory. **Today.**

---

## The Mental Model

Users should read this panel like a **risk radar**:
> "These are the asset classes currently absorbing the shock."

**It is NOT:**
- A forecast
- A trade signal
- A price target

**It IS:**
- Risk exposure mapping

---

## What Each Asset Row Represents

### 🔥 Gas — High

**What this tells the user:**
- European gas markets are under meaningful stress
- Supply narratives are active
- Sensitivity to headlines is elevated

**Conceptually:** Gas is the first responder in European energy crises.

**If Gas is "High":**
- Volatility risk is present
- Hedging costs may rise
- Downstream power prices may follow

---

### 🛢️ Oil — Elevated

**What this tells the user:**
- Oil is feeling spillover, not panic
- Risk is present but not dominant
- Oil is reacting to context, not leading it

**Conceptually:** Oil is aware, but not alarmed.

This distinction matters enormously to professionals.

---

### 🚢 Freight — Severe

**What this tells the user:**
- Logistics and trade routes are actively disrupted
- Physical constraints are binding
- Supply chain stress is real, not narrative

**Conceptually:** Freight is where geopolitical risk becomes physical reality.

This is often:
- The earliest confirmation of systemic stress
- A warning before prices fully react

---

### 💱 FX — Elevated

**What this tells the user:**
- Currency markets are repricing uncertainty
- Risk premiums are widening
- Capital is cautious, not fleeing

**Conceptually:** FX reflects confidence — Elevated means confidence is weakening.

---

## Why These Four Assets Together Are Powerful

Individually, they tell a story.
Together, they tell whether **risk is systemic**.

**Patterns users will learn:**

| Pattern | Interpretation |
|---------|----------------|
| Gas + Freight high | Physical supply stress |
| Oil + FX elevated | Macro spillover |
| All four high | Systemic shock |

This panel trains users to see **alignment**, not noise.

---

## Directional Bias (↑ ↓ ~)

This is subtle, but very powerful.

**It answers:**
> "Is stress increasing, easing, or stable?"

Not price direction. Not forecasts.

Just:
- **↑** Pressure building
- **↓** Pressure easing
- **~** Stable stress

**Conceptually:** This is momentum of *risk*, not momentum of *price*.

Professionals care deeply about this distinction.

---

## Color-coded Risk Bands — Fast Cognition

Colors are not decoration. They are **cognitive shortcuts**.

They allow users to:
- Absorb the situation in 2 seconds
- Compare assets instantly
- Spot shifts day-to-day

A glance should tell them:
> "Freight is flashing red. Everything else is amber."

That alone can change how someone trades or hedges.

---

## Why Traders and Analysts Love This Module

Because it:
- Saves time
- Reduces cognitive load
- Replaces guesswork
- Provides cross-asset context
- Works before price confirmation

This is the kind of panel that ends up:
- On a second monitor
- Checked every morning
- Referenced in daily notes

---

## The Emotional Reaction We Want

When a Pro user sees this panel, the reaction should be:
> "Okay — that's where the stress is."

**Not:**
- "What does this mean?"
- "How was this calculated?"
- "Is this subjective?"

It should feel **obvious and trustworthy**.

---

## Strategic Importance

This panel quietly does something huge:

It shifts the platform from:
> "Index provider"

to:
> "Risk intelligence system."

We are no longer just saying:
> "Risk is high"

We are saying:
> "Here is where risk lives today."

That is immensely valuable.

---

## Positioning

This panel should be:
- ✅ Pro-only
- ✅ Compact
- ✅ Always visible (above the fold)
- ✅ Stable in layout

Because over time, users will:
- Stop reading headlines first
- Start here

**That is product gravity.**
