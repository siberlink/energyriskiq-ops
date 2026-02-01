import os
import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Header, HTTPException

from src.db.db import advisory_lock

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])

LOCK_IDS = {
    'ingest': 1001,
    'ai': 1002,
    'risk': 1003,
    'alerts': 1004,
    'digest': 1005,
    'alerts_generate': 2001,
    'alerts_fanout': 2002,
    'pro_delivery': 3001,
    'geri_delivery': 3002,
    'trader_delivery': 3003,
    'eeri_compute': 4000,
    'egsi_compute': 4001,
    'egsi_s_compute': 4002,
    'oil_price_capture': 4003,
    'gas_storage_capture': 4004,
    'backfill_snapshots': 5001,
    'backfill_egsi': 5002,
    'calculate_oil_changes': 5003,
}


def validate_runner_token(x_runner_token: Optional[str] = Header(None)):
    expected_token = os.environ.get('INTERNAL_RUNNER_TOKEN')
    
    if not expected_token:
        logger.error("INTERNAL_RUNNER_TOKEN not configured")
        raise HTTPException(status_code=500, detail="Runner token not configured")
    
    if not x_runner_token or x_runner_token != expected_token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    return True


def run_job_with_lock(job_name: str, job_function, *args, **kwargs):
    lock_id = LOCK_IDS.get(job_name)
    if not lock_id:
        raise ValueError(f"Unknown job: {job_name}")
    
    started_at = datetime.utcnow()
    
    with advisory_lock(lock_id) as acquired:
        if not acquired:
            return {
                "status": "busy",
                "job": job_name,
                "message": f"Job {job_name} is already running"
            }, 409
        
        try:
            logger.info(f"Starting job: {job_name}")
            result = job_function(*args, **kwargs)
            finished_at = datetime.utcnow()
            
            return {
                "status": "ok",
                "job": job_name,
                "started_at": started_at.isoformat(),
                "finished_at": finished_at.isoformat(),
                "duration_seconds": (finished_at - started_at).total_seconds(),
                "details": result if isinstance(result, dict) else {}
            }, 200
        
        except Exception as e:
            finished_at = datetime.utcnow()
            logger.error(f"Job {job_name} failed: {e}")
            return {
                "status": "error",
                "job": job_name,
                "started_at": started_at.isoformat(),
                "finished_at": finished_at.isoformat(),
                "error": str(e)
            }, 500


@router.post("/run/ingest")
def run_ingest(x_runner_token: Optional[str] = Header(None)):
    validate_runner_token(x_runner_token)
    
    from src.ingest.ingest_runner import run_ingestion
    
    def ingest_job():
        stats = run_ingestion()
        return stats if stats else {}
    
    response, status_code = run_job_with_lock('ingest', ingest_job)
    
    if status_code == 409:
        raise HTTPException(status_code=409, detail=response)
    if status_code == 500:
        raise HTTPException(status_code=500, detail=response)
    
    return response


@router.post("/run/ai")
def run_ai(x_runner_token: Optional[str] = Header(None)):
    validate_runner_token(x_runner_token)
    
    from src.ai.ai_worker import run_ai_worker
    
    def ai_job():
        stats = run_ai_worker()
        return stats if stats else {}
    
    response, status_code = run_job_with_lock('ai', ai_job)
    
    if status_code == 409:
        raise HTTPException(status_code=409, detail=response)
    if status_code == 500:
        raise HTTPException(status_code=500, detail=response)
    
    return response


@router.post("/run/risk")
def run_risk(x_runner_token: Optional[str] = Header(None)):
    validate_runner_token(x_runner_token)
    
    from src.risk.risk_engine import run_risk_engine
    
    def risk_job():
        stats = run_risk_engine()
        return stats if stats else {}
    
    response, status_code = run_job_with_lock('risk', risk_job)
    
    if status_code == 409:
        raise HTTPException(status_code=409, detail=response)
    if status_code == 500:
        raise HTTPException(status_code=500, detail=response)
    
    return response


@router.post("/run/alerts")
def run_alerts(x_runner_token: Optional[str] = Header(None)):
    validate_runner_token(x_runner_token)
    
    alerts_v2 = os.environ.get('ALERTS_V2_ENABLED', 'true').lower() == 'true'
    
    if alerts_v2:
        from src.alerts.alerts_engine_v2 import run_alerts_engine_v2
        
        def alerts_job():
            result = run_alerts_engine_v2(dry_run=False)
            return result
        
        response, status_code = run_job_with_lock('alerts', alerts_job)
    else:
        from src.alerts.alerts_engine import run_alerts_engine
        
        def alerts_job():
            alerts = run_alerts_engine(dry_run=False)
            return {"alerts_processed": len(alerts) if alerts else 0}
        
        response, status_code = run_job_with_lock('alerts', alerts_job)
    
    if status_code == 409:
        raise HTTPException(status_code=409, detail=response)
    if status_code == 500:
        raise HTTPException(status_code=500, detail=response)
    
    return response


