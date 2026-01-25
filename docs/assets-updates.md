# Assets Updates

This document tracks updates and changes to all EnergyRiskIQ assets including Alerts, GERI, RERI, and EERI.

---

## Alerts

### 2026-01-25: Granular Thematic Categories for Event Classification

**Summary:** Updated the event classification system to use granular thematic categories instead of broad categories.

**Previous Behavior:**
- Events were classified into 3 broad categories: `energy`, `geopolitical`, `supply_chain`
- EERI Top Drivers showed generic category labels

**New Behavior:**
- Events are now classified into 10 granular thematic categories based on keyword matching
- Categories align with EERI's weighting system for proper severity scoring

**New Thematic Categories:**

| Category | Weight | Keywords |
|----------|--------|----------|
| `war` | 1.6 | war, invasion, occupation, attack, missile, bombing, airstrike, shelling |
| `military` | 1.6 | military, troops, nato, defense, army, navy, air force, weapons |
| `conflict` | 1.6 | conflict, clashes, fighting, hostilities, violence, battle |
| `strike` | 1.6 | strike, walkout, labor dispute, workers strike, industrial action |
| `supply_disruption` | 1.5 | disruption, outage, shutdown, halt, suspend, blockade, congestion |
| `sanctions` | 1.3 | sanctions, embargo, tariff, trade ban, asset freeze, blacklist |
| `energy` | 1.3 | oil, gas, lng, opec, crude, refinery, pipeline, power, electricity |
| `political` | 1.0 | government, election, parliament, minister, policy, legislation, regulation |
| `diplomacy` | 0.7 | diplomatic, negotiation, summit, talks, agreement, treaty, ceasefire |
| `geopolitical` | 1.0 | (fallback if no keywords match) |

**Files Changed:**
- `src/ingest/classifier.py` - Added `classify_thematic_category()` function and `THEMATIC_CATEGORY_KEYWORDS` mapping
- `src/alerts/alerts_engine_v2.py` - Updated HIGH_IMPACT_EVENT filter to accept all thematic categories

**Impact:**
- New events ingested after this change will have granular thematic categories
- EERI Top Drivers will display meaningful category labels (war, sanctions, energy, etc.)
- EERI severity weighting now works correctly based on thematic category weights
- Existing alerts in production are unchanged (only new ingestions affected)

---

## GERI (Global Energy Risk Index)

*No updates yet.*

---

## RERI (Regional Escalation Risk Index)

*No updates yet.*

---

## EERI (Europe Energy Risk Index)

*No updates yet.*

---
