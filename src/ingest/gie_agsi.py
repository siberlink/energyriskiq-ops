"""
GIE AGSI+ (Gas Infrastructure Europe - Aggregated Gas Storage Inventory) Integration

Fetches EU gas storage data for quantitative risk alerts:
- EU gas storage level vs seasonal norm
- Refill speed (injection/withdrawal rates)
- Winter deviation risk (current level vs target trajectory)

API Documentation: https://www.gie.eu/transparency-platform/GIE_API_documentation_v007.pdf
Data Source: https://agsi.gie.eu/
"""

import os
import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)

GIE_API_BASE = "https://agsi.gie.eu/api"
GIE_API_KEY = os.environ.get("GIE_API_KEY", "")

EU_STORAGE_TARGET_NOV1 = 90.0
EU_STORAGE_TARGET_FEB1 = 45.0

SEASONAL_NORMS = {
    1: 65.0,
    2: 50.0,
    3: 40.0,
    4: 45.0,
    5: 55.0,
    6: 65.0,
    7: 75.0,
    8: 82.0,
    9: 88.0,
    10: 92.0,
    11: 90.0,
    12: 80.0,
}

MAJOR_EU_COUNTRIES = ["DE", "IT", "FR", "AT", "NL", "PL", "CZ", "HU", "SK", "BE"]


@dataclass
class StorageSnapshot:
    """Represents a daily gas storage snapshot."""
    date: str
    country: str
    gas_in_storage_twh: float
    full_percent: float
    injection_twh: float
    withdrawal_twh: float
    working_gas_volume_twh: float
    trend_vs_yesterday: float
    consumption_days: Optional[float] = None


@dataclass
class StorageMetrics:
    """Computed storage risk metrics."""
    date: str
    eu_storage_percent: float
    seasonal_norm: float
    deviation_from_norm: float
    refill_speed_7d: float
    withdrawal_rate_7d: float
    winter_deviation_risk: str
    days_to_target: Optional[int] = None
    risk_score: int = 0
    risk_band: str = "LOW"
    interpretation: str = ""


