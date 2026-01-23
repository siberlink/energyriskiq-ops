"""
GERI v1 Compute Functions (Pure Functions)

Calculates index components from alert data.
"""
import re
from typing import List, Dict, Any, Optional
from collections import defaultdict

from src.geri.types import (
    AlertRecord,
    GERIComponents,
    VALID_ALERT_TYPES,
)


def extract_event_title_from_body(body: Optional[str]) -> Optional[str]:
    """
    Extract actual event title from HIGH_IMPACT_EVENT body.
    Body format: "HIGH-IMPACT EVENT ALERT\n\nEvent: <actual title>\nSeverity: ..."
    """
    if not body:
        return None
    
    match = re.search(r'Event:\s*(.+?)(?:\n|$)', body)
    if match:
        return match.group(1).strip()
    return None


def extract_category_from_body(body: Optional[str]) -> Optional[str]:
    """
    Extract category from HIGH_IMPACT_EVENT body.
    Body format: "...Category: ENERGY\nRegion: ..."
    Returns lowercase category (energy, geopolitical, supply_chain)
    """
    if not body:
        return None
    
    match = re.search(r'Category:\s*(\w+)', body, re.IGNORECASE)
    if match:
        cat = match.group(1).strip().lower()
        # Normalize category names
        if cat == 'supply_chain' or cat == 'supplychain':
            return 'supply_chain'
        return cat
    return None


def severity_from_risk_score(risk_score: float) -> int:
    """Map risk_score to severity (1-5 buckets)."""
    if risk_score is None:
        return 3
    if risk_score >= 80:
        return 5
    elif risk_score >= 60:
        return 4
    elif risk_score >= 40:
        return 3
    elif risk_score >= 20:
        return 2
    else:
        return 1


def risk_score_from_severity(severity: int) -> float:
    """Map severity (1-5) to risk_score approximation."""
    if severity is None:
        return 50.0
    mapping = {1: 10.0, 2: 30.0, 3: 50.0, 4: 70.0, 5: 90.0}
    return mapping.get(severity, 50.0)


def get_effective_severity(alert: AlertRecord) -> int:
    """Get severity, deriving from risk_score if missing."""
    if alert.severity is not None:
        return alert.severity
    return severity_from_risk_score(alert.risk_score)


def get_effective_risk_score(alert: AlertRecord) -> float:
    """Get risk_score, deriving from severity if missing."""
    if alert.risk_score is not None:
        return alert.risk_score
    return risk_score_from_severity(alert.severity)


def compute_components(alerts: List[AlertRecord]) -> GERIComponents:
    """
    Compute GERI components from a list of alerts.
    Pure function - no side effects.
    """
    components = GERIComponents()
    components.total_alerts = len(alerts)
    
    if not alerts:
        return components
    
    region_risk_totals: Dict[str, float] = defaultdict(float)
    severity_sum = 0.0
    alert_scores: List[Dict[str, Any]] = []
    
    for alert in alerts:
        severity = get_effective_severity(alert)
        risk_score = get_effective_risk_score(alert)
        weight = alert.weight if alert.weight else 1.0
        region = alert.region if alert.region else "Unknown"
        
        severity_sum += severity
        region_risk_totals[region] += risk_score
        
        if alert.headline:
            # For HIGH_IMPACT_EVENT, try to extract actual event title and category from body
            display_headline = alert.headline
            display_category = alert.category or ''
            if alert.alert_type == 'HIGH_IMPACT_EVENT' and alert.body:
                extracted_title = extract_event_title_from_body(alert.body)
                if extracted_title:
                    display_headline = extracted_title
                extracted_category = extract_category_from_body(alert.body)
                if extracted_category:
                    display_category = extracted_category
            
            alert_scores.append({
                'headline': display_headline,
                'alert_type': alert.alert_type,
                'severity': severity,
                'risk_score': risk_score,
                'region': region,
                'category': display_category,
            })
        
        if alert.alert_type == 'HIGH_IMPACT_EVENT':
            components.high_impact_events += 1
            components.high_impact_score += severity * weight
        
        elif alert.alert_type == 'REGIONAL_RISK_SPIKE':
            components.regional_spikes += 1
            components.regional_spike_score += risk_score
        
        elif alert.alert_type == 'ASSET_RISK_ALERT':
            components.asset_spikes += 1
            components.asset_risk_score += risk_score
    
    components.avg_severity = severity_sum / len(alerts) if alerts else 0.0
    
    components.regions_count = len(region_risk_totals)
    
    if region_risk_totals:
        sorted_regions = sorted(
            region_risk_totals.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        components.top_regions = [
            {'region': r, 'risk_total': round(v, 2)}
            for r, v in sorted_regions[:3]
        ]
        
        total_risk = sum(region_risk_totals.values())
        if total_risk > 0:
            max_region_risk = sorted_regions[0][1]
            components.top_region_weight = max_region_risk / total_risk
            components.region_concentration_score_raw = components.top_region_weight * 100
    
    if alert_scores:
        # Filter out REGIONAL_RISK_SPIKE - these are aggregated alerts, not atomic drivers
        # Also filter out ASSET_RISK_SPIKE since they are derived alerts
        atomic_drivers = [
            a for a in alert_scores 
            if a.get('alert_type') not in ('REGIONAL_RISK_SPIKE', 'ASSET_RISK_SPIKE')
        ]
        
        # Fall back to all alerts if no atomic drivers found
        candidates = atomic_drivers if atomic_drivers else alert_scores
        
        sorted_alerts = sorted(
            candidates,
            key=lambda x: (x['severity'], x['risk_score']),
            reverse=True
        )
        # Deduplicate by headline, keeping highest-scored instance
        seen_headlines = set()
        unique_drivers = []
        for alert in sorted_alerts:
            if alert['headline'] not in seen_headlines:
                seen_headlines.add(alert['headline'])
                unique_drivers.append(alert)
                if len(unique_drivers) >= 5:
                    break
        components.top_drivers = unique_drivers
    
    return components
