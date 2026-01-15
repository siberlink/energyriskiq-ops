"""
Quota and Preference Helpers for Alerts v2

Provides quota enforcement, preference checking, and delivery kind determination.
"""

import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

from src.db.db import execute_query, execute_one

logger = logging.getLogger(__name__)

DEFAULT_PLAN_QUOTAS = {
    'free': {
        'instant_email_per_day': 0,
        'instant_telegram_per_day': 0,
        'instant_sms_per_day': 0,
        'digest_per_day': 1,
        'digest_only': True,
        'sms_enabled': False
    },
    'personal': {
        'instant_email_per_day': 5,
        'instant_telegram_per_day': 5,
        'instant_sms_per_day': 0,
        'digest_per_day': 2,
        'digest_only': False,
        'sms_enabled': False
    },
    'trader': {
        'instant_email_per_day': 20,
        'instant_telegram_per_day': 20,
        'instant_sms_per_day': 0,
        'digest_per_day': 3,
        'digest_only': False,
        'sms_enabled': False
    },
    'pro': {
        'instant_email_per_day': 50,
        'instant_telegram_per_day': 50,
        'instant_sms_per_day': 5,
        'digest_per_day': 5,
        'digest_only': False,
        'sms_enabled': True
    },
    'enterprise': {
        'instant_email_per_day': 200,
        'instant_telegram_per_day': 200,
        'instant_sms_per_day': 20,
        'digest_per_day': 10,
        'digest_only': False,
        'sms_enabled': True
    }
}


def get_plan_quotas(plan: str) -> Dict:
    """Get quota configuration for a plan."""
    plan_lower = plan.lower() if plan else 'free'
    return DEFAULT_PLAN_QUOTAS.get(plan_lower, DEFAULT_PLAN_QUOTAS['free'])


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
