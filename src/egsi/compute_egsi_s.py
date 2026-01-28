"""
EGSI-S Compute Module

Computes EGSI-S (System Stress) index based on:
- Storage levels vs seasonal targets
- TTF price volatility
- Injection/withdrawal rates
- Winter readiness assessment
- Supply-related alerts
"""
import logging
from datetime import date, datetime
from typing import Optional, List, Dict, Any

from src.egsi.types import (
    EGSI_S_WEIGHTS,
    EGSI_S_NORMALIZATION_CAPS,
    EGSI_S_STORAGE_TARGETS,
    EGSISComponents,
    MarketDataSnapshot,
    clamp,
    get_egsi_band,
)
from src.egsi.data_sources import get_market_data_provider

logger = logging.getLogger(__name__)


def get_seasonal_storage_target(target_date: date) -> float:
    """
    Get the seasonal storage target for a given date.
    
    EU storage targets:
    - Nov 1 (winter start): 90%
    - Spring (Mar-May): 30%
    - Summer (Jun-Aug): 50%
    - Autumn (Sep-Oct): 80%
    """
    month = target_date.month
    
    if month == 11:
        return EGSI_S_STORAGE_TARGETS['winter_start']
    elif month in [12, 1, 2]:
        days_into_winter = (target_date.month - 12) % 12 * 30 + target_date.day
        decay = days_into_winter * 0.004
        return max(0.40, EGSI_S_STORAGE_TARGETS['winter_start'] - decay)
    elif month in [3, 4, 5]:
        return EGSI_S_STORAGE_TARGETS['spring']
    elif month in [6, 7, 8]:
        return EGSI_S_STORAGE_TARGETS['summer']
    else:
        return EGSI_S_STORAGE_TARGETS['autumn']


def days_until_winter_start(target_date: date) -> int:
    """Calculate days until November 1 (EU winter heating season start)."""
    current_year = target_date.year
    winter_start = date(current_year, 11, 1)
    
    if target_date >= winter_start:
        winter_start = date(current_year + 1, 11, 1)
    
    return (winter_start - target_date).days


def compute_storage_stress(
    storage_level_pct: float,
    target_pct: float,
    days_to_winter: int
) -> float:
    """
    Compute storage stress based on current vs target levels.
    
    Higher stress when:
    - Below target
    - Close to winter
    - Large gap between current and target
    """
    gap = target_pct - storage_level_pct
    
    if gap <= 0:
        return 0.0
    
    if days_to_winter > 180:
        urgency_factor = 0.5
    elif days_to_winter > 90:
        urgency_factor = 0.8
    elif days_to_winter > 30:
        urgency_factor = 1.2
    else:
        urgency_factor = 1.5
    
    stress = gap * 100 * urgency_factor
    
    return min(100.0, stress)


def compute_price_volatility_stress(
    current_price: float,
    ma7_price: float,
    volatility: float
) -> float:
    """
    Compute price volatility stress.
    
    Higher stress when:
    - Current price significantly above moving average
    - High historical volatility
    """
    if ma7_price <= 0:
        return 0.0
    
    deviation = abs(current_price - ma7_price) / ma7_price * 100
    
    combined = deviation * 0.6 + volatility * 0.4
    
    return min(50.0, combined)


def compute_injection_stress(injection_rate: float, is_injection_season: bool) -> float:
    """
    Compute injection/withdrawal stress.
    
    During injection season (Apr-Oct): Stress if injection rate too low
    During withdrawal season (Nov-Mar): Stress if withdrawal rate too high
    """
    if is_injection_season:
        if injection_rate < 0:
            return 5.0
        elif injection_rate < 0.5:
            return 3.0
        else:
            return 0.0
    else:
        if injection_rate < -1.0:
            return 4.0
        elif injection_rate < -0.5:
            return 2.0
        else:
            return 0.0


def compute_winter_readiness(
    storage_level_pct: float,
    days_to_winter: int,
    is_before_winter: bool
) -> float:
    """
    Compute winter readiness score.
    
    Higher stress when winter is approaching and storage is below target.
    """
    if not is_before_winter or days_to_winter > 120:
        return 0.0
    
    target_90 = 0.90
    gap = max(0, target_90 - storage_level_pct)
    
    if days_to_winter > 60:
        time_factor = 0.5
    elif days_to_winter > 30:
        time_factor = 1.0
    else:
        time_factor = 2.0
    
    stress = gap * 100 * time_factor
    
    return min(100.0, stress)


def compute_supply_pressure(alerts: List[Dict[str, Any]]) -> float:
    """
    Compute supply pressure from supply-related alerts.
    """
    supply_keywords = ['supply', 'shortage', 'disruption', 'outage', 'maintenance', 'force majeure']
    
    count = 0
    weight_sum = 0.0
    
    for alert in alerts:
        text = f"{alert.get('title', '')} {alert.get('summary', '')}".lower()
        for kw in supply_keywords:
            if kw in text:
                count += 1
                impact = alert.get('impact_score', 3)
                weight_sum += impact / 5.0
                break
    
    return min(1.0, weight_sum / 5.0) if count > 0 else 0.0


def generate_egsi_s_interpretation(
    value: float,
    components: EGSISComponents,
    days_to_winter: int
) -> str:
    """Generate human-readable interpretation of EGSI-S value."""
    band = get_egsi_band(value)
    
    if band.value == "LOW":
        base = "European gas system is in comfortable position"
    elif band.value == "NORMAL":
        base = "European gas system shows baseline stress levels"
    elif band.value == "ELEVATED":
        base = "European gas system shows elevated stress signals"
    elif band.value == "HIGH":
        base = "European gas system under significant stress"
    else:
        base = "European gas system in critical stress condition"
    
    factors = []
    
    if components.storage_stress_norm > 0.5:
        factors.append("storage below seasonal targets")
    
    if components.price_volatility_norm > 0.5:
        factors.append("elevated price volatility")
    
    if days_to_winter < 60 and components.winter_readiness_norm > 0.3:
        factors.append(f"winter readiness concerns ({days_to_winter} days to Nov 1)")
    
    if components.supply_pressure > 0.3:
        factors.append("supply-side alerts active")
    
    if factors:
        return f"{base} with {', '.join(factors)}."
    else:
        return f"{base}."


