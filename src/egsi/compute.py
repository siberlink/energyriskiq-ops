"""
EGSI-M Compute Engine

Calculates Europe Gas Stress Index (Market/Transmission) from:
- RERI_EU value (regional risk anchor)
- Theme Pressure (gas-related alerts)
- Asset Transmission (gas asset risk spikes)
- Chokepoint Factor (infrastructure entity mentions)

Formula: EGSI-M = 100 * (0.35*RERI_EU/100 + 0.35*ThemePressure_norm + 0.20*AssetTransmission_norm + 0.10*Chokepoint_norm)
"""
import logging
import re
from typing import List, Dict, Any, Optional, Tuple

from src.egsi.types import (
    EGSIMComponents,
    EGSI_M_WEIGHTS,
    CHOKEPOINTS_V1,
    GAS_THEME_KEYWORDS,
    NORMALIZATION_CAPS,
    clamp,
)
from src.reri.types import AlertRecord

logger = logging.getLogger(__name__)


def is_gas_related(alert: AlertRecord) -> bool:
    """Check if alert is related to gas/LNG themes."""
    text = f"{alert.headline or ''} {alert.body or ''} {alert.category or ''}".lower()
    
    for keyword in GAS_THEME_KEYWORDS:
        if keyword in text:
            return True
    
    if alert.assets:
        for asset in alert.assets:
            if asset and asset.lower() in ['gas', 'lng', 'natural gas', 'ttf']:
                return True
    
    return False


def compute_theme_pressure(alerts: List[AlertRecord]) -> Tuple[float, int]:
    """
    Compute Theme Pressure component - gas-related alert pressure in Europe.
    
    Returns:
        Tuple of (raw_pressure, gas_alert_count)
    """
    total_pressure = 0.0
    gas_count = 0
    
    for alert in alerts:
        if not is_gas_related(alert):
            continue
        
        gas_count += 1
        severity = alert.severity if alert.severity is not None else 3
        confidence = alert.confidence if alert.confidence is not None else 0.8
        
        base_weight = 1.0
        if alert.alert_type == 'HIGH_IMPACT_EVENT':
            base_weight = 1.5
        elif alert.alert_type == 'ASSET_RISK_SPIKE':
            base_weight = 1.3
        
        total_pressure += severity * confidence * base_weight
    
    return total_pressure, gas_count


def compute_asset_transmission(alerts: List[AlertRecord]) -> Tuple[float, int, List[str]]:
    """
    Compute Asset Transmission component - distinct gas assets with risk spikes.
    
    Returns:
        Tuple of (raw_transmission, asset_count, affected_assets)
    """
    gas_assets = set()
    transmission_score = 0.0
    
    for alert in alerts:
        if alert.alert_type != 'ASSET_RISK_SPIKE':
            continue
        
        if not alert.assets:
            continue
        
        for asset in alert.assets:
            if not asset:
                continue
            
            asset_lower = asset.lower()
            if asset_lower in ['gas', 'lng', 'natural gas', 'ttf', 'power', 'electricity']:
                gas_assets.add(asset_lower)
                
                severity = alert.severity if alert.severity is not None else 3
                confidence = alert.confidence if alert.confidence is not None else 0.8
                transmission_score += severity * confidence * 0.5
    
    return transmission_score, len(gas_assets), sorted(list(gas_assets))


def match_chokepoint(text: str, chokepoint: Dict[str, Any]) -> bool:
    """Check if text mentions a chokepoint entity."""
    text_lower = text.lower()
    for keyword in chokepoint['keywords']:
        if keyword in text_lower:
            return True
    return False


def compute_chokepoint_factor(alerts: List[AlertRecord]) -> Tuple[float, List[Dict[str, Any]]]:
    """
    Compute Chokepoint Factor - infrastructure entity mentions weighted by importance.
    
    Returns:
        Tuple of (raw_factor, chokepoint_hits)
    """
    chokepoint_scores: Dict[str, float] = {}
    chokepoint_alerts: Dict[str, List[Dict]] = {}
    
    for alert in alerts:
        text = f"{alert.headline or ''} {alert.body or ''}"
        
        for cp in CHOKEPOINTS_V1['entities']:
            if match_chokepoint(text, cp):
                cp_id = cp['id']
                severity = alert.severity if alert.severity is not None else 3
                confidence = alert.confidence if alert.confidence is not None else 0.8
                weight = cp['weight']
                
                score = severity * confidence * weight
                
                if cp_id not in chokepoint_scores:
                    chokepoint_scores[cp_id] = 0.0
                    chokepoint_alerts[cp_id] = []
                
                chokepoint_scores[cp_id] += score
                chokepoint_alerts[cp_id].append({
                    'alert_id': alert.id,
                    'headline': alert.headline,
                    'severity': severity,
                })
    
    total_factor = sum(chokepoint_scores.values())
    
    hits = []
    for cp_id, score in sorted(chokepoint_scores.items(), key=lambda x: -x[1]):
        cp_info = next((c for c in CHOKEPOINTS_V1['entities'] if c['id'] == cp_id), None)
        if cp_info:
            hits.append({
                'chokepoint_id': cp_id,
                'name': cp_info['name'],
                'category': cp_info['category'],
                'score': round(score, 2),
                'alert_count': len(chokepoint_alerts[cp_id]),
            })
    
    return total_factor, hits


def normalize_component(raw_value: float, cap: float) -> float:
    """Normalize component using cap-based scaling (fallback for early days)."""
    if cap <= 0:
        return 0.0
    return clamp(raw_value / cap)


