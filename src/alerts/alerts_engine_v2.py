import logging
import os
import json
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Tuple

from src.db.db import get_cursor, execute_query, execute_one


def safe_json_serializer(obj):
    """Custom JSON serializer for types not serializable by default json encoder."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, (set, frozenset)):
        return list(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
from src.alerts.templates import (
    format_regional_risk_spike,
    format_asset_risk_spike,
    format_high_impact_event,
    add_upgrade_hook_if_free
)
from src.alerts.channels import send_email, send_telegram, send_sms
from src.plans.plan_helpers import get_plan_settings, get_allowed_alert_types

logger = logging.getLogger(__name__)

ALERTS_V2_ENABLED = os.environ.get('ALERTS_V2_ENABLED', 'true').lower() == 'true'
ALERTS_SEND_ALLOWLIST_USER_IDS = os.environ.get('ALERTS_SEND_ALLOWLIST_USER_IDS', '').strip()
ALERTS_MAX_SEND_PER_RUN = int(os.environ.get('ALERTS_MAX_SEND_PER_RUN', '1000'))
DEFAULT_THRESHOLD = 70


def get_allowlisted_user_ids() -> Optional[set]:
    """
    Parse allowlist from environment variable.
    Returns None if no allowlist is configured (normal operation).
    Returns set of user IDs if allowlist is configured.
    """
    if not ALERTS_SEND_ALLOWLIST_USER_IDS:
        return None
    
    try:
        ids = {int(uid.strip()) for uid in ALERTS_SEND_ALLOWLIST_USER_IDS.split(',') if uid.strip()}
        if ids:
            logger.info(f"Allowlist active: restricting to user IDs {ids}")
            return ids
    except ValueError as e:
        logger.warning(f"Invalid ALERTS_SEND_ALLOWLIST_USER_IDS format: {e}")
    return None


HIGH_IMPACT_REGIONS = ['Europe', 'Middle East', 'Black Sea']
HIGH_IMPACT_CATEGORIES = ['energy', 'geopolitical']
HIGH_SEVERITY_KEYWORDS = [
    'attack', 'missile', 'explosion', 'shutdown', 'blockade', 'sanctions',
    'crisis', 'turmoil', 'halt', 'suspend', 'collapse', 'war', 'conflict',
    'seize', 'capture', 'embargo', 'invasion', 'emergency', 'critical'
]


def get_risk_summary(region: str = 'Europe') -> Dict:
    idx_query = """
    SELECT window_days, risk_score, trend
    FROM risk_indices
    WHERE LOWER(region) = LOWER(%s)
    ORDER BY calculated_at DESC
    LIMIT 2
    """
    idx_results = execute_query(idx_query, (region,))
    
    risk_7d = None
    trend_7d = None
    risk_30d = None
    
    if idx_results:
        for row in idx_results:
            if row['window_days'] == 7 and risk_7d is None:
                risk_7d = row['risk_score']
                trend_7d = row['trend']
            elif row['window_days'] == 30 and risk_30d is None:
                risk_30d = row['risk_score']
    
    asset_query = """
    SELECT DISTINCT ON (asset) asset, risk_score, direction
    FROM asset_risk
    WHERE LOWER(region) = LOWER(%s) AND window_days = 7
    ORDER BY asset, calculated_at DESC
    """
    asset_results = execute_query(asset_query, (region,))
    
    assets = {}
    if asset_results:
        for row in asset_results:
            assets[row['asset']] = {
                'risk': row['risk_score'],
                'direction': row['direction']
            }
    
    return {
        'region': region,
        'risk_7d': risk_7d or 0,
        'trend_7d': trend_7d or 'stable',
        'risk_30d': risk_30d or 0,
        'assets': assets
    }


def get_previous_risk_score(region: str) -> Optional[float]:
    query = """
    SELECT last_7d_score FROM alert_state
    WHERE LOWER(region) = LOWER(%s) AND window_days = 7
    """
    result = execute_one(query, (region,))
    return result['last_7d_score'] if result else None


def get_top_driver_events(region: str, limit: int = 3) -> List[Dict]:
    query = """
    SELECT e.id, e.title, e.region, e.category, r.weighted_score
    FROM risk_events r
    JOIN events e ON e.id = r.event_id
    WHERE r.created_at >= NOW() - INTERVAL '7 days'
    ORDER BY r.weighted_score DESC
    LIMIT %s
    """
    results = execute_query(query, (limit,))
    return results if results else []


THEMATIC_CATEGORIES = (
    'war', 'military', 'conflict', 'strike', 'supply_disruption',
    'sanctions', 'energy', 'political', 'diplomacy', 'geopolitical'
)

def get_high_impact_events_global() -> List[Dict]:
    query = """
    SELECT e.id, e.title, e.region, e.category, e.severity_score, e.ai_summary, 
           e.source_url, e.event_time, e.ai_impact_json, e.signal_quality_score
    FROM events e
    WHERE e.severity_score >= 4
      AND e.category IN %s
      AND e.region IN ('Europe', 'Middle East', 'Black Sea', 'Asia', 'North Africa', 'South America', 'Russia', 'North America', 'Global')
      AND e.inserted_at >= NOW() - INTERVAL '24 hours'
      AND NOT EXISTS (
          SELECT 1 FROM alert_events ae 
          WHERE ae.alert_type = 'HIGH_IMPACT_EVENT' 
          AND ae.driver_event_ids @> ARRAY[e.id]
          AND ae.created_at >= NOW() - INTERVAL '24 hours'
      )
    ORDER BY e.severity_score DESC, e.inserted_at DESC
    LIMIT 20
    """
    results = execute_query(query, (THEMATIC_CATEGORIES,))
    return results if results else []


def update_alert_state(region: str, risk_7d: float, risk_30d: float, assets: Dict):
    with get_cursor() as cursor:
        cursor.execute(
            """INSERT INTO alert_state (region, window_days, last_7d_score, last_30d_score, last_asset_scores, updated_at)
               VALUES (%s, 7, %s, %s, %s, NOW())
               ON CONFLICT (region, window_days) DO UPDATE SET
                   last_7d_score = EXCLUDED.last_7d_score,
                   last_30d_score = EXCLUDED.last_30d_score,
                   last_asset_scores = EXCLUDED.last_asset_scores,
                   updated_at = NOW()""",
            (region, risk_7d, risk_30d, json.dumps(assets))
        )


def create_alert_event(
    alert_type: str,
    scope_region: Optional[str],
    scope_assets: List[str],
    severity: int,
    headline: str,
    body: str,
    driver_event_ids: List[int],
    cooldown_key: str,
    event_fingerprint: Optional[str] = None,
    raw_input: Optional[Dict] = None,
    classification: Optional[Dict] = None,
    category: Optional[str] = None,
    confidence: Optional[float] = None
) -> Tuple[Optional[int], bool]:
    """
    Create a global alert event (user-agnostic).
    
    SAFETY INVARIANT: alert_events table must NEVER contain user_id.
    This function creates global events that are later fanned out to users
    via user_alert_deliveries in Phase B.
    
    Uses event_fingerprint for uniqueness (ON CONFLICT DO NOTHING).
    
    Metadata fields:
        raw_input: Original news/signal data that triggered this alert (JSONB)
        classification: AI-processed classification data (JSONB)
        category: Event category (geopolitical, energy, supply_chain, etc.)
        confidence: AI confidence score (0.0-1.0)
    
    Returns:
        Tuple of (event_id or None, was_skipped_duplicate)
    """
    if severity < 5:
        logger.debug(f"Filtered alert_event: severity {severity} < 5 for {headline[:50]}")
        return None, False

    if event_fingerprint is None:
        event_fingerprint = cooldown_key
    
    raw_input_json = json.dumps(raw_input, default=safe_json_serializer) if raw_input else None
    classification_json = json.dumps(classification, default=safe_json_serializer) if classification else None
    
    try:
        with get_cursor() as cursor:
            cursor.execute(
                """INSERT INTO alert_events 
                   (alert_type, scope_region, scope_assets, severity, headline, body, driver_event_ids, cooldown_key, event_fingerprint, raw_input, classification, category, confidence)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (event_fingerprint) DO UPDATE SET
                       raw_input = COALESCE(alert_events.raw_input, EXCLUDED.raw_input),
                       classification = COALESCE(alert_events.classification, EXCLUDED.classification),
                       category = COALESCE(alert_events.category, EXCLUDED.category),
                       confidence = COALESCE(alert_events.confidence, EXCLUDED.confidence)
                   RETURNING id""",
                (alert_type, scope_region, scope_assets, severity, headline, body, driver_event_ids, cooldown_key, event_fingerprint, raw_input_json, classification_json, category, confidence)
            )
            result = cursor.fetchone()
            if result:
                logger.info(f"Created/updated alert_event {result['id']}: {alert_type} - {headline[:50]} (category={category}, confidence={confidence})")
                return result['id'], False
            else:
                logger.debug(f"Alert event conflict without id return: {event_fingerprint}")
                return None, True
    except Exception as e:
        logger.error(f"Error creating alert event: {e}")
        return None, False


def generate_regional_risk_spike_events(regions: List[str] = None) -> Dict:
    if regions is None:
        regions = ['Europe', 'Middle East', 'Black Sea', 'Asia', 'North Africa', 'South America', 'Russia', 'North America']
    
    created_event_ids = []
    skipped_count = 0
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    
    for region in regions:
        summary = get_risk_summary(region)
        risk_7d = summary['risk_7d']
        prev_risk = get_previous_risk_score(region)
        
        spike_by_threshold = risk_7d >= DEFAULT_THRESHOLD
        spike_by_change = False
        if prev_risk and prev_risk > 0:
            change_pct = ((risk_7d - prev_risk) / prev_risk) * 100
            spike_by_change = change_pct >= 20
        
        if not (spike_by_threshold or spike_by_change):
            continue
        
        driver_events = get_top_driver_events(region, limit=3)
        driver_ids = [e['id'] for e in driver_events] if driver_events else []
        
        title, body = format_regional_risk_spike(
            region=region,
            risk_7d=risk_7d,
            prev_risk_7d=prev_risk,
            trend=summary['trend_7d'],
            driver_events=driver_events,
            assets=summary['assets']
        )
        
        cooldown_key = f"REGION:{region}:RISK_SPIKE:{today}:threshold_{int(risk_7d)}"
        fingerprint = f"REGIONAL_RISK_SPIKE:{region}:{today}"
        
        severity = 3
        if risk_7d >= 90:
            severity = 5
        elif risk_7d >= 80:
            severity = 4
        elif risk_7d >= 70:
            severity = 3
        
        raw_input_data = {
            "type": "risk_summary",
            "region": region,
            "risk_7d": risk_7d,
            "prev_risk_7d": prev_risk,
            "trend": summary['trend_7d'],
            "assets": summary['assets'],
            "driver_events": driver_events
        }
        
        classification_data = {
            "alert_type": "REGIONAL_RISK_SPIKE",
            "spike_by_threshold": spike_by_threshold,
            "spike_by_change": spike_by_change,
            "threshold_value": DEFAULT_THRESHOLD,
            "change_pct": ((risk_7d - prev_risk) / prev_risk * 100) if prev_risk and prev_risk > 0 else 0
        }
        
        confidence_score = min(1.0, risk_7d / 100) if risk_7d else 0.5
        
        event_id, was_skipped = create_alert_event(
            alert_type='REGIONAL_RISK_SPIKE',
            scope_region=region,
            scope_assets=[],
            severity=severity,
            headline=title,
            body=body,
            driver_event_ids=driver_ids,
            cooldown_key=cooldown_key,
            event_fingerprint=fingerprint,
            raw_input=raw_input_data,
            classification=classification_data,
            category="regional_risk",
            confidence=confidence_score
        )
        
        if event_id:
            created_event_ids.append(event_id)
        if was_skipped:
            skipped_count += 1
    
    return {'created': created_event_ids, 'skipped': skipped_count}


def generate_asset_risk_spike_events(regions: List[str] = None, assets: List[str] = None) -> Dict:
    if regions is None:
        regions = ['Europe', 'Middle East', 'Black Sea', 'Asia', 'North Africa', 'South America', 'Russia', 'North America']
    if assets is None:
        assets = ['oil', 'gas', 'fx', 'freight']
    
    created_event_ids = []
    skipped_count = 0
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    
    for region in regions:
        summary = get_risk_summary(region)
        
        for asset in assets:
            if asset not in summary['assets']:
                continue
            
            asset_data = summary['assets'][asset]
            risk_score = asset_data.get('risk', 0)
            direction = asset_data.get('direction', 'unclear')
            
            if risk_score < DEFAULT_THRESHOLD:
                continue
            
            driver_events = get_top_driver_events(region, limit=2)
            driver_ids = [e['id'] for e in driver_events] if driver_events else []
            
            title, body = format_asset_risk_spike(
                asset=asset,
                region=region,
                risk_score=risk_score,
                direction=direction,
                confidence=0.7,
                driver_events=driver_events
            )
            
            cooldown_key = f"ASSET:{region}:{asset}:SPIKE:{today}"
            fingerprint = f"ASSET_RISK_SPIKE:{region}:{asset}:{today}"
            
            severity = 3
            if risk_score >= 90:
                severity = 5
            elif risk_score >= 80:
                severity = 4
            
            raw_input_data = {
                "type": "asset_risk",
                "region": region,
                "asset": asset,
                "risk_score": risk_score,
                "direction": direction,
                "driver_events": driver_events
            }
            
            classification_data = {
                "alert_type": "ASSET_RISK_SPIKE",
                "threshold_value": DEFAULT_THRESHOLD,
                "direction": direction
            }
            
            confidence_score = min(1.0, risk_score / 100) if risk_score else 0.5
            
            event_id, was_skipped = create_alert_event(
                alert_type='ASSET_RISK_SPIKE',
                scope_region=region,
                scope_assets=[asset],
                severity=severity,
                headline=title,
                body=body,
                driver_event_ids=driver_ids,
                cooldown_key=cooldown_key,
                event_fingerprint=fingerprint,
                raw_input=raw_input_data,
                classification=classification_data,
                category="asset_risk",
                confidence=confidence_score
            )
            
            if event_id:
                created_event_ids.append(event_id)
            if was_skipped:
                skipped_count += 1
    
    return {'created': created_event_ids, 'skipped': skipped_count}


def generate_high_impact_event_alerts() -> Dict:
    events = get_high_impact_events_global()
    created_event_ids = []
    skipped_count = 0
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    
    for event in events:
        title, body = format_high_impact_event(event, event['region'])
        
        cooldown_key = f"EVENT:HIGH_IMPACT:{event['id']}:{today}"
        fingerprint = f"HIGH_IMPACT_EVENT:{event['id']}"
        
        raw_input_data = {
            "type": "news_event",
            "event_id": event['id'],
            "title": event.get('title'),
            "source_url": event.get('source_url'),
            "event_time": str(event.get('event_time')) if event.get('event_time') else None,
            "region": event['region'],
            "category": event.get('category')
        }
        
        ai_impact = {}
        if event.get('ai_impact_json'):
            try:
                import json as _json
                ai_impact = _json.loads(event['ai_impact_json']) if isinstance(event['ai_impact_json'], str) else event['ai_impact_json']
            except Exception:
                ai_impact = {}
        
        classification_data = {
            "alert_type": "HIGH_IMPACT_EVENT",
            "ai_summary": event.get('ai_summary'),
            "ai_impact_score": float(ai_impact.get('impact_score', 0)) if ai_impact.get('impact_score') else None,
            "ai_affected_assets": ai_impact.get('affected_assets', [])
        }
        
        event_category = event.get('category', 'geopolitical')
        sq_score = event.get('signal_quality_score')
        confidence_score = float(sq_score) / 100.0 if sq_score else 0.7
        
        event_id, was_skipped = create_alert_event(
            alert_type='HIGH_IMPACT_EVENT',
            scope_region=event['region'],
            scope_assets=[],
            severity=event['severity_score'],
            headline=title,
            body=body,
            driver_event_ids=[event['id']],
            cooldown_key=cooldown_key,
            event_fingerprint=fingerprint,
            raw_input=raw_input_data,
            classification=classification_data,
            category=event_category,
            confidence=confidence_score
        )
        
        if event_id:
            created_event_ids.append(event_id)
        if was_skipped:
            skipped_count += 1
    
    return {'created': created_event_ids, 'skipped': skipped_count}


def generate_storage_risk_events() -> Dict:
    """
    Generate alert events from EU gas storage data.
    
    Fetches current storage metrics from GIE AGSI+ API, persists snapshot,
    and creates ASSET_RISK_SPIKE alert if storage conditions warrant.
    
    Note: GIE AGSI+ data is typically for yesterday (T-1) due to reporting lag.
    Idempotency is based on the actual data date from the API response.
    """
    created_event_ids = []
    skipped_count = 0
    
    try:
        from src.ingest.gie_agsi import (
            fetch_eu_storage_data,
            fetch_historical_storage,
            compute_storage_metrics,
            generate_storage_alert
        )
    except ImportError as e:
        logger.warning(f"GIE AGSI+ module not available: {e}")
        return {'created': [], 'skipped': 0, 'error': 'module_not_available'}
    
    gie_api_key = os.environ.get('GIE_API_KEY', '')
    if not gie_api_key:
        logger.info("GIE_API_KEY not configured - skipping storage check")
        return {'created': [], 'skipped': 0, 'error': 'api_key_not_configured'}
    
    logger.info("Fetching EU gas storage data from GIE AGSI+...")
    current_data = fetch_eu_storage_data()
    if not current_data:
        logger.warning("Failed to fetch current EU storage data")
        return {'created': [], 'skipped': 0, 'error': 'fetch_failed'}
    
    data_date = current_data.get('date')
    if not data_date:
        logger.warning("No date in storage data response")
        return {'created': [], 'skipped': 0, 'error': 'no_date_in_response'}
    
    existing_check = execute_one(
        "SELECT id FROM gas_storage_snapshots WHERE date = %s",
        (data_date,)
    )
    if existing_check:
        logger.debug(f"Storage snapshot already exists for {data_date} - skipping")
        return {'created': [], 'skipped': 1, 'already_processed': True, 'data_date': data_date}
    
    historical_data = fetch_historical_storage(days=7)
    
    metrics = compute_storage_metrics(current_data, historical_data)
    logger.info(f"Storage metrics: {metrics.eu_storage_percent}% full, "
                f"deviation {metrics.deviation_from_norm:+.1f}%, "
                f"risk score {metrics.risk_score} ({metrics.risk_band})")
    
    try:
        with get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO gas_storage_snapshots 
                (date, eu_storage_percent, seasonal_norm, deviation_from_norm,
                 refill_speed_7d, withdrawal_rate_7d, winter_deviation_risk,
                 days_to_target, risk_score, risk_band, interpretation, raw_data)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (date) DO UPDATE SET
                    eu_storage_percent = EXCLUDED.eu_storage_percent,
                    seasonal_norm = EXCLUDED.seasonal_norm,
                    deviation_from_norm = EXCLUDED.deviation_from_norm,
                    refill_speed_7d = EXCLUDED.refill_speed_7d,
                    withdrawal_rate_7d = EXCLUDED.withdrawal_rate_7d,
                    winter_deviation_risk = EXCLUDED.winter_deviation_risk,
                    days_to_target = EXCLUDED.days_to_target,
                    risk_score = EXCLUDED.risk_score,
                    risk_band = EXCLUDED.risk_band,
                    interpretation = EXCLUDED.interpretation,
                    raw_data = EXCLUDED.raw_data
            """, (
                metrics.date,
                metrics.eu_storage_percent,
                metrics.seasonal_norm,
                metrics.deviation_from_norm,
                metrics.refill_speed_7d,
                metrics.withdrawal_rate_7d,
                metrics.winter_deviation_risk,
                metrics.days_to_target,
                metrics.risk_score,
                metrics.risk_band,
                metrics.interpretation,
                json.dumps(current_data, default=safe_json_serializer)
            ))
        logger.info(f"Persisted storage snapshot for {metrics.date}")
    except Exception as e:
        logger.error(f"Failed to persist storage snapshot: {e}")
    
    alert_data = generate_storage_alert(metrics)
    
    if not alert_data:
        logger.info("No storage alert warranted - conditions normal")
        return {'created': [], 'skipped': 0, 'metrics': {
            'date': metrics.date,
            'storage_percent': metrics.eu_storage_percent,
            'risk_score': metrics.risk_score,
            'risk_band': metrics.risk_band
        }}
    
    cooldown_key = f"STORAGE:ASSET_RISK:{metrics.date}"
    fingerprint = f"STORAGE_RISK:{metrics.date}"
    
    raw_input_data = {
        "type": "quantitative_data",
        "source": "GIE AGSI+",
        "data_date": metrics.date,
        "metrics": alert_data.get('raw_metrics', {})
    }
    
    classification_data = {
        "alert_type": "ASSET_RISK_SPIKE",
        "sub_type": alert_data.get('event_type', 'STORAGE_LEVEL'),
        "risk_score": metrics.risk_score,
        "risk_band": metrics.risk_band,
        "drivers": alert_data.get('drivers', [])
    }
    
    event_id, was_skipped = create_alert_event(
        alert_type='ASSET_RISK_SPIKE',
        scope_region='Europe',
        scope_assets=['gas'],
        severity=alert_data.get('severity', 3),
        headline=alert_data.get('headline', f"EU Gas Storage Alert: {metrics.eu_storage_percent}%"),
        body=alert_data.get('summary', metrics.interpretation),
        driver_event_ids=[],
        cooldown_key=cooldown_key,
        event_fingerprint=fingerprint,
        raw_input=raw_input_data,
        classification=classification_data,
        category='energy',
        confidence=alert_data.get('confidence', 0.95)
    )
    
    if event_id:
        created_event_ids.append(event_id)
        logger.info(f"Created storage alert event {event_id}: {alert_data.get('headline', '')[:50]}")
    if was_skipped:
        skipped_count += 1
    
    return {
        'created': created_event_ids,
        'skipped': skipped_count,
        'metrics': {
            'date': metrics.date,
            'storage_percent': metrics.eu_storage_percent,
            'deviation': metrics.deviation_from_norm,
            'risk_score': metrics.risk_score,
            'risk_band': metrics.risk_band
        }
    }


