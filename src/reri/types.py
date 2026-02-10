"""
RERI/EERI Types and Constants

Defines data structures and constants for regional index computation.
"""
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional, Dict, List, Any
from enum import Enum

EERI_INDEX_ID = "europe:eeri"
RERI_EU_INDEX_ID = "europe:reri"
MODEL_VERSION = "eeri_v1"

CANONICAL_REGIONS = {
    'europe': {
        'id': 'europe',
        'name': 'Europe',
        'type': 'energy',
        'aliases': ['EU', 'European', 'Western Europe', 'Eastern Europe'],
        'core_assets': ['gas', 'oil', 'power', 'fx'],
    },
    'middle-east': {
        'id': 'middle-east',
        'name': 'Middle East',
        'type': 'conflict',
        'aliases': ['Middle Eastern', 'Gulf', 'MENA', 'Persian Gulf'],
        'core_assets': ['oil', 'gas', 'lng', 'freight'],
    },
    'black-sea': {
        'id': 'black-sea',
        'name': 'Black Sea',
        'type': 'shipping',
        'aliases': ['Black Sea Region', 'Bosphorus', 'Ukraine Region'],
        'core_assets': ['freight', 'oil', 'grain', 'gas'],
    },
}

VALID_ALERT_TYPES = [
    'HIGH_IMPACT_EVENT',
    'REGIONAL_RISK_SPIKE',
    'ASSET_RISK_SPIKE',
]

CATEGORY_WEIGHTS = {
    'war': 1.6,
    'military': 1.6,
    'strike': 1.6,
    'conflict': 1.6,
    'supply_disruption': 1.5,
    'supplychain': 1.5,
    'supply_chain': 1.5,
    'energy': 1.3,
    'sanctions': 1.3,
    'political': 1.0,
    'geopolitical': 1.0,
    'diplomacy': 0.7,
    'unknown': 1.0,
}

RERI_WEIGHTS = {
    'severity_pressure': 0.45,
    'high_impact_count': 0.30,
    'asset_overlap': 0.15,
    'velocity': 0.10,
}

EERI_WEIGHTS_V1 = {
    'reri_eu': 0.45,
    'theme_pressure': 0.25,
    'asset_transmission': 0.20,
    'contagion': 0.10,
}

EERI_WEIGHTS = EERI_WEIGHTS_V1

CONTAGION_NEIGHBORS = {
    'europe': {
        'middle-east': 0.6,
        'black-sea': 0.4,
    },
}

NORMALIZATION_CAPS = {
    'severity_pressure': 25.0,
    'high_impact_count': 6.0,
    'asset_overlap': 4.0,
    'velocity_range': 20.0,
    'velocity_offset': 10.0,
    'theme_pressure': 30.0,
    'asset_transmission': 4.0,
}


class RiskBand(Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    ELEVATED = "ELEVATED"
    SEVERE = "SEVERE"
    CRITICAL = "CRITICAL"


def get_band(value: int) -> RiskBand:
    """Map index value (0-100) to risk band."""
    if value <= 20:
        return RiskBand.LOW
    elif value <= 40:
        return RiskBand.MODERATE
    elif value <= 60:
        return RiskBand.ELEVATED
    elif value <= 80:
        return RiskBand.SEVERE
    else:
        return RiskBand.CRITICAL


@dataclass
class AlertRecord:
    """Represents an alert from alert_events table."""
    id: int
    alert_type: str
    severity: Optional[int]
    confidence: Optional[float]
    region: Optional[str]
    assets: List[str]
    created_at: datetime
    headline: Optional[str] = None
    body: Optional[str] = None
    category: Optional[str] = None


@dataclass
class RERIComponents:
    """Components used to calculate base RERI index."""
    severity_pressure_raw: float = 0.0
    high_impact_count: int = 0
    asset_overlap_count: int = 0
    velocity_raw: float = 0.0
    
    severity_pressure_norm: float = 0.0
    high_impact_norm: float = 0.0
    asset_overlap_norm: float = 0.0
    velocity_norm: float = 0.0
    
    total_alerts: int = 0
    distinct_assets: List[str] = field(default_factory=list)
    insufficient_history: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'severity_pressure': {
                'raw': round(self.severity_pressure_raw, 2),
                'normalized': round(self.severity_pressure_norm, 4),
            },
            'high_impact_count': {
                'raw': self.high_impact_count,
                'normalized': round(self.high_impact_norm, 4),
            },
            'asset_overlap': {
                'raw': self.asset_overlap_count,
                'assets': self.distinct_assets,
                'normalized': round(self.asset_overlap_norm, 4),
            },
            'velocity': {
                'raw': round(self.velocity_raw, 2),
                'normalized': round(self.velocity_norm, 4),
            },
            'total_alerts': self.total_alerts,
            'insufficient_history': self.insufficient_history,
            'weights': RERI_WEIGHTS,
        }


@dataclass
class EERIComponents:
    """Components used to calculate EERI (Europe Energy Risk Index)."""
    reri_eu_value: int = 0
    reri_eu_components: Optional[RERIComponents] = None
    
    theme_pressure_raw: float = 0.0
    theme_pressure_norm: float = 0.0
    
    asset_transmission_raw: float = 0.0
    asset_transmission_norm: float = 0.0
    
    contagion_raw: float = 0.0
    contagion_norm: float = 0.0
    
    top_drivers: List[Dict[str, Any]] = field(default_factory=list)
    interpretation: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'reri_eu': {
                'value': self.reri_eu_value,
                'components': self.reri_eu_components.to_dict() if self.reri_eu_components else None,
            },
            'theme_pressure': {
                'raw': round(self.theme_pressure_raw, 2),
                'normalized': round(self.theme_pressure_norm, 4),
            },
            'asset_transmission': {
                'raw': round(self.asset_transmission_raw, 2),
                'normalized': round(self.asset_transmission_norm, 4),
            },
            'contagion': {
                'raw': round(self.contagion_raw, 2),
                'normalized': round(self.contagion_norm, 4),
                'enabled': False,
            },
            'top_drivers': self.top_drivers,
            'interpretation': self.interpretation,
            'weights': EERI_WEIGHTS,
        }


@dataclass
class RERIResult:
    """Result of RERI/EERI index computation."""
    index_id: str
    region_id: str
    index_date: date
    value: int
    band: RiskBand
    trend_1d: Optional[int]
    trend_7d: Optional[int]
    components: EERIComponents
    drivers: List[Dict[str, Any]]
    model_version: str = MODEL_VERSION
    computed_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'index_id': self.index_id,
            'region_id': self.region_id,
            'date': self.index_date.isoformat(),
            'value': self.value,
            'band': self.band.value,
            'trend_1d': self.trend_1d,
            'trend_7d': self.trend_7d,
            'components': self.components.to_dict(),
            'drivers': self.drivers,
            'model_version': self.model_version,
            'computed_at': self.computed_at.isoformat() if self.computed_at else None,
        }


@dataclass
class HistoricalBaseline:
    """Rolling baseline stats for normalization."""
    severity_min: float = 0.0
    severity_max: float = 0.0
    high_impact_min: float = 0.0
    high_impact_max: float = 0.0
    asset_overlap_min: float = 0.0
    asset_overlap_max: float = 0.0
    velocity_min: float = 0.0
    velocity_max: float = 0.0
    days_count: int = 0