def compute_egsi_m_value(components: EGSIMComponents) -> float:
    """
    Compute EGSI-M value from components.
    
    EGSI-M = 100 * (0.35*RERI_EU/100 + 0.35*ThemePressure_norm + 0.20*AssetTransmission_norm + 0.10*Chokepoint_norm)
    """
    weights = EGSI_M_WEIGHTS
    
    raw_value = (
        weights['reri_eu'] * (components.reri_eu_value / 100.0) +
        weights['theme_pressure'] * components.theme_pressure_norm +
        weights['asset_transmission'] * components.asset_transmission_norm +
        weights['chokepoint_factor'] * components.chokepoint_factor_norm
    )
    
    return clamp(raw_value, 0, 1) * 100


def extract_top_drivers(
    alerts: List[AlertRecord],
    components: EGSIMComponents,
    max_drivers: int = 5
) -> List[Dict[str, Any]]:
    """
    Extract top drivers for EGSI-M move.
    
    Prioritizes:
    1. Chokepoint-related alerts (highest signal)
    2. Gas theme alerts with high severity
    3. Asset risk spikes on gas
    """
    scored_alerts = []
    
    for alert in alerts:
        if not is_gas_related(alert):
            continue
        
        severity = alert.severity if alert.severity is not None else 3
        confidence = alert.confidence if alert.confidence is not None else 0.8
        
        score = severity * confidence
        
        text = f"{alert.headline or ''} {alert.body or ''}"
        for cp in CHOKEPOINTS_V1['entities']:
            if match_chokepoint(text, cp):
                score *= 1.5
                break
        
        if alert.alert_type == 'HIGH_IMPACT_EVENT':
            score *= 1.3
        
        scored_alerts.append({
            'alert_id': alert.id,
            'headline': alert.headline,
            'severity': severity,
            'confidence': confidence,
            'score': round(score, 2),
            'region': alert.region,
            'category': alert.category,
        })
    
    scored_alerts.sort(key=lambda x: -x['score'])
    
    return scored_alerts[:max_drivers]


def generate_interpretation(value: float, components: EGSIMComponents) -> str:
    """Generate human-readable interpretation of EGSI-M."""
    if value <= 20:
        stress_level = "low"
        trend_desc = "stable"
    elif value <= 40:
        stress_level = "normal"
        trend_desc = "contained"
    elif value <= 60:
        stress_level = "elevated"
        trend_desc = "rising"
    elif value <= 80:
        stress_level = "high"
        trend_desc = "significant"
    else:
        stress_level = "critical"
        trend_desc = "extreme"
    
    drivers = []
    
    if components.reri_eu_value >= 50:
        drivers.append("regional risk regime")
    
    if components.theme_pressure_norm >= 0.5:
        drivers.append("gas-theme alert pressure")
    
    if components.chokepoint_hits:
        top_cp = components.chokepoint_hits[0]['name']
        drivers.append(f"infrastructure watch ({top_cp})")
    
    if components.asset_transmission_norm >= 0.5:
        drivers.append("gas asset risk transmission")
    
    driver_text = ", ".join(drivers) if drivers else "baseline factors"
    
    return f"Europe gas market stress is {stress_level} with {trend_desc} transmission pressure driven by {driver_text}."


def compute_egsi_m_components(
    alerts: List[AlertRecord],
    reri_eu_value: int,
    use_percentile_norm: bool = False,
    norm_stats: Optional[Dict[str, Any]] = None,
) -> EGSIMComponents:
    """
    Compute all EGSI-M components from daily alerts and RERI_EU.
    
    Args:
        alerts: List of alerts for the day (Europe region)
        reri_eu_value: RERI value for Europe (0-100)
        use_percentile_norm: Whether to use percentile-based normalization
        norm_stats: Historical normalization stats if using percentile scaling
    
    Returns:
        EGSIMComponents with all raw and normalized values
    """
    components = EGSIMComponents()
    components.reri_eu_value = reri_eu_value
    
    theme_raw, theme_count = compute_theme_pressure(alerts)
    components.theme_pressure_raw = theme_raw
    components.theme_alert_count = theme_count
    
    if use_percentile_norm and norm_stats and 'theme_pressure' in norm_stats:
        stats = norm_stats['theme_pressure']
        components.theme_pressure_norm = stats.normalize(theme_raw)
    else:
        components.theme_pressure_norm = normalize_component(
            theme_raw, NORMALIZATION_CAPS['theme_pressure']
        )
    
    trans_raw, asset_count, affected_assets = compute_asset_transmission(alerts)
    components.asset_transmission_raw = trans_raw
    components.asset_count = asset_count
    components.affected_assets = affected_assets
    
    if use_percentile_norm and norm_stats and 'asset_transmission' in norm_stats:
        stats = norm_stats['asset_transmission']
        components.asset_transmission_norm = stats.normalize(trans_raw)
    else:
        components.asset_transmission_norm = normalize_component(
            trans_raw, NORMALIZATION_CAPS['asset_transmission']
        )
    
    cp_raw, cp_hits = compute_chokepoint_factor(alerts)
    components.chokepoint_factor_raw = cp_raw
    components.chokepoint_hits = cp_hits
    
    if use_percentile_norm and norm_stats and 'chokepoint_factor' in norm_stats:
        stats = norm_stats['chokepoint_factor']
        components.chokepoint_factor_norm = stats.normalize(cp_raw)
    else:
        components.chokepoint_factor_norm = normalize_component(
            cp_raw, NORMALIZATION_CAPS['chokepoint_factor']
        )
    
    components.top_drivers = extract_top_drivers(alerts, components)
    
    value = compute_egsi_m_value(components)
    components.interpretation = generate_interpretation(value, components)
    
    return components