def generate_global_alert_events() -> Dict:
    logger.info("Phase A: Generating global alert events...")
    
    regional_result = generate_regional_risk_spike_events()
    asset_result = generate_asset_risk_spike_events()
    high_impact_result = generate_high_impact_event_alerts()
    storage_result = generate_storage_risk_events()
    
    for region in ['Europe', 'Middle East', 'Black Sea', 'Asia', 'North Africa', 'South America', 'Russia', 'North America']:
        try:
            summary = get_risk_summary(region)
            update_alert_state(region, summary['risk_7d'], summary['risk_30d'], summary['assets'])
        except Exception as e:
            logger.warning(f"Failed to update alert_state for {region}: {e}")
    
    all_created = (
        regional_result['created'] + 
        asset_result['created'] + 
        high_impact_result['created'] +
        storage_result.get('created', [])
    )
    total_skipped = (
        regional_result['skipped'] + 
        asset_result['skipped'] + 
        high_impact_result['skipped'] +
        storage_result.get('skipped', 0)
    )
    
    result = {
        'regional_risk_spikes': len(regional_result['created']),
        'asset_risk_spikes': len(asset_result['created']),
        'high_impact_events': len(high_impact_result['created']),
        'storage_alerts': len(storage_result.get('created', [])),
        'storage_metrics': storage_result.get('metrics'),
        'total': len(all_created),
        'skipped': total_skipped,
        'event_ids': all_created
    }
    
    logger.info(f"Phase A complete: {result['total']} alert events created, {total_skipped} skipped (duplicates)")
    return result


