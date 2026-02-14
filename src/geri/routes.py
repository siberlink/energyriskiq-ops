"""
GERI v1 API Routes

Mounted under /api/v1/indices
"""
import logging
from datetime import date, datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from src.geri import ENABLE_GERI
from src.geri.repo import get_latest_index, get_index_history, get_index_for_date, get_delayed_index
from src.geri.service import compute_geri_for_date, compute_yesterday, backfill, auto_backfill

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
    
    try:
        result = get_latest_index()
    except Exception as e:
        logger.error(f"Error fetching latest GERI index: {e}")
        return {
            'success': False,
            'message': 'Database error fetching GERI data',
            'data': None,
        }
    
    if not result:
        logger.info("No GERI data found in database")
        return {
            'success': False,
            'message': 'No GERI data available yet',
            'data': None,
        }
    
    logger.info(f"GERI latest: date={result.get('date')}, value={result.get('value')}, band={result.get('band')}")
    
    try:
        if result.get('date'):
            result['date'] = result['date'].isoformat() if isinstance(result['date'], date) else str(result['date'])
        if result.get('computed_at'):
            result['computed_at'] = result['computed_at'].isoformat() if isinstance(result['computed_at'], datetime) else str(result['computed_at'])
        
        components = result.get('components')
        if components is None:
            components = {}
        elif isinstance(components, str):
            import json as _json
            try:
                components = _json.loads(components)
            except Exception:
                components = {}
        result['components'] = components
    except Exception as e:
        logger.error(f"Error processing GERI result: {e}", exc_info=True)
        return {
            'success': False,
            'message': f'Error processing GERI data: {str(e)}',
            'data': None,
        }
    
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


@router.post("/geri/compute-yesterday")
async def compute_geri_yesterday():
    """
    Compute GERI index for yesterday (scheduler endpoint).
    
    Called by GitHub Actions workflow at 01:10 UTC daily.
    """
    check_enabled()
    
    from datetime import timedelta
    yesterday = date.today() - timedelta(days=1)
    
    try:
        result = compute_yesterday()
        
        if result:
            return {
                'success': True,
                'message': f"GERI index computed for {yesterday}",
                'date': yesterday.isoformat(),
                'value': result.value,
                'band': result.band.value,
            }
        else:
            return {
                'success': True,
                'skipped': True,
                'message': f"GERI index for {yesterday} already exists or no data",
                'date': yesterday.isoformat(),
            }
    except Exception as e:
        logger.error(f"Error computing GERI for yesterday: {e}")
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


@router.get("/geri/trader-intel")
async def get_geri_trader_intel_endpoint(
    x_user_token: Optional[str] = Header(None)
):
    """
    Get GERI Trader Intelligence data.
    
    Server-side plan enforcement: resolves user plan from session token.
    - Trader (plan_level=2): 7 base modules (lead/lag, divergence, confirmation, storage, regime, reaction, alerts)
    - Pro (plan_level=3): All Trader + rolling correlations, risk decomposition, regime probability
    - Enterprise (plan_level=4): All Pro + spillover analysis
    """
    check_enabled()
    
    plan_level = 0
    try:
        from src.api.user_routes import verify_user_session
        from src.db.db import get_cursor
        session = verify_user_session(x_user_token)
        user_id = session["user_id"]
        with get_cursor(commit=False) as cur:
            cur.execute("SELECT plan FROM user_plans WHERE user_id = %s ORDER BY created_at DESC LIMIT 1", (user_id,))
            row = cur.fetchone()
            if row:
                plan_map = {'free': 0, 'personal': 1, 'trader': 2, 'pro': 3, 'enterprise': 4}
                plan_level = plan_map.get(row['plan'], 0)
    except Exception as auth_err:
        logger.warning(f"Auth check for trader-intel: {auth_err}")
        return {
            'success': False,
            'message': 'Authentication required for GERI Trader Intelligence',
            'upgrade_required': True,
        }
    
    if plan_level < 2:
        return {
            'success': False,
            'message': 'GERI Trader Intelligence requires Trader plan or above',
            'upgrade_required': True,
        }

    try:
        from src.geri.trader_intel import get_geri_trader_intel
        data = get_geri_trader_intel(plan_level=max(2, min(4, plan_level)))
        return {
            'success': True,
            'data': data,
        }
    except Exception as e:
        logger.error(f"Error computing GERI trader intel: {e}", exc_info=True)
        return {
            'success': False,
            'message': f'Error computing trader intelligence: {str(e)}',
            'data': None,
        }


