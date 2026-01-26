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

### 2026-01-25: Updated EERI Formula with Correct Weights and Contagion

**Summary:** Updated EERI to match the official specification with corrected weights, expanded theme filters, additional energy assets, and contagion enabled.

**Previous Formula:**
```
EERI = 100 × clamp(
    0.50 × RERI_EU +
    0.28 × ThemePressure +
    0.22 × AssetTransmission +
    0.00 × Contagion  // disabled
)
```

**New Formula:**
```
EERI = 100 × clamp(
    0.45 × RERI_EU +
    0.25 × ThemePressure +
    0.20 × AssetTransmission +
    0.10 × Contagion
)
```

**Changes:**

| Component | Previous | New |
|-----------|----------|-----|
| RERI_EU weight | 0.50 | 0.45 |
| ThemePressure weight | 0.28 | 0.25 |
| AssetTransmission weight | 0.22 | 0.20 |
| Contagion weight | 0.00 | 0.10 |

**Theme Filters (ThemePressure):**

| Previous | New |
|----------|-----|
| energy, supply_chain, supply_disruption, sanctions | energy, supply_chain, supply_disruption, sanctions, **war, military, conflict, strike** |

**Theme Multipliers:**
- war/military: 1.5
- conflict/strike: 1.4
- supply_disruption/supply_chain/energy: 1.3
- sanctions: 1.2

**Energy Assets (AssetTransmission):**

| Previous | New |
|----------|-----|
| gas, oil, power, lng, electricity | gas, oil, power, lng, electricity, **freight, fx** |

**Contagion Implementation:**
- Now enabled with 0.10 weight
- Neighbors for Europe:
  - Middle East: weight 0.6
  - Black Sea: weight 0.4
- Formula: `Contagion = sum(neighbor_weight × neighbor_RERI / 100)`

**Files Changed:**
- `src/reri/types.py` - Updated EERI_WEIGHTS_V1, added CONTAGION_NEIGHBORS
- `src/reri/compute.py` - Added compute_contagion(), ENERGY_THEME_CATEGORIES, ENERGY_THEME_MULTIPLIERS, ENERGY_ASSETS
- `src/reri/service.py` - Now computes RERI for Middle East and Black Sea neighbors, passes to EERI computation

**Impact:**
- EERI values will now include contagion risk from neighboring regions
- Higher weight on war/military events improves risk signal accuracy
- Freight and FX assets now tracked for transmission
- Status endpoint now shows `contagion_enabled: true`

### 2026-01-26: Fixed Dictionary Key Access in repo.py

**Summary:** Fixed runtime errors caused by using tuple indexing on dictionary rows from RealDictCursor.

**Error:**
```
KeyError: 1
File "src/reri/repo.py", line 110
return [row[1] for row in rows if row[1] is not None]
```

**Fixes Applied:**
- Line 110: `row[1]` → `row['s_value']`
- Line 277: `row[7]` → `row['components']`
- Line 278: `row[8]` → `row['drivers']`
- Line 387: `row[7]` → `row['components']`

**Root Cause:**
- PostgreSQL connection uses `RealDictCursor` which returns rows as dictionaries
- Code was using tuple indices (e.g., `row[0]`, `row[7]`) instead of column names

**Files Changed:**
- `src/reri/repo.py`

**Impact:**
- EERI daily computation now works correctly (manual and automated)
- `/api/v1/indices/eeri/compute-yesterday` endpoint functional

---
