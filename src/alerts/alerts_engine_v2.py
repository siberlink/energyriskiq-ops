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
    cooldown_key: str
) -> Optional[int]:
    try:
        with get_cursor() as cursor:
            cursor.execute(
                """INSERT INTO alert_events 
                   (alert_type, scope_region, scope_assets, severity, headline, body, driver_event_ids, cooldown_key)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (cooldown_key) DO NOTHING
                   RETURNING id""",
                (alert_type, scope_region, scope_assets, severity, headline, body, driver_event_ids, cooldown_key)
            )
            result = cursor.fetchone()
            if result:
                logger.info(f"Created alert_event {result['id']}: {alert_type} - {headline[:50]}")
                return result['id']
            else:
                logger.debug(f"Alert event already exists: {cooldown_key}")
                return None
    except Exception as e:
        logger.error(f"Error creating alert event: {e}")
        return None


def generate_regional_risk_spike_events(regions: List[str] = None) -> List[int]:
    if regions is None:
        regions = ['Europe', 'Middle East', 'Black Sea']
    
    created_event_ids = []
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
        
        severity = 3
        if risk_7d >= 90:
            severity = 5
        elif risk_7d >= 80:
            severity = 4
        elif risk_7d >= 70:
            severity = 3
        
        event_id = create_alert_event(
            alert_type='REGIONAL_RISK_SPIKE',
            scope_region=region,
            scope_assets=[],
            severity=severity,
            headline=title,
            body=body,
            driver_event_ids=driver_ids,
            cooldown_key=cooldown_key
        )
        
        if event_id:
            created_event_ids.append(event_id)
    
    return created_event_ids


def generate_asset_risk_spike_events(regions: List[str] = None, assets: List[str] = None) -> List[int]:
    if regions is None:
        regions = ['Europe', 'Middle East', 'Black Sea']
    if assets is None:
        assets = ['oil', 'gas', 'fx', 'freight']
    
    created_event_ids = []
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
            
            severity = 3
            if risk_score >= 90:
                severity = 5
            elif risk_score >= 80:
                severity = 4
            
            event_id = create_alert_event(
                alert_type='ASSET_RISK_SPIKE',
                scope_region=region,
                scope_assets=[asset],
                severity=severity,
                headline=title,
                body=body,
                driver_event_ids=driver_ids,
                cooldown_key=cooldown_key
            )
            
            if event_id:
                created_event_ids.append(event_id)
    
    return created_event_ids


def generate_high_impact_event_alerts() -> List[int]:
    events = get_high_impact_events_global()
    created_event_ids = []
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    
    for event in events:
        title, body = format_high_impact_event(event, event['region'])
        
        cooldown_key = f"EVENT:HIGH_IMPACT:{event['id']}:{today}"
        
        event_id = create_alert_event(
            alert_type='HIGH_IMPACT_EVENT',
            scope_region=event['region'],
            scope_assets=[],
            severity=event['severity_score'],
            headline=title,
            body=body,
            driver_event_ids=[event['id']],
            cooldown_key=cooldown_key
        )
        
        if event_id:
            created_event_ids.append(event_id)
    
    return created_event_ids


