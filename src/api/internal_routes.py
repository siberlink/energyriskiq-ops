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
    'alerts_fanout': 2002
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
        generate_sitemap_entries
    )
    from src.db.migrations import run_seo_tables_migration
    
    run_seo_tables_migration()
    
    yesterday = get_yesterday_date()
    
    results = {
        'pages': [],
        'sitemap_entries': 0,
        'dry_run': dry_run
    }
    
    if backfill and backfill > 0:
        for i in range(min(backfill, 90)):
            target = yesterday - timedelta(days=i)
            model = generate_daily_page_model(target)
            if not dry_run:
                page_id = save_daily_page(target, model)
                results['pages'].append({'date': target.isoformat(), 'page_id': page_id, 'alerts': model['stats']['total_alerts']})
            else:
                results['pages'].append({'date': target.isoformat(), 'alerts': model['stats']['total_alerts'], 'dry_run': True})
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
    else:
        target = yesterday
        model = generate_daily_page_model(target)
        if not dry_run:
            page_id = save_daily_page(target, model)
            results['pages'].append({'date': target.isoformat(), 'page_id': page_id, 'alerts': model['stats']['total_alerts']})
        else:
            results['pages'].append({'date': target.isoformat(), 'alerts': model['stats']['total_alerts'], 'dry_run': True})
    
    entries = generate_sitemap_entries()
    results['sitemap_entries'] = len(entries)
    
    return results


@router.get("/alerts/metadata")
def get_alert_metadata(
    x_runner_token: Optional[str] = Header(None),
    limit: int = 50,
    offset: int = 0,
    alert_type: Optional[str] = None,
    category: Optional[str] = None,
    region: Optional[str] = None,
    min_confidence: Optional[float] = None
):
    """
    Retrieve alert metadata for analytics and debugging.
    
    Returns alerts with their raw_input, classification, category, and confidence data.
    Supports filtering by alert_type, category, region, and minimum confidence.
    """
    validate_runner_token(x_runner_token)
    
    from src.db.db import execute_query
    
    query = """
        SELECT 
            id, alert_type, scope_region, scope_assets, severity, headline,
            raw_input, classification, category, confidence,
            driver_event_ids, created_at, event_fingerprint
        FROM alert_events
        WHERE 1=1
    """
    params = []
    
    if alert_type:
        query += " AND alert_type = %s"
        params.append(alert_type)
    
    if category:
        query += " AND category = %s"
        params.append(category)
    
    if region:
        query += " AND LOWER(scope_region) = LOWER(%s)"
        params.append(region)
    
    if min_confidence is not None:
        query += " AND confidence >= %s"
        params.append(min_confidence)
    
    query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])
    
    results = execute_query(query, tuple(params))
    
    alerts = []
    for row in results or []:
        alerts.append({
            'id': row['id'],
            'alert_type': row['alert_type'],
            'scope_region': row['scope_region'],
            'scope_assets': row['scope_assets'],
            'severity': row['severity'],
            'headline': row['headline'],
            'raw_input': row['raw_input'],
            'classification': row['classification'],
            'category': row['category'],
            'confidence': float(row['confidence']) if row['confidence'] else None,
            'driver_event_ids': row['driver_event_ids'],
            'created_at': row['created_at'].isoformat() if row['created_at'] else None,
            'event_fingerprint': row['event_fingerprint']
        })
    
    return {
        'alerts': alerts,
        'count': len(alerts),
        'limit': limit,
        'offset': offset
    }


@router.get("/alerts/metadata/{alert_id}")
def get_alert_metadata_by_id(
    alert_id: int,
    x_runner_token: Optional[str] = Header(None)
):
    """
    Retrieve detailed metadata for a specific alert.
    """
    validate_runner_token(x_runner_token)
    
    from src.db.db import execute_one
    
    query = """
        SELECT 
            id, alert_type, scope_region, scope_assets, severity, headline, body,
            raw_input, classification, category, confidence,
            driver_event_ids, cooldown_key, event_fingerprint,
            fanout_completed_at, created_at
        FROM alert_events
        WHERE id = %s
    """
    
    result = execute_one(query, (alert_id,))
    
    if not result:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    return {
        'id': result['id'],
        'alert_type': result['alert_type'],
        'scope_region': result['scope_region'],
        'scope_assets': result['scope_assets'],
        'severity': result['severity'],
        'headline': result['headline'],
        'body': result['body'],
        'raw_input': result['raw_input'],
        'classification': result['classification'],
        'category': result['category'],
        'confidence': float(result['confidence']) if result['confidence'] else None,
        'driver_event_ids': result['driver_event_ids'],
        'cooldown_key': result['cooldown_key'],
        'event_fingerprint': result['event_fingerprint'],
        'fanout_completed_at': result['fanout_completed_at'].isoformat() if result['fanout_completed_at'] else None,
        'created_at': result['created_at'].isoformat() if result['created_at'] else None
    }