def identify_egsi_s_drivers(components: EGSISComponents) -> List[Dict[str, Any]]:
    """Identify top drivers of EGSI-S value."""
    drivers = []
    
    if components.storage_stress_norm > 0.2:
        drivers.append({
            'name': 'Storage Gap',
            'type': 'storage',
            'contribution': round(EGSI_S_WEIGHTS['storage'] * components.storage_stress_norm * 100, 1),
            'details': {
                'current': f"{components.storage_level_pct * 100:.1f}%",
                'target': f"{components.storage_target_pct * 100:.1f}%",
            },
        })
    
    if components.price_volatility_norm > 0.2:
        drivers.append({
            'name': 'Price Volatility',
            'type': 'market',
            'contribution': round(EGSI_S_WEIGHTS['market'] * components.price_volatility_norm * 100, 1),
            'details': {
                'ttf_price': f"{components.ttf_price:.2f} EUR/MWh",
                'volatility': f"{components.price_volatility_raw:.1f}%",
            },
        })
    
    if components.winter_readiness_norm > 0.2:
        drivers.append({
            'name': 'Winter Readiness',
            'type': 'seasonal',
            'contribution': round(EGSI_S_WEIGHTS['supply'] * components.winter_readiness_norm * 100, 1),
            'details': {
                'days_to_winter': components.days_to_winter,
            },
        })
    
    if components.supply_pressure > 0.2:
        drivers.append({
            'name': 'Supply Alerts',
            'type': 'alerts',
            'contribution': round(EGSI_S_WEIGHTS['policy'] * components.supply_pressure * 100, 1),
            'details': {
                'alert_count': components.supply_alerts_count,
            },
        })
    
    drivers.sort(key=lambda x: x['contribution'], reverse=True)
    
    return drivers[:5]


def compute_egsi_s_components(
    market_data: MarketDataSnapshot,
    alerts: List[Dict[str, Any]],
) -> EGSISComponents:
    """
    Compute all EGSI-S components from market data and alerts.
    """
    target_date = market_data.data_date
    
    storage_target = get_seasonal_storage_target(target_date)
    days_to_winter = days_until_winter_start(target_date)
    is_before_winter = target_date.month in [4, 5, 6, 7, 8, 9, 10]
    is_injection_season = target_date.month in [4, 5, 6, 7, 8, 9, 10]
    
    storage_level = market_data.storage_level_pct or 0.0
    ttf_price = market_data.ttf_price or 0.0
    ttf_ma7 = market_data.ttf_price_ma7 or ttf_price
    volatility = market_data.ttf_volatility or 0.0
    injection_rate = market_data.injection_rate_twh or 0.0
    
    storage_stress = compute_storage_stress(storage_level, storage_target, days_to_winter)
    storage_stress_norm = clamp(storage_stress / EGSI_S_NORMALIZATION_CAPS['storage_stress'])
    
    price_vol_stress = compute_price_volatility_stress(ttf_price, ttf_ma7, volatility)
    price_vol_norm = clamp(price_vol_stress / EGSI_S_NORMALIZATION_CAPS['price_volatility'])
    
    injection_stress = compute_injection_stress(injection_rate, is_injection_season)
    injection_norm = clamp(injection_stress / EGSI_S_NORMALIZATION_CAPS['injection_rate'])
    
    winter_stress = compute_winter_readiness(storage_level, days_to_winter, is_before_winter)
    winter_norm = clamp(winter_stress / EGSI_S_NORMALIZATION_CAPS['winter_readiness'])
    
    supply_pressure = compute_supply_pressure(alerts)
    
    components = EGSISComponents(
        storage_level_pct=storage_level,
        storage_target_pct=storage_target,
        storage_stress_raw=storage_stress,
        storage_stress_norm=storage_stress_norm,
        
        ttf_price=ttf_price,
        ttf_price_ma7=ttf_ma7,
        price_volatility_raw=price_vol_stress,
        price_volatility_norm=price_vol_norm,
        
        injection_rate=injection_rate,
        injection_rate_norm=injection_norm,
        
        winter_readiness_raw=winter_stress,
        winter_readiness_norm=winter_norm,
        days_to_winter=days_to_winter,
        
        supply_alerts_count=len(alerts),
        supply_pressure=supply_pressure,
        
        data_sources=[market_data.source],
    )
    
    components.top_drivers = identify_egsi_s_drivers(components)
    components.interpretation = generate_egsi_s_interpretation(0, components, days_to_winter)
    
    return components


def compute_egsi_s_value(components: EGSISComponents) -> float:
    """
    Compute final EGSI-S index value from components.
    
    Formula: 100 * weighted sum of normalized components
    """
    value = 100 * (
        EGSI_S_WEIGHTS['storage'] * components.storage_stress_norm +
        EGSI_S_WEIGHTS['market'] * components.price_volatility_norm +
        EGSI_S_WEIGHTS['transit'] * components.injection_rate_norm +
        EGSI_S_WEIGHTS['supply'] * components.winter_readiness_norm +
        EGSI_S_WEIGHTS['policy'] * components.supply_pressure
    )
    
    return max(0.0, min(100.0, value))