@router.post("/run/digest")
def run_digest(x_runner_token: Optional[str] = Header(None)):
    validate_runner_token(x_runner_token)
    
    from src.alerts.digest_worker import run_digest_worker
    
    def digest_job():
        stats = run_digest_worker()
        return stats if stats else {}
    
    response, status_code = run_job_with_lock('digest', digest_job)
    
    if status_code == 409:
        raise HTTPException(status_code=409, detail=response)
    if status_code == 500:
        raise HTTPException(status_code=500, detail=response)
    
    return response


def validate_internal_token(x_internal_token: Optional[str] = Header(None)):
    """Validate x-internal-token header for admin endpoints."""
    expected_token = os.environ.get('INTERNAL_RUNNER_TOKEN')
    
    if not expected_token:
        logger.error("INTERNAL_RUNNER_TOKEN not configured")
        raise HTTPException(status_code=500, detail="Internal token not configured")
    
    if not x_internal_token or x_internal_token != expected_token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    return True


@router.get("/alerts/engine/runs")
def get_engine_runs(
    limit: int = 50,
    x_internal_token: Optional[str] = Header(None)
):
    """Get the latest engine run records."""
    validate_internal_token(x_internal_token)
    
    from src.alerts.engine_observability import get_engine_runs
    
    runs = get_engine_runs(limit=min(limit, 200))
    
    return {
        "count": len(runs),
        "runs": runs
    }


@router.get("/alerts/engine/runs/{run_id}")
def get_engine_run_detail(
    run_id: str,
    x_internal_token: Optional[str] = Header(None)
):
    """Get detailed information about a specific engine run."""
    validate_internal_token(x_internal_token)
    
    from src.alerts.engine_observability import get_engine_run_detail
    
    run = get_engine_run_detail(run_id)
    
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    return run


@router.get("/alerts/engine/health")
def get_engine_health(
    x_internal_token: Optional[str] = Header(None)
):
    """Get alerts engine health metrics."""
    validate_internal_token(x_internal_token)
    
    from src.alerts.engine_observability import get_delivery_health_metrics, get_digest_health_metrics
    
    delivery_metrics = get_delivery_health_metrics(hours=24)
    digest_metrics = get_digest_health_metrics(days=7)
    
    return {
        "deliveries_24h": delivery_metrics,
        "digests_7d": digest_metrics,
        "generated_at": datetime.utcnow().isoformat()
    }


@router.post("/alerts/engine/retry_failed")
def retry_failed_items(
    kind: str = "deliveries",
    since_hours: int = 24,
    dry_run: bool = True,
    x_internal_token: Optional[str] = Header(None)
):
    """
    Re-queue failed deliveries or digests for retry.
    
    Args:
        kind: 'deliveries' or 'digests'
        since_hours: Look back window in hours
        dry_run: If True, only report eligible items without changing them
    """
    validate_internal_token(x_internal_token)
    
    if kind not in ['deliveries', 'digests']:
        raise HTTPException(status_code=400, detail="kind must be 'deliveries' or 'digests'")
    
    from src.alerts.engine_observability import retry_failed_deliveries
    
    result = retry_failed_deliveries(kind=kind, since_hours=since_hours, dry_run=dry_run)
    
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    
    return result


