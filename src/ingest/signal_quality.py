import math
import re
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

SOURCE_CREDIBILITY = {
    "Reuters Energy": 0.95,
    "European Commission – Energy": 0.95,
    "EIA (US Energy Info Admin)": 0.95,
    "EU Energy Commission": 0.90,
    "OPEC News": 0.95,
    "OPEC Press Releases": 0.95,
    "Norwegian Offshore Directorate": 0.90,
    "ICIS Energy News": 0.90,
    "Energy Intelligence": 0.85,
    "Maritime Executive": 0.85,
    "Hellenic Shipping News — Oil & Energy": 0.80,
    "Hellenic Shipping News — Shipping": 0.80,
    "FreightWaves": 0.80,
    "Oil & Gas Journal": 0.80,
    "Rigzone": 0.80,
    "Politico Europe": 0.75,
    "Xinhua — Business/Energy": 0.80,
    "China Daily — Business": 0.75,
    "Al Jazeera News": 0.70,
    "OilPrice.com": 0.65,
    "Energy Live News": 0.65,
    "Power Technology": 0.65,
}

DEFAULT_CREDIBILITY = 0.60

NAMED_ENTITIES = {
    "chokepoints": [
        "strait of hormuz", "bab el-mandeb", "bab-el-mandeb", "suez canal",
        "panama canal", "bosphorus", "turkish straits", "malacca strait",
        "cape of good hope", "danish straits", "red sea"
    ],
    "pipelines": [
        "nord stream", "turkstream", "yamal", "druzhba", "trans-adriatic",
        "trans-anatolian", "tanap", "tap", "eastern mediterranean",
        "keystone", "keystone xl", "dakota access", "colonial pipeline",
        "nabucco", "south stream", "blue stream"
    ],
    "lng_terminals": [
        "sabine pass", "cameron lng", "freeport lng", "cove point",
        "elba island", "corpus christi", "cheniere", "ras laffan",
        "yamal lng", "arctic lng", "sakhalin", "gladstone",
        "gate terminal", "dunkerque lng", "montoir", "zeebrugge",
        "swinoujscie", "floating storage"
    ],
    "producers": [
        "saudi aramco", "aramco", "gazprom", "rosneft", "lukoil",
        "qatarenergy", "adnoc", "kuwait petroleum", "national iranian",
        "petrochina", "sinopec", "cnooc", "equinor", "shell", "bp",
        "totalenergies", "exxonmobil", "chevron", "conocophillips",
        "eni", "petrobras"
    ],
    "countries_high_risk": [
        "iran", "russia", "ukraine", "yemen", "libya", "iraq",
        "syria", "venezuela", "nigeria", "sudan", "myanmar"
    ],
    "organizations": [
        "opec", "opec+", "iea", "eia", "nato", "eu commission",
        "european commission", "un security council"
    ]
}

NOISE_INDICATORS = [
    "opinion", "editorial", "comment", "column", "podcast",
    "review", "interview transcript", "book review", "obituary",
    "celebrity", "entertainment", "sports", "lifestyle", "recipe",
    "horoscope", "weather forecast", "travel guide"
]

ENERGY_RELEVANCE_BOOSTERS = [
    "crude oil", "natural gas", "lng", "opec", "production cut",
    "output cut", "sanctions", "embargo", "pipeline", "refinery",
    "oil price", "gas price", "ttf", "brent", "wti", "energy crisis",
    "power outage", "grid failure", "storage", "fuel", "petroleum",
    "drilling", "upstream", "downstream", "midstream", "tanker",
    "freight rate", "shipping lane", "chokepoint", "blockade",
    "nuclear plant", "reactor", "uranium", "coal", "electricity",
    "power generation", "energy security", "supply disruption",
    "demand shock", "winter supply", "gas storage", "strategic reserve"
]

TAXONOMY_BASE_SEVERITY = {
    "war": 1.0,
    "military": 0.9,
    "conflict": 0.85,
    "sanctions": 0.80,
    "supply_disruption": 0.85,
    "strike": 0.70,
    "energy": 0.60,
    "political": 0.50,
    "diplomacy": 0.45,
    "geopolitical": 0.55,
}

REGION_ENERGY_EXPOSURE = {
    "Middle East": 1.0,
    "Europe": 0.85,
    "Black Sea": 0.90,
    "North Africa": 0.80,
    "North America": 0.70,
    "Asia": 0.75,
    "Global": 0.60,
}


def _get_source_credibility(source_name: str) -> float:
    return SOURCE_CREDIBILITY.get(source_name, DEFAULT_CREDIBILITY)


def _compute_freshness(event_time: Optional[datetime], half_life_hours: float = 48.0) -> float:
    if not event_time:
        return 0.5

    now = datetime.now(timezone.utc) if event_time.tzinfo else datetime.now()
    delta_hours = max(0, (now - event_time).total_seconds() / 3600.0)

    return math.exp(-delta_hours / half_life_hours)


def _compute_entity_specificity(text: str) -> Tuple[float, list]:
    text_lower = text.lower()
    found_entities = []

    for entity_type, entities in NAMED_ENTITIES.items():
        for entity in entities:
            if entity in text_lower:
                found_entities.append({"type": entity_type, "entity": entity})

    if not found_entities:
        return 0.2, found_entities

    unique_types = len(set(e["type"] for e in found_entities))
    count = len(found_entities)

    score = min(1.0, 0.3 + (count * 0.1) + (unique_types * 0.15))
    return score, found_entities


