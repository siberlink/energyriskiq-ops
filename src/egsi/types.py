"""
EGSI Types and Constants

Defines data structures, weights, and chokepoint configuration for EGSI indices.
"""
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional, Dict, List, Any
from enum import Enum
import os

ENABLE_EGSI = os.environ.get("ENABLE_EGSI", "true").lower() == "true"

EGSI_M_INDEX_ID = "europe:egsi_m"
EGSI_S_INDEX_ID = "europe:egsi_s"
MODEL_VERSION = "egsi_m_v1"

EGSI_M_WEIGHTS = {
    'reri_eu': 0.35,
    'theme_pressure': 0.35,
    'asset_transmission': 0.20,
    'chokepoint_factor': 0.10,
}

EGSI_S_WEIGHTS = {
    'supply': 0.25,
    'transit': 0.20,
    'storage': 0.20,
    'market': 0.20,
    'policy': 0.15,
}

CHOKEPOINTS_V1 = {
    'version': 'v1',
    'description': 'Minimal high-signal Europe gas chokepoints',
    'entities': [
        {
            'id': 'ukraine_transit',
            'name': 'Ukraine Transit',
            'keywords': ['ukraine transit', 'ukraine gas', 'sudzha', 'urengoy', 'yamal'],
            'weight': 1.0,
            'category': 'transit',
        },
        {
            'id': 'turkstream',
            'name': 'TurkStream / Black Sea',
            'keywords': ['turkstream', 'turk stream', 'blue stream', 'black sea gas'],
            'weight': 0.9,
            'category': 'transit',
        },
        {
            'id': 'norway_pipelines',
            'name': 'Norway Export Pipelines',
            'keywords': ['langeled', 'europipe', 'norpipe', 'franpipe', 'nyhamna', 'kollsnes', 'karsto'],
            'weight': 0.85,
            'category': 'supply',
        },
        {
            'id': 'lng_gate',
            'name': 'LNG Gate Terminal',
            'keywords': ['gate terminal', 'rotterdam lng', 'lng terminal rotterdam'],
            'weight': 0.7,
            'category': 'lng',
        },
        {
            'id': 'lng_zeebrugge',
            'name': 'Zeebrugge LNG',
            'keywords': ['zeebrugge lng', 'fluxys lng', 'belgium lng'],
            'weight': 0.7,
            'category': 'lng',
        },
        {
            'id': 'lng_dunkirk',
            'name': 'Dunkirk LNG',
            'keywords': ['dunkirk lng', 'dunkerque lng', 'france lng terminal'],
            'weight': 0.65,
            'category': 'lng',
        },
        {
            'id': 'lng_brunsbuttel',
            'name': 'Brunsbuttel FSRU',
            'keywords': ['brunsbuttel', 'german fsru', 'germany lng floating'],
            'weight': 0.6,
            'category': 'lng',
        },
        {
            'id': 'lng_wilhelmshaven',
            'name': 'Wilhelmshaven FSRU',
            'keywords': ['wilhelmshaven', 'wilhelmshaven fsru', 'hoegh lng'],
            'weight': 0.6,
            'category': 'lng',
        },
        {
            'id': 'algeria_pipeline',
            'name': 'Algeria-Europe Pipelines',
            'keywords': ['transmed', 'medgaz', 'algeria gas', 'gmep'],
            'weight': 0.55,
            'category': 'supply',
        },
        {
            'id': 'interconnector_uk',
            'name': 'UK Interconnector',
            'keywords': ['interconnector', 'bacton', 'uk-belgium', 'bbil'],
            'weight': 0.5,
            'category': 'transit',
        },
    ],
}

GAS_THEME_KEYWORDS = [
    'gas', 'lng', 'natural gas', 'pipeline', 'gazprom', 'ttf', 'nbp',
    'storage', 'injection', 'withdrawal', 'winter', 'heating',
    'methane', 'liquefied', 'regasification', 'gasification',
]

NORMALIZATION_CAPS = {
    'theme_pressure': 50.0,
    'asset_transmission': 8.0,
    'chokepoint_factor': 10.0,
}


