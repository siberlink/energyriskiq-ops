import re
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

GEOPOLITICAL_KEYWORDS = [
    'war', 'attack', 'missile', 'conflict', 'sanctions', 'embargo', 
    'pipeline', 'sabotage', 'border', 'nato', 'coup', 'terrorism'
]

ENERGY_KEYWORDS = [
    'opec', 'crude', 'oil', 'gas', 'lng', 'refinery', 'upstream', 
    'production cut', 'rig', 'shale', 'brent', 'wti', 'ttf', 'power prices'
]

SUPPLY_CHAIN_KEYWORDS = [
    'port', 'shipping', 'freight', 'container', 'strike', 'congestion', 
    'blockade', 'reroute', 'suez', 'panama', 'bosphorus', 'logistics', 'rail disruption'
]

REGION_MAPPINGS = {
    'europe': ['ukraine', 'russia', 'eu', 'germany', 'france', 'romania', 'netherlands', 
               'poland', 'uk', 'britain', 'spain', 'italy', 'norway', 'sweden'],
    'middle_east': ['israel', 'iran', 'gaza', 'lebanon', 'saudi', 'yemen', 'iraq', 
                    'syria', 'qatar', 'uae', 'kuwait', 'bahrain'],
    'black_sea': ['black sea', 'bosphorus', 'turkey', 'constanta', 'odessa'],
    'north_africa': ['suez', 'egypt', 'libya', 'algeria', 'morocco', 'tunisia'],
    'asia': ['china', 'japan', 'korea', 'india', 'singapore', 'taiwan', 'vietnam', 
             'indonesia', 'malaysia', 'thailand', 'philippines'],
    'north_america': ['usa', 'united states', 'canada', 'mexico', 'gulf of mexico']
}

HIGH_SEVERITY_KEYWORDS = ['attack', 'missile', 'explosion', 'shutdown', 'blockade', 'sanctions']
MEDIUM_SEVERITY_KEYWORDS = ['strike', 'disruption', 'outage', 'congestion']
OPEC_KEYWORDS = ['opec', 'production cut']

def count_keyword_matches(text: str, keywords: list) -> int:
    text_lower = text.lower()
    count = 0
    for keyword in keywords:
        if keyword in text_lower:
            count += 1
    return count

def classify_category(title: str, raw_text: str = "") -> str:
    combined_text = f"{title} {raw_text or ''}"
    
    geo_score = count_keyword_matches(combined_text, GEOPOLITICAL_KEYWORDS)
    energy_score = count_keyword_matches(combined_text, ENERGY_KEYWORDS)
    supply_score = count_keyword_matches(combined_text, SUPPLY_CHAIN_KEYWORDS)
    
    scores = [
        ('energy', energy_score),
        ('geopolitical', geo_score),
        ('supply_chain', supply_score)
    ]
    
    scores.sort(key=lambda x: x[1], reverse=True)
    
    if scores[0][1] == 0:
        return 'geopolitical'
    
    return scores[0][0]

def classify_region(title: str, raw_text: str = "") -> str:
    combined_text = f"{title} {raw_text or ''}".lower()
    
    region_scores = {}
    for region, keywords in REGION_MAPPINGS.items():
        score = 0
        for keyword in keywords:
            if keyword in combined_text:
                score += 1
        if score > 0:
            region_scores[region] = score
    
    if not region_scores:
        return 'global'
    
    best_region = max(region_scores, key=region_scores.get)
    
    region_display_names = {
        'europe': 'Europe',
        'middle_east': 'Middle East',
        'black_sea': 'Black Sea',
        'north_africa': 'North Africa',
        'asia': 'Asia',
        'north_america': 'North America'
    }
    
    return region_display_names.get(best_region, 'Global')

def calculate_severity(title: str, raw_text: str = "") -> int:
    combined_text = f"{title} {raw_text or ''}".lower()
    
    score = 2
    
    for keyword in HIGH_SEVERITY_KEYWORDS:
        if keyword in combined_text:
            score += 2
            break
    
    for keyword in MEDIUM_SEVERITY_KEYWORDS:
        if keyword in combined_text:
            score += 1
            break
    
    for keyword in OPEC_KEYWORDS:
        if keyword in combined_text:
            score += 1
            break
    
    return max(1, min(5, score))

def classify_event(title: str, raw_text: str = "") -> Tuple[str, str, int]:
    category = classify_category(title, raw_text)
    region = classify_region(title, raw_text)
    severity = calculate_severity(title, raw_text)
    
    logger.debug(f"Classified '{title[:50]}...' as category={category}, region={region}, severity={severity}")
    
    return category, region, severity
