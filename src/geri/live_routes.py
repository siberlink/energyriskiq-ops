"""
GERI Live Routes — REST + SSE endpoints for real-time GERI index

Endpoints:
  GET  /api/v1/indices/geri/live/latest  — Latest live GERI (REST, JSON)
  GET  /api/v1/indices/geri/live/stream  — SSE stream for real-time updates
  POST /api/v1/indices/geri/live/compute — Trigger recomputation (internal)
  GET  /api/v1/indices/geri/live/timeline — Intraday timeline data
"""

import asyncio
import json
import logging
import time
from typing import Optional

from fastapi import APIRouter, Header, Query, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse

from src.geri.live import (
    compute_live_geri,
    get_latest_live_geri,
    get_live_geri_timeline,
    register_live_client,
    unregister_live_client,
    broadcast_live_update,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/indices/geri/live", tags=["GERI Live"])

ALLOWED_PLANS = {'pro', 'enterprise'}


def _verify_plan(plan: str):
    if plan not in ALLOWED_PLANS:
        raise HTTPException(
            status_code=403,
            detail="GERI Live is available for Pro and Enterprise plans only"
        )


def _get_user_plan(token: str) -> dict:
    try:
        from src.api.user_routes import verify_user_session
        session = verify_user_session(token)
        if not session:
            raise HTTPException(status_code=401, detail="Invalid session")
        user_id = session.get('user_id')
        from src.db.db import execute_one
        row = execute_one(
            "SELECT plan FROM user_plans WHERE user_id = %s", (user_id,)
        )
        plan = row['plan'] if row else 'free'
        return {'user_id': user_id, 'plan': plan}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"GERI Live auth error: {e}")
        raise HTTPException(status_code=401, detail="Authentication failed")


@router.get("/latest")
async def get_live_latest(x_user_token: Optional[str] = Header(None)):
    if not x_user_token:
        raise HTTPException(status_code=401, detail="Authentication required")

    user_info = _get_user_plan(x_user_token)
    _verify_plan(user_info['plan'])

    latest = get_latest_live_geri()
    timeline = get_live_geri_timeline()

    if not latest:
        result = compute_live_geri(force=True)
        if result:
            latest = result
            timeline = get_live_geri_timeline()

    if not latest:
        from src.geri.live import _get_yesterday_geri_value
        yd_val = _get_yesterday_geri_value()
        return JSONResponse(content={
            'success': True,
            'data': {
                'value': 0,
                'band': 'LOW',
                'trend_vs_yesterday': None,
                'alert_count': 0,
                'top_drivers': [],
                'top_regions': [],
                'interpretation': '',
                'computed_at': None,
                'timeline': [],
                'no_data': True,
                'yesterday_value': yd_val,
            }
        })

    from src.geri.live import _get_yesterday_geri_value, _compute_velocity, _compute_band_proximity, _compute_peak_low
    yesterday_val = _get_yesterday_geri_value()
    value = latest['value']
    velocity = latest.get('velocity') or _compute_velocity(timeline, value)
    band_proximity = latest.get('band_proximity') or _compute_band_proximity(value)
    peak_low = latest.get('peak_low') or _compute_peak_low(timeline, value)

    return JSONResponse(content={
        'success': True,
        'data': {
            'value': value,
            'band': latest['band'],
            'trend_vs_yesterday': latest.get('trend_vs_yesterday'),
            'alert_count': latest.get('alert_count', 0),
            'top_drivers': latest.get('top_drivers', []),
            'top_regions': latest.get('top_regions', []),
            'components': latest.get('components', {}),
            'interpretation': latest.get('interpretation', ''),
            'computed_at': latest.get('computed_at'),
            'timeline': timeline,
            'yesterday_value': yesterday_val,
            'velocity': velocity,
            'band_proximity': band_proximity,
            'peak_low': peak_low,
        }
    })


@router.get("/timeline")
async def get_timeline(x_user_token: Optional[str] = Header(None)):
    if not x_user_token:
        raise HTTPException(status_code=401, detail="Authentication required")

    user_info = _get_user_plan(x_user_token)
    _verify_plan(user_info['plan'])

    return JSONResponse(content={
        'success': True,
        'data': get_live_geri_timeline()
    })


@router.get("/stream")
async def live_stream(token: Optional[str] = Query(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required (pass token as query param)")

    user_info = _get_user_plan(token)
    _verify_plan(user_info['plan'])

    queue: asyncio.Queue = asyncio.Queue(maxsize=50)
    await register_live_client(queue)

    async def event_generator():
        try:
            latest = get_latest_live_geri()
            if latest:
                from src.geri.live import _get_yesterday_geri_value, _compute_velocity, _compute_band_proximity, _compute_peak_low
                latest['yesterday_value'] = _get_yesterday_geri_value()
                tl = get_live_geri_timeline()
                latest['velocity'] = latest.get('velocity') or _compute_velocity(tl, latest['value'])
                latest['band_proximity'] = latest.get('band_proximity') or _compute_band_proximity(latest['value'])
                latest['peak_low'] = latest.get('peak_low') or _compute_peak_low(tl, latest['value'])
                yield f"data: {json.dumps({'type': 'initial', **latest})}\n\n"

            last_heartbeat = time.time()
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=5.0)
                    yield f"data: {json.dumps({'type': 'update', **data})}\n\n"
                except asyncio.TimeoutError:
                    if time.time() - last_heartbeat >= 30:
                        yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
                        last_heartbeat = time.time()
        except asyncio.CancelledError:
            pass
        finally:
            await unregister_live_client(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.post("/compute")
async def trigger_compute(x_admin_token: Optional[str] = Header(None)):
    from src.api.admin_routes import verify_admin_token
    verify_admin_token(x_admin_token)
    try:
        result = compute_live_geri(force=False)
        if result:
            broadcast_data = {
                'value': result['value'],
                'band': result['band'],
                'trend_vs_yesterday': result.get('trend_vs_yesterday'),
                'alert_count': result.get('alert_count', 0),
                'top_drivers': result.get('top_drivers', []),
                'top_regions': result.get('top_regions', []),
                'interpretation': result.get('interpretation', ''),
                'interpretation_updated': result.get('interpretation_updated', False),
                'computed_at': result.get('computed_at'),
            }
            await broadcast_live_update(broadcast_data)
            return JSONResponse(content={
                'success': True,
                'value': result['value'],
                'band': result['band'],
                'alert_count': result.get('alert_count', 0),
            })
        return JSONResponse(content={
            'success': True,
            'message': 'debounced or no change',
        })
    except Exception as e:
        logger.error(f"GERI Live compute error: {e}")
        return JSONResponse(
            status_code=500,
            content={'success': False, 'error': str(e)}
        )
