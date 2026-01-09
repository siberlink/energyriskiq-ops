from fastapi import APIRouter
from src.alerts.templates import generate_sample_alerts, generate_tiered_sample_alerts, LANDING_COPY
from src.db.db import get_cursor
from datetime import datetime, timezone, timedelta

router = APIRouter(prefix="/marketing", tags=["marketing"])


@router.get("/samples")
def get_sample_alerts():
    samples = generate_tiered_sample_alerts()
    
    return {
        "samples": samples,
        "cta": LANDING_COPY["cta"],
        "cta_upgrade": LANDING_COPY["cta_upgrade"]
    }


@router.get("/landing-copy")
def get_landing_copy():
    return {
        "hero": LANDING_COPY["hero"],
        "subhero": LANDING_COPY["subhero"],
        "bullets": LANDING_COPY["bullets"],
        "example_alerts": LANDING_COPY["example_alerts"],
        "cta": LANDING_COPY["cta"],
        "cta_upgrade": LANDING_COPY["cta_upgrade"],
        "disclaimer": LANDING_COPY["disclaimer"],
        "pricing": LANDING_COPY["pricing"]
    }


@router.get("/real-samples")
def get_real_sample_alerts():
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    
    with get_cursor(commit=False) as cur:
        cur.execute("""
            SELECT id, alert_type, region, asset, triggered_value, threshold,
                   title, message, channel, created_at, sent_at
            FROM alerts
            WHERE status = 'sent'
              AND created_at < %s
            ORDER BY created_at DESC
            LIMIT 6
        """, (cutoff,))
        rows = cur.fetchall()
    
    samples = []
    for row in rows:
        sent_at = row["sent_at"] or row["created_at"]
        if sent_at:
            if hasattr(sent_at, 'isoformat'):
                sent_at_str = sent_at.isoformat()
            else:
                sent_at_str = str(sent_at)
        else:
            sent_at_str = None
            
        samples.append({
            "id": row["id"],
            "type": row["alert_type"],
            "title": row["title"],
            "message": row["message"],
            "region": row["region"],
            "asset": row["asset"],
            "channel": row["channel"],
            "triggered_value": float(row["triggered_value"]) if row["triggered_value"] else None,
            "threshold": float(row["threshold"]) if row["threshold"] else None,
            "sent_at": sent_at_str
        })
    
    return {
        "samples": samples,
        "count": len(samples),
        "delay_hours": 24,
        "disclaimer": "These are REAL alerts that were sent 24+ hours ago. Displayed for sample purposes only. Not to be used as real-time intelligence.",
        "last_updated": datetime.now(timezone.utc).isoformat()
    }