@router.post("/run/seo")
def run_seo_generator(
    date: Optional[str] = None,
    backfill: Optional[int] = None,
    dry_run: bool = False,
    x_internal_token: Optional[str] = Header(None)
):
    """
    Generate SEO daily pages.
    
    Args:
        date: Specific date (YYYY-MM-DD) or None for yesterday. Must be <= yesterday (24h delay enforced).
        backfill: Number of days to backfill (all dates must be <= yesterday)
        dry_run: If True, preview without saving
    """
    validate_internal_token(x_internal_token)
    
    from datetime import datetime as dt, timedelta
    from src.seo.seo_generator import (
        get_yesterday_date,
        generate_daily_page_model,
        save_daily_page,
        generate_sitemap_entries,
        generate_and_save_regional_daily_page,
        REGION_DISPLAY_NAMES,
    )
    from src.db.migrations import run_seo_tables_migration
    
    run_seo_tables_migration()
    
    yesterday = get_yesterday_date()
    
    results = {
        'pages': [],
        'regional_pages': [],
        'sitemap_entries': 0,
        'dry_run': dry_run
    }
    
    def generate_regional_for_date(target_date, dry_run_flag):
        regional_results = []
        for region_slug in REGION_DISPLAY_NAMES.keys():
            try:
                if dry_run_flag:
                    regional_results.append({'date': target_date.isoformat(), 'region': region_slug, 'dry_run': True})
                else:
                    model = generate_and_save_regional_daily_page(target_date, region_slug)
                    regional_results.append({
                        'date': target_date.isoformat(),
                        'region': region_slug,
                        'alerts': model['stats']['total_alerts']
                    })
            except Exception as e:
                regional_results.append({'date': target_date.isoformat(), 'region': region_slug, 'error': str(e)})
        return regional_results
    
    if backfill and backfill > 0:
        for i in range(min(backfill, 90)):
            target = yesterday - timedelta(days=i)
            model = generate_daily_page_model(target)
            if not dry_run:
                page_id = save_daily_page(target, model)
                results['pages'].append({'date': target.isoformat(), 'page_id': page_id, 'alerts': model['stats']['total_alerts']})
            else:
                results['pages'].append({'date': target.isoformat(), 'alerts': model['stats']['total_alerts'], 'dry_run': True})
            results['regional_pages'].extend(generate_regional_for_date(target, dry_run))
    elif date:
        try:
            target = dt.strptime(date, '%Y-%m-%d').date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
        
        if target > yesterday:
            raise HTTPException(status_code=400, detail=f"24h delay enforced. Cannot generate page for {target}. Maximum allowed date is {yesterday}.")
        
        model = generate_daily_page_model(target)
        if not dry_run:
            page_id = save_daily_page(target, model)
            results['pages'].append({'date': target.isoformat(), 'page_id': page_id, 'alerts': model['stats']['total_alerts']})
        else:
            results['pages'].append({'date': target.isoformat(), 'alerts': model['stats']['total_alerts'], 'dry_run': True})
        results['regional_pages'].extend(generate_regional_for_date(target, dry_run))
    else:
        target = yesterday
        model = generate_daily_page_model(target)
        if not dry_run:
            page_id = save_daily_page(target, model)
            results['pages'].append({'date': target.isoformat(), 'page_id': page_id, 'alerts': model['stats']['total_alerts']})
        else:
            results['pages'].append({'date': target.isoformat(), 'alerts': model['stats']['total_alerts'], 'dry_run': True})
        results['regional_pages'].extend(generate_regional_for_date(target, dry_run))
    
    entries = generate_sitemap_entries()
    results['sitemap_entries'] = len(entries)
    
    return results


@router.post("/backfill-alert-metadata")
async def backfill_alert_metadata_endpoint(
    dry_run: bool = False,
    x_runner_token: Optional[str] = Header(None)
):
    """
    Backfill raw_input, classification, category, and confidence
    for alert_events with NULL values.
    """
    validate_runner_token(x_runner_token)
    
    from src.alerts.backfill_metadata import backfill_alert_metadata
    
    try:
        summary = backfill_alert_metadata(dry_run=dry_run)
        return {
            "status": "success",
            "summary": summary
        }
    except Exception as e:
        logger.error(f"Error during alert metadata backfill: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run/pro-delivery")
def run_pro_delivery(
    since_minutes: int = 15,
    include_geri: bool = True,
    x_runner_token: Optional[str] = Header(None)
):
    """
    Trigger Pro plan alert delivery.
    Called every 15 minutes by GitHub Actions.
    
    - Sends batched email alerts (up to daily limit) prioritized by risk score
    - Sends all alerts via Telegram to linked users
    - If include_geri=True, also sends any unsent GERI to Pro users
    """
    validate_runner_token(x_runner_token)
    
    from src.delivery.pro_delivery_worker import run_pro_delivery as do_pro_delivery, send_geri_to_pro_users_if_new
    
    response, status_code = run_job_with_lock('pro_delivery', do_pro_delivery, since_minutes)
    
    if status_code != 200:
        raise HTTPException(status_code=status_code, detail=response.get('message', 'Error'))
    
    if include_geri:
        geri_response, geri_status = run_job_with_lock('geri_delivery', send_geri_to_pro_users_if_new)
        response['geri_delivery'] = {
            'status': geri_response.get('status', 'unknown'),
            'details': geri_response.get('details', {}),
            'http_status': geri_status
        }
    
    return response


