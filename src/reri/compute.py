"""
EERI v1 Compute Functions (Pure Functions)

Calculates EERI (Europe Energy Risk Index) components from alert data.
"""
import re
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict
from datetime import datetime, timedelta

from src.reri.types import (
    AlertRecord,
    RERIComponents,
    EERIComponents,
    CATEGORY_WEIGHTS,
    RERI_WEIGHTS,
    EERI_WEIGHTS,
    NORMALIZATION_CAPS,
    VALID_ALERT_TYPES,
)


def clamp(value: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
    """Clamp value between min and max."""
    return max(min_val, min(max_val, value))


def extract_category_from_body(body: Optional[str]) -> str:
    """
    Extract category from alert body text.
    Pattern: "Category: ENERGY" or similar.
    Returns lowercase category or 'unknown'.
    """
    if not body:
        return 'unknown'
    
    match = re.search(r'Category:\s*(\w+)', body, re.IGNORECASE)
    if match:
        cat = match.group(1).strip().lower()
        if cat in ['supply_chain', 'supplychain', 'supply']:
            return 'supply_chain'
        return cat
    return 'unknown'


def extract_event_title_from_body(body: Optional[str]) -> Optional[str]:
    """
    Extract actual event title from body.
    Pattern: "Event: <title>" or "HIGH-IMPACT EVENT ALERT\n\nEvent: <title>"
    """
    if not body:
        return None
    
    match = re.search(r'Event:\s*(.+?)(?:\n|$)', body)
    if match:
        return match.group(1).strip()
    return None


def get_category_weight(category: str) -> float:
    """Get weight multiplier for category."""
    return CATEGORY_WEIGHTS.get(category.lower(), 1.0)


def normalize_region(region: Optional[str]) -> Optional[str]:
    """
    Normalize region string to canonical region ID.
    Returns 'europe', 'middle-east', 'black-sea', or None.
    """
    if not region:
        return None
    
    region_lower = region.lower().strip()
    
    if any(alias in region_lower for alias in ['europe', 'eu', 'european']):
        return 'europe'
    elif any(alias in region_lower for alias in ['middle east', 'middle-east', 'gulf', 'mena', 'persian']):
        return 'middle-east'
    elif any(alias in region_lower for alias in ['black sea', 'black-sea', 'bosphorus', 'ukraine']):
        return 'black-sea'
    
    return None


def filter_alerts_by_region(alerts: List[AlertRecord], region_id: str) -> List[AlertRecord]:
    """Filter alerts that belong to the specified canonical region."""
    filtered = []
    for alert in alerts:
        normalized = normalize_region(alert.region)
        if normalized == region_id:
            filtered.append(alert)
    return filtered


def compute_severity_pressure(alerts: List[AlertRecord]) -> float:
    """
    Compute Severity Pressure (S) component.
    S = sum(severity * category_weight * confidence)
    
    IMPORTANT: Only uses HIGH_IMPACT_EVENT alerts.
    REGIONAL_RISK_SPIKE should NOT be used for S computation 
    (it should be derived from RERI, not used as input - see docs section 3.5).
    """
    total = 0.0
    for alert in alerts:
        if alert.alert_type != 'HIGH_IMPACT_EVENT':
            continue
        
        severity = alert.severity if alert.severity is not None else 3
        confidence = alert.confidence if alert.confidence is not None else 1.0
        category = extract_category_from_body(alert.body) if not alert.category else alert.category
        weight = get_category_weight(category)
        
        total += severity * weight * confidence
    
    return total


def compute_high_impact_count(alerts: List[AlertRecord]) -> int:
    """
    Compute High-Impact Count (H) component.
    Count alerts that are:
    - alert_type = HIGH_IMPACT_EVENT (always counts)
    - alert_type = REGIONAL_RISK_SPIKE (counts for clustering signal)
    - OR severity >= 4 (any alert type)
    
    Note: REGIONAL_RISK_SPIKE is included in count for clustering detection,
    but not in severity pressure calculation (see docs section 3.6).
    """
    counted_ids = set()
    
    for alert in alerts:
        if alert.alert_type == 'HIGH_IMPACT_EVENT':
            counted_ids.add(alert.id)
        elif alert.alert_type == 'REGIONAL_RISK_SPIKE':
            counted_ids.add(alert.id)
        elif alert.severity is not None and alert.severity >= 4:
            counted_ids.add(alert.id)
    
    return len(counted_ids)


def compute_asset_overlap(alerts: List[AlertRecord]) -> Tuple[int, List[str]]:
    """
    Compute Asset Overlap (O) component.
    O = count(distinct assets with ASSET_RISK_SPIKE today)
    Returns (count, list of distinct assets)
    """
    distinct_assets = set()
    
    for alert in alerts:
        if alert.alert_type == 'ASSET_RISK_SPIKE' and alert.assets:
            for asset in alert.assets:
                if asset:
                    distinct_assets.add(asset.lower())
    
    assets_list = sorted(list(distinct_assets))
    return len(assets_list), assets_list


def compute_velocity(current_s: float, historical_s_values: List[float]) -> float:
    """
    Compute Velocity (V) component.
    V = S_today - avg(S over last 3 days)
    """
    if not historical_s_values:
        return 0.0
    
    last_3 = historical_s_values[-3:] if len(historical_s_values) >= 3 else historical_s_values
    avg_s = sum(last_3) / len(last_3) if last_3 else 0.0
    
    return current_s - avg_s


def compute_reri_components(
    alerts: List[AlertRecord],
    historical_s_values: Optional[List[float]] = None,
    use_rolling_normalization: bool = False,
    baseline_caps: Optional[Dict[str, float]] = None,
) -> RERIComponents:
    """
    Compute all RERI base components for a region.
    Pure function - no side effects.
    
    Args:
        alerts: List of alerts for the day
        historical_s_values: Historical severity values for velocity calculation
        use_rolling_normalization: If True, use baseline_caps from history
        baseline_caps: Rolling baseline caps (min/max) from historical data
    """
    components = RERIComponents()
    components.total_alerts = len(alerts)
    
    if not alerts:
        return components
    
    components.severity_pressure_raw = compute_severity_pressure(alerts)
    components.high_impact_count = compute_high_impact_count(alerts)
    overlap_count, assets = compute_asset_overlap(alerts)
    components.asset_overlap_count = overlap_count
    components.distinct_assets = assets
    
    if historical_s_values:
        components.velocity_raw = compute_velocity(
            components.severity_pressure_raw, 
            historical_s_values
        )
    else:
        components.insufficient_history = True
    
    if use_rolling_normalization and baseline_caps:
        s_cap = baseline_caps.get('severity_max', NORMALIZATION_CAPS['severity_pressure'])
        h_cap = baseline_caps.get('high_impact_max', NORMALIZATION_CAPS['high_impact_count'])
        o_cap = baseline_caps.get('asset_overlap_max', NORMALIZATION_CAPS['asset_overlap'])
        v_range = baseline_caps.get('velocity_range', NORMALIZATION_CAPS['velocity_range'])
    else:
        s_cap = NORMALIZATION_CAPS['severity_pressure']
        h_cap = NORMALIZATION_CAPS['high_impact_count']
        o_cap = NORMALIZATION_CAPS['asset_overlap']
        v_range = NORMALIZATION_CAPS['velocity_range']
    
    components.severity_pressure_norm = clamp(
        components.severity_pressure_raw / max(s_cap, 1.0)
    )
    components.high_impact_norm = clamp(
        components.high_impact_count / max(h_cap, 1.0)
    )
    components.asset_overlap_norm = clamp(
        components.asset_overlap_count / max(o_cap, 1.0)
    )
    components.velocity_norm = clamp(
        (components.velocity_raw + NORMALIZATION_CAPS['velocity_offset']) / max(v_range, 1.0)
    )
    
    return components


def compute_reri_value(components: RERIComponents) -> int:
    """
    Compute RERI value from normalized components.
    RERI = 100 * (0.45*S_norm + 0.30*H_norm + 0.15*O_norm + 0.10*V_norm)
    """
    weights = RERI_WEIGHTS
    
    raw_value = (
        weights['severity_pressure'] * components.severity_pressure_norm +
        weights['high_impact_count'] * components.high_impact_norm +
        weights['asset_overlap'] * components.asset_overlap_norm +
        weights['velocity'] * components.velocity_norm
    )
    
    return int(round(clamp(raw_value, 0, 1) * 100))


ENERGY_THEME_CATEGORIES = {
    'energy', 'supply_chain', 'supply_disruption', 'sanctions', 
    'war', 'military', 'conflict', 'strike'
}

ENERGY_THEME_MULTIPLIERS = {
    'war': 1.5,
    'military': 1.5,
    'conflict': 1.4,
    'strike': 1.4,
    'supply_disruption': 1.3,
    'supply_chain': 1.3,
    'energy': 1.3,
    'sanctions': 1.2,
}

def compute_theme_pressure(
    alerts: List[AlertRecord],
    theme: str = 'energy'
) -> float:
    """
    Compute ThemePressure for a specific theme.
    ThemePressure = sum(severity * confidence * typeMultiplier)
    
    Theme filters for 'energy':
    - Categories: ENERGY, SUPPLY_DISRUPTION, SANCTIONS, WAR/MILITARY
    """
    total = 0.0
    
    for alert in alerts:
        category = extract_category_from_body(alert.body) if not alert.category else alert.category
        category_lower = category.lower() if category else 'unknown'
        
        if theme == 'energy' and category_lower in ENERGY_THEME_CATEGORIES:
            multiplier = ENERGY_THEME_MULTIPLIERS.get(category_lower, 1.0)
        else:
            multiplier = 1.0
        
        severity = alert.severity if alert.severity is not None else 3
        confidence = alert.confidence if alert.confidence is not None else 1.0
        
        total += severity * confidence * multiplier
    
    return total


ENERGY_ASSETS = {'gas', 'oil', 'power', 'lng', 'electricity', 'freight', 'fx'}

def compute_asset_transmission(alerts: List[AlertRecord], theme: str = 'energy') -> float:
    """
    Compute AssetTransmission for a theme.
    Count distinct assets with spikes related to the theme.
    
    Energy assets: gas, power, oil, lng, freight, fx
    """
    theme_assets = set()
    
    for alert in alerts:
        if alert.alert_type == 'ASSET_RISK_SPIKE' and alert.assets:
            for asset in alert.assets:
                if asset and asset.lower() in ENERGY_ASSETS:
                    theme_assets.add(asset.lower())
    
    return float(len(theme_assets))


def compute_contagion(
    neighbor_reri_values: Dict[str, int],
    target_region: str = 'europe'
) -> float:
    """
    Compute Contagion component from neighboring regions.
    Contagion = sum(neighbor_weight * neighbor_RERI / 100)
    
    For Europe:
    - Middle East: weight 0.6
    - Black Sea: weight 0.4
    """
    from src.reri.types import CONTAGION_NEIGHBORS
    
    if target_region not in CONTAGION_NEIGHBORS:
        return 0.0
    
    neighbors = CONTAGION_NEIGHBORS[target_region]
    total = 0.0
    
    for neighbor_id, weight in neighbors.items():
        neighbor_reri = neighbor_reri_values.get(neighbor_id, 0)
        total += weight * (neighbor_reri / 100.0)
    
    return total


def compute_eeri_components(
    alerts: List[AlertRecord],
    reri_eu_value: int,
    reri_eu_components: RERIComponents,
    neighbor_reri_values: Optional[Dict[str, int]] = None,
) -> EERIComponents:
    """
    Compute EERI (Europe Energy Risk Index) components.
    EERI formula:
    EERI = 100 * clamp(
        0.45*RERI_EU + 
        0.25*ThemePressure_norm + 
        0.20*AssetTransmission_norm + 
        0.10*Contagion
    )
    
    Theme filters: ENERGY, SUPPLY_DISRUPTION, SANCTIONS, WAR/MILITARY
    Energy assets: gas, power, oil, lng, freight, fx
    Contagion neighbors: Middle East (0.6), Black Sea (0.4)
    """
    components = EERIComponents()
    components.reri_eu_value = reri_eu_value
    components.reri_eu_components = reri_eu_components
    
    components.theme_pressure_raw = compute_theme_pressure(alerts, 'energy')
    components.theme_pressure_norm = clamp(
        components.theme_pressure_raw / NORMALIZATION_CAPS['theme_pressure']
    )
    
    components.asset_transmission_raw = compute_asset_transmission(alerts, 'energy')
    components.asset_transmission_norm = clamp(
        components.asset_transmission_raw / NORMALIZATION_CAPS['asset_transmission']
    )
    
    if neighbor_reri_values:
        components.contagion_raw = compute_contagion(neighbor_reri_values, 'europe')
        components.contagion_norm = clamp(components.contagion_raw)
    else:
        components.contagion_raw = 0.0
        components.contagion_norm = 0.0
    
    return components


def compute_eeri_value(components: EERIComponents) -> int:
    """
    Compute EERI value from components.
    EERI = 100 * clamp(
        0.45*RERI_EU/100 + 
        0.25*ThemePressure_norm + 
        0.20*AssetTransmission_norm +
        0.10*Contagion_norm
    )
    """
    weights = EERI_WEIGHTS
    
    raw_value = (
        weights['reri_eu'] * (components.reri_eu_value / 100.0) +
        weights['theme_pressure'] * components.theme_pressure_norm +
        weights['asset_transmission'] * components.asset_transmission_norm +
        weights['contagion'] * components.contagion_norm
    )
    
    return int(round(clamp(raw_value, 0, 1) * 100))


def extract_top_drivers(alerts: List[AlertRecord], limit: int = 5) -> List[Dict[str, Any]]:
    """
    Extract top driver events based on severity and confidence.
    Returns list of driver dicts with headline, severity, category.
    """
    scored_alerts = []
    
    for alert in alerts:
        if alert.alert_type != 'HIGH_IMPACT_EVENT':
            continue
        
        severity = alert.severity if alert.severity is not None else 3
        confidence = alert.confidence if alert.confidence is not None else 1.0
        score = severity * confidence
        
        title = extract_event_title_from_body(alert.body) or alert.headline or "Unknown event"
        category = extract_category_from_body(alert.body) if not alert.category else alert.category
        
        scored_alerts.append({
            'headline': title[:100],
            'severity': severity,
            'category': category,
            'confidence': round(confidence, 2),
            'score': round(score, 2),
        })
    
    sorted_alerts = sorted(scored_alerts, key=lambda x: x['score'], reverse=True)
    return sorted_alerts[:limit]


def generate_interpretation(
    eeri_value: int,
    components: EERIComponents,
    drivers: List[Dict[str, Any]]
) -> str:
    """Generate human-readable interpretation of EERI value."""
    if eeri_value >= 76:
        level = "CRITICAL"
        outlook = "Significant energy supply disruption risk detected"
    elif eeri_value >= 51:
        level = "ELEVATED"
        outlook = "Heightened energy market stress observed"
    elif eeri_value >= 26:
        level = "MODERATE"
        outlook = "Some energy-related risk signals present"
    else:
        level = "LOW"
        outlook = "Energy risk environment relatively calm"
    
    driver_summary = ""
    if drivers:
        top_driver = drivers[0]['headline'][:60]
        driver_summary = f" Top driver: {top_driver}."
    
    assets = components.reri_eu_components.distinct_assets if components.reri_eu_components else []
    asset_summary = f" Assets affected: {', '.join(assets)}." if assets else ""
    
    return f"{level}: {outlook}.{driver_summary}{asset_summary}"
