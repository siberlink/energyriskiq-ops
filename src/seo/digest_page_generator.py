import logging
import json
from datetime import datetime, timezone, timedelta, date
from typing import Dict, List, Optional

from src.db.db import get_cursor, execute_query, execute_one
from src.api.daily_digest_routes import (
    compute_asset_changes,
    determine_risk_tone,
    generate_ai_digest,
    get_upgrade_hints,
)

logger = logging.getLogger(__name__)


def get_alerts_for_date(target_date: date, limit: int = 20) -> List[Dict]:
    start = target_date - timedelta(days=1)
    end = target_date
    rows = execute_query("""
        SELECT id, alert_type, scope_region, scope_assets, severity, headline, body,
               category, confidence, created_at, classification
        FROM alert_events
        WHERE created_at >= %s AND created_at < %s
        ORDER BY severity DESC, created_at DESC
        LIMIT %s
    """, (start, end, limit))
    result = []
    if not rows:
        return result
    for r in rows:
        result.append({
            "id": r["id"],
            "alert_type": r["alert_type"],
            "region": r["scope_region"],
            "assets": r["scope_assets"] if r["scope_assets"] else [],
            "severity": r["severity"],
            "headline": r["headline"],
            "category": r["category"],
            "confidence": float(r["confidence"]) if r["confidence"] else 0,
            "created_at": r["created_at"].isoformat() if r["created_at"] else None
        })
    return result


def get_index_snapshot_for_date(index_id: str, target_date: date, days: int = 7) -> List[Dict]:
    rows = execute_query("""
        SELECT date, value, band, trend_1d, trend_7d, interpretation, components
        FROM intel_indices_daily
        WHERE index_id = %s AND date <= %s
        ORDER BY date DESC
        LIMIT %s
    """, (index_id, target_date, days))
    return [dict(r) for r in rows] if rows else []


def get_eeri_snapshot_for_date(target_date: date, days: int = 2) -> List[Dict]:
    rows = execute_query("""
        SELECT date, value, band, trend_1d, trend_7d, interpretation, components, drivers
        FROM reri_indices_daily
        WHERE index_id = 'europe:eeri' AND date <= %s
        ORDER BY date DESC
        LIMIT %s
    """, (target_date, days))
    return [dict(r) for r in rows] if rows else []


def get_egsi_snapshot_for_date(target_date: date, days: int = 2) -> List[Dict]:
    rows = execute_query("""
        SELECT index_date as date, index_value as value, band, trend_1d, trend_7d, interpretation
        FROM egsi_m_daily
        WHERE index_date <= %s
        ORDER BY index_date DESC
        LIMIT %s
    """, (target_date, days))
    return [dict(r) for r in rows] if rows else []


def get_asset_snapshots_for_date(target_date: date, days: int = 7) -> Dict:
    brent = execute_query(
        "SELECT date, brent_price, brent_change_pct FROM oil_price_snapshots WHERE date <= %s ORDER BY date DESC LIMIT %s",
        (target_date, days)
    )
    ttf = execute_query(
        "SELECT date, ttf_price FROM ttf_gas_snapshots WHERE date <= %s ORDER BY date DESC LIMIT %s",
        (target_date, days)
    )
    vix = execute_query(
        "SELECT date, vix_close FROM vix_snapshots WHERE date <= %s ORDER BY date DESC LIMIT %s",
        (target_date, days)
    )
    eurusd = execute_query(
        "SELECT date, rate FROM eurusd_snapshots WHERE date <= %s ORDER BY date DESC LIMIT %s",
        (target_date, days)
    )
    storage = execute_query(
        "SELECT date, eu_storage_percent, risk_band FROM gas_storage_snapshots WHERE date <= %s ORDER BY date DESC LIMIT %s",
        (target_date, days)
    )

    def to_list(rows):
        return [dict(r) for r in rows] if rows else []

    return {
        "brent": to_list(brent),
        "ttf": to_list(ttf),
        "vix": to_list(vix),
        "eurusd": to_list(eurusd),
        "storage": to_list(storage)
    }


