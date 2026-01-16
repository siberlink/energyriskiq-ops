"""
Quota and Preference Helpers for Alerts v2

Provides quota enforcement, preference checking, and delivery kind determination.
Quotas are read from the plan_settings database table.
"""

import os
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

from src.db.db import execute_query, execute_one

logger = logging.getLogger(__name__)

_quota_cache: Dict[str, Dict] = {}
_quota_cache_time: Dict[str, float] = {}
QUOTA_CACHE_TTL_SECONDS = 300

FALLBACK_QUOTAS = {
    'instant_email_per_day': 0,
    'instant_telegram_per_day': 0,
    'instant_sms_per_day': 0,
    'digest_per_day': 1,
    'digest_only': True,
    'sms_enabled': False,
    'telegram_enabled': False
}


def _parse_delivery_config_to_quotas(plan_settings: Dict) -> Dict:
    """
    Parse plan_settings (from DB) into quota format.
    
    Uses delivery_config JSON and max_email_alerts_per_day.
    """
    delivery_config = plan_settings.get('delivery_config', {})
    max_email = plan_settings.get('max_email_alerts_per_day', 0)
    
    email_config = delivery_config.get('email', {})
    telegram_config = delivery_config.get('telegram', {})
    sms_config = delivery_config.get('sms', {})
    
    email_max_per_day = email_config.get('max_per_day', max_email) or max_email
    email_realtime_limit = email_config.get('realtime_limit')
    email_mode = email_config.get('mode', 'limited')
    
    digest_only = False
    if email_mode == 'limited' and email_realtime_limit is not None and email_realtime_limit == 0:
        digest_only = True
    
    telegram_enabled = telegram_config.get('enabled', False)
    telegram_send_all = telegram_config.get('send_all', False)
    
    if telegram_enabled and telegram_send_all:
        instant_telegram = email_max_per_day
    elif telegram_enabled:
        instant_telegram = email_realtime_limit if email_realtime_limit else 0
    else:
        instant_telegram = 0
    
    sms_enabled = sms_config.get('enabled', False)
    sms_send_all = sms_config.get('send_all', False)
    
    if sms_enabled and sms_send_all:
        instant_sms = email_max_per_day
    elif sms_enabled:
        instant_sms = email_realtime_limit if email_realtime_limit else 0
    else:
        instant_sms = 0
    
    if digest_only:
        instant_email = 0
    elif email_realtime_limit is None:
        instant_email = email_max_per_day
    else:
        instant_email = email_realtime_limit
    
    digest_per_day = max(1, email_max_per_day // 4) if email_max_per_day > 0 else 1
    
    return {
        'instant_email_per_day': instant_email,
        'instant_telegram_per_day': instant_telegram,
        'instant_sms_per_day': instant_sms,
        'digest_per_day': digest_per_day,
        'digest_only': digest_only,
        'sms_enabled': sms_enabled,
        'telegram_enabled': telegram_enabled,
        'email_max_per_day': email_max_per_day,
        'email_realtime_limit': email_realtime_limit
    }


def get_plan_quotas(plan: str) -> Dict:
    """
    Get quota configuration for a plan from database.
    
    Uses caching to avoid repeated DB queries.
    Falls back to safe defaults if DB query fails.
    """
    plan_lower = (plan.lower() if plan else 'free').strip()
    
    if plan_lower not in ['free', 'personal', 'trader', 'pro', 'enterprise']:
        plan_lower = 'free'
    
    now = time.time()
    if plan_lower in _quota_cache:
        cache_age = now - _quota_cache_time.get(plan_lower, 0)
        if cache_age < QUOTA_CACHE_TTL_SECONDS:
            return _quota_cache[plan_lower]
    
    try:
        from src.plans.plan_helpers import get_plan_settings
        plan_settings = get_plan_settings(plan_lower)
        quotas = _parse_delivery_config_to_quotas(plan_settings)
        
        _quota_cache[plan_lower] = quotas
        _quota_cache_time[plan_lower] = now
        
        return quotas
    except Exception as e:
        logger.warning(f"Failed to get plan quotas from DB for '{plan_lower}': {e}. Using fallback.")
        return FALLBACK_QUOTAS.copy()


def get_start_of_day_utc() -> datetime:
    """Get the start of the current UTC day."""
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def count_user_deliveries_today(user_id: int, channel: str, delivery_kind: str = 'instant') -> int:
    """
    Count deliveries for a user today.
    
    Counts both queued and sent deliveries in the current UTC day.
    """
    start_of_day = get_start_of_day_utc()
    
    result = execute_one(
        """
        SELECT COUNT(*) as cnt
        FROM user_alert_deliveries
        WHERE user_id = %s
          AND channel = %s
          AND delivery_kind = %s
          AND status IN ('queued', 'sending', 'sent')
          AND created_at >= %s
        """,
        (user_id, channel, delivery_kind, start_of_day)
    )
    
    return result['cnt'] if result else 0


def check_quota(user_id: int, channel: str, plan: str, delivery_kind: str = 'instant') -> Tuple[bool, Optional[str]]:
    """
    Check if user has quota available for a delivery.
    
    Returns:
        Tuple of (quota_available, reason_if_not)
    """
    quotas = get_plan_quotas(plan)
    
    if delivery_kind == 'instant':
        if quotas.get('digest_only', False):
            return False, "plan_digest_only"
        
        quota_key = f'instant_{channel}_per_day'
        max_quota = quotas.get(quota_key, 0)
        
        if max_quota <= 0:
            return False, "channel_not_allowed"
        
        current_count = count_user_deliveries_today(user_id, channel, 'instant')
        
        if current_count >= max_quota:
            return False, "quota_exceeded"
    
    elif delivery_kind == 'digest':
        max_digest = quotas.get('digest_per_day', 0)
        
        if max_digest <= 0:
            return False, "digest_not_allowed"
        
        current_count = count_user_deliveries_today(user_id, 'digest', 'digest')
        
        if current_count >= max_digest:
            return False, "quota_exceeded"
    
    return True, None


def check_sms_enabled(plan: str) -> bool:
    """Check if SMS is enabled for a plan."""
    quotas = get_plan_quotas(plan)
    return quotas.get('sms_enabled', False)


def determine_delivery_kind(user_prefs: Optional[Dict], plan: str) -> str:
    """
    Determine delivery kind based on user preferences and plan.
    
    Rules:
    - If user preference says digest_only => 'digest'
    - If plan is Free => 'digest'
    - Else => 'instant'
    """
    quotas = get_plan_quotas(plan)
    
    if quotas.get('digest_only', False):
        return 'digest'
    
    if user_prefs:
        if user_prefs.get('digest_only', False):
            return 'digest'
        if user_prefs.get('delivery_mode') == 'digest':
            return 'digest'
    
    return 'instant'


def get_user_alert_prefs(user_id: int) -> Optional[Dict]:
    """Get user alert preferences.
    
    The user_alert_prefs table stores per-alert-type preferences,
    not per-channel preferences. This returns aggregated preferences.
    """
    results = execute_query(
        """
        SELECT region, alert_type, asset, threshold, enabled, cooldown_minutes
        FROM user_alert_prefs
        WHERE user_id = %s AND enabled = TRUE
        """,
        (user_id,)
    )
    
    if not results:
        return None
    
    alert_types = list(set(r['alert_type'] for r in results if r.get('alert_type')))
    regions = list(set(r['region'] for r in results if r.get('region')))
    cooldowns = [r['cooldown_minutes'] for r in results if r.get('cooldown_minutes')]
    
    return {
        'alert_types': alert_types,
        'regions': regions,
        'cooldown_minutes': min(cooldowns) if cooldowns else 60,
        'email_enabled': True,
        'telegram_enabled': True,
        'sms_enabled': True
    }


def is_channel_enabled_for_user(user_id: int, channel: str, user_prefs: Optional[Dict] = None) -> bool:
    """Check if a channel is enabled for a user based on their preferences.
    
    Note: The current schema doesn't have per-channel preferences,
    so all channels are enabled by default.
    """
    return True


def get_user_destination(user: Dict, channel: str) -> Optional[str]:
    """Get the destination address for a channel from user data."""
    if channel == 'email':
        return user.get('email')
    elif channel == 'telegram':
        return user.get('telegram_chat_id')
    elif channel == 'sms':
        return user.get('phone_number')
    return None


class DeliveryEligibility:
    """Result of checking delivery eligibility."""
    
    def __init__(
        self,
        eligible: bool,
        delivery_kind: str = 'instant',
        skip_reason: Optional[str] = None
    ):
        self.eligible = eligible
        self.delivery_kind = delivery_kind
        self.skip_reason = skip_reason


def check_delivery_eligibility(
    user_id: int,
    user: Dict,
    channel: str,
    plan: str,
    alert_event_id: int
) -> DeliveryEligibility:
    """
    Comprehensive eligibility check for a delivery.
    
    Checks:
    1. User has destination for channel
    2. Channel is enabled in user preferences
    3. SMS is allowed for plan (if channel is sms)
    4. Quota is available
    5. No duplicate delivery exists
    
    Returns DeliveryEligibility with details.
    """
    destination = get_user_destination(user, channel)
    if not destination:
        return DeliveryEligibility(False, skip_reason="missing_destination")
    
    user_prefs = get_user_alert_prefs(user_id)
    
    if not is_channel_enabled_for_user(user_id, channel, user_prefs):
        return DeliveryEligibility(False, skip_reason="channel_disabled_by_user")
    
    if channel == 'sms' and not check_sms_enabled(plan):
        return DeliveryEligibility(False, skip_reason="sms_not_in_plan")
    
    delivery_kind = determine_delivery_kind(user_prefs, plan)
    
    quota_ok, quota_reason = check_quota(user_id, channel, plan, delivery_kind)
    if not quota_ok:
        return DeliveryEligibility(False, delivery_kind=delivery_kind, skip_reason=quota_reason)
    
    existing = execute_one(
        """
        SELECT id FROM user_alert_deliveries
        WHERE user_id = %s AND alert_event_id = %s AND channel = %s
        LIMIT 1
        """,
        (user_id, alert_event_id, channel)
    )
    if existing:
        return DeliveryEligibility(False, delivery_kind=delivery_kind, skip_reason="already_exists")
    
    return DeliveryEligibility(True, delivery_kind=delivery_kind)