def get_eligible_users() -> List[Dict]:
    query = """
    SELECT u.id, u.email, u.telegram_chat_id, u.phone_number, 
           COALESCE(up.plan, 'free') as plan
    FROM users u
    LEFT JOIN user_plans up ON up.user_id = u.id
    WHERE u.email_verified = TRUE OR u.email_verified IS NULL
    """
    results = execute_query(query)
    return results if results else []


def get_user_regions(user_id: int) -> List[str]:
    query = """
    SELECT DISTINCT region FROM user_alert_prefs
    WHERE user_id = %s AND enabled = TRUE AND region IS NOT NULL
    """
    results = execute_query(query, (user_id,))
    if results:
        regions = [r['region'] for r in results if r.get('region')]
        if regions:
            return regions
    return ['Europe']


def get_user_enabled_alert_types(user_id: int) -> List[str]:
    query = """
    SELECT DISTINCT alert_type FROM user_alert_prefs
    WHERE user_id = %s AND enabled = TRUE AND alert_type IS NOT NULL
    """
    results = execute_query(query, (user_id,))
    if results:
        alert_types = [r['alert_type'] for r in results if r.get('alert_type')]
        if alert_types:
            return alert_types
    return ['HIGH_IMPACT_EVENT']


def get_user_enabled_assets(user_id: int) -> List[str]:
    query = """
    SELECT DISTINCT asset FROM user_alert_prefs
    WHERE user_id = %s AND enabled = TRUE AND asset IS NOT NULL
    """
    results = execute_query(query, (user_id,))
    if results:
        return [r['asset'] for r in results if r['asset']]
    return ['oil', 'gas']


