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

*(To be defined)*

---

## Implementation Status

| Index | Status | Location |
|-------|--------|----------|
| GERI v1 | ✅ Complete | `src/geri/` |
| RERI | 🔜 Planned | TBD |
| Asset Indices | 📋 Future | TBD |

---

*Last updated: January 2026*
