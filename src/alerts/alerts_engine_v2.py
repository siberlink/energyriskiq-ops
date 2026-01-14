import logging
import os
import json
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Tuple

from src.db.db import get_cursor, execute_query, execute_one
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
DEFAULT_THRESHOLD = 70
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


def get_high_impact_events_global() -> List[Dict]:
    query = """
    SELECT e.id, e.title, e.region, e.category, e.severity_score, e.ai_summary, e.source_url
    FROM events e
    WHERE e.severity_score >= 4
      AND e.category IN ('energy', 'geopolitical')
      AND e.region IN ('Europe', 'Middle East', 'Black Sea')
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
    results = execute_query(query)
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
    event_fingerprint: Optional[str] = None
) -> Tuple[Optional[int], bool]:
    """
    Create a global alert event (user-agnostic).
    
    SAFETY INVARIANT: alert_events table must NEVER contain user_id.
    This function creates global events that are later fanned out to users
    via user_alert_deliveries in Phase B.
    
    Uses event_fingerprint for uniqueness (ON CONFLICT DO NOTHING).
    
    Returns:
        Tuple of (event_id or None, was_skipped_duplicate)
    """
    if event_fingerprint is None:
        event_fingerprint = cooldown_key
    
    try:
        with get_cursor() as cursor:
            cursor.execute(
                """INSERT INTO alert_events 
                   (alert_type, scope_region, scope_assets, severity, headline, body, driver_event_ids, cooldown_key, event_fingerprint)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (event_fingerprint) DO NOTHING
                   RETURNING id""",
                (alert_type, scope_region, scope_assets, severity, headline, body, driver_event_ids, cooldown_key, event_fingerprint)
            )
            result = cursor.fetchone()
            if result:
                logger.info(f"Created alert_event {result['id']}: {alert_type} - {headline[:50]}")
                return result['id'], False
            else:
                logger.debug(f"Alert event already exists (fingerprint): {event_fingerprint}")
                return None, True
    except Exception as e:
        logger.error(f"Error creating alert event: {e}")
        return None, False


def generate_regional_risk_spike_events(regions: List[str] = None) -> Dict:
    if regions is None:
        regions = ['Europe', 'Middle East', 'Black Sea']
    
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
        
        event_id, was_skipped = create_alert_event(
            alert_type='REGIONAL_RISK_SPIKE',
            scope_region=region,
            scope_assets=[],
            severity=severity,
            headline=title,
            body=body,
            driver_event_ids=driver_ids,
            cooldown_key=cooldown_key,
            event_fingerprint=fingerprint
        )
        
        if event_id:
            created_event_ids.append(event_id)
        if was_skipped:
            skipped_count += 1
    
    return {'created': created_event_ids, 'skipped': skipped_count}


def generate_asset_risk_spike_events(regions: List[str] = None, assets: List[str] = None) -> Dict:
    if regions is None:
        regions = ['Europe', 'Middle East', 'Black Sea']
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
            
            event_id, was_skipped = create_alert_event(
                alert_type='ASSET_RISK_SPIKE',
                scope_region=region,
                scope_assets=[asset],
                severity=severity,
                headline=title,
                body=body,
                driver_event_ids=driver_ids,
                cooldown_key=cooldown_key,
                event_fingerprint=fingerprint
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
        
        event_id, was_skipped = create_alert_event(
            alert_type='HIGH_IMPACT_EVENT',
            scope_region=event['region'],
            scope_assets=[],
            severity=event['severity_score'],
            headline=title,
            body=body,
            driver_event_ids=[event['id']],
            cooldown_key=cooldown_key,
            event_fingerprint=fingerprint
        )
        
        if event_id:
            created_event_ids.append(event_id)
        if was_skipped:
            skipped_count += 1
    
    return {'created': created_event_ids, 'skipped': skipped_count}


def generate_global_alert_events() -> Dict:
    logger.info("Phase A: Generating global alert events...")
    
    regional_result = generate_regional_risk_spike_events()
    asset_result = generate_asset_risk_spike_events()
    high_impact_result = generate_high_impact_event_alerts()
    
    summary = get_risk_summary('Europe')
    update_alert_state('Europe', summary['risk_7d'], summary['risk_30d'], summary['assets'])
    
    all_created = (
        regional_result['created'] + 
        asset_result['created'] + 
        high_impact_result['created']
    )
    total_skipped = (
        regional_result['skipped'] + 
        asset_result['skipped'] + 
        high_impact_result['skipped']
    )
    
    result = {
        'regional_risk_spikes': len(regional_result['created']),
        'asset_risk_spikes': len(asset_result['created']),
        'high_impact_events': len(high_impact_result['created']),
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
    WHERE user_id = %s AND enabled = TRUE
    """
    results = execute_query(query, (user_id,))
    if results:
        return [r['region'] for r in results]
    return ['Europe']