def count_deliveries_today(user_id: int, channel: str) -> int:
    today_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    query = """
    SELECT COUNT(*) as cnt FROM user_alert_deliveries
    WHERE user_id = %s
      AND channel = %s
      AND created_at::date = %s
      AND status IN ('sent', 'queued')
    """
    result = execute_one(query, (user_id, channel, today_utc))
    return result['cnt'] if result else 0


def check_delivery_cooldown(user_id: int, alert_event_id: int, channel: str) -> bool:
    query = """
    SELECT 1 FROM user_alert_deliveries
    WHERE user_id = %s AND alert_event_id = %s AND channel = %s
    LIMIT 1
    """
    result = execute_one(query, (user_id, alert_event_id, channel))
    return result is not None


def create_delivery(
    user_id: int,
    alert_event_id: int,
    channel: str,
    status: str,
    reason: Optional[str] = None,
    delivery_kind: str = 'instant'
) -> Optional[int]:
    try:
        with get_cursor() as cursor:
            cursor.execute(
                """INSERT INTO user_alert_deliveries
                   (user_id, alert_event_id, channel, status, reason, delivery_kind)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (user_id, alert_event_id, channel) DO NOTHING
                   RETURNING id""",
                (user_id, alert_event_id, channel, status, reason, delivery_kind)
            )
            result = cursor.fetchone()
            return result['id'] if result else None
    except Exception as e:
        logger.error(f"Error creating delivery: {e}")
        return None


