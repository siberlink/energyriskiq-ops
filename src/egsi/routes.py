"""
EGSI API Routes

Mounted under /api/v1/indices
"""
import logging
from datetime import date, datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.egsi.types import ENABLE_EGSI, EGSI_M_INDEX_ID
from src.egsi.repo import (
    get_egsi_m_for_date,
    get_egsi_m_latest,
    get_egsi_m_delayed,
    get_egsi_m_history,
)
from src.egsi.service import compute_egsi_m_for_date, get_egsi_m_status

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/indices", tags=["EGSI Indices"])


class ComputeRequest(BaseModel):
    date: str
    force: bool = False


def check_enabled():
    """Raise 503 if EGSI module is disabled."""
    if not ENABLE_EGSI:
        raise HTTPException(
            status_code=503,
            detail="EGSI module is disabled. Set ENABLE_EGSI=true to enable."
        )


@router.get("/egsi-m/public")
async def get_egsi_m_public():
    """
    Get EGSI-M index for public display (24h delayed).
    
    This is a FREE, unauthenticated endpoint for marketing/SEO.
    Returns data from 24+ hours ago to provide value while protecting premium real-time access.
    """
    check_enabled()
    
    result = get_egsi_m_delayed()
    
    if not result:
        return {
            'success': False,
            'message': 'No EGSI-M data available yet',
            'data': None,
        }
    
    components = result.get('components', {})
    if isinstance(components, str):
        import json
        components = json.loads(components)
    
    return {
        'success': True,
        'value': result.get('value', 0),
        'band': result.get('band', 'LOW'),
        'trend_1d': result.get('trend_1d'),
        'trend_7d': result.get('trend_7d'),
        'date': result.get('date').isoformat() if result.get('date') else None,
        'explanation': result.get('explanation', ''),
        'top_drivers': components.get('top_drivers', [])[:3],
        'chokepoint_watch': components.get('chokepoint_factor', {}).get('hits', [])[:2],
        'is_delayed': True,
        'delay_hours': 24,
    }


@router.get("/egsi-m/latest")
async def get_egsi_m_latest_endpoint():
    """
    Get the latest EGSI-M index value (Pro users).
    """
    check_enabled()
    
    result = get_egsi_m_latest()
    
    if not result:
        raise HTTPException(
            status_code=404,
            detail="No EGSI-M index data available. Run compute first."
        )
    
    return {
        'success': True,
        'data': {
            'index_id': EGSI_M_INDEX_ID,
            'region': result.get('region', 'Europe'),
            'date': result.get('date').isoformat() if result.get('date') else None,
            'value': result.get('value'),
            'band': result.get('band'),
            'trend_1d': result.get('trend_1d'),
            'trend_7d': result.get('trend_7d'),
            'components': result.get('components'),
            'explanation': result.get('explanation'),
            'computed_at': result.get('computed_at').isoformat() if result.get('computed_at') else None,
        },
    }


@router.get("/egsi-m")
async def get_egsi_m_history_endpoint(
    from_date: Optional[str] = Query(None, alias="from", description="Start date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, alias="to", description="End date (YYYY-MM-DD)"),
    days: int = Query(30, description="Number of days of history (default 30)")
):
    """
    Get EGSI-M index history.
    """
    check_enabled()
    
    history = get_egsi_m_history(days=days)
    
    if not history:
        return {
            'success': True,
            'count': 0,
            'data': [],
        }
    
    return {
        'success': True,
        'count': len(history),
        'data': [
            {
                'date': h.get('date').isoformat() if h.get('date') else None,
                'value': h.get('value'),
                'band': h.get('band'),
                'trend_1d': h.get('trend_1d'),
                'trend_7d': h.get('trend_7d'),
            }
            for h in history
        ],
    }


@router.post("/egsi-m/compute")
async def compute_egsi_m_endpoint(request: ComputeRequest):
    """
    Manually trigger EGSI-M computation for a specific date.
    """
    check_enabled()
    
    try:
        target_date = date.fromisoformat(request.date)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date format. Use YYYY-MM-DD."
        )
    
    result = compute_egsi_m_for_date(target_date, force=request.force)
    
    if not result:
        return {
            'success': False,
            'message': f'EGSI-M computation failed or skipped for {request.date}. Check if EERI exists for this date.',
        }
    
    return {
        'success': True,
        'message': f'EGSI-M computed for {request.date}',
        'data': result.to_dict(),
    }


@router.get("/egsi-m/status")
async def get_egsi_m_status_endpoint():
    """
    Get EGSI-M module status for health checks.
    """
    status = get_egsi_m_status()
    
    return {
        'success': True,
        **status,
    }


@router.get("/egsi-m/{target_date}")
async def get_egsi_m_by_date(target_date: str):
    """
    Get EGSI-M index for a specific date.
    """
    check_enabled()
    
    try:
        dt = date.fromisoformat(target_date)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date format. Use YYYY-MM-DD."
        )
    
    result = get_egsi_m_for_date(dt)
    
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"No EGSI-M data for {target_date}"
        )
    
    return {
        'success': True,
        'data': result,
    }