class EGSIBand(Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


def get_egsi_band(value: float) -> EGSIBand:
    """Map index value (0-100) to EGSI band."""
    if value <= 20:
        return EGSIBand.LOW
    elif value <= 40:
        return EGSIBand.NORMAL
    elif value <= 60:
        return EGSIBand.ELEVATED
    elif value <= 80:
        return EGSIBand.HIGH
    else:
        return EGSIBand.CRITICAL


def clamp(value: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
    """Clamp value between min and max."""
    return max(min_val, min(max_val, value))


@dataclass
class EGSIMComponents:
    """Components used to calculate EGSI-M (Market/Transmission) index."""
    reri_eu_value: int = 0
    
    theme_pressure_raw: float = 0.0
    theme_pressure_norm: float = 0.0
    theme_alert_count: int = 0
    
    asset_transmission_raw: float = 0.0
    asset_transmission_norm: float = 0.0
    asset_count: int = 0
    affected_assets: List[str] = field(default_factory=list)
    
    chokepoint_factor_raw: float = 0.0
    chokepoint_factor_norm: float = 0.0
    chokepoint_hits: List[Dict[str, Any]] = field(default_factory=list)
    
    top_drivers: List[Dict[str, Any]] = field(default_factory=list)
    interpretation: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'reri_eu': {
                'value': self.reri_eu_value,
                'contribution': round(EGSI_M_WEIGHTS['reri_eu'] * (self.reri_eu_value / 100.0), 4),
            },
            'theme_pressure': {
                'raw': round(self.theme_pressure_raw, 2),
                'normalized': round(self.theme_pressure_norm, 4),
                'alert_count': self.theme_alert_count,
                'contribution': round(EGSI_M_WEIGHTS['theme_pressure'] * self.theme_pressure_norm, 4),
            },
            'asset_transmission': {
                'raw': round(self.asset_transmission_raw, 2),
                'normalized': round(self.asset_transmission_norm, 4),
                'asset_count': self.asset_count,
                'affected_assets': self.affected_assets[:5],
                'contribution': round(EGSI_M_WEIGHTS['asset_transmission'] * self.asset_transmission_norm, 4),
            },
            'chokepoint_factor': {
                'raw': round(self.chokepoint_factor_raw, 2),
                'normalized': round(self.chokepoint_factor_norm, 4),
                'hits': self.chokepoint_hits[:5],
                'contribution': round(EGSI_M_WEIGHTS['chokepoint_factor'] * self.chokepoint_factor_norm, 4),
            },
            'top_drivers': self.top_drivers,
            'interpretation': self.interpretation,
            'weights': EGSI_M_WEIGHTS,
            'chokepoint_version': CHOKEPOINTS_V1['version'],
        }


@dataclass
class EGSIMResult:
    """Result of EGSI-M index computation."""
    index_id: str
    region: str
    index_date: date
    value: float
    band: EGSIBand
    trend_1d: Optional[float]
    trend_7d: Optional[float]
    components: EGSIMComponents
    model_version: str = MODEL_VERSION
    computed_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'index_id': self.index_id,
            'region': self.region,
            'date': self.index_date.isoformat(),
            'value': round(self.value, 2),
            'band': self.band.value,
            'trend_1d': round(self.trend_1d, 2) if self.trend_1d is not None else None,
            'trend_7d': round(self.trend_7d, 2) if self.trend_7d is not None else None,
            'components': self.components.to_dict(),
            'model_version': self.model_version,
            'computed_at': self.computed_at.isoformat() if self.computed_at else None,
        }


@dataclass
class NormStats:
    """Normalization statistics for a component."""
    component_key: str
    p10: float = 0.0
    p50: float = 0.0
    p90: float = 0.0
    p95: float = 0.0
    window_days: int = 90
    
    def normalize(self, raw_value: float) -> float:
        """Normalize value using percentile scaling."""
        if self.p90 <= self.p10:
            return 0.5
        return clamp((raw_value - self.p10) / (self.p90 - self.p10))


EGSI_S_MODEL_VERSION = "egsi_s_v1"

EGSI_S_NORMALIZATION_CAPS = {
    'storage_stress': 100.0,
    'price_volatility': 50.0,
    'injection_rate': 5.0,
    'winter_readiness': 100.0,
}

EGSI_S_STORAGE_TARGETS = {
    'winter_start': 0.90,
    'spring': 0.30,
    'summer': 0.50,
    'autumn': 0.80,
}