def update_delivery_status(delivery_id: int, status: str, provider_message_id: Optional[str] = None, reason: Optional[str] = None):
    with get_cursor() as cursor:
        if status == 'sent':
            cursor.execute(
                """UPDATE user_alert_deliveries 
                   SET status = %s, sent_at = NOW(), provider_message_id = %s
                   WHERE id = %s""",
                (status, provider_message_id, delivery_id)
            )
        else:
            cursor.execute(
                """UPDATE user_alert_deliveries 
                   SET status = %s, reason = %s
                   WHERE id = %s""",
                (status, reason, delivery_id)
            )


def get_unsent_alert_events(lookback_hours: int = 24) -> List[Dict]:
    """
    Get alert events that haven't been fanned out yet.
    Uses fanout_completed_at marker for idempotency.
    """
    query = """
    SELECT id, alert_type, scope_region, scope_assets, severity, headline, body, driver_event_ids, cooldown_key, created_at
    FROM alert_events
    WHERE created_at >= NOW() - make_interval(hours => %s)
      AND fanout_completed_at IS NULL
    ORDER BY created_at ASC
    """
    results = execute_query(query, (lookback_hours,))
    return results if results else []


def mark_fanout_completed(alert_event_id: int):
    """Mark an alert event as having completed fanout."""
    with get_cursor() as cursor:
        cursor.execute(
            "UPDATE alert_events SET fanout_completed_at = NOW() WHERE id = %s",
            (alert_event_id,)
        )
        logger.debug(f"Marked fanout completed for alert_event {alert_event_id}")


def fanout_alert_events_to_users() -> Dict:
    """
    Phase B: Fanout alert events to eligible users.
    
    Enforces:
    - Plan quotas (instant vs digest limits)
    - User preferences (channel enablement)
    - delivery_kind determination (instant vs digest)
    - Idempotency via unique constraint
    - User allowlist filtering (if ALERTS_SEND_ALLOWLIST_USER_IDS is set)
    
    Returns structured counts for monitoring.
    """
    from src.alerts.quota_helpers import (
        check_delivery_eligibility,
        determine_delivery_kind,
        get_user_alert_prefs,
        get_plan_quotas
    )
    
    logger.info("Phase B: Fanout alert events to eligible users...")
    
    allowlist = get_allowlisted_user_ids()
    
    alert_events = get_unsent_alert_events(lookback_hours=24)
    if not alert_events:
        logger.info("No recent alert events to fan out")
        return {
            'events_processed': 0,
            'users_considered': 0,
            'deliveries_created': 0,
            'deliveries_skipped_quota': 0,
            'deliveries_skipped_prefs': 0,
            'deliveries_skipped_missing_dest': 0,
            'allowlist_active': allowlist is not None
        }
    
    users = get_eligible_users()
    
    if allowlist:
        original_count = len(users) if users else 0
        users = [u for u in users if u['id'] in allowlist] if users else []
        logger.info(f"Allowlist filter: {original_count} -> {len(users)} users")
    
    if not users:
        logger.info("No eligible users found")
        return {
            'events_processed': len(alert_events),
            'users_considered': 0,
            'deliveries_created': 0,
            'deliveries_skipped_quota': 0,
            'deliveries_skipped_prefs': 0,
            'deliveries_skipped_missing_dest': 0
        }
    
    logger.info(f"Processing {len(alert_events)} alert events for {len(users)} users")
    
    for u in users:
        logger.info(f"Eligible user: id={u['id']}, email={u['email']}, plan={u.get('plan', 'free')}")
    
    deliveries_created = 0
    skipped_quota = 0
    skipped_prefs = 0
    skipped_missing_dest = 0
    skipped_already_exists = 0
    skipped_filter = 0
    users_considered = 0
    
    for ae in alert_events:
        alert_event_id = ae['id']
        alert_type = ae['alert_type']
        scope_region = ae['scope_region']
        scope_assets = ae['scope_assets'] or []
        
        logger.info(f"Processing alert_event {alert_event_id}: type={alert_type}, region={scope_region}")
        
        for user in users:
            user_id = user['id']
            plan = user['plan'] or 'free'
            users_considered += 1
            
            try:
                plan_settings = get_plan_settings(plan)
                allowed_types = get_allowed_alert_types(plan)
            except Exception:
                plan_settings = get_plan_settings('free')
                allowed_types = get_allowed_alert_types('free')
            
            if alert_type not in allowed_types:
                logger.info(f"User {user_id}: skipped - alert_type {alert_type} not in allowed_types {allowed_types}")
                skipped_filter += 1
                continue
            
            user_regions = get_user_regions(user_id)
            if scope_region and scope_region not in user_regions and 'global' not in user_regions:
                logger.info(f"User {user_id}: skipped - region mismatch (event={scope_region}, user={user_regions})")
                skipped_filter += 1
                continue
            
            if alert_type == 'ASSET_RISK_SPIKE' and scope_assets:
                user_assets = get_user_enabled_assets(user_id)
                if not any(a in user_assets for a in scope_assets):
                    logger.info(f"User {user_id}: skipped - asset mismatch")
                    skipped_filter += 1
                    continue
            
            user_enabled_types = get_user_enabled_alert_types(user_id)
            if alert_type not in user_enabled_types:
                logger.info(f"User {user_id}: skipped - alert_type {alert_type} not in user_enabled_types {user_enabled_types}")
                skipped_filter += 1
                continue
            
            user_prefs = get_user_alert_prefs(user_id)
            delivery_kind = determine_delivery_kind(user_prefs, plan)
            
            logger.info(f"User {user_id}: PASSED all filters for alert_event {alert_event_id}")
            
            account_id = create_delivery(user_id, alert_event_id, 'account', 'sent', delivery_kind=delivery_kind)
            if account_id:
                logger.info(f"User {user_id}: created account delivery {account_id}")
                deliveries_created += 1
            
            for channel in ['email', 'telegram', 'sms']:
                eligibility = check_delivery_eligibility(
                    user_id=user_id,
                    user=user,
                    channel=channel,
                    plan=plan,
                    alert_event_id=alert_event_id
                )
                
                if not eligibility.eligible:
                    logger.info(f"User {user_id}: {channel} not eligible - {eligibility.skip_reason}")
                    if eligibility.skip_reason == 'missing_destination':
                        skipped_missing_dest += 1
                    elif eligibility.skip_reason == 'already_exists':
                        skipped_already_exists += 1
                    elif eligibility.skip_reason in ('channel_disabled_by_user', 'sms_not_in_plan'):
                        skipped_prefs += 1
                    elif eligibility.skip_reason in ('quota_exceeded', 'plan_digest_only', 'channel_not_allowed'):
                        skipped_quota += 1
                    continue
                
                d_id = create_delivery(
                    user_id, alert_event_id, channel, 'queued',
                    delivery_kind=eligibility.delivery_kind
                )
                if d_id:
                    logger.info(f"User {user_id}: created {channel} delivery {d_id} (kind={eligibility.delivery_kind})")
                    deliveries_created += 1
                else:
                    logger.info(f"User {user_id}: failed to create {channel} delivery (already exists?)")
        
        mark_fanout_completed(alert_event_id)
    
    result = {
        'events_processed': len(alert_events),
        'users_considered': users_considered,
        'deliveries_created': deliveries_created,
        'deliveries_skipped_quota': skipped_quota,
        'deliveries_skipped_prefs': skipped_prefs,
        'deliveries_skipped_missing_dest': skipped_missing_dest,
        'deliveries_skipped_already_exists': skipped_already_exists,
        'deliveries_skipped_filter': skipped_filter,
        'allowlist_active': allowlist is not None
    }
    
    logger.info(f"Phase B complete: {deliveries_created} created, skipped: quota={skipped_quota}, prefs={skipped_prefs}, missing={skipped_missing_dest}, exists={skipped_already_exists}, filter={skipped_filter}")
    return result


