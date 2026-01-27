"""
EERI v1 API Routes

Mounted under /api/v1/indices
"""
import logging
from datetime import date, datetime, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.reri import ENABLE_EERI
from src.reri.types import EERI_INDEX_ID
from src.reri.repo import get_latest_reri, get_reri_for_date, get_reri_history
from src.reri.service import compute_eeri_for_date

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/indices", tags=["EERI Indices"])


class ComputeRequest(BaseModel):
    date: str
    force: bool = False


def check_enabled():
    """Raise 503 if EERI module is disabled."""
    if not ENABLE_EERI:
        raise HTTPException(
            status_code=503,
            detail="EERI module is disabled. Set ENABLE_EERI=true to enable."
        )


@router.get("/eeri/public")
async def get_eeri_public():
    """
    Get EERI index for public display (24h delayed).
    
    This is a FREE, unauthenticated endpoint for marketing/SEO.
    Returns data from 24+ hours ago to provide value while protecting premium real-time access.
    """
    check_enabled()
    
    from src.reri.eeri_history_service import get_eeri_delayed
    
    result = get_eeri_delayed()
    
    if not result:
        return {
            'success': False,
            'message': 'No EERI data available yet',
            'data': None,
        }
    
    return {
        'success': True,
        'value': result.get('value', 0),
        'band': result.get('band', 'LOW'),
        'trend_7d': result.get('trend_7d', 0),
        'date': result.get('date'),
        'computed_at': result.get('computed_at'),
    }


@router.get("/eeri/latest")
async def get_eeri_latest():
    """
    Get the latest EERI index value.
    """
    check_enabled()
    
    result = get_latest_reri(EERI_INDEX_ID)
    
    if not result:
        raise HTTPException(
            status_code=404,
            detail="No EERI index data available. Run compute first."
        )
    
    return {
        'success': True,
        'data': {
            'index_id': result.index_id,
            'region_id': result.region_id,
            'date': result.index_date.isoformat() if result.index_date else None,
            'value': float(result.value) if result.value else None,
            'band': result.band.value if result.band else None,
            'trend_1d': result.trend_1d,
            'trend_7d': result.trend_7d,
            'computed_at': result.computed_at.isoformat() if result.computed_at else None,
        },
    }


@router.get("/eeri")
async def get_eeri_history_endpoint(
    from_date: Optional[str] = Query(None, alias="from", description="Start date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, alias="to", description="End date (YYYY-MM-DD)")
):
    """
    Get EERI index history for a date range.
    
    If no date range specified, returns last 30 days.
    """
    check_enabled()
    
    try:
        if from_date:
            start = datetime.strptime(from_date, "%Y-%m-%d").date()
        else:
            start = date.today() - timedelta(days=30)
        
        if to_date:
            end = datetime.strptime(to_date, "%Y-%m-%d").date()
        else:
            end = date.today()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date format. Use YYYY-MM-DD."
        )
    
    results = get_reri_history(EERI_INDEX_ID, start, end)
    
    return {
        'success': True,
        'data': [
            {
                'date': r.index_date.isoformat() if r.index_date else None,
                'value': float(r.value) if r.value else None,
                'band': r.band.value if r.band else None,
                'trend_1d': r.trend_1d,
                'trend_7d': r.trend_7d,
            }
            for r in results
        ],
        'count': len(results),
    }


@router.post("/eeri/compute")
async def compute_eeri_endpoint(request: ComputeRequest):
    """
    Compute EERI for a specific date.
    """
    check_enabled()
    
    try:
        target_date = datetime.strptime(request.date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date format. Use YYYY-MM-DD."
        )
    
    if target_date >= date.today():
        raise HTTPException(
            status_code=400,
            detail="Cannot compute EERI for today or future dates."
        )
    
    result = compute_eeri_for_date(target_date, force=request.force)
    
    if result:
        return {
            'success': True,
            'data': {
                'date': result.index_date.isoformat(),
                'value': float(result.value),
                'band': result.band.value if result.band else None,
            },
        }
    else:
        return {
            'success': False,
            'skipped': True,
            'message': f"EERI for {target_date} already exists. Use force=true to overwrite.",
        }


@router.post("/eeri/compute-yesterday")
async def compute_eeri_yesterday():
    """
    Compute EERI for yesterday (for scheduled runs).
    """
    check_enabled()
    
    target_date = date.today() - timedelta(days=1)
    
    logger.info(f"Computing EERI for yesterday ({target_date})")
    
    result = compute_eeri_for_date(target_date, force=False)
    
    if result:
        return {
            'success': True,
            'data': {
                'date': result.index_date.isoformat(),
                'value': float(result.value),
                'band': result.band.value if result.band else None,
            },
        }
    else:
        return {
            'success': False,
            'skipped': True,
            'message': f"EERI for {target_date} already exists or failed to compute.",
        }


class BackfillRequest(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    force: bool = False


@router.post("/eeri/backfill")
async def backfill_eeri_endpoint(request: BackfillRequest):
    """
    Backfill EERI indices from historical alert_events.
    
    If dates not specified:
    - start_date: auto-detected from earliest alert
    - end_date: yesterday
    """
    check_enabled()
    
    from src.reri.backfill import run_eeri_backfill
    
    start = None
    end = None
    
    if request.start_date:
        try:
            start = datetime.strptime(request.start_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid start_date format. Use YYYY-MM-DD."
            )
    
    if request.end_date:
        try:
            end = datetime.strptime(request.end_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid end_date format. Use YYYY-MM-DD."
            )
    
    logger.info(f"Starting EERI backfill: start={start}, end={end}, force={request.force}")
    
    result = run_eeri_backfill(
        start_date=start,
        end_date=end,
        force=request.force,
    )
    
    return {
        'success': True,
        'data': result,
    }
