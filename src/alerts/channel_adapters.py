"""
Channel Adapters for Alerts v2

Provides a unified interface for sending alerts via email, telegram, and sms.
Includes config validation, failure classification, and production safeguards.
"""

import os
import logging
import random
import time
from typing import Dict, Tuple, Optional
from enum import Enum
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

ALERTS_MAX_ATTEMPTS = int(os.environ.get('ALERTS_MAX_ATTEMPTS', '5'))
ALERTS_RETRY_BASE_SECONDS = int(os.environ.get('ALERTS_RETRY_BASE_SECONDS', '60'))
ALERTS_RETRY_MAX_SECONDS = int(os.environ.get('ALERTS_RETRY_MAX_SECONDS', '3600'))
ALERTS_RATE_LIMIT_EMAIL_PER_MINUTE = int(os.environ.get('ALERTS_RATE_LIMIT_EMAIL_PER_MINUTE', '0'))
ALERTS_RATE_LIMIT_TELEGRAM_PER_MINUTE = int(os.environ.get('ALERTS_RATE_LIMIT_TELEGRAM_PER_MINUTE', '0'))
ALERTS_RATE_LIMIT_SMS_PER_MINUTE = int(os.environ.get('ALERTS_RATE_LIMIT_SMS_PER_MINUTE', '0'))
ALERTS_FAIL_OPEN_ON_CHANNEL_MISSING = os.environ.get('ALERTS_FAIL_OPEN_ON_CHANNEL_MISSING', 'false').lower() == 'true'


class FailureType(Enum):
    TRANSIENT = "transient"
    PERMANENT = "permanent"


@dataclass
class SendResult:
    success: bool
    error: Optional[str] = None
    message_id: Optional[str] = None
    failure_type: Optional[FailureType] = None
    should_skip: bool = False
    skip_reason: Optional[str] = None


def classify_failure(error: str, status_code: Optional[int] = None) -> FailureType:
    """
    Classify a failure as transient or permanent.
    
    Transient failures (retry):
    - Timeouts, network errors
    - 429 (rate limited)
    - 5xx (server errors)
    - Provider unavailable
    
    Permanent failures (no retry):
    - Invalid recipient (phone, email, chat_id)
    - Malformed payload
    - 4xx except 429
    - Authentication errors (bad API key)
    """
    error_lower = error.lower()
    
    transient_keywords = [
        'timeout', 'timed out', 'network', 'connection',
        'temporarily', 'unavailable', 'retry', 'rate limit',
        'too many requests', 'service unavailable', '503', '502', '504',
        'internal server error', '500', 'overloaded'
    ]
    
    for keyword in transient_keywords:
        if keyword in error_lower:
            return FailureType.TRANSIENT
    
    if status_code:
        if status_code == 429:
            return FailureType.TRANSIENT
        if status_code >= 500:
            return FailureType.TRANSIENT
        if 400 <= status_code < 500:
            return FailureType.PERMANENT
    
    permanent_keywords = [
        'invalid', 'not found', 'blocked', 'banned', 'deactivated',
        'malformed', 'bad request', '400', '401', '403', '404',
        'unauthorized', 'forbidden', 'unsubscribed', 'bounced'
    ]
    
    for keyword in permanent_keywords:
        if keyword in error_lower:
            return FailureType.PERMANENT
    
    return FailureType.TRANSIENT


def compute_next_retry_delay(attempts: int) -> int:
    """
    Compute next retry delay using exponential backoff with jitter.
    
    delay = min(RETRY_MAX, RETRY_BASE * 2^(attempts-1))
    jitter = random 0-20% of delay
    """
    base_delay = ALERTS_RETRY_BASE_SECONDS * (2 ** (attempts - 1))
    capped_delay = min(base_delay, ALERTS_RETRY_MAX_SECONDS)
    jitter = random.uniform(0, 0.2) * capped_delay
    return int(capped_delay + jitter)


def should_retry(attempts: int, failure_type: FailureType) -> bool:
    """Determine if we should retry based on attempts and failure type."""
    if failure_type == FailureType.PERMANENT:
        return False
    return attempts < ALERTS_MAX_ATTEMPTS


class ChannelConfig:
    """Check and cache channel configuration status."""
    
    _email_configured: Optional[bool] = None
    _telegram_configured: Optional[bool] = None
    _sms_configured: Optional[bool] = None
    
    @classmethod
    def is_email_configured(cls) -> Tuple[bool, Optional[str]]:
        """Check if email channel is properly configured."""
        provider = os.environ.get('EMAIL_PROVIDER', 'brevo')
        
        if provider == 'resend':
            api_key = os.environ.get('RESEND_API_KEY', '')
            if not api_key:
                return False, "RESEND_API_KEY not configured"
        elif provider == 'brevo':
            api_key = os.environ.get('BREVO_API_KEY', '')
            if not api_key:
                return False, "BREVO_API_KEY not configured"
        else:
            return False, f"Unknown email provider: {provider}"
        
        email_from = os.environ.get('EMAIL_FROM', '')
        if not email_from:
            return False, "EMAIL_FROM not configured"
        
        return True, None
    
    @classmethod
    def is_telegram_configured(cls) -> Tuple[bool, Optional[str]]:
        """Check if Telegram channel is properly configured."""
        token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
        if not token:
            return False, "TELEGRAM_BOT_TOKEN not configured"
        return True, None
    
    @classmethod
    def is_sms_configured(cls) -> Tuple[bool, Optional[str]]:
        """Check if SMS channel is properly configured."""
        account_sid = os.environ.get('TWILIO_ACCOUNT_SID', '')
        auth_token = os.environ.get('TWILIO_AUTH_TOKEN', '')
        phone = os.environ.get('TWILIO_PHONE_NUMBER', '')
        
        if not account_sid:
            return False, "TWILIO_ACCOUNT_SID not configured"
        if not auth_token:
            return False, "TWILIO_AUTH_TOKEN not configured"
        if not phone:
            return False, "TWILIO_PHONE_NUMBER not configured"
        
        return True, None