def send_queued_deliveries(batch_size: int = 100, max_per_run: int = None) -> Dict:
    """
    Phase C: Send queued deliveries with retry logic and channel safeguards.
    
    IMPORTANT: Only processes instant deliveries (delivery_kind='instant').
    Digest deliveries are handled by send_queued_digests().
    
    Features:
    - FOR UPDATE SKIP LOCKED to prevent concurrent sends
    - Exponential backoff with jitter for retries
    - Failure classification (transient vs permanent)
    - Channel config validation (skip if not configured)
    - Max attempts enforcement
    - Continues processing after individual failures
    - User allowlist filtering (if ALERTS_SEND_ALLOWLIST_USER_IDS is set)
    - Max per run circuit breaker (ALERTS_MAX_SEND_PER_RUN)
    
    Returns structured counts for monitoring.
    """
    from src.alerts.channel_adapters import (
        send_email_v2, send_telegram_v2, send_sms_v2,
        classify_failure, compute_next_retry_delay, should_retry,
        FailureType, ALERTS_MAX_ATTEMPTS
    )
    from datetime import timedelta
    
    if max_per_run is None:
        max_per_run = ALERTS_MAX_SEND_PER_RUN
    
    allowlist = get_allowlisted_user_ids()
    
    logger.info(f"Phase C: Sending queued deliveries (batch_size={batch_size}, max_per_run={max_per_run})...")
    
    counts = {
        'queued_selected': 0,
        'sent': 0,
        'failed': 0,
        'retried': 0,
        'skipped_not_configured': 0,
        'skipped_missing_destination': 0,
        'stopped_early': False,
        'allowlist_active': allowlist is not None
    }
    
    allowlist_clause = ""
    params = [batch_size]
    if allowlist:
        allowlist_clause = "AND d.user_id = ANY(%s)"
        params = [list(allowlist), batch_size]
    
    with get_cursor() as cursor:
        query = f"""
            SELECT d.id, d.user_id, d.alert_event_id, d.channel, d.attempts,
                   ae.headline, ae.body, ae.alert_type,
                   u.email, u.telegram_chat_id, u.phone_number,
                   COALESCE(up.plan, 'free') as plan
            FROM user_alert_deliveries d
            JOIN alert_events ae ON ae.id = d.alert_event_id
            JOIN users u ON u.id = d.user_id
            LEFT JOIN user_plans up ON up.user_id = u.id
            WHERE d.status = 'queued'
              AND d.delivery_kind = 'instant'
              AND (d.next_retry_at IS NULL OR d.next_retry_at <= NOW())
              {allowlist_clause}
            ORDER BY d.created_at ASC
            LIMIT %s
            FOR UPDATE OF d SKIP LOCKED
        """
        if allowlist:
            cursor.execute(query, (list(allowlist), batch_size))
        else:
            cursor.execute(query, (batch_size,))
        deliveries = cursor.fetchall()
        
        if not deliveries:
            logger.info("No queued deliveries to send (all locked or none available)")
            return counts
        
        counts['queued_selected'] = len(deliveries)
        logger.info(f"Acquired lock on {len(deliveries)} deliveries for sending")
        
        delivery_ids = [d['id'] for d in deliveries]
        cursor.execute(
            """
            UPDATE user_alert_deliveries 
            SET status = 'sending', attempts = COALESCE(attempts, 0) + 1
            WHERE id = ANY(%s)
            """,
            (delivery_ids,)
        )
    
    total_sent_this_run = 0
    
    for d in deliveries:
        if total_sent_this_run >= max_per_run:
            logger.warning(f"Max per run limit reached ({max_per_run}), stopping early")
            counts['stopped_early'] = True
            break
        
        delivery_id = d['id']
        channel = d['channel']
        headline = d['headline']
        body = d['body']
        plan = d['plan']
        attempts = (d['attempts'] or 0) + 1
        
        if plan == 'free':
            body = add_upgrade_hook_if_free(body, plan)
        
        try:
            if channel == 'email':
                result = send_email_v2(d['email'], headline, body, delivery_id)
            elif channel == 'telegram':
                result = send_telegram_v2(d['telegram_chat_id'], body, delivery_id)
            elif channel == 'sms':
                sms_message = f"{headline}\n{body[:500]}"
                result = send_sms_v2(d['phone_number'], sms_message, delivery_id)
            elif channel == 'account':
                _mark_delivery_sent(delivery_id, None)
                counts['sent'] += 1
                total_sent_this_run += 1
                continue
            else:
                logger.warning(f"Unknown channel '{channel}' for delivery {delivery_id}")
                _mark_delivery_skipped(delivery_id, f"unknown_channel:{channel}")
                continue
            
            if result.success:
                _mark_delivery_sent(delivery_id, result.message_id)
                counts['sent'] += 1
                total_sent_this_run += 1
            
            elif result.should_skip:
                if result.skip_reason == 'channel_not_configured':
                    counts['skipped_not_configured'] += 1
                elif result.skip_reason in ('missing_destination', 'invalid_destination'):
                    counts['skipped_missing_destination'] += 1
                _mark_delivery_skipped(delivery_id, result.skip_reason or result.error)
            
            else:
                failure_type = result.failure_type or FailureType.TRANSIENT
                
                if should_retry(attempts, failure_type):
                    delay = compute_next_retry_delay(attempts)
                    _mark_delivery_retry(delivery_id, result.error, delay)
                    counts['retried'] += 1
                    logger.info(f"Delivery {delivery_id} scheduled for retry in {delay}s (attempt {attempts})")
                else:
                    _mark_delivery_failed(delivery_id, result.error, permanent=True)
                    counts['failed'] += 1
                    if failure_type == FailureType.PERMANENT:
                        logger.warning(f"Delivery {delivery_id} failed permanently: {result.error}")
                    else:
                        logger.warning(f"Delivery {delivery_id} failed after max attempts ({ALERTS_MAX_ATTEMPTS})")
        
        except Exception as e:
            logger.error(f"Unexpected error sending delivery {delivery_id}: {e}")
            failure_type = classify_failure(str(e))
            
            if should_retry(attempts, failure_type):
                delay = compute_next_retry_delay(attempts)
                _mark_delivery_retry(delivery_id, str(e), delay)
                counts['retried'] += 1
            else:
                _mark_delivery_failed(delivery_id, str(e), permanent=True)
                counts['failed'] += 1
    
    logger.info(f"Phase C complete: sent={counts['sent']}, failed={counts['failed']}, "
                f"retried={counts['retried']}, skipped_config={counts['skipped_not_configured']}, "
                f"skipped_dest={counts['skipped_missing_destination']}")
    return counts


