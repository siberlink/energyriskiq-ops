"""
RERI - Regional Escalation Risk Index Module

Computes regional risk indices including EERI (Europe Energy Risk Index).

Feature Flag: ENABLE_EERI=true|false (default: false)
"""
import os

ENABLE_EERI = os.environ.get('ENABLE_EERI', 'false').lower() == 'true'

from src.reri.types import (
    CANONICAL_REGIONS,
    CATEGORY_WEIGHTS,
    EERI_WEIGHTS,
    EERI_INDEX_ID,
    MODEL_VERSION,
    RiskBand,
    get_band,
    RERIComponents,
    EERIComponents,
    RERIResult,
)

__all__ = [
    'ENABLE_EERI',
    'CANONICAL_REGIONS',
    'CATEGORY_WEIGHTS',
    'EERI_WEIGHTS',
    'EERI_INDEX_ID',
    'MODEL_VERSION',
    'RiskBand',
    'get_band',
    'RERIComponents',
    'EERIComponents',
    'RERIResult',
]
