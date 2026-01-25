"""
Unit tests for EERI compute functions.
"""
import pytest
from datetime import datetime
from typing import Optional

from src.reri.types import AlertRecord
from src.reri.compute import (
    clamp,
    extract_category_from_body,
    normalize_region,
    get_category_weight,
    compute_severity_pressure,
    compute_high_impact_count,
    compute_asset_overlap,
    compute_velocity,
    compute_reri_components,
    compute_reri_value,
    compute_eeri_components,
    compute_eeri_value,
)


def test_clamp():
    assert clamp(0.5) == 0.5
    assert clamp(-0.1) == 0.0
    assert clamp(1.5) == 1.0
    assert clamp(0.0) == 0.0
    assert clamp(1.0) == 1.0


def test_extract_category_from_body():
    body_energy = "HIGH-IMPACT EVENT ALERT\n\nEvent: Gas pipeline issue\nCategory: ENERGY\nRegion: Europe"
    assert extract_category_from_body(body_energy) == 'energy'
    
    body_sanctions = "Event: New sanctions\nCategory: SANCTIONS\nRegion: Europe"
    assert extract_category_from_body(body_sanctions) == 'sanctions'
    
    body_supply = "Category: supply_chain"
    assert extract_category_from_body(body_supply) == 'supply_chain'
    
    assert extract_category_from_body(None) == 'unknown'
    assert extract_category_from_body("No category here") == 'unknown'


def test_normalize_region():
    assert normalize_region("Europe") == 'europe'
    assert normalize_region("EU") == 'europe'
    assert normalize_region("Western Europe") == 'europe'
    
    assert normalize_region("Middle East") == 'middle-east'
    assert normalize_region("Persian Gulf") == 'middle-east'
    
    assert normalize_region("Black Sea") == 'black-sea'
    assert normalize_region("Ukraine") == 'black-sea'
    
    assert normalize_region("Asia Pacific") is None
    assert normalize_region(None) is None


def test_get_category_weight():
    assert get_category_weight('war') == 1.6
    assert get_category_weight('energy') == 1.3
    assert get_category_weight('political') == 1.0
    assert get_category_weight('diplomacy') == 0.7
    assert get_category_weight('unknown_cat') == 1.0


_alert_id_counter = 0

def make_alert(
    alert_type: str = 'HIGH_IMPACT_EVENT',
    severity: int = 5,
    confidence: float = 0.9,
    region: str = 'Europe',
    assets: Optional[list] = None,
    body: Optional[str] = None,
) -> AlertRecord:
    global _alert_id_counter
    _alert_id_counter += 1
    return AlertRecord(
        id=_alert_id_counter,
        alert_type=alert_type,
        severity=severity,
        confidence=confidence,
        region=region,
        assets=assets or [],
        created_at=datetime.utcnow(),
        headline="Test alert",
        body=body or "Event: Test\nCategory: ENERGY\nRegion: Europe",
    )


def test_compute_severity_pressure():
    alerts = [
        make_alert(alert_type='HIGH_IMPACT_EVENT', severity=5, confidence=0.9),
        make_alert(alert_type='HIGH_IMPACT_EVENT', severity=4, confidence=0.8),
    ]
    
    s = compute_severity_pressure(alerts)
    assert s > 0
    expected = (5 * 1.3 * 0.9) + (4 * 1.3 * 0.8)
    assert abs(s - expected) < 0.01


def test_severity_pressure_excludes_regional_spike():
    """REGIONAL_RISK_SPIKE should NOT be included in severity calculation."""
    alerts = [
        make_alert(alert_type='HIGH_IMPACT_EVENT', severity=5, confidence=1.0),
        make_alert(alert_type='REGIONAL_RISK_SPIKE', severity=5, confidence=1.0),
    ]
    
    s = compute_severity_pressure(alerts)
    expected = 5 * 1.3 * 1.0
    assert abs(s - expected) < 0.01


def test_compute_high_impact_count():
    alerts = [
        make_alert(alert_type='HIGH_IMPACT_EVENT', severity=5),
        make_alert(alert_type='HIGH_IMPACT_EVENT', severity=3),
        make_alert(alert_type='ASSET_RISK_SPIKE', severity=3),
        make_alert(alert_type='REGIONAL_RISK_SPIKE', severity=2),
    ]
    
    h = compute_high_impact_count(alerts)
    assert h == 3


def test_high_impact_includes_regional_spike_for_clustering():
    """REGIONAL_RISK_SPIKE IS included in high-impact count (for clustering signal)."""
    alerts = [
        make_alert(alert_type='HIGH_IMPACT_EVENT', severity=5),
        make_alert(alert_type='REGIONAL_RISK_SPIKE', severity=5),
    ]
    
    h = compute_high_impact_count(alerts)
    assert h == 2


def test_high_impact_counts_severity_ge_4():
    """Alerts with severity >= 4 should count even if not HIGH_IMPACT_EVENT."""
    alerts = [
        make_alert(alert_type='ASSET_RISK_SPIKE', severity=4),
        make_alert(alert_type='ASSET_RISK_SPIKE', severity=3),
    ]
    
    h = compute_high_impact_count(alerts)
    assert h == 1


def test_compute_asset_overlap():
    alerts = [
        make_alert(alert_type='ASSET_RISK_SPIKE', assets=['gas']),
        make_alert(alert_type='ASSET_RISK_SPIKE', assets=['oil', 'gas']),
        make_alert(alert_type='HIGH_IMPACT_EVENT', assets=['power']),
    ]
    
    count, assets = compute_asset_overlap(alerts)
    assert count == 2
    assert 'gas' in assets
    assert 'oil' in assets


def test_compute_velocity():
    historical = [5.0, 6.0, 7.0]
    current = 10.0
    
    v = compute_velocity(current, historical)
    avg_hist = (5.0 + 6.0 + 7.0) / 3
    expected = 10.0 - avg_hist
    assert abs(v - expected) < 0.01


def test_compute_reri_components():
    alerts = [
        make_alert(alert_type='HIGH_IMPACT_EVENT', severity=5, confidence=0.9, assets=['gas']),
        make_alert(alert_type='ASSET_RISK_SPIKE', severity=4, confidence=0.8, assets=['oil']),
    ]
    
    components = compute_reri_components(alerts)
    
    assert components.total_alerts == 2
    assert components.severity_pressure_raw > 0
    assert components.severity_pressure_norm >= 0
    assert components.severity_pressure_norm <= 1


def test_compute_reri_value():
    alerts = [
        make_alert(severity=5, confidence=1.0),
    ]
    
    components = compute_reri_components(alerts)
    value = compute_reri_value(components)
    
    assert 0 <= value <= 100


def test_compute_eeri_value():
    alerts = [
        make_alert(severity=5, confidence=0.9),
    ]
    
    reri_components = compute_reri_components(alerts)
    reri_value = compute_reri_value(reri_components)
    
    eeri_components = compute_eeri_components(alerts, reri_value, reri_components)
    eeri_value = compute_eeri_value(eeri_components)
    
    assert 0 <= eeri_value <= 100
    assert eeri_components.reri_eu_value == reri_value


def test_empty_alerts():
    components = compute_reri_components([])
    
    assert components.total_alerts == 0
    assert components.severity_pressure_raw == 0
    assert components.high_impact_count == 0
    
    value = compute_reri_value(components)
    assert value == 0