def _mark_delivery_sent(delivery_id: int, message_id: Optional[str]):
    """Mark a delivery as successfully sent."""
    with get_cursor() as cursor:
        cursor.execute(
            """
            UPDATE user_alert_deliveries 
            SET status = 'sent', sent_at = NOW(), provider_message_id = %s, last_error = NULL
            WHERE id = %s
            """,
            (message_id, delivery_id)
        )


def _mark_delivery_failed(delivery_id: int, error: str, permanent: bool = False):
    """Mark a delivery as failed (permanently)."""
    with get_cursor() as cursor:
        cursor.execute(
            """
            UPDATE user_alert_deliveries 
            SET status = 'failed', last_error = %s
            WHERE id = %s
            """,
            (error, delivery_id)
        )


def _mark_delivery_retry(delivery_id: int, error: str, delay_seconds: int):
    """Mark a delivery for retry with backoff delay."""
    with get_cursor() as cursor:
        cursor.execute(
            """
            UPDATE user_alert_deliveries 
            SET status = 'queued', 
                last_error = %s, 
                next_retry_at = NOW() + make_interval(secs => %s)
            WHERE id = %s
            """,
            (error, delay_seconds, delivery_id)
        )


def _mark_delivery_skipped(delivery_id: int, reason: str):
    """Mark a delivery as skipped (terminal, no retry)."""
    with get_cursor() as cursor:
        cursor.execute(
            """
            UPDATE user_alert_deliveries 
            SET status = 'skipped', last_error = %s
            WHERE id = %s
            """,
            (reason, delivery_id)
        )


def send_queued_digests(batch_size: int = 50, max_per_run: int = None) -> Dict:
    """
    Phase C (part 2): Send queued digests with retry logic and channel safeguards.
    
    Features:
    - FOR UPDATE SKIP LOCKED to prevent concurrent digest sends
    - Exponential backoff with jitter for retries
    - Channel config validation (skip if not configured)
    - Max attempts enforcement
    - Aggregates multiple events into single message
    - User allowlist filtering (if ALERTS_SEND_ALLOWLIST_USER_IDS is set)
    - Max per run circuit breaker (ALERTS_MAX_SEND_PER_RUN)
    
    Returns structured counts for monitoring.
    """
    from src.alerts.channel_adapters import (
        send_email_v2, send_telegram_v2,
        classify_failure, compute_next_retry_delay, should_retry,
        FailureType, ALERTS_MAX_ATTEMPTS
    )
    from src.alerts.digest_builder import (
        get_digest_events, format_email_digest, format_telegram_digest
    )
    
    if max_per_run is None:
        max_per_run = ALERTS_MAX_SEND_PER_RUN
    
    allowlist = get_allowlisted_user_ids()
    
    logger.info(f"Phase C (Digests): Sending queued digests (batch_size={batch_size}, max_per_run={max_per_run})...")
    
    counts = {
        'digests_selected': 0,
        'digests_sent': 0,
        'digests_failed': 0,
        'digests_retried': 0,
        'digests_skipped_empty': 0,
        'digests_skipped_not_configured': 0,
        'digests_skipped_missing_destination': 0,
        'stopped_early': False,
        'allowlist_active': allowlist is not None
    }
    
    allowlist_clause = ""
    if allowlist:
        allowlist_clause = "AND d.user_id = ANY(%s)"
    
    with get_cursor() as cursor:
        query = f"""
            SELECT d.id, d.user_id, d.channel, d.period, d.window_start, d.window_end,
                   d.attempts, d.digest_key,
                   u.email, u.telegram_chat_id
            FROM user_alert_digests d
            JOIN users u ON u.id = d.user_id
            WHERE d.status = 'queued'
              AND (d.next_retry_at IS NULL OR d.next_retry_at <= NOW())
              {allowlist_clause}
            ORDER BY d.created_at ASC
            LIMIT %s
            FOR UPDATE OF d SKIP LOCKED
        """
        if allowlist:
            cursor.execute(query, (list(allowlist), batch_size))
        else:
            cursor.execute(query, (batch_size,))
        digests = cursor.fetchall()
        
        if not digests:
            logger.info("No queued digests to send")
            return counts
        
        counts['digests_selected'] = len(digests)
        logger.info(f"Acquired lock on {len(digests)} digests for sending")
        
        digest_ids = [d['id'] for d in digests]
        cursor.execute(
            """
            UPDATE user_alert_digests 
            SET status = 'sending', attempts = COALESCE(attempts, 0) + 1
            WHERE id = ANY(%s)
            """,
            (digest_ids,)
        )
    
    total_sent_this_run = 0
    
    for d in digests:
        if total_sent_this_run >= max_per_run:
            logger.warning(f"Max per run limit reached ({max_per_run}), stopping early")
            counts['stopped_early'] = True
            break
        
        digest_id = d['id']
        channel = d['channel']
        window_start = d['window_start']
        window_end = d['window_end']
        attempts = (d['attempts'] or 0) + 1
        
        events = get_digest_events(digest_id)
        
        if not events:
            logger.info(f"Digest {digest_id} has no events, marking as skipped")
            _mark_digest_skipped(digest_id, "no_events")
            counts['digests_skipped_empty'] += 1
            continue
        
        try:
            if channel == 'email':
                if not d['email']:
                    _mark_digest_skipped(digest_id, "missing_destination")
                    counts['digests_skipped_missing_destination'] += 1
                    continue
                
                subject, body = format_email_digest(events, window_start, window_end)
                result = send_email_v2(d['email'], subject, body, f"digest_{digest_id}")
            
            elif channel == 'telegram':
                if not d['telegram_chat_id']:
                    _mark_digest_skipped(digest_id, "missing_destination")
                    counts['digests_skipped_missing_destination'] += 1
                    continue
                
                body = format_telegram_digest(events, window_start, window_end)
                result = send_telegram_v2(d['telegram_chat_id'], body, f"digest_{digest_id}")
            
            else:
                logger.warning(f"Unsupported digest channel '{channel}' for digest {digest_id}")
                _mark_digest_skipped(digest_id, f"unsupported_channel:{channel}")
                continue
            
            if result.success:
                _mark_digest_sent(digest_id, result.message_id)
                counts['digests_sent'] += 1
                total_sent_this_run += 1
            
            elif result.should_skip:
                if result.skip_reason == 'channel_not_configured':
                    counts['digests_skipped_not_configured'] += 1
                elif result.skip_reason in ('missing_destination', 'invalid_destination'):
                    counts['digests_skipped_missing_destination'] += 1
                _mark_digest_skipped(digest_id, result.skip_reason or result.error)
            
            else:
                failure_type = result.failure_type or FailureType.TRANSIENT
                
                if should_retry(attempts, failure_type):
                    delay = compute_next_retry_delay(attempts)
                    _mark_digest_retry(digest_id, result.error, delay)
                    counts['digests_retried'] += 1
                    logger.info(f"Digest {digest_id} scheduled for retry in {delay}s (attempt {attempts})")
                else:
                    _mark_digest_failed(digest_id, result.error)
                    counts['digests_failed'] += 1
        
        except Exception as e:
            logger.error(f"Unexpected error sending digest {digest_id}: {e}")
            failure_type = classify_failure(str(e))
            
            if should_retry(attempts, failure_type):
                delay = compute_next_retry_delay(attempts)
                _mark_digest_retry(digest_id, str(e), delay)
                counts['digests_retried'] += 1
            else:
                _mark_digest_failed(digest_id, str(e))
                counts['digests_failed'] += 1
    
    logger.info(f"Phase C (Digests) complete: sent={counts['digests_sent']}, "
                f"failed={counts['digests_failed']}, retried={counts['digests_retried']}, "
                f"empty={counts['digests_skipped_empty']}")
    return counts


