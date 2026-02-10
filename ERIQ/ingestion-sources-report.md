# EnergyRiskIQ — Ingestion Sources Report

## Overview

This document provides a quality assessment of all current RSS news sources used by the EnergyRiskIQ event ingestion pipeline, along with identified gaps and recommendations.

---

## Current Source Inventory (14 feeds)

---

### Tier 1 — High Quality (Institutional / Primary Sources)

| Source | Type | Region | Weight | Assessment |
|---|---|---|---|---|
| **Reuters Energy** | Market news | Global | 1.0 | Gold standard for energy markets. However, the RSS feed URL may intermittently restrict access. |
| **European Commission – Energy** | Policy/regulation | Europe | 1.0 | Official EU press releases. Authoritative but narrow — only covers EU regulatory actions. |
| **EIA (US Energy Info Admin)** | Market data/analysis | North America | 0.9 | US government primary source. Excellent quality, but covers only US energy data. |
| **EU Energy Commission** | Regulation | Europe | 0.9 | Official EU energy policy. Similar to the first EC source — potential overlap. |
| **ICIS Energy News** | Gas/LNG market | Europe | 0.9 | Industry-leading gas intelligence. Feed URL points to a podcast RSS, which may not return traditional article entries. |

---

### Tier 2 — Good Quality (Industry / Specialist)

| Source | Type | Region | Weight | Assessment |
|---|---|---|---|---|
| **Energy Intelligence** | Market intelligence | Europe | 0.85 | Respected industry source. May require subscription for full content. |
| **Politico Europe** | Policy/geopolitical | Europe | 0.8 | Strong political coverage but general — not energy-specific. Many articles won't be relevant. |
| **FreightWaves** | Shipping/logistics | Global | 0.8 | Excellent for supply chain and freight risk signals. Highly relevant for transit disruption tracking. |
| **Oil & Gas Journal** | Energy industry | Global | 0.8 | Long-established trade publication. Good for upstream/infrastructure news. |

---

### Tier 3 — Moderate Quality (General / Secondary)

| Source | Type | Region | Weight | Assessment |
|---|---|---|---|---|
| **Al Jazeera News** | Geopolitical/conflict | Global | 0.7 | Full news feed (all topics), not energy-filtered. Very high noise — most articles won't be energy-relevant. |
| **OilPrice.com** | Energy market | Global | 0.7 | Popular energy site but editorial quality varies. Some clickbait/opinion content. |
| **Energy Live News** | Energy industry | Europe | 0.7 | Decent niche source. Smaller outlet, moderate authority. |
| **Power Technology** | Infrastructure | Europe | 0.7 | Good for power/grid infrastructure, less useful for oil/gas risk events. |

---

## Key Issues

### 1. Heavy Europe Bias

8 of 14 sources have a Europe region hint. Very thin coverage of Middle East, Asia, Africa, and Latin America despite these being critical energy risk regions.

### 2. No Dedicated Middle East Source

This is a significant gap given that Middle East events drive much of global energy risk. Al Jazeera is the only one touching this, and it's an unfiltered full-news feed.

### 3. No Dedicated Conflict/Security Source

No feeds from defense or security-focused outlets (e.g., Jane's, ACLED, or similar).

### 4. Noise-to-Signal Ratio Concerns

Al Jazeera and Politico feed entire editorial output, not energy-filtered content. The classifier catches relevant articles via keywords, but a large number of irrelevant articles are processed each cycle.

### 5. Potential Dead/Restricted Feeds

The ICIS feed URL points to a podcast RSS, and some sources (Reuters, Energy Intelligence) may restrict content via their RSS feeds.

### 6. No Asia-Pacific Source

Missing coverage for China, India, Southeast Asia energy markets.

### 7. No OPEC-Specific Source

Despite OPEC being a critical risk driver, there's no direct OPEC news feed.

### 8. Deduplication Is Basic

Title normalization only. No semantic deduplication yet (as outlined in GERI documentation Part 8).

---

## Classification Quality Assessment

The classifier uses keyword matching across approximately 150 keywords in 4 categories (geopolitical, energy, supply chain, regulatory) plus thematic sub-classification (war, sanctions, strikes, etc.) and 6 regional mappings.

### Strengths

- Covers core energy and geopolitical keyword space
- Thematic sub-classification provides granular event typing
- Region detection spans 6 major zones with country-level keywords
- Confidence scoring provides a useful quality signal
- Priority-based tie-breaking ensures consistent categorization

### Weaknesses

- **No AI/NLP classification** — purely keyword-based
- **Severity scoring is coarse** — 1–5 scale with simple keyword presence checks
- **Confidence scores are heuristic** — not model-calibrated
- **No entity extraction** — doesn't identify specific actors, companies, or infrastructure
- **No temporal awareness** — can't distinguish developing vs. resolved events

---

## Regional Coverage Gap Analysis

| Region | Sources | Gap Severity |
|---|---|---|
| Europe | 8 sources | Over-served |
| North America | 1 source (EIA) | Moderate gap |
| Middle East | 0 dedicated | Critical gap |
| Asia-Pacific | 0 dedicated | Critical gap |
| Africa | 0 dedicated | Significant gap |
| Latin America | 0 dedicated | Moderate gap |
| Russia/Black Sea | 0 dedicated | Significant gap |

---

## Signal Type Coverage

| Signal Type | Sources | Coverage |
|---|---|---|
| Market/price | 5 (Reuters, EIA, OilPrice, Energy Intel, Energy Live) | Good |
| Policy/regulation | 3 (EU Commission x2, Politico) | Good for EU only |
| Shipping/transit | 1 (FreightWaves) | Thin |
| Conflict/military | 1 (Al Jazeera, unfiltered) | Very thin |
| Infrastructure | 2 (Power Technology, OGJ) | Moderate |
| Gas storage/LNG | 2 (ICIS, EU Energy Commission) | Moderate |
| OPEC/production | 0 dedicated | Gap |
| Nuclear | 0 dedicated | Gap |

---

## Summary

The current ingestion pipeline has a solid foundation with good institutional sources (EIA, EU Commission, Reuters) but is Europe-heavy, missing key geopolitical regions, and relying on basic keyword classification. For the GERI evolution model, expanding to 25–30 feeds with better regional balance and adding AI-powered classification would significantly improve signal quality.
