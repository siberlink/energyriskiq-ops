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
            SELECT id, alert_type, scope_region, scope_assets, severity,
                   headline, body, created_at, fanout_completed_at
            FROM alert_events
            WHERE headline IS NOT NULL
              AND created_at < %s
            ORDER BY created_at DESC
            LIMIT 6
        """, (cutoff,))
        rows = cur.fetchall()
    
    samples = []
    for row in rows:
        sent_at = row["fanout_completed_at"] or row["created_at"]
        if sent_at:
            if hasattr(sent_at, 'isoformat'):
                sent_at_str = sent_at.isoformat()
            else:
                sent_at_str = str(sent_at)
        else:
            sent_at_str = None
        
        assets = row["scope_assets"] or []
        asset = assets[0] if assets else None
            
        samples.append({
            "id": row["id"],
            "type": row["alert_type"],
            "title": row["headline"],
            "message": row["body"],
            "region": row["scope_region"],
            "asset": asset,
            "channel": "email",
            "severity": row["severity"],
            "sent_at": sent_at_str
        })
    
    return {
        "samples": samples,
        "count": len(samples),
        "delay_hours": 24,
        "disclaimer": "These are REAL alerts that were sent 24+ hours ago. Displayed for sample purposes only. Not to be used as real-time intelligence.",
        "last_updated": datetime.now(timezone.utc).isoformat()
    }
