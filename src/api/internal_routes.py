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
    'alerts': 1004
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