def generate_public_digest_model(target_date: date) -> Dict:
    is_delayed = True
    alerts_date = target_date - timedelta(days=1)
    alerts = get_alerts_for_date(target_date, limit=20)

    geri = get_index_snapshot_for_date("global:geo_energy_risk", alerts_date, days=7)
    eeri = get_eeri_snapshot_for_date(alerts_date, days=2)
    egsi = get_egsi_snapshot_for_date(alerts_date, days=2)
    assets = get_asset_snapshots_for_date(alerts_date, days=7)

    asset_changes = compute_asset_changes(assets)
    risk_tone = determine_risk_tone(geri)

    visible_alerts = []
    for a in alerts[:2]:
        visible_alerts.append({
            "headline": a["headline"],
            "region": a["region"],
            "severity": a["severity"],
            "category": a.get("category", ""),
            "confidence": a.get("confidence", 0)
        })

    geri_summary = None
    if geri:
        g = geri[0]
        geri_summary = {
            "value": g.get("value"),
            "band": g.get("band"),
            "trend_1d": g.get("trend_1d"),
            "trend_7d": g.get("trend_7d"),
            "date": g.get("date").isoformat() if g.get("date") else None
        }

    ai_narrative = generate_ai_digest(
        plan='free',
        alerts=alerts,
        geri=geri,
        eeri=eeri,
        egsi=egsi,
        asset_changes=asset_changes,
        correlations=None,
        betas=None,
        risk_tone=risk_tone,
        regime=None
    )

    digest_date = target_date.isoformat()

    formatted_date = target_date.strftime("%B %d, %Y")
    seo_title = f"Daily Geo-Energy Intelligence Digest - {formatted_date} | EnergyRiskIQ"
    seo_description = (
        f"Free daily geo-energy risk intelligence digest for {formatted_date}. "
        f"GERI index, market reactions, top risk events, and AI-generated executive brief. "
        f"24h delayed data from EnergyRiskIQ."
    )

    model = {
        "digest_date": digest_date,
        "alerts_date": alerts_date.isoformat(),
        "date_display": formatted_date,
        "risk_tone": risk_tone,
        "geri": geri_summary,
        "asset_changes": asset_changes,
        "alerts": visible_alerts,
        "total_alerts_yesterday": len(alerts),
        "ai_narrative": ai_narrative,
        "is_delayed": is_delayed,
        "upgrade_hints": get_upgrade_hints(0),
        "seo_title": seo_title,
        "seo_description": seo_description,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    return model


def save_public_digest_page(target_date: date, model: Dict) -> int:
    with get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO public_digest_pages (
                page_date, seo_title, seo_description, page_json, generated_at
            ) VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (page_date) DO UPDATE SET
                seo_title = EXCLUDED.seo_title,
                seo_description = EXCLUDED.seo_description,
                page_json = EXCLUDED.page_json,
                generated_at = NOW(),
                updated_at = NOW()
            RETURNING id
        """, (
            target_date,
            model.get('seo_title', ''),
            model.get('seo_description', ''),
            json.dumps(model),
        ))
        result = cursor.fetchone()
        return result['id'] if result else None


def get_public_digest_page(target_date: date) -> Optional[Dict]:
    query = """
    SELECT id, page_date, seo_title, seo_description, page_json, generated_at, updated_at
    FROM public_digest_pages
    WHERE page_date = %s
    """
    result = execute_one(query, (target_date,))
    if result:
        page_json = result['page_json']
        if page_json:
            if isinstance(page_json, str):
                model = json.loads(page_json)
            else:
                model = page_json
        else:
            model = None
        return {
            'id': result['id'],
            'page_date': result['page_date'],
            'seo_title': result['seo_title'],
            'seo_description': result['seo_description'],
            'model': model,
            'generated_at': result['generated_at'],
            'updated_at': result['updated_at']
        }
    return None


def get_recent_public_digest_pages(limit: int = 90) -> List[Dict]:
    query = """
    SELECT page_date, seo_title, generated_at
    FROM public_digest_pages
    ORDER BY page_date DESC
    LIMIT %s
    """
    results = execute_query(query, (limit,))
    return results if results else []


def get_public_digest_available_dates() -> List[str]:
    query = """
    SELECT page_date
    FROM public_digest_pages
    ORDER BY page_date DESC
    """
    results = execute_query(query)
    if not results:
        return []
    dates = []
    for r in results:
        pd = r['page_date']
        if isinstance(pd, str):
            dates.append(pd)
        else:
            dates.append(pd.isoformat())
    return dates


def generate_and_save_public_digest(target_date: date) -> Dict:
    model = generate_public_digest_model(target_date)
    page_id = save_public_digest_page(target_date, model)
    logger.info(f"Generated public digest page for {target_date}: page_id={page_id}")
    return model