@router.get("/geri/status")
async def get_geri_status():
    """Get GERI module status."""
    return {
        'enabled': ENABLE_GERI,
        'index_id': 'global:geo_energy_risk',
        'model_version': 'geri_v1',
    }


@router.get("/geri/public")
async def get_geri_public():
    """
    Get GERI index for public display (24h delayed).
    
    This is a FREE, unauthenticated endpoint for marketing/SEO.
    Returns data from 24+ hours ago to provide value while protecting premium real-time access.
    """
    check_enabled()
    
    result = get_delayed_index(delay_days=1)
    
    if not result:
        return {
            'success': False,
            'message': 'No GERI data available yet',
            'data': None,
        }
    
    components = result.get('components', {})
    if isinstance(components, str):
        import json
        components = json.loads(components)
    
    top_drivers = components.get('top_drivers', [])
    top_regions = components.get('top_regions', [])
    
    # Deduplicate headlines (stored data may have duplicates)
    seen = set()
    driver_headlines = []
    driver_details = []
    for d in top_drivers:
        headline = d.get('headline', '')
        if headline and headline not in seen:
            seen.add(headline)
            driver_headlines.append(headline)
            driver_details.append({
                'headline': headline,
                'region': d.get('region', ''),
                'category': d.get('category', ''),
            })
    
    region_names = [r.get('region', '') for r in top_regions[:3] if r.get('region')]
    
    index_date = result.get('date')
    if hasattr(index_date, 'isoformat'):
        index_date = index_date.isoformat()
    
    return {
        'success': True,
        'delayed': True,
        'delay_hours': 24,
        'data': {
            'date': index_date,
            'value': result.get('value'),
            'band': result.get('band'),
            'trend_1d': result.get('trend_1d'),
            'trend_7d': result.get('trend_7d'),
            'top_drivers': driver_headlines,
            'top_drivers_detailed': driver_details,
            'top_regions': region_names,
        }
    }


