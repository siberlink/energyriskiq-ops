"""
GERI v1 Types and Constants
"""
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional, Dict, List, Any
from enum import Enum

INDEX_ID = "global:geo_energy_risk"
MODEL_VERSION = "geri_v1"

VALID_ALERT_TYPES = [
    'HIGH_IMPACT_EVENT',
    'REGIONAL_RISK_SPIKE',
    'ASSET_RISK_ALERT',
]

GERI_WEIGHTS = {
    'high_impact': 0.40,
    'regional_spike': 0.25,
    'asset_risk': 0.20,
    'region_concentration': 0.15,
}


class RiskBand(Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    ELEVATED = "ELEVATED"
    CRITICAL = "CRITICAL"


def get_band(value: int) -> RiskBand:
    """Map index value (0-100) to risk band."""
    if value <= 25:
        return RiskBand.LOW
    elif value <= 50:
        return RiskBand.MODERATE
    elif value <= 75:
        return RiskBand.ELEVATED
    else:
        return RiskBand.CRITICAL


@dataclass
class AlertRecord:
    """Represents an alert from alert_events table."""
    id: int
    alert_type: str
    severity: Optional[int]
    risk_score: Optional[float]
    region: Optional[str]
    weight: Optional[float]
    created_at: datetime
    headline: Optional[str] = None
    body: Optional[str] = None
    category: Optional[str] = None


@dataclass
class GERIComponents:
    """Components used to calculate GERI index."""
    high_impact_events: int = 0
    high_impact_score: float = 0.0
    regional_spikes: int = 0
    regional_spike_score: float = 0.0
    asset_spikes: int = 0
    asset_risk_score: float = 0.0
    regions_count: int = 0
    top_regions: List[Dict[str, Any]] = field(default_factory=list)
    top_region_weight: float = 0.0
    region_concentration_score_raw: float = 0.0
    avg_severity: float = 0.0
    total_alerts: int = 0
    insufficient_history: bool = False
    top_drivers: List[Dict[str, Any]] = field(default_factory=list)
    
    norm_high_impact: float = 0.0
    norm_regional_spike: float = 0.0
    norm_asset_risk: float = 0.0
    norm_region_concentration: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'high_impact_events': self.high_impact_events,
            'high_impact_score': self.high_impact_score,
            'regional_spikes': self.regional_spikes,
            'regional_spike_score': self.regional_spike_score,
            'asset_spikes': self.asset_spikes,
            'asset_risk_score': self.asset_risk_score,
            'regions_count': self.regions_count,
            'top_regions': self.top_regions,
            'top_region_weight': round(self.top_region_weight, 4),
            'region_concentration_score_raw': round(self.region_concentration_score_raw, 2),
            'avg_severity': round(self.avg_severity, 2),
            'total_alerts': self.total_alerts,
            'insufficient_history': self.insufficient_history,
            'top_drivers': self.top_drivers,
            'normalized': {
                'high_impact': round(self.norm_high_impact, 2),
                'regional_spike': round(self.norm_regional_spike, 2),
                'asset_risk': round(self.norm_asset_risk, 2),
                'region_concentration': round(self.norm_region_concentration, 2),
            },
            'weights': GERI_WEIGHTS,
        }


@dataclass
class GERIResult:
    """Result of GERI index computation."""
    index_id: str
    index_date: date
    value: int
    band: RiskBand
    trend_1d: Optional[int]
    trend_7d: Optional[int]
    components: GERIComponents
    model_version: str = MODEL_VERSION
    computed_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'index_id': self.index_id,
            'date': self.index_date.isoformat(),
            'value': self.value,
            'band': self.band.value,
            'trend_1d': self.trend_1d,
            'trend_7d': self.trend_7d,
            'components': self.components.to_dict(),
            'model_version': self.model_version,
            'computed_at': self.computed_at.isoformat() if self.computed_at else None,
        }


@dataclass
class HistoricalBaseline:
    """Rolling baseline stats for normalization."""
    high_impact_min: float = 0.0
    high_impact_max: float = 0.0
    regional_spike_min: float = 0.0
    regional_spike_max: float = 0.0
    asset_risk_min: float = 0.0
    asset_risk_max: float = 0.0
    region_concentration_min: float = 0.0
    region_concentration_max: float = 0.0
    days_count: int = 0
