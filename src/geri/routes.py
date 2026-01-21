"""
GERI v1 API Routes

Mounted under /api/v1/indices
"""
import logging
from datetime import date, datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.geri import ENABLE_GERI
from src.geri.repo import get_latest_index, get_index_history, get_index_for_date
from src.geri.service import compute_geri_for_date, backfill, auto_backfill

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/indices", tags=["GERI Indices"])


class ComputeRequest(BaseModel):
    date: str
    force: bool = False


class BackfillRequest(BaseModel):
    from_date: str
    to_date: str
    force: bool = False


def check_enabled():
    """Raise 503 if GERI module is disabled."""
    if not ENABLE_GERI:
        raise HTTPException(
            status_code=503,
            detail="GERI module is disabled. Set ENABLE_GERI=true to enable."
        )


@router.get("/geri/latest")
async def get_geri_latest():
    """
    Get the latest GERI index value.
    
    Returns the most recent computed index from intel_indices_daily.
    """
    check_enabled()
    
    result = get_latest_index()
    
    if not result:
        raise HTTPException(
            status_code=404,
            detail="No GERI index data available. Run compute or backfill first."
        )
    
    if result.get('date'):
        result['date'] = result['date'].isoformat() if isinstance(result['date'], date) else result['date']
    if result.get('computed_at'):
        result['computed_at'] = result['computed_at'].isoformat() if isinstance(result['computed_at'], datetime) else result['computed_at']
    
    return {
        'success': True,
        'data': result,
    }


@router.get("/geri")
async def get_geri_history(
    from_date: Optional[str] = Query(None, alias="from", description="Start date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, alias="to", description="End date (YYYY-MM-DD)")
):
    """
    Get GERI index history for a date range.
    
    Returns rows from intel_indices_daily in ascending date order.
    If no date range specified, returns last 30 days.
    """
    check_enabled()
    
    try:
        if to_date:
            end = datetime.strptime(to_date, "%Y-%m-%d").date()
        else:
            end = date.today()
        
        if from_date:
            start = datetime.strptime(from_date, "%Y-%m-%d").date()
        else:
            from datetime import timedelta
            start = end - timedelta(days=30)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date format. Use YYYY-MM-DD."
        )
    
    results = get_index_history(start, end)
    
    for r in results:
        if r.get('date'):
            r['date'] = r['date'].isoformat() if isinstance(r['date'], date) else r['date']
        if r.get('computed_at'):
            r['computed_at'] = r['computed_at'].isoformat() if isinstance(r['computed_at'], datetime) else r['computed_at']
    
    return {
        'success': True,
        'from': start.isoformat(),
        'to': end.isoformat(),
        'count': len(results),
        'data': results,
    }


@router.post("/geri/compute")
async def compute_geri(request: ComputeRequest):
    """
    Compute GERI index for a specific date (admin-only).
    
    Reads from alert_events for that day and writes result to intel_indices_daily.
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
            detail="Cannot compute index for today or future dates. Use yesterday or earlier."
        )
    
    try:
        result = compute_geri_for_date(target_date, force=request.force)
        
        if result:
            return {
                'success': True,
                'message': f"GERI index computed for {target_date}",
                'data': result.to_dict(),
            }
        else:
            return {
                'success': True,
                'message': f"GERI index for {target_date} already exists (skipped)",
                'skipped': True,
            }
    except Exception as e:
        logger.error(f"Error computing GERI for {target_date}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to compute GERI: {str(e)}"
        )


@router.post("/geri/backfill")
async def backfill_geri(request: BackfillRequest):
    """
    Backfill GERI indices for a date range (admin-only).
    
    Processes all days in the range, computing indices from alert_events
    and storing results in intel_indices_daily.
    """
    check_enabled()
    
    try:
        start = datetime.strptime(request.from_date, "%Y-%m-%d").date()
        end = datetime.strptime(request.to_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date format. Use YYYY-MM-DD."
        )
    
    if start > end:
        raise HTTPException(
            status_code=400,
            detail="from_date must be before or equal to to_date"
        )
    
    if end >= date.today():
        from datetime import timedelta
        end = date.today() - timedelta(days=1)
    
    try:
        summary = backfill(start, end, force=request.force)
        return {
            'success': True,
            'summary': summary,
        }
    except Exception as e:
        logger.error(f"Error during backfill: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to backfill: {str(e)}"
        )


@router.post("/geri/backfill-auto")
async def auto_backfill_geri(force: bool = False):
    """
    Automatically backfill all historical alerts (admin-only).
    
    Determines date range from alert_events and processes all days.
    """
    check_enabled()
    
    try:
        summary = auto_backfill(force=force)
        return {
            'success': True,
            'summary': summary,
        }
    except Exception as e:
        logger.error(f"Error during auto-backfill: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to auto-backfill: {str(e)}"
        )


@router.get("/geri/status")
async def get_geri_status():
    """Get GERI module status."""
    return {
        'enabled': ENABLE_GERI,
        'index_id': 'global:geo_energy_risk',
        'model_version': 'geri_v1',
    }