def _make_api_request(endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
    """Make authenticated request to GIE AGSI+ API."""
    if not GIE_API_KEY:
        logger.warning("GIE_API_KEY not configured - using public endpoint")
    
    url = f"{GIE_API_BASE}/{endpoint}"
    headers = {
        "x-key": GIE_API_KEY,
        "Accept": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"GIE API request failed: {e}")
        return None


def fetch_eu_storage_data(date_str: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Fetch EU-wide gas storage data for a specific date.
    
    Args:
        date_str: Date in YYYY-MM-DD format. Defaults to yesterday.
    
    Returns:
        Dict with EU storage data or None on error.
    """
    if not date_str:
        date_str = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    params = {
        "from": date_str,
        "to": date_str,
        "size": 1
    }
    
    data = _make_api_request("eu", params)
    
    if not data or "data" not in data:
        logger.error(f"Failed to fetch EU storage data for {date_str}")
        return None
    
    entries = data.get("data", [])
    if not entries:
        logger.warning(f"No EU storage data for {date_str}")
        return None
    
    entry = entries[0]
    return {
        "date": entry.get("gasDayStart", date_str),
        "gas_in_storage_twh": float(entry.get("gasInStorage", 0) or 0),
        "full_percent": float(entry.get("full", 0) or 0),
        "injection_twh": float(entry.get("injection", 0) or 0),
        "withdrawal_twh": float(entry.get("withdrawal", 0) or 0),
        "working_gas_volume_twh": float(entry.get("workingGasVolume", 0) or 0),
        "trend": float(entry.get("trend", 0) or 0),
        "consumption_twh": float(entry.get("consumption", 0) or 0),
    }


def fetch_country_storage_data(country_code: str, date_str: Optional[str] = None) -> Optional[Dict]:
    """Fetch storage data for a specific country."""
    if not date_str:
        date_str = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    params = {"from": date_str, "to": date_str, "size": 1}
    data = _make_api_request(country_code.lower(), params)
    
    if not data or "data" not in data:
        return None
    
    entries = data.get("data", [])
    if not entries:
        return None
    
    entry = entries[0]
    return {
        "country": country_code.upper(),
        "date": entry.get("gasDayStart", date_str),
        "gas_in_storage_twh": float(entry.get("gasInStorage", 0) or 0),
        "full_percent": float(entry.get("full", 0) or 0),
        "injection_twh": float(entry.get("injection", 0) or 0),
        "withdrawal_twh": float(entry.get("withdrawal", 0) or 0),
    }


def fetch_historical_storage(days: int = 7) -> List[Dict]:
    """Fetch historical EU storage data for trend analysis."""
    end_date = datetime.utcnow() - timedelta(days=1)
    start_date = end_date - timedelta(days=days)
    
    params = {
        "from": start_date.strftime("%Y-%m-%d"),
        "to": end_date.strftime("%Y-%m-%d"),
        "size": days + 1
    }
    
    data = _make_api_request("eu", params)
    
    if not data or "data" not in data:
        return []
    
    return [
        {
            "date": entry.get("gasDayStart"),
            "full_percent": float(entry.get("full", 0) or 0),
            "injection_twh": float(entry.get("injection", 0) or 0),
            "withdrawal_twh": float(entry.get("withdrawal", 0) or 0),
        }
        for entry in data.get("data", [])
    ]


def compute_storage_metrics(current_data: Dict, historical_data: List[Dict]) -> StorageMetrics:
    """
    Compute risk metrics from storage data.
    
    Inputs computed:
    1. EU gas storage level vs seasonal norm
    2. Refill speed (7-day average injection rate)
    3. Winter deviation risk (trajectory vs target)
    """
    date_str = current_data.get("date", datetime.utcnow().strftime("%Y-%m-%d"))
    current_month = int(date_str.split("-")[1])
    current_day = int(date_str.split("-")[2])
    
    eu_storage_percent = current_data.get("full_percent", 0)
    seasonal_norm = SEASONAL_NORMS.get(current_month, 70.0)
    deviation_from_norm = eu_storage_percent - seasonal_norm
    
    refill_speed_7d = 0.0
    withdrawal_rate_7d = 0.0
    
    if historical_data:
        injections = [d.get("injection_twh", 0) for d in historical_data]
        withdrawals = [d.get("withdrawal_twh", 0) for d in historical_data]
        refill_speed_7d = sum(injections) / len(injections) if injections else 0
        withdrawal_rate_7d = sum(withdrawals) / len(withdrawals) if withdrawals else 0
    
    winter_deviation_risk = "LOW"
    days_to_target = None
    
    if current_month in [11, 12, 1, 2, 3]:
        if current_month in [11, 12]:
            target_percent = EU_STORAGE_TARGET_NOV1
        else:
            target_percent = EU_STORAGE_TARGET_FEB1
        
        if eu_storage_percent < target_percent:
            winter_deviation_risk = "CRITICAL"
        elif eu_storage_percent < target_percent + 10:
            winter_deviation_risk = "ELEVATED"
        elif eu_storage_percent < target_percent + 20:
            winter_deviation_risk = "MODERATE"
        
        working_gas = current_data.get("working_gas_volume_twh", 0)
        if withdrawal_rate_7d > 0 and working_gas > 0:
            current_gas_twh = (eu_storage_percent / 100.0) * working_gas
            target_gas_twh = (target_percent / 100.0) * working_gas
            excess_gas_twh = current_gas_twh - target_gas_twh
            days_to_target = int(excess_gas_twh / withdrawal_rate_7d) if excess_gas_twh > 0 else 0
    else:
        if eu_storage_percent < EU_STORAGE_TARGET_NOV1 - 45:
            winter_deviation_risk = "CRITICAL"
        elif eu_storage_percent < EU_STORAGE_TARGET_NOV1 - 30:
            winter_deviation_risk = "ELEVATED"
    
    risk_score = compute_storage_risk_score(
        eu_storage_percent,
        deviation_from_norm,
        refill_speed_7d,
        withdrawal_rate_7d,
        current_month
    )
    
    risk_band = get_risk_band(risk_score)
    interpretation = generate_interpretation(
        eu_storage_percent,
        deviation_from_norm,
        winter_deviation_risk,
        current_month
    )
    
    return StorageMetrics(
        date=date_str,
        eu_storage_percent=round(eu_storage_percent, 1),
        seasonal_norm=seasonal_norm,
        deviation_from_norm=round(deviation_from_norm, 1),
        refill_speed_7d=round(refill_speed_7d, 2),
        withdrawal_rate_7d=round(withdrawal_rate_7d, 2),
        winter_deviation_risk=winter_deviation_risk,
        days_to_target=days_to_target,
        risk_score=risk_score,
        risk_band=risk_band,
        interpretation=interpretation
    )


def compute_storage_risk_score(
    storage_percent: float,
    deviation: float,
    refill_speed: float,
    withdrawal_rate: float,
    month: int
) -> int:
    """
    Compute quantitative risk score (0-100) from storage metrics.
    
    Formula:
    - Base: Inverse of storage level (lower storage = higher risk)
    - Deviation penalty: Negative deviation from norm adds risk
    - Seasonal adjustment: Winter months have higher base risk
    - Flow dynamics: High withdrawals vs low injections add risk
    """
    base_risk = max(0, 100 - storage_percent)
    
    deviation_factor = 0
    if deviation < 0:
        deviation_factor = min(30, abs(deviation) * 1.5)
    elif deviation > 15:
        deviation_factor = -10
    
    is_winter = month in [11, 12, 1, 2, 3]
    seasonal_factor = 15 if is_winter else 0
    
    flow_factor = 0
    if is_winter and withdrawal_rate > 0:
        if withdrawal_rate > 2.0:
            flow_factor = 10
        elif withdrawal_rate > 1.5:
            flow_factor = 5
    
    raw_score = base_risk * 0.5 + deviation_factor + seasonal_factor + flow_factor
    
    return max(0, min(100, int(raw_score)))


def get_risk_band(score: int) -> str:
    """Convert risk score to band label."""
    if score <= 25:
        return "LOW"
    elif score <= 50:
        return "MODERATE"
    elif score <= 75:
        return "ELEVATED"
    else:
        return "CRITICAL"


def generate_interpretation(
    storage_percent: float,
    deviation: float,
    winter_risk: str,
    month: int
) -> str:
    """Generate human-readable interpretation of storage metrics."""
    is_winter = month in [11, 12, 1, 2, 3]
    
    if storage_percent >= 80:
        level_desc = "well-stocked"
    elif storage_percent >= 60:
        level_desc = "adequately supplied"
    elif storage_percent >= 40:
        level_desc = "moderately depleted"
    else:
        level_desc = "critically low"
    
    if deviation >= 10:
        norm_desc = f"{abs(deviation):.0f}% above seasonal average"
    elif deviation <= -10:
        norm_desc = f"{abs(deviation):.0f}% below seasonal average"
    else:
        norm_desc = "near seasonal average"
    
    if is_winter:
        if winter_risk == "CRITICAL":
            outlook = "Winter supply security at significant risk."
        elif winter_risk == "ELEVATED":
            outlook = "Winter supply outlook requires close monitoring."
        else:
            outlook = "Winter supply outlook stable."
    else:
        outlook = "Refilling season in progress." if month in [4, 5, 6, 7, 8, 9, 10] else ""
    
    return f"EU gas storage {level_desc} at {storage_percent:.1f}%, {norm_desc}. {outlook}".strip()


def generate_storage_alert(metrics: StorageMetrics) -> Optional[Dict[str, Any]]:
    """
    Generate an alert event if storage conditions warrant.
    
    Returns alert dict compatible with alert_events table.
    """
    if metrics.risk_score < 40 and metrics.winter_deviation_risk == "LOW":
        return None
    
    severity = 2
    if metrics.risk_score >= 75:
        severity = 5
    elif metrics.risk_score >= 60:
        severity = 4
    elif metrics.risk_score >= 45:
        severity = 3
    
    if metrics.deviation_from_norm < -15:
        headline = f"EU Gas Storage Below Seasonal Norm: {metrics.eu_storage_percent}% ({metrics.deviation_from_norm:+.1f}% deviation)"
        event_type = "STORAGE_DEVIATION"
    elif metrics.winter_deviation_risk in ["ELEVATED", "CRITICAL"]:
        headline = f"EU Winter Gas Supply Risk: {metrics.winter_deviation_risk} - Storage at {metrics.eu_storage_percent}%"
        event_type = "WINTER_RISK"
    else:
        headline = f"EU Gas Storage Alert: {metrics.eu_storage_percent}% Full - {metrics.risk_band} Risk"
        event_type = "STORAGE_LEVEL"
    
    return {
        "headline": headline,
        "summary": metrics.interpretation,
        "severity": severity,
        "confidence": 0.95,
        "category": "ENERGY",
        "event_type": event_type,
        "scope_region": "Europe",
        "scope_asset": ["gas"],
        "drivers": [
            f"Storage level: {metrics.eu_storage_percent}% full",
            f"Seasonal deviation: {metrics.deviation_from_norm:+.1f}%",
            f"7-day withdrawal rate: {metrics.withdrawal_rate_7d:.2f} TWh/day"
        ],
        "data_source": "GIE AGSI+",
        "data_date": metrics.date,
        "raw_metrics": {
            "eu_storage_percent": metrics.eu_storage_percent,
            "seasonal_norm": metrics.seasonal_norm,
            "deviation_from_norm": metrics.deviation_from_norm,
            "refill_speed_7d": metrics.refill_speed_7d,
            "withdrawal_rate_7d": metrics.withdrawal_rate_7d,
            "winter_deviation_risk": metrics.winter_deviation_risk,
            "risk_score": metrics.risk_score,
            "risk_band": metrics.risk_band
        }
    }


def run_storage_check() -> Optional[Dict[str, Any]]:
    """
    Main entry point: Fetch current storage data and generate alert if needed.
    
    Returns alert dict or None if no alert warranted.
    """
    logger.info("Running GIE AGSI+ storage check...")
    
    current_data = fetch_eu_storage_data()
    if not current_data:
        logger.error("Failed to fetch current EU storage data")
        return None
    
    historical_data = fetch_historical_storage(days=7)
    
    metrics = compute_storage_metrics(current_data, historical_data)
    logger.info(f"Storage metrics: {metrics.eu_storage_percent}% full, "
                f"deviation {metrics.deviation_from_norm:+.1f}%, "
                f"risk score {metrics.risk_score} ({metrics.risk_band})")
    
    alert = generate_storage_alert(metrics)
    
    if alert:
        logger.info(f"Generated storage alert: {alert['headline']}")
    else:
        logger.info("No storage alert warranted - conditions normal")
    
    return alert


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = run_storage_check()
    if result:
        import json
        print(json.dumps(result, indent=2))