def get_user_enabled_alert_types(user_id: int) -> List[str]:
    query = """
    SELECT DISTINCT alert_type FROM user_alert_prefs
    WHERE user_id = %s AND enabled = TRUE
    """
    results = execute_query(query, (user_id,))
    if results:
        return [r['alert_type'] for r in results]
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
    
    Returns structured counts for monitoring.
    """
    from src.alerts.quota_helpers import (
        check_delivery_eligibility,
        determine_delivery_kind,
        get_user_alert_prefs,
        get_plan_quotas
    )
    
    logger.info("Phase B: Fanout alert events to eligible users...")
    
    alert_events = get_unsent_alert_events(lookback_hours=24)
    if not alert_events:
        logger.info("No recent alert events to fan out")
        return {
            'events_processed': 0,
            'users_considered': 0,
            'deliveries_created': 0,
            'deliveries_skipped_quota': 0,
            'deliveries_skipped_prefs': 0,
            'deliveries_skipped_missing_dest': 0
        }
    
    users = get_eligible_users()
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
    
    deliveries_created = 0
    skipped_quota = 0
    skipped_prefs = 0
    skipped_missing_dest = 0
    users_considered = 0
    
    for ae in alert_events:
        alert_event_id = ae['id']
        alert_type = ae['alert_type']
        scope_region = ae['scope_region']
        scope_assets = ae['scope_assets'] or []
        
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
                continue
            
            user_regions = get_user_regions(user_id)
            if scope_region and scope_region not in user_regions and 'global' not in user_regions:
                continue
            
            if alert_type == 'ASSET_RISK_SPIKE' and scope_assets:
                user_assets = get_user_enabled_assets(user_id)
                if not any(a in user_assets for a in scope_assets):
                    continue
            
            user_enabled_types = get_user_enabled_alert_types(user_id)
            if alert_type not in user_enabled_types:
                continue
            
            user_prefs = get_user_alert_prefs(user_id)
            delivery_kind = determine_delivery_kind(user_prefs, plan)
            
            account_id = create_delivery(user_id, alert_event_id, 'account', 'sent', delivery_kind=delivery_kind)
            if account_id:
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
                    if eligibility.skip_reason == 'missing_destination':
                        skipped_missing_dest += 1
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
                    deliveries_created += 1
        
        mark_fanout_completed(alert_event_id)
    
    result = {
        'events_processed': len(alert_events),
        'users_considered': users_considered,
        'deliveries_created': deliveries_created,
        'deliveries_skipped_quota': skipped_quota,
        'deliveries_skipped_prefs': skipped_prefs,
        'deliveries_skipped_missing_dest': skipped_missing_dest
    }
    
    logger.info(f"Phase B complete: {deliveries_created} created, skipped: quota={skipped_quota}, prefs={skipped_prefs}, missing={skipped_missing_dest}")
    return result


def send_queued_deliveries(batch_size: int = 100) -> Dict:
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
    
    Returns structured counts for monitoring.
    """
    from src.alerts.channel_adapters import (
        send_email_v2, send_telegram_v2, send_sms_v2,
        classify_failure, compute_next_retry_delay, should_retry,
        FailureType, ALERTS_MAX_ATTEMPTS
    )
    from datetime import timedelta
    
    logger.info(f"Phase C: Sending queued deliveries (batch_size={batch_size})...")
    
    counts = {
        'queued_selected': 0,
        'sent': 0,
        'failed': 0,
        'retried': 0,
        'skipped_not_configured': 0,
        'skipped_missing_destination': 0
    }
    
    with get_cursor() as cursor:
        cursor.execute(
            """
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
            ORDER BY d.created_at ASC
            LIMIT %s
            FOR UPDATE OF d SKIP LOCKED
            """,
            (batch_size,)
        )
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
    
    for d in deliveries:
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
                continue
            else:
                logger.warning(f"Unknown channel '{channel}' for delivery {delivery_id}")
                _mark_delivery_skipped(delivery_id, f"unknown_channel:{channel}")
                continue
            
            if result.success:
                _mark_delivery_sent(delivery_id, result.message_id)
                counts['sent'] += 1
            
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


def send_queued_digests(batch_size: int = 50) -> Dict:
    """
    Phase C (part 2): Send queued digests with retry logic and channel safeguards.
    
    Features:
    - FOR UPDATE SKIP LOCKED to prevent concurrent digest sends
    - Exponential backoff with jitter for retries
    - Channel config validation (skip if not configured)
    - Max attempts enforcement
    - Aggregates multiple events into single message
    
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
    
    logger.info(f"Phase C (Digests): Sending queued digests (batch_size={batch_size})...")
    
    counts = {
        'digests_selected': 0,
        'digests_sent': 0,
        'digests_failed': 0,
        'digests_retried': 0,
        'digests_skipped_empty': 0,
        'digests_skipped_not_configured': 0,
        'digests_skipped_missing_destination': 0
    }
    
    with get_cursor() as cursor:
        cursor.execute(
            """
            SELECT d.id, d.user_id, d.channel, d.period, d.window_start, d.window_end,
                   d.attempts, d.digest_key,
                   u.email, u.telegram_chat_id
            FROM user_alert_digests d
            JOIN users u ON u.id = d.user_id
            WHERE d.status = 'queued'
              AND (d.next_retry_at IS NULL OR d.next_retry_at <= NOW())
            ORDER BY d.created_at ASC
            LIMIT %s
            FOR UPDATE OF d SKIP LOCKED
            """,
            (batch_size,)
        )
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
    
    for d in digests:
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
    digest_result = send_queued_digests()
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
