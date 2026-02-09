"""
EGSI API Routes

Mounted under /api/v1/indices
"""
import logging
import json
from datetime import date, datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.egsi.types import ENABLE_EGSI, EGSI_M_INDEX_ID
from src.egsi.repo import (
    get_egsi_m_for_date,
    get_egsi_m_latest,
    get_egsi_m_history,
    get_egsi_m_delayed,
    get_egsi_s_for_date,
    get_egsi_s_latest,
    get_egsi_s_history,
    get_egsi_s_delayed,
)
from src.egsi.egsi_history_service import get_egsi_m_delayed as get_egsi_m_delayed_hours
from src.egsi.service import compute_egsi_m_for_date, get_egsi_m_status
from src.egsi.service_egsi_s import compute_egsi_s_for_date, get_egsi_s_status

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
    
    result = get_egsi_m_delayed_hours(delay_hours=24)
    
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
    
    result_date = result.get('date')
    if hasattr(result_date, 'isoformat'):
        result_date = result_date.isoformat()
    
    return {
        'success': True,
        'value': round(result.get('value', 0)),
        'band': result.get('band', 'LOW'),
        'trend_1d': round(result.get('trend_1d')) if result.get('trend_1d') else None,
        'trend_7d': round(result.get('trend_7d')) if result.get('trend_7d') else None,
        'date': result_date,
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


@router.get("/egsi-m/history")
async def get_egsi_m_history_list(
    days: int = Query(30, description="Number of days of history (default 30)")
):
    """
    Get EGSI-M index history as a list.
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


@router.get("/egsi-s/status")
async def get_egsi_s_status_endpoint():
    """
    Get EGSI-S module status for health checks.
    """
    status = get_egsi_s_status()
    
    return {
        'success': True,
        **status,
    }


@router.get("/egsi-s/latest")
async def get_egsi_s_latest_endpoint():
    """
    Get the latest EGSI-S index value.
    """
    check_enabled()
    
    result = get_egsi_s_latest()
    
    if not result:
        return {
            'success': False,
            'message': 'No EGSI-S data available yet. Computation requires external market data.',
            'data': None,
        }
    
    return {
        'success': True,
        'data': result,
    }


@router.get("/egsi-s/history")
async def get_egsi_s_history_endpoint(
    days: int = Query(30, description="Number of days of history")
):
    """
    Get EGSI-S index history.
    """
    check_enabled()
    
    history = get_egsi_s_history(days=days)
    
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


@router.post("/egsi-s/compute")
async def compute_egsi_s_endpoint(request: ComputeRequest):
    """
    Trigger EGSI-S computation for a specific date.
    
    Note: EGSI-S uses mock data by default. Set EGSI_S_DATA_SOURCE environment
    variable to "agsi" or "ttf" with appropriate API keys for real data.
    """
    check_enabled()
    
    try:
        target_date = date.fromisoformat(request.date)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date format. Use YYYY-MM-DD."
        )
    
    result = compute_egsi_s_for_date(target_date, force=request.force)
    
    if not result:
        return {
            'success': False,
            'message': f'EGSI-S computation failed or skipped for {request.date}.',
        }
    
    return {
        'success': True,
        'message': f'EGSI-S computed for {request.date}',
        'data': result.to_dict(),
    }


@router.get("/egsi-s/{target_date}")
async def get_egsi_s_by_date(target_date: str):
    """
    Get EGSI-S index for a specific date.
    """
    check_enabled()
    
    try:
        dt = date.fromisoformat(target_date)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date format. Use YYYY-MM-DD."
        )
    
    result = get_egsi_s_for_date(dt)
    
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"No EGSI-S data for {target_date}"
        )
    
    return {
        'success': True,
        'data': result,
    }


def _parse_components(raw):
    """Parse components JSON if stored as string."""
    if raw is None:
        return {}
    if isinstance(raw, str):
        return json.loads(raw)
    return raw


@router.get("/egsi/dashboard")
async def get_egsi_dashboard(
    plan: str = Query("free", description="User plan tier"),
    history_days: int = Query(30, description="Days of history to return"),
):
    """
    Combined EGSI dashboard endpoint for authenticated users.
    Returns EGSI-M + EGSI-S latest data, components, drivers, and history.
    Plan-tiered: free users get 24h delayed data, paid users get real-time.
    """
    check_enabled()

    use_delayed = plan == 'free'

    if use_delayed:
        egsi_m = get_egsi_m_delayed(delay_days=1)
        egsi_s = get_egsi_s_delayed(delay_days=1)
    else:
        egsi_m = get_egsi_m_latest()
        egsi_s = get_egsi_s_latest()

    egsi_m_data = None
    if egsi_m:
        components = _parse_components(egsi_m.get('components'))
        m_date = egsi_m.get('date')
        if hasattr(m_date, 'isoformat'):
            m_date = m_date.isoformat()
        computed_at = egsi_m.get('computed_at')
        if hasattr(computed_at, 'isoformat'):
            computed_at = computed_at.isoformat()
        egsi_m_data = {
            'value': round(float(egsi_m.get('value', 0)), 1),
            'band': egsi_m.get('band', 'LOW'),
            'trend_1d': round(float(egsi_m.get('trend_1d', 0)), 1) if egsi_m.get('trend_1d') is not None else None,
            'trend_7d': round(float(egsi_m.get('trend_7d', 0)), 1) if egsi_m.get('trend_7d') is not None else None,
            'date': m_date,
            'explanation': egsi_m.get('explanation', ''),
            'is_delayed': use_delayed,
            'computed_at': computed_at,
            'components': {
                'reri_eu': components.get('reri_eu', {}),
                'theme_pressure': components.get('theme_pressure', {}),
                'asset_transmission': components.get('asset_transmission', {}),
                'chokepoint_factor': components.get('chokepoint_factor', {}),
            },
            'top_drivers': components.get('top_drivers', [])[:5],
            'chokepoint_watch': components.get('chokepoint_factor', {}).get('hits', [])[:5],
            'interpretation': components.get('interpretation', egsi_m.get('explanation', '')),
        }

    egsi_s_data = None
    if egsi_s:
        s_components = _parse_components(egsi_s.get('components'))
        s_date = egsi_s.get('date')
        if hasattr(s_date, 'isoformat'):
            s_date = s_date.isoformat()
        s_computed = egsi_s.get('computed_at')
        if hasattr(s_computed, 'isoformat'):
            s_computed = s_computed.isoformat()
        egsi_s_data = {
            'value': round(float(egsi_s.get('value', 0)), 1),
            'band': egsi_s.get('band', 'LOW'),
            'trend_1d': round(float(egsi_s.get('trend_1d', 0)), 1) if egsi_s.get('trend_1d') is not None else None,
            'trend_7d': round(float(egsi_s.get('trend_7d', 0)), 1) if egsi_s.get('trend_7d') is not None else None,
            'date': s_date,
            'explanation': egsi_s.get('explanation', ''),
            'computed_at': s_computed,
            'data_sources': egsi_s.get('data_sources', []),
            'components': {
                'storage': s_components.get('storage', {}),
                'price': s_components.get('price', {}),
                'flows': s_components.get('flows', {}),
                'winter_readiness': s_components.get('winter_readiness', {}),
                'alerts': s_components.get('alerts', {}),
            },
            'top_drivers': s_components.get('top_drivers', [])[:5],
            'interpretation': s_components.get('interpretation', egsi_s.get('explanation', '')),
        }

    max_history = {
        'free': 14,
        'personal': 90,
        'trader': 365,
        'pro': 365,
        'enterprise': 365,
    }.get(plan, 14)
    actual_days = min(history_days, max_history)

    m_history = get_egsi_m_history(days=actual_days)
    s_history = get_egsi_s_history(days=actual_days)

    def format_history(items):
        return [{
            'date': h.get('date').isoformat() if hasattr(h.get('date'), 'isoformat') else h.get('date'),
            'value': round(float(h.get('value', 0)), 1),
            'band': h.get('band'),
            'trend_1d': round(float(h.get('trend_1d', 0)), 1) if h.get('trend_1d') is not None else None,
        } for h in items]

    return {
        'success': True,
        'plan': plan,
        'egsi_m': egsi_m_data,
        'egsi_s': egsi_s_data,
        'history': {
            'egsi_m': format_history(m_history),
            'egsi_s': format_history(s_history),
            'days': actual_days,
            'max_days': max_history,
        },
    }