def _compute_energy_relevance(text: str, category_hint: Optional[str] = None,
                               signal_type: Optional[str] = None) -> float:
    text_lower = text.lower()

    matches = sum(1 for term in ENERGY_RELEVANCE_BOOSTERS if term in text_lower)

    if matches == 0:
        base = 0.15
    elif matches <= 2:
        base = 0.4
    elif matches <= 5:
        base = 0.65
    elif matches <= 10:
        base = 0.8
    else:
        base = 0.95

    if category_hint == "energy":
        base = min(1.0, base + 0.15)
    if signal_type in ("market", "gas_storage", "shipping", "infrastructure"):
        base = min(1.0, base + 0.10)

    return round(base, 3)


def _compute_noise_penalty(title: str, raw_text: str = "") -> float:
    combined = f"{title} {raw_text or ''}".lower()

    noise_hits = sum(1 for indicator in NOISE_INDICATORS if indicator in combined)

    if noise_hits == 0:
        return 0.0
    elif noise_hits == 1:
        return 0.15
    elif noise_hits == 2:
        return 0.30
    else:
        return min(0.60, noise_hits * 0.15)


def _compute_severity(thematic_category: str, region: str,
                       classifier_severity: int, text: str) -> float:
    base = TAXONOMY_BASE_SEVERITY.get(thematic_category, 0.50)

    exposure = REGION_ENERGY_EXPOSURE.get(region, 0.60)

    classifier_factor = classifier_severity / 5.0

    persistence = 0.6
    text_lower = text.lower()
    structural_keywords = ["permanent", "structural", "long-term", "fundamental", "systemic", "irreversible"]
    medium_keywords = ["ongoing", "continuing", "multi-day", "extended", "sustained", "prolonged"]

    if any(kw in text_lower for kw in structural_keywords):
        persistence = 1.0
    elif any(kw in text_lower for kw in medium_keywords):
        persistence = 0.8

    severity = base * exposure * persistence * (0.4 + 0.6 * classifier_factor)
    return round(min(1.0, severity), 3)


def _compute_market_relevance(severity: float, region: str,
                                thematic_category: str, entity_count: int) -> float:
    region_amp = REGION_ENERGY_EXPOSURE.get(region, 0.60)

    category_amp = TAXONOMY_BASE_SEVERITY.get(thematic_category, 0.50)

    entity_boost = min(0.3, entity_count * 0.05)

    raw = severity * 0.4 + region_amp * 0.25 + category_amp * 0.2 + entity_boost + 0.1

    return round(min(1.0, max(0.0, 1.0 / (1.0 + math.exp(-6.0 * (raw - 0.5))))), 3)


def compute_signal_quality(event: Dict[str, Any],
                            thematic_category: str,
                            region: str,
                            classifier_severity: int,
                            classifier_confidence: float) -> Dict[str, Any]:
    title = event.get("title", "")
    raw_text = event.get("raw_text", "") or ""
    source_name = event.get("source_name", "")
    event_time = event.get("event_time")
    category_hint = event.get("category_hint")
    signal_type = event.get("signal_type")
    source_weight = event.get("weight", 0.5)

    combined_text = f"{title} {raw_text}"

    credibility = _get_source_credibility(source_name)

    freshness = _compute_freshness(event_time)

    entity_specificity, entities_found = _compute_entity_specificity(combined_text)

    energy_relevance = _compute_energy_relevance(combined_text, category_hint, signal_type)

    noise_penalty = _compute_noise_penalty(title, raw_text)

    severity = _compute_severity(thematic_category, region, classifier_severity, combined_text)

    market_relevance = _compute_market_relevance(
        severity, region, thematic_category, len(entities_found)
    )

    signal_score = 100.0 * energy_relevance * credibility * freshness * entity_specificity * (1.0 - noise_penalty)

    source_weight_factor = 0.7 + 0.3 * source_weight
    signal_score *= source_weight_factor

    signal_score = round(min(100.0, max(0.0, signal_score)), 1)

    if signal_score >= 60:
        quality_band = "high"
    elif signal_score >= 35:
        quality_band = "medium"
    elif signal_score >= 15:
        quality_band = "low"
    else:
        quality_band = "noise"

    result = {
        "signal_score": signal_score,
        "quality_band": quality_band,
        "components": {
            "energy_relevance": energy_relevance,
            "source_credibility": credibility,
            "freshness": round(freshness, 3),
            "entity_specificity": entity_specificity,
            "noise_penalty": noise_penalty,
            "severity": severity,
            "market_relevance": market_relevance,
            "classifier_confidence": round(classifier_confidence, 3),
            "source_weight": source_weight,
        },
        "entities_found": entities_found[:10],
        "is_geri_driver": signal_score >= 35 and market_relevance >= 0.4,
    }

    logger.debug(
        f"Signal quality for '{title[:50]}...': score={signal_score} "
        f"band={quality_band} market_rel={market_relevance} "
        f"entities={len(entities_found)} geri_driver={result['is_geri_driver']}"
    )

    return result
