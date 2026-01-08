import os
import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)

EMAIL_PROVIDER = os.environ.get('EMAIL_PROVIDER', 'resend')
EMAIL_FROM = os.environ.get('EMAIL_FROM', 'alerts@energyriskiq.com')
RESEND_API_KEY = os.environ.get('RESEND_API_KEY', '')
BREVO_API_KEY = os.environ.get('BREVO_API_KEY', '')
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')


def send_email(to_email: str, subject: str, body: str) -> tuple:
    if not to_email:
        return False, "No email address provided"
    
    if EMAIL_PROVIDER == 'resend':
        return _send_resend(to_email, subject, body)
    elif EMAIL_PROVIDER == 'brevo':
        return _send_brevo(to_email, subject, body)
    else:
        logger.warning(f"Email provider '{EMAIL_PROVIDER}' not configured, simulating send")
        return _simulate_send(to_email, subject, body)


def _send_resend(to_email: str, subject: str, body: str) -> tuple:
    if not RESEND_API_KEY:
        logger.warning("RESEND_API_KEY not set, simulating email send")
        return _simulate_send(to_email, subject, body)
    
    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "from": EMAIL_FROM,
                "to": [to_email],
                "subject": subject,
                "text": body
            },
            timeout=30
        )
        
        if response.status_code in [200, 201]:
            logger.info(f"Email sent to {to_email}")
            return True, None
        else:
            error = f"Resend API error: {response.status_code} - {response.text}"
            logger.error(error)
            return False, error
    
    except Exception as e:
        error = f"Email send failed: {str(e)}"
        logger.error(error)
        return False, error


def _send_brevo(to_email: str, subject: str, body: str) -> tuple:
    if not BREVO_API_KEY:
        logger.warning("BREVO_API_KEY not set, simulating email send")
        return _simulate_send(to_email, subject, body)
    
    try:
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={
                "api-key": BREVO_API_KEY,
                "Content-Type": "application/json"
            },
            json={
                "sender": {"email": EMAIL_FROM},
                "to": [{"email": to_email}],
                "subject": subject,
                "textContent": body
            },
            timeout=30
        )
        
        if response.status_code in [200, 201, 202]:
            logger.info(f"Email sent to {to_email}")
            return True, None
        else:
            error = f"Brevo API error: {response.status_code} - {response.text}"
            logger.error(error)
            return False, error
    
    except Exception as e:
        error = f"Email send failed: {str(e)}"
        logger.error(error)
        return False, error


def _simulate_send(to_email: str, subject: str, body: str) -> tuple:
    logger.info(f"[SIMULATED] Email to {to_email}: {subject}")
    logger.debug(f"Body preview: {body[:200]}...")
    return True, None


def send_telegram(chat_id: str, message: str) -> tuple:
    if not chat_id:
        return False, "No Telegram chat ID provided"
    
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not set, simulating Telegram send")
        return _simulate_telegram(chat_id, message)
    
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown"
            },
            timeout=30
        )
        
        if response.status_code == 200:
            logger.info(f"Telegram sent to {chat_id}")
            return True, None
        else:
            error = f"Telegram API error: {response.status_code} - {response.text}"
            logger.error(error)
            return False, error
    
    except Exception as e:
        error = f"Telegram send failed: {str(e)}"
        logger.error(error)
        return False, error


def _simulate_telegram(chat_id: str, message: str) -> tuple:
    logger.info(f"[SIMULATED] Telegram to {chat_id}")
    logger.debug(f"Message preview: {message[:200]}...")
    return True, None