@router.post("/run/geri-delivery")
def run_geri_delivery(x_runner_token: Optional[str] = Header(None)):
    """
    Trigger GERI delivery to Pro users.
    Called immediately after GERI computation.
    
    - Sends GERI email (counts toward daily limit)
    - Sends GERI via Telegram to linked users
    """
    validate_runner_token(x_runner_token)
    
    from src.delivery.pro_delivery_worker import send_geri_to_pro_users
    
    response, status_code = run_job_with_lock('geri_delivery', send_geri_to_pro_users)
    
    if status_code != 200:
        raise HTTPException(status_code=status_code, detail=response.get('message', 'Error'))
    
    return response


@router.post("/run/trader-delivery")
def run_trader_delivery(
    since_minutes: int = 30,
    x_runner_token: Optional[str] = Header(None)
):
    """
    Trigger Trader plan alert delivery.
    Called every 30 minutes by GitHub Actions.
    
    - Sends batched email alerts (up to 8 per day) prioritized by risk score
    - Sends all alerts via Telegram to linked users
    - No GERI (Pro+ only)
    """
    validate_runner_token(x_runner_token)
    
    from src.delivery.trader_delivery_worker import run_trader_delivery as do_trader_delivery
    
    response, status_code = run_job_with_lock('trader_delivery', do_trader_delivery, since_minutes)
    
    if status_code != 200:
        raise HTTPException(status_code=status_code, detail=response.get('message', 'Error'))
    
    return response