def generate_global_alert_events() -> Dict:
    logger.info("Phase A: Generating global alert events...")
    
    regional_ids = generate_regional_risk_spike_events()
    asset_ids = generate_asset_risk_spike_events()
    high_impact_ids = generate_high_impact_event_alerts()
    
    summary = get_risk_summary('Europe')
    update_alert_state('Europe', summary['risk_7d'], summary['risk_30d'], summary['assets'])
    
    result = {
        'regional_risk_spikes': len(regional_ids),
        'asset_risk_spikes': len(asset_ids),
        'high_impact_events': len(high_impact_ids),
        'total': len(regional_ids) + len(asset_ids) + len(high_impact_ids),
        'event_ids': regional_ids + asset_ids + high_impact_ids
    }
    
    logger.info(f"Phase A complete: {result['total']} alert events created")
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
    reason: Optional[str] = None
) -> Optional[int]:
    try:
        with get_cursor() as cursor:
            cursor.execute(
                """INSERT INTO user_alert_deliveries
                   (user_id, alert_event_id, channel, status, reason)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (user_id, alert_event_id, channel) DO NOTHING
                   RETURNING id""",
                (user_id, alert_event_id, channel, status, reason)
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
    query = """
    SELECT id, alert_type, scope_region, scope_assets, severity, headline, body, driver_event_ids, cooldown_key, created_at
    FROM alert_events
    WHERE created_at >= NOW() - make_interval(hours => %s)
    ORDER BY created_at DESC
    """
    results = execute_query(query, (lookback_hours,))
    return results if results else []


def fanout_alert_events_to_users() -> Dict:
    logger.info("Phase B: Fanout alert events to eligible users...")
    
    alert_events = get_unsent_alert_events(lookback_hours=24)
    if not alert_events:
        logger.info("No recent alert events to fan out")
        return {'processed': 0, 'deliveries_created': 0}
    
    users = get_eligible_users()
    if not users:
        logger.info("No eligible users found")
        return {'processed': len(alert_events), 'deliveries_created': 0}
    
    logger.info(f"Processing {len(alert_events)} alert events for {len(users)} users")
    
    deliveries_created = 0
    skipped = 0
    
    for ae in alert_events:
        alert_event_id = ae['id']
        alert_type = ae['alert_type']
        scope_region = ae['scope_region']
        scope_assets = ae['scope_assets'] or []
        
        for user in users:
            user_id = user['id']
            plan = user['plan'] or 'free'
            
            try:
                plan_settings = get_plan_settings(plan)
                allowed_types = get_allowed_alert_types(plan)
                delivery_config = plan_settings.get('delivery_config', {})
                max_email = plan_settings.get('max_email_alerts_per_day', 2)
            except Exception:
                plan_settings = get_plan_settings('free')
                allowed_types = get_allowed_alert_types('free')
                delivery_config = plan_settings.get('delivery_config', {})
                max_email = 2
            
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
            
            account_id = create_delivery(user_id, alert_event_id, 'account', 'sent')
            if account_id:
                deliveries_created += 1
            
            email_config = delivery_config.get('email', {})
            if isinstance(email_config, dict):
                email_enabled = email_config.get('mode') in ['limited', 'unlimited']
                email_max = email_config.get('max_per_day', max_email)
            else:
                email_enabled = True
                email_max = max_email
            
            if email_enabled and user.get('email'):
                if check_delivery_cooldown(user_id, alert_event_id, 'email'):
                    pass
                elif count_deliveries_today(user_id, 'email') >= email_max:
                    create_delivery(user_id, alert_event_id, 'email', 'skipped', 'quota_exceeded')
                    skipped += 1
                else:
                    d_id = create_delivery(user_id, alert_event_id, 'email', 'queued')
                    if d_id:
                        deliveries_created += 1
            
            telegram_config = delivery_config.get('telegram', {})
            if isinstance(telegram_config, dict):
                telegram_enabled = telegram_config.get('enabled', False)
            else:
                telegram_enabled = bool(telegram_config)
            
            if telegram_enabled and user.get('telegram_chat_id'):
                if check_delivery_cooldown(user_id, alert_event_id, 'telegram'):
                    pass
                elif count_deliveries_today(user_id, 'telegram') >= email_max:
                    create_delivery(user_id, alert_event_id, 'telegram', 'skipped', 'quota_exceeded')
                    skipped += 1
                else:
                    d_id = create_delivery(user_id, alert_event_id, 'telegram', 'queued')
                    if d_id:
                        deliveries_created += 1
            
            sms_config = delivery_config.get('sms', {})
            if isinstance(sms_config, dict):
                sms_enabled = sms_config.get('enabled', False)
            else:
                sms_enabled = bool(sms_config)
            
            if sms_enabled and user.get('phone_number'):
                if not check_delivery_cooldown(user_id, alert_event_id, 'sms'):
                    d_id = create_delivery(user_id, alert_event_id, 'sms', 'queued')
                    if d_id:
                        deliveries_created += 1
    
    result = {
        'processed': len(alert_events),
        'users_checked': len(users),
        'deliveries_created': deliveries_created,
        'skipped': skipped
    }
    
    logger.info(f"Phase B complete: {deliveries_created} deliveries created, {skipped} skipped")
    return result


def send_queued_deliveries() -> Dict:
    logger.info("Phase C: Sending queued deliveries...")
    
    query = """
    SELECT d.id, d.user_id, d.alert_event_id, d.channel,
           ae.headline, ae.body, ae.alert_type,
           u.email, u.telegram_chat_id, u.phone_number,
           COALESCE(up.plan, 'free') as plan
    FROM user_alert_deliveries d
    JOIN alert_events ae ON ae.id = d.alert_event_id
    JOIN users u ON u.id = d.user_id
    LEFT JOIN user_plans up ON up.user_id = u.id
    WHERE d.status = 'queued'
    ORDER BY d.created_at ASC
    LIMIT 100
    """
    
    deliveries = execute_query(query)
    if not deliveries:
        logger.info("No queued deliveries to send")
        return {'sent': 0, 'failed': 0}
    
    logger.info(f"Sending {len(deliveries)} queued deliveries")
    
    sent = 0
    failed = 0
    
    for d in deliveries:
        delivery_id = d['id']
        channel = d['channel']
        headline = d['headline']
        body = d['body']
        plan = d['plan']
        
        if plan == 'free':
            body = add_upgrade_hook_if_free(body, plan)
        
        try:
            if channel == 'email':
                success, error, msg_id = send_email(d['email'], headline, body)
                if success:
                    update_delivery_status(delivery_id, 'sent', msg_id)
                    sent += 1
                else:
                    update_delivery_status(delivery_id, 'failed', reason=error)
                    failed += 1
            
            elif channel == 'telegram':
                success, error = send_telegram(d['telegram_chat_id'], body)
                if success:
                    update_delivery_status(delivery_id, 'sent')
                    sent += 1
                else:
                    update_delivery_status(delivery_id, 'failed', reason=error)
                    failed += 1
            
            elif channel == 'sms':
                sms_message = f"{headline}\n{body[:500]}"
                success, error = send_sms(d['phone_number'], sms_message)
                if success:
                    update_delivery_status(delivery_id, 'sent')
                    sent += 1
                else:
                    update_delivery_status(delivery_id, 'failed', reason=error)
                    failed += 1
            
            elif channel == 'account':
                update_delivery_status(delivery_id, 'sent')
                sent += 1
        
        except Exception as e:
            logger.error(f"Error sending delivery {delivery_id}: {e}")
            update_delivery_status(delivery_id, 'failed', reason=str(e))
            failed += 1
    
    result = {'sent': sent, 'failed': failed}
    logger.info(f"Phase C complete: {sent} sent, {failed} failed")
    return result


def run_alerts_engine_v2(dry_run: bool = False) -> Dict:
    logger.info("=" * 60)
    logger.info("Starting EnergyRiskIQ Alerts Engine v2 (Global + Fanout)")
    logger.info(f"ALERTS_V2_ENABLED: {ALERTS_V2_ENABLED}")
    logger.info(f"Dry run: {dry_run}")
    logger.info("=" * 60)
    
    if dry_run:
        logger.info("Dry run mode - no database changes")
        return {'dry_run': True, 'phase_a': {}, 'phase_b': {}, 'phase_c': {}}
    
    phase_a_result = generate_global_alert_events()
    
    phase_b_result = fanout_alert_events_to_users()
    
    phase_c_result = send_queued_deliveries()
    
    result = {
        'phase_a': phase_a_result,
        'phase_b': phase_b_result,
        'phase_c': phase_c_result,
        'total_events_created': phase_a_result.get('total', 0),
        'total_deliveries': phase_b_result.get('deliveries_created', 0),
        'total_sent': phase_c_result.get('sent', 0)
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