_rate_limit_state: Dict[str, list] = {
    'email': [],
    'telegram': [],
    'sms': []
}


def _check_rate_limit(channel: str) -> bool:
    """
    Check if we should throttle based on rate limit.
    Returns True if we should proceed, False if we should wait.
    Simple sliding window implementation.
    """
    limits = {
        'email': ALERTS_RATE_LIMIT_EMAIL_PER_MINUTE,
        'telegram': ALERTS_RATE_LIMIT_TELEGRAM_PER_MINUTE,
        'sms': ALERTS_RATE_LIMIT_SMS_PER_MINUTE
    }
    
    limit = limits.get(channel, 0)
    if limit <= 0:
        return True
    
    now = time.time()
    window_start = now - 60
    
    _rate_limit_state[channel] = [t for t in _rate_limit_state[channel] if t > window_start]
    
    if len(_rate_limit_state[channel]) >= limit:
        oldest = _rate_limit_state[channel][0]
        sleep_time = oldest - window_start + 0.1
        if sleep_time > 0:
            logger.info(f"Rate limiting {channel}: sleeping {sleep_time:.2f}s")
            time.sleep(sleep_time)
    
    _rate_limit_state[channel].append(now)
    return True


def send_email_v2(
    to_email: str,
    subject: str,
    body: str,
    delivery_id: Optional[int] = None
) -> SendResult:
    """
    Send email with config validation and failure classification.
    """
    if not to_email:
        return SendResult(
            success=False,
            should_skip=True,
            skip_reason="missing_destination",
            error="No email address provided"
        )
    
    configured, reason = ChannelConfig.is_email_configured()
    if not configured:
        logger.warning(f"Email channel not configured: {reason}")
        return SendResult(
            success=False,
            should_skip=True,
            skip_reason="channel_not_configured",
            error=reason
        )
    
    _check_rate_limit('email')
    
    from src.alerts.channels import send_email
    success, error, message_id = send_email(to_email, subject, body)
    
    if success:
        return SendResult(success=True, message_id=message_id)
    
    status_code = None
    if error and 'error:' in error.lower():
        import re
        match = re.search(r'(\d{3})', error)
        if match:
            status_code = int(match.group(1))
    
    failure_type = classify_failure(error or "", status_code)
    
    return SendResult(
        success=False,
        error=error,
        failure_type=failure_type
    )


def send_telegram_v2(
    chat_id: str,
    message: str,
    delivery_id: Optional[int] = None
) -> SendResult:
    """
    Send Telegram message with config validation and failure classification.
    """
    if not chat_id:
        return SendResult(
            success=False,
            should_skip=True,
            skip_reason="missing_destination",
            error="No Telegram chat ID provided"
        )
    
    configured, reason = ChannelConfig.is_telegram_configured()
    if not configured:
        logger.warning(f"Telegram channel not configured: {reason}")
        return SendResult(
            success=False,
            should_skip=True,
            skip_reason="channel_not_configured",
            error=reason
        )
    
    _check_rate_limit('telegram')
    
    from src.alerts.channels import send_telegram
    success, error = send_telegram(chat_id, message)
    
    if success:
        return SendResult(success=True)
    
    status_code = None
    if error:
        import re
        match = re.search(r'(\d{3})', error)
        if match:
            status_code = int(match.group(1))
    
    failure_type = classify_failure(error or "", status_code)
    
    if 'chat not found' in (error or '').lower() or 'user is deactivated' in (error or '').lower():
        return SendResult(
            success=False,
            should_skip=True,
            skip_reason="invalid_destination",
            error=error,
            failure_type=FailureType.PERMANENT
        )
    
    return SendResult(
        success=False,
        error=error,
        failure_type=failure_type
    )


def send_sms_v2(
    to_phone: str,
    message: str,
    delivery_id: Optional[int] = None
) -> SendResult:
    """
    Send SMS with config validation and failure classification.
    """
    if not to_phone:
        return SendResult(
            success=False,
            should_skip=True,
            skip_reason="missing_destination",
            error="No phone number provided"
        )
    
    configured, reason = ChannelConfig.is_sms_configured()
    if not configured:
        logger.warning(f"SMS channel not configured: {reason}")
        return SendResult(
            success=False,
            should_skip=True,
            skip_reason="channel_not_configured",
            error=reason
        )
    
    _check_rate_limit('sms')
    
    from src.alerts.channels import send_sms
    success, error = send_sms(to_phone, message)
    
    if success:
        return SendResult(success=True)
    
    status_code = None
    if error:
        import re
        match = re.search(r'(\d{3})', error)
        if match:
            status_code = int(match.group(1))
    
    failure_type = classify_failure(error or "", status_code)
    
    invalid_phone_patterns = [
        'invalid phone', 'unverified', 'is not a valid phone',
        'cannot route', 'blacklisted', 'landline'
    ]
    for pattern in invalid_phone_patterns:
        if pattern in (error or '').lower():
            return SendResult(
                success=False,
                should_skip=True,
                skip_reason="invalid_destination",
                error=error,
                failure_type=FailureType.PERMANENT
            )
    
    return SendResult(
        success=False,
        error=error,
        failure_type=failure_type
    )


def get_channel_adapter(channel: str):
    """Get the appropriate channel adapter function."""
    adapters = {
        'email': send_email_v2,
        'telegram': send_telegram_v2,
        'sms': send_sms_v2
    }
    return adapters.get(channel)