@router.post("/run/eeri-compute")
def run_eeri_compute(
    target_date: Optional[str] = None,
    force: bool = False,
    x_runner_token: Optional[str] = Header(None)
):
    """
    Trigger EERI (Europe Energy Risk Index) computation.
    
    Computes for yesterday by default, or a specific date if provided.
    
    Args:
        target_date: Date to compute (YYYY-MM-DD format). Defaults to yesterday.
        force: Whether to recompute if already exists.
    """
    validate_runner_token(x_runner_token)
    
    from datetime import date, timedelta
    from src.reri import ENABLE_EERI
    from src.reri.service import compute_eeri_for_date
    
    if not ENABLE_EERI:
        return {
            "status": "skipped",
            "message": "EERI module is disabled (ENABLE_EERI=false)"
        }
    
    if target_date:
        try:
            compute_date = date.fromisoformat(target_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
    else:
        compute_date = date.today() - timedelta(days=1)
    
    def eeri_job():
        result = compute_eeri_for_date(compute_date, save=True, force=force)
        if result:
            return {
                'date': result.index_date.isoformat(),
                'value': result.value,
                'band': result.band.value,
                'trend_1d': result.trend_1d,
                'computed': True,
            }
        else:
            return {
                'date': compute_date.isoformat(),
                'computed': False,
                'message': 'Computation skipped or failed (already exists or no data)',
            }
    
    response, status_code = run_job_with_lock('eeri_compute', eeri_job)
    
    if status_code == 409:
        raise HTTPException(status_code=409, detail=response)
    if status_code == 500:
        raise HTTPException(status_code=500, detail=response)
    
    return response


@router.post("/run/egsi-compute")
def run_egsi_compute(
    target_date: Optional[str] = None,
    force: bool = False,
    x_runner_token: Optional[str] = Header(None)
):
    """
    Trigger EGSI-M (Europe Gas Stress Index - Market) computation.
    
    Should run AFTER EERI is computed since EGSI-M depends on RERI_EU.
    Computes for yesterday by default, or a specific date if provided.
    
    Args:
        target_date: Date to compute (YYYY-MM-DD format). Defaults to yesterday.
        force: Whether to recompute if already exists.
    """
    validate_runner_token(x_runner_token)
    
    from datetime import date, timedelta
    from src.egsi.types import ENABLE_EGSI
    from src.egsi.service import compute_egsi_m_for_date
    
    if not ENABLE_EGSI:
        return {
            "status": "skipped",
            "message": "EGSI module is disabled (ENABLE_EGSI=false)"
        }
    
    if target_date:
        try:
            compute_date = date.fromisoformat(target_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
    else:
        compute_date = date.today() - timedelta(days=1)
    
    def egsi_job():
        result = compute_egsi_m_for_date(compute_date, save=True, force=force)
        if result:
            return {
                'date': result.index_date.isoformat(),
                'value': round(result.value, 2),
                'band': result.band.value,
                'trend_1d': result.trend_1d,
                'computed': True,
            }
        else:
            return {
                'date': compute_date.isoformat(),
                'computed': False,
                'message': 'Computation skipped or failed (check if EERI exists for this date)',
            }
    
    response, status_code = run_job_with_lock('egsi_compute', egsi_job)
    
    if status_code == 409:
        raise HTTPException(status_code=409, detail=response)
    if status_code == 500:
        raise HTTPException(status_code=500, detail=response)
    
    return response


@router.post("/run/egsi-s-compute")
def run_egsi_s_compute(
    target_date: Optional[str] = None,
    force: bool = False,
    x_runner_token: Optional[str] = Header(None)
):
    """
    Trigger EGSI-S (Europe Gas Stress Index - System) computation.
    
    Uses real AGSI+ storage data when GIE_API_KEY is configured.
    Computes for yesterday by default, or a specific date if provided.
    
    Args:
        target_date: Date to compute (YYYY-MM-DD format). Defaults to yesterday.
        force: Whether to recompute if already exists.
    """
    validate_runner_token(x_runner_token)
    
    from datetime import date, timedelta
    from src.egsi.types import ENABLE_EGSI
    from src.egsi.service_egsi_s import compute_egsi_s_for_date
    
    if not ENABLE_EGSI:
        return {
            "status": "skipped",
            "message": "EGSI module is disabled (ENABLE_EGSI=false)"
        }
    
    if target_date:
        try:
            compute_date = date.fromisoformat(target_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
    else:
        compute_date = date.today() - timedelta(days=1)
    
    def egsi_s_job():
        result = compute_egsi_s_for_date(compute_date, save=True, force=force)
        if result:
            return {
                'date': result.index_date.isoformat(),
                'value': round(result.value, 2),
                'band': result.band.value,
                'trend_1d': result.trend_1d,
                'data_source': result.components.data_sources[0] if result.components.data_sources else 'unknown',
                'computed': True,
            }
        else:
            return {
                'date': compute_date.isoformat(),
                'computed': False,
                'message': 'Computation skipped or failed (check logs for details)',
            }
    
    response, status_code = run_job_with_lock('egsi_s_compute', egsi_s_job)
    
    if status_code == 409:
        raise HTTPException(status_code=409, detail=response)
    if status_code == 500:
        raise HTTPException(status_code=500, detail=response)
    
    return response


@router.post("/run/oil-price-capture")
def run_oil_price_capture(
    x_runner_token: Optional[str] = Header(None)
):
    """
    Capture daily oil prices (Brent Crude and WTI) from OilPriceAPI.
    
    Stores snapshot in oil_price_snapshots table for future index calculations.
    Skips if snapshot already exists for today (idempotent).
    """
    validate_runner_token(x_runner_token)
    
    from src.ingest.oil_price import capture_oil_price_snapshot
    
    def oil_price_job():
        return capture_oil_price_snapshot()
    
    response, status_code = run_job_with_lock('oil_price_capture', oil_price_job)
    
    if status_code == 409:
        raise HTTPException(status_code=409, detail=response)
    if status_code == 500:
        raise HTTPException(status_code=500, detail=response)
    
    return response


@router.post("/run/gas-storage-capture")
def run_gas_storage_capture(
    target_date: Optional[str] = None,
    x_runner_token: Optional[str] = Header(None)
):
    """
    Capture daily EU gas storage data from GIE AGSI+.
    
    Stores snapshot in gas_storage_snapshots table for EGSI-S calculations.
    Defaults to yesterday's date (end-of-day data).
    
    Args:
        target_date: Date to capture (YYYY-MM-DD format). Defaults to yesterday.
    """
    validate_runner_token(x_runner_token)
    
    from datetime import date, timedelta
    from src.scripts.backfill_snapshots import fetch_gas_storage_for_date, compute_gas_metrics, save_gas_storage_snapshot, get_db_connection
    
    if target_date:
        try:
            capture_date = date.fromisoformat(target_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
    else:
        capture_date = date.today() - timedelta(days=1)
    
    def gas_storage_job():
        date_str = capture_date.strftime("%Y-%m-%d")
        
        gas_data = fetch_gas_storage_for_date(date_str)
        if not gas_data:
            return {
                "status": "skipped",
                "date": date_str,
                "message": "No gas storage data available from AGSI+"
            }
        
        metrics = compute_gas_metrics(gas_data, capture_date.month)
        
        conn = get_db_connection()
        try:
            if save_gas_storage_snapshot(conn, date_str, metrics):
                return {
                    "status": "success",
                    "date": date_str,
                    "eu_storage_percent": metrics["eu_storage_percent"],
                    "risk_band": metrics["risk_band"],
                    "interpretation": metrics["interpretation"]
                }
            else:
                return {
                    "status": "error",
                    "date": date_str,
                    "message": "Failed to save gas storage snapshot"
                }
        finally:
            conn.close()
    
    response, status_code = run_job_with_lock('gas_storage_capture', gas_storage_job)
    
    if status_code == 409:
        raise HTTPException(status_code=409, detail=response)
    if status_code == 500:
        raise HTTPException(status_code=500, detail=response)
    
    return response


@router.post("/run/backfill-snapshots")
def run_backfill_snapshots(
    days: int = 15,
    x_runner_token: Optional[str] = Header(None)
):
    """
    Backfill gas_storage_snapshots and oil_price_snapshots tables.
    
    Fetches historical data from GIE AGSI+ and OilPriceAPI.
    This is a one-time operation for populating historical data.
    
    Args:
        days: Number of days to backfill (default 15)
    """
    validate_runner_token(x_runner_token)
    
    from datetime import date, timedelta
    from src.scripts.backfill_snapshots import backfill_date_range
    
    def backfill_job():
        end_date = date.today() - timedelta(days=1)
        start_date = end_date - timedelta(days=days - 1)
        
        logger.info(f"Starting backfill from {start_date} to {end_date}")
        results = backfill_date_range(start_date, end_date)
        
        return {
            "status": "success",
            "start_date": str(start_date),
            "end_date": str(end_date),
            "gas_storage": results["gas_storage"],
            "oil_price": results["oil_price"],
            "dates_processed": len(results["dates_processed"])
        }
    
    response, status_code = run_job_with_lock('backfill_snapshots', backfill_job)
    
    if status_code == 409:
        raise HTTPException(status_code=409, detail=response)
    if status_code == 500:
        raise HTTPException(status_code=500, detail=response)
    
    return response


@router.post("/run/calculate-oil-changes")
def run_calculate_oil_changes(
    x_runner_token: Optional[str] = Header(None)
):
    """
    Calculate 24h changes for oil price snapshots.
    
    Computes brent_change_24h, brent_change_pct, wti_change_24h, wti_change_pct
    by comparing consecutive days in the oil_price_snapshots table.
    """
    validate_runner_token(x_runner_token)
    
    from src.scripts.backfill_snapshots import calculate_oil_price_changes
    
    def calculate_job():
        logger.info("Calculating 24h changes for oil price snapshots...")
        return calculate_oil_price_changes()
    
    response, status_code = run_job_with_lock('backfill_snapshots', calculate_job)
    
    if status_code == 409:
        raise HTTPException(status_code=409, detail=response)
    if status_code == 500:
        raise HTTPException(status_code=500, detail=response)
    
    return response


@router.post("/run/backfill-egsi")
def run_backfill_egsi(
    days: int = 15,
    x_runner_token: Optional[str] = Header(None)
):
    """
    Backfill EGSI-M and EGSI-S indices for the specified number of days.
    
    Computes both indices using existing gas_storage_snapshots, alert_events,
    and RERI data. Uses force=True to overwrite existing records.
    
    Args:
        days: Number of days to backfill (default 15)
    """
    validate_runner_token(x_runner_token)
    
    import traceback
    from datetime import date, timedelta
    
    try:
        from src.scripts.backfill_snapshots import backfill_egsi_indices
    except Exception as e:
        logger.error(f"Failed to import backfill module: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Import error: {str(e)}")
    
    def backfill_job():
        end_date = date.today() - timedelta(days=1)
        start_date = end_date - timedelta(days=days - 1)
        
        logger.info(f"Starting EGSI backfill from {start_date} to {end_date}")
        results = backfill_egsi_indices(start_date, end_date)
        
        return {
            "status": "success",
            "start_date": str(start_date),
            "end_date": str(end_date),
            "egsi_m": results.get("egsi_m", {}),
            "egsi_s": results.get("egsi_s", {}),
            "dates_processed": len(results.get("dates_processed", []))
        }
    
    response, status_code = run_job_with_lock('backfill_egsi', backfill_job)
    
    if status_code == 409:
        raise HTTPException(status_code=409, detail=response)
    if status_code == 500:
        raise HTTPException(status_code=500, detail=response)
    
    return response
