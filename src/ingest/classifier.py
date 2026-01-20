import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

GEOPOLITICAL_KEYWORDS = [
    'war', 'attack', 'missile', 'conflict', 'sanctions', 'embargo', 
    'pipeline', 'sabotage', 'border', 'nato', 'coup', 'terrorism',
    'military', 'troops', 'invasion', 'occupation', 'ceasefire', 'humanitarian',
    'refugee', 'crisis', 'defense', 'security', 'intelligence', 'espionage'
]

ENERGY_KEYWORDS = [
    'opec', 'crude', 'oil', 'gas', 'lng', 'refinery', 'upstream', 
    'production cut', 'rig', 'shale', 'brent', 'wti', 'ttf', 'power prices',
    'electricity', 'grid', 'renewable', 'solar', 'wind', 'nuclear', 'coal',
    'carbon', 'emissions', 'energy storage', 'hydrogen', 'biofuel', 'petrochemical'
]

SUPPLY_CHAIN_KEYWORDS = [
    'port', 'shipping', 'freight', 'container', 'strike', 'congestion', 
    'blockade', 'reroute', 'suez', 'panama', 'bosphorus', 'logistics', 'rail disruption',
    'tanker', 'vessel', 'cargo', 'maritime', 'import', 'export', 'tariff', 'customs'
]

REGULATORY_KEYWORDS = [
    'regulation', 'directive', 'legislation', 'law', 'policy', 'commission',
    'parliament', 'council', 'minister', 'government', 'authority', 'regulator',
    'acer', 'entsoe', 'entso-e', 'eu energy', 'energy union', 'green deal',
    'fit for 55', 'repower', 'taxonomy', 'eia', 'ferc', 'compliance'
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

HIGH_SEVERITY_KEYWORDS = [
    'attack', 'missile', 'explosion', 'shutdown', 'blockade', 'sanctions',
    'crisis', 'turmoil', 'halt', 'suspend', 'collapse', 'war', 'conflict',
    'seize', 'capture', 'embargo', 'invasion', 'emergency', 'critical'
]
MEDIUM_SEVERITY_KEYWORDS = [
    'strike', 'disruption', 'outage', 'congestion', 'shortage', 'delay',
    'spike', 'surge', 'plunge', 'threat', 'risk', 'warning', 'tension'
]
OPEC_KEYWORDS = ['opec', 'production cut', 'output cut', 'supply cut']

VALID_CATEGORIES = ['geopolitical', 'energy', 'supply_chain']

def count_keyword_matches(text: str, keywords: list) -> int:
    text_lower = text.lower()
    count = 0
    for keyword in keywords:
        if keyword in text_lower:
            count += 1
    return count

def classify_category_with_reason(title: str, raw_text: str = "", category_hint: Optional[str] = None, signal_type: Optional[str] = None) -> Tuple[str, str, float]:
    combined_text = f"{title} {raw_text or ''}"
    
    geo_score = count_keyword_matches(combined_text, GEOPOLITICAL_KEYWORDS)
    energy_score = count_keyword_matches(combined_text, ENERGY_KEYWORDS)
    supply_score = count_keyword_matches(combined_text, SUPPLY_CHAIN_KEYWORDS)
    reg_score = count_keyword_matches(combined_text, REGULATORY_KEYWORDS)
    
    if reg_score > 0:
        if signal_type in ['regulation', 'policy']:
            energy_score += reg_score
        else:
            geo_score += reg_score // 2
    
    hint_valid = category_hint in VALID_CATEGORIES if category_hint else False
    hint_str = category_hint if hint_valid else "none"
    
    scores = {
        'energy': energy_score,
        'geopolitical': geo_score,
        'supply_chain': supply_score
    }
    
    max_score = max(scores.values())
    total_score = sum(scores.values())
    
    if max_score == 0:
        if hint_valid:
            chosen = category_hint
            decision = "no_keywords_used_hint"
            confidence = 0.5
        else:
            chosen = 'geopolitical'
            decision = "no_keywords_default_geo"
            confidence = 0.3
    else:
        top_categories = [cat for cat, score in scores.items() if score == max_score]
        confidence = min(0.95, 0.5 + (max_score / max(total_score, 1)) * 0.4 + (max_score * 0.02))
        
        if len(top_categories) == 1:
            chosen = top_categories[0]
            decision = "keyword_winner"
        else:
            confidence *= 0.8
            if hint_valid and category_hint in top_categories:
                chosen = category_hint
                decision = "tie_resolved_by_hint"
            else:
                priority = ['energy', 'geopolitical', 'supply_chain']
                for cat in priority:
                    if cat in top_categories:
                        chosen = cat
                        decision = "tie_resolved_by_priority"
                        break
    
    reason = f"energy={energy_score};geo={geo_score};sc={supply_score};reg={reg_score};hint={hint_str};chosen={chosen};decision={decision};conf={confidence:.2f}"
    
    return chosen, reason, confidence

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
        return 'Global'
    
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

def classify_event(title: str, raw_text: str = "", category_hint: Optional[str] = None, signal_type: Optional[str] = None) -> Tuple[str, str, int, str, float]:
    category, classification_reason, confidence = classify_category_with_reason(title, raw_text, category_hint, signal_type)
    region = classify_region(title, raw_text)
    severity = calculate_severity(title, raw_text)
    
    logger.debug(f"Classified '{title[:50]}...' as category={category}, region={region}, severity={severity}, confidence={confidence:.2f}")
    
    return category, region, severity, classification_reason, confidence
