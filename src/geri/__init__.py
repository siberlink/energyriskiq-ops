"""
GERI v1 - Global Energy Risk Index Module

An encapsulated module that computes daily risk indices from alert_events
and stores results in intel_indices_daily.

Feature Flag: ENABLE_GERI=true|false (default: false)
"""
import os

ENABLE_GERI = os.environ.get('ENABLE_GERI', 'false').lower() == 'true'

from src.geri.types import (
    GERIComponents,
    GERIResult,
    RiskBand,
    INDEX_ID,
    MODEL_VERSION,
)

__all__ = [
    'ENABLE_GERI',
    'GERIComponents',
    'GERIResult',
    'RiskBand',
    'INDEX_ID',
    'MODEL_VERSION',
]