@router.get("/geri/market-overlays")
async def get_geri_market_overlays(
    from_date: Optional[str] = Query(None, alias="from", description="Start date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, alias="to", description="End date (YYYY-MM-DD)")
):
    """
    Get market overlay data for GERI chart visualization.
    
    Returns real market data aligned with GERI index dates only.
    Data before the first GERI date is excluded.
    
    Sources:
    - oil_price_snapshots (Brent oil prices)
    - gas_storage_snapshots (EU gas storage levels)
    - vix_snapshots (VIX volatility index)
    - ttf_gas_snapshots (TTF gas prices)
    - eurusd_snapshots (EUR/USD exchange rate)
    """
    check_enabled()
    
    from src.db.db import get_cursor
    
    with get_cursor() as cur:
        cur.execute("""
            SELECT MIN(date) as first_date, MAX(date) as last_date
            FROM intel_indices_daily
        """)
        geri_range = cur.fetchone()
        
        if not geri_range or not geri_range['first_date']:
            return {
                'success': False,
                'message': 'No GERI data available',
                'overlays': {}
            }
        
        geri_first = geri_range['first_date']
        geri_last = geri_range['last_date']
    
    try:
        if from_date:
            start = datetime.strptime(from_date, "%Y-%m-%d").date()
            start = max(start, geri_first)
        else:
            start = geri_first
        
        if to_date:
            end = datetime.strptime(to_date, "%Y-%m-%d").date()
            end = min(end, geri_last)
        else:
            end = geri_last
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date format. Use YYYY-MM-DD."
        )
    
    with get_cursor() as cur:
        cur.execute("""
            SELECT date, brent_price, wti_price
            FROM oil_price_snapshots
            WHERE date >= %s AND date <= %s
            ORDER BY date ASC
        """, (start, end))
        oil_rows = cur.fetchall()
        
        cur.execute("""
            SELECT date, eu_storage_percent, risk_score
            FROM gas_storage_snapshots
            WHERE date >= %s AND date <= %s
            ORDER BY date ASC
        """, (start, end))
        gas_rows = cur.fetchall()
        
        cur.execute("""
            SELECT date, vix_close
            FROM vix_snapshots
            WHERE date >= %s AND date <= %s
            ORDER BY date ASC
        """, (start, end))
        vix_rows = cur.fetchall()
        
        cur.execute("""
            SELECT date, ttf_price
            FROM ttf_gas_snapshots
            WHERE date >= %s AND date <= %s
            ORDER BY date ASC
        """, (start, end))
        ttf_rows = cur.fetchall()
        
        cur.execute("""
            SELECT date, rate
            FROM eurusd_snapshots
            WHERE date >= %s AND date <= %s
            ORDER BY date ASC
        """, (start, end))
        eurusd_rows = cur.fetchall()
    
    brent_data = []
    for row in oil_rows:
        row_date = row['date']
        brent_data.append({
            'date': row_date.isoformat() if isinstance(row_date, date) else row_date,
            'value': float(row['brent_price']) if row['brent_price'] else None,
            'wti': float(row['wti_price']) if row['wti_price'] else None
        })
    
    gas_storage_data = []
    for row in gas_rows:
        row_date = row['date']
        gas_storage_data.append({
            'date': row_date.isoformat() if isinstance(row_date, date) else row_date,
            'value': float(row['eu_storage_percent']) if row['eu_storage_percent'] else None,
            'risk_score': int(row['risk_score']) if row['risk_score'] else None
        })
    
    vix_data = []
    for row in vix_rows:
        row_date = row['date']
        vix_data.append({
            'date': row_date.isoformat() if isinstance(row_date, date) else row_date,
            'value': float(row['vix_close']) if row['vix_close'] else None
        })
    
    ttf_data = []
    for row in ttf_rows:
        row_date = row['date']
        ttf_data.append({
            'date': row_date.isoformat() if isinstance(row_date, date) else row_date,
            'value': float(row['ttf_price']) if row['ttf_price'] else None
        })
    
    eurusd_data = []
    for row in eurusd_rows:
        row_date = row['date']
        eurusd_data.append({
            'date': row_date.isoformat() if isinstance(row_date, date) else row_date,
            'value': float(row['rate']) if row['rate'] else None
        })
    
    available = ['brent', 'gas_storage']
    if vix_data:
        available.append('vix')
    if ttf_data:
        available.append('ttf')
    if eurusd_data:
        available.append('eurusd')
    
    unavailable = []
    if not vix_data:
        unavailable.append('vix')
    if not ttf_data:
        unavailable.append('ttf')
    if not eurusd_data:
        unavailable.append('eurusd')
    unavailable.append('freight')
    
    return {
        'success': True,
        'from': start.isoformat(),
        'to': end.isoformat(),
        'overlays': {
            'brent': {
                'label': 'Brent Oil',
                'unit': 'USD/barrel',
                'count': len(brent_data),
                'data': brent_data
            },
            'gas_storage': {
                'label': 'EU Gas Storage',
                'unit': '%',
                'count': len(gas_storage_data),
                'data': gas_storage_data
            },
            'vix': {
                'label': 'VIX',
                'unit': 'index',
                'count': len(vix_data),
                'data': vix_data
            },
            'ttf': {
                'label': 'TTF Gas',
                'unit': 'EUR/MWh',
                'count': len(ttf_data),
                'data': ttf_data
            },
            'eurusd': {
                'label': 'EUR/USD',
                'unit': 'rate',
                'count': len(eurusd_data),
                'data': eurusd_data
            }
        },
        'available': available,
        'unavailable': unavailable,
        'note': 'Freight (Baltic Dry Index) requires paid subscription - not available'
    }