@dataclass
class EGSISComponents:
    """Components used to calculate EGSI-S (System Stress) index."""
    storage_level_pct: float = 0.0
    storage_target_pct: float = 0.0
    storage_stress_raw: float = 0.0
    storage_stress_norm: float = 0.0
    
    ttf_price: float = 0.0
    ttf_price_ma7: float = 0.0
    price_volatility_raw: float = 0.0
    price_volatility_norm: float = 0.0
    
    injection_rate: float = 0.0
    injection_rate_norm: float = 0.0
    
    winter_readiness_raw: float = 0.0
    winter_readiness_norm: float = 0.0
    days_to_winter: int = 0
    
    supply_alerts_count: int = 0
    supply_pressure: float = 0.0
    
    top_drivers: List[Dict[str, Any]] = field(default_factory=list)
    interpretation: str = ""
    data_sources: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'storage': {
                'level_pct': round(self.storage_level_pct, 2),
                'target_pct': round(self.storage_target_pct, 2),
                'stress_raw': round(self.storage_stress_raw, 2),
                'stress_norm': round(self.storage_stress_norm, 4),
                'contribution': round(EGSI_S_WEIGHTS['storage'] * self.storage_stress_norm, 4),
            },
            'price': {
                'ttf_current': round(self.ttf_price, 2),
                'ttf_ma7': round(self.ttf_price_ma7, 2),
                'volatility_raw': round(self.price_volatility_raw, 2),
                'volatility_norm': round(self.price_volatility_norm, 4),
                'contribution': round(EGSI_S_WEIGHTS['market'] * self.price_volatility_norm, 4),
            },
            'flows': {
                'injection_rate': round(self.injection_rate, 2),
                'injection_norm': round(self.injection_rate_norm, 4),
                'contribution': round(EGSI_S_WEIGHTS['transit'] * self.injection_rate_norm, 4),
            },
            'winter_readiness': {
                'raw': round(self.winter_readiness_raw, 2),
                'norm': round(self.winter_readiness_norm, 4),
                'days_to_winter': self.days_to_winter,
                'contribution': round(EGSI_S_WEIGHTS['supply'] * self.winter_readiness_norm, 4),
            },
            'alerts': {
                'supply_count': self.supply_alerts_count,
                'supply_pressure': round(self.supply_pressure, 2),
                'contribution': round(EGSI_S_WEIGHTS['policy'] * self.supply_pressure, 4),
            },
            'top_drivers': self.top_drivers,
            'interpretation': self.interpretation,
            'data_sources': self.data_sources,
            'weights': EGSI_S_WEIGHTS,
        }


@dataclass
class EGSISResult:
    """Result of EGSI-S (System) index computation."""
    index_id: str
    region: str
    index_date: date
    value: float
    band: EGSIBand
    trend_1d: Optional[float]
    trend_7d: Optional[float]
    components: EGSISComponents
    model_version: str = EGSI_S_MODEL_VERSION
    computed_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'index_id': self.index_id,
            'region': self.region,
            'date': self.index_date.isoformat(),
            'value': round(self.value, 2),
            'band': self.band.value,
            'trend_1d': round(self.trend_1d, 2) if self.trend_1d is not None else None,
            'trend_7d': round(self.trend_7d, 2) if self.trend_7d is not None else None,
            'components': self.components.to_dict(),
            'model_version': self.model_version,
            'computed_at': self.computed_at.isoformat() if self.computed_at else None,
        }


@dataclass
class MarketDataSnapshot:
    """
    External market data snapshot - pluggable data source interface.
    
    This is the abstraction layer for external data sources like:
    - TTF gas prices (ICE/EEX)
    - EU gas storage levels (AGSI+)
    - Injection/withdrawal rates
    """
    data_date: date
    ttf_price: Optional[float] = None
    ttf_price_ma7: Optional[float] = None
    ttf_volatility: Optional[float] = None
    
    storage_level_twh: Optional[float] = None
    storage_capacity_twh: Optional[float] = None
    storage_level_pct: Optional[float] = None
    
    injection_rate_twh: Optional[float] = None
    withdrawal_rate_twh: Optional[float] = None
    
    source: str = "mock"
    fetched_at: Optional[datetime] = None
    
    @property
    def has_price_data(self) -> bool:
        return self.ttf_price is not None
    
    @property
    def has_storage_data(self) -> bool:
        return self.storage_level_pct is not None
    
    @property
    def is_complete(self) -> bool:
        return self.has_price_data and self.has_storage_data