def _mark_digest_sent(digest_id: int, message_id: Optional[str]):
    """Mark a digest as successfully sent, clearing retry metadata."""
    with get_cursor() as cursor:
        cursor.execute(
            """
            UPDATE user_alert_digests 
            SET status = 'sent', sent_at = NOW(), last_error = NULL, next_retry_at = NULL
            WHERE id = %s
            """,
            (digest_id,)
        )


def _mark_digest_failed(digest_id: int, error: str):
    """Mark a digest as failed (permanently), clearing retry metadata."""
    with get_cursor() as cursor:
        cursor.execute(
            """
            UPDATE user_alert_digests 
            SET status = 'failed', last_error = %s, next_retry_at = NULL
            WHERE id = %s
            """,
            (error, digest_id)
        )


def _mark_digest_retry(digest_id: int, error: str, delay_seconds: int):
    """Mark a digest for retry with backoff delay."""
    with get_cursor() as cursor:
        cursor.execute(
            """
            UPDATE user_alert_digests 
            SET status = 'queued', 
                last_error = %s, 
                next_retry_at = NOW() + make_interval(secs => %s)
            WHERE id = %s
            """,
            (error, delay_seconds, digest_id)
        )


def _mark_digest_skipped(digest_id: int, reason: str):
    """Mark a digest as skipped (terminal, no retry)."""
    with get_cursor() as cursor:
        cursor.execute(
            """
            UPDATE user_alert_digests 
            SET status = 'skipped', last_error = %s
            WHERE id = %s
            """,
            (reason, digest_id)
        )


def run_alerts_engine_v2(dry_run: bool = False) -> Dict:
    logger.info("=" * 60)
    logger.info("Starting EnergyRiskIQ Alerts Engine v2 (Global + Fanout)")
    logger.info(f"ALERTS_V2_ENABLED: {ALERTS_V2_ENABLED}")
    logger.info(f"Dry run: {dry_run}")
    logger.info("=" * 60)
    
    if dry_run:
        logger.info("Dry run mode - no database changes")
        return {'dry_run': True, 'phase_a': {}, 'phase_b': {}, 'phase_c': {}, 'phase_d': {}}
    
    phase_a_result = generate_global_alert_events()
    
    phase_b_result = fanout_alert_events_to_users()
    
    from src.alerts.digest_builder import build_digests
    phase_d_result = build_digests()
    
    phase_c_result = send_queued_deliveries()
    
    instant_sent = phase_c_result.get('sent', 0)
    remaining_quota = max(0, ALERTS_MAX_SEND_PER_RUN - instant_sent)
    
    if remaining_quota > 0 and not phase_c_result.get('stopped_early', False):
        digest_result = send_queued_digests(max_per_run=remaining_quota)
    else:
        digest_result = {
            'digests_selected': 0,
            'digests_sent': 0,
            'digests_skipped_quota_reached': phase_c_result.get('stopped_early', False)
        }
    phase_c_result['digests'] = digest_result
    
    result = {
        'phase_a': phase_a_result,
        'phase_b': phase_b_result,
        'phase_d': phase_d_result,
        'phase_c': phase_c_result,
        'total_events_created': phase_a_result.get('total', 0),
        'total_deliveries': phase_b_result.get('deliveries_created', 0),
        'total_sent': phase_c_result.get('sent', 0) + digest_result.get('digests_sent', 0)
    }
    
    logger.info("=" * 60)
    logger.info("Alerts Engine v2 Complete")
    logger.info(f"Events created: {result['total_events_created']}")
    logger.info(f"Deliveries created: {result['total_deliveries']}")
    logger.info(f"Messages sent: {result['total_sent']}")
    logger.info("=" * 60)
    
    return result


if __name__ == "__main__":
    from src.db.migrations import run_migrations
    run_migrations()
    run_alerts_engine_v2()
