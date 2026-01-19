import logging
from datetime import datetime, timedelta
from fastapi import APIRouter
from src.db.db import get_cursor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ops", tags=["operations"])

STALE_THRESHOLDS = {
    "ingest": 60,
    "ai": 360,
    "risk": 60,
    "alerts": 60,
    "digest": 2160,
}


def is_stale(last_run: datetime, threshold_minutes: int) -> bool:
    if not last_run:
        return True
    return datetime.utcnow() - last_run > timedelta(minutes=threshold_minutes)


@router.get("/status")
def get_worker_status():
    now_utc = datetime.utcnow()
    
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT finished_at, inserted_items 
            FROM ingestion_runs 
            WHERE status = 'success' 
            ORDER BY finished_at DESC 
            LIMIT 1
        """)
        ingest_row = cursor.fetchone()
        ingest_last = ingest_row['finished_at'] if ingest_row else None
        ingest_count = ingest_row['inserted_items'] if ingest_row else 0
        
        cursor.execute("""
            SELECT MAX(ai_processed_at) as last_processed, 
                   COUNT(*) FILTER (WHERE processed = true) as total_processed
            FROM events
        """)
        ai_row = cursor.fetchone()
        ai_last = ai_row['last_processed'] if ai_row else None
        ai_count = ai_row['total_processed'] if ai_row else 0
        
        cursor.execute("""
            SELECT MAX(calculated_at) as last_calc, COUNT(*) as total
            FROM risk_indices
        """)
        risk_row = cursor.fetchone()
        risk_last = risk_row['last_calc'] if risk_row else None
        risk_count = risk_row['total'] if risk_row else 0
        
        cursor.execute("""
            SELECT MAX(uad.sent_at) as last_sent, 
                   COUNT(*) FILTER (WHERE uad.status = 'sent') as total_sent
            FROM user_alert_deliveries uad
            JOIN alert_events ae ON ae.id = uad.alert_event_id
            WHERE ae.alert_type != 'DAILY_DIGEST'
        """)
        alerts_row = cursor.fetchone()
        alerts_last = alerts_row['last_sent'] if alerts_row else None
        alerts_count = alerts_row['total_sent'] if alerts_row else 0
        
        cursor.execute("""
            SELECT MAX(uad.sent_at) as last_sent, COUNT(*) as total
            FROM user_alert_deliveries uad
            JOIN alert_events ae ON ae.id = uad.alert_event_id
            WHERE ae.alert_type = 'DAILY_DIGEST' AND uad.status = 'sent'
        """)
        digest_row = cursor.fetchone()
        digest_last = digest_row['last_sent'] if digest_row else None
        digest_count = digest_row['total'] if digest_row else 0
    
    return {
        "now_utc": now_utc.isoformat(),
        "workers": {
            "ingest": {
                "last_run": ingest_last.isoformat() if ingest_last else None,
                "count": ingest_count,
                "stale": is_stale(ingest_last, STALE_THRESHOLDS["ingest"])
            },
            "ai": {
                "last_run": ai_last.isoformat() if ai_last else None,
                "count": ai_count,
                "stale": is_stale(ai_last, STALE_THRESHOLDS["ai"])
            },
            "risk": {
                "last_run": risk_last.isoformat() if risk_last else None,
                "count": risk_count,
                "stale": is_stale(risk_last, STALE_THRESHOLDS["risk"])
            },
            "alerts": {
                "last_run": alerts_last.isoformat() if alerts_last else None,
                "count": alerts_count,
                "stale": is_stale(alerts_last, STALE_THRESHOLDS["alerts"])
            },
            "digest": {
                "last_run": digest_last.isoformat() if digest_last else None,
                "count": digest_count,
                "stale": is_stale(digest_last, STALE_THRESHOLDS["digest"])
            }
        }
    }
