"""
Telegram Bot Handler for EnergyRiskIQ

Handles /start command for linking user accounts to Telegram.
Supports both:
- Option A: Manual Chat ID entry
- Option B: Bot /start flow with link codes
"""

import os
import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Tuple
import requests

from src.db.db import get_cursor

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_BOT_USERNAME = 'energyriskiq_bot'
LINK_CODE_EXPIRY_MINUTES = 15


def generate_link_code(user_id: int) -> str:
    """
    Generate a unique link code for a user and store it in the database.
    Returns the link code.
    """
    link_code = secrets.token_urlsafe(16)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=LINK_CODE_EXPIRY_MINUTES)
    
    with get_cursor(commit=True) as cursor:
        cursor.execute("""
            UPDATE users 
            SET telegram_link_code = %s, 
                telegram_link_expires = %s
            WHERE id = %s
        """, (link_code, expires_at, user_id))
    
    logger.info(f"Generated Telegram link code for user {user_id}, expires at {expires_at}")
    return link_code


def get_telegram_link_url(user_id: int) -> str:
    """
    Generate a Telegram bot link URL with the user's link code.
    User clicks this to connect their Telegram account.
    """
    link_code = generate_link_code(user_id)
    return f"https://t.me/{TELEGRAM_BOT_USERNAME}?start={link_code}"


def validate_and_link_telegram(link_code: str, chat_id: str) -> Tuple[bool, Optional[str], Optional[int]]:
    """
    Validate a link code and link the Telegram chat_id to the user account.
    
    Returns: (success, error_message, user_id)
    """
    with get_cursor(commit=True) as cursor:
        cursor.execute("""
            SELECT id, email, telegram_link_expires 
            FROM users 
            WHERE telegram_link_code = %s
        """, (link_code,))
        row = cursor.fetchone()
        
        if not row:
            return False, "Invalid or expired link code", None
        
        user_id = row['id']
        email = row['email']
        expires_at = row['telegram_link_expires']
        
        if expires_at and expires_at < datetime.now(timezone.utc):
            return False, "Link code has expired. Please generate a new link from your account.", None
        
        cursor.execute("""
            UPDATE users 
            SET telegram_chat_id = %s,
                telegram_link_code = NULL,
                telegram_link_expires = NULL,
                telegram_connected_at = NOW()
            WHERE id = %s
        """, (chat_id, user_id))
        
        logger.info(f"Linked Telegram chat_id {chat_id} to user {user_id} ({email})")
        return True, None, user_id


def link_telegram_manually(user_id: int, chat_id: str) -> Tuple[bool, Optional[str]]:
    """
    Link a Telegram chat_id to a user account manually (Option A).
    
    Returns: (success, error_message)
    """
    if not chat_id or not chat_id.strip():
        return False, "Chat ID is required"
    
    chat_id = chat_id.strip()
    
    if not chat_id.lstrip('-').isdigit():
        return False, "Invalid Chat ID format. Chat ID should be a number."
    
    with get_cursor(commit=True) as cursor:
        cursor.execute("""
            UPDATE users 
            SET telegram_chat_id = %s,
                telegram_link_code = NULL,
                telegram_link_expires = NULL,
                telegram_connected_at = NOW()
            WHERE id = %s
        """, (chat_id, user_id))
    
    logger.info(f"Manually linked Telegram chat_id {chat_id} to user {user_id}")
    return True, None


def unlink_telegram(user_id: int) -> Tuple[bool, Optional[str]]:
    """
    Unlink Telegram from a user account.
    
    Returns: (success, error_message)
    """
    with get_cursor(commit=True) as cursor:
        cursor.execute("""
            UPDATE users 
            SET telegram_chat_id = NULL,
                telegram_link_code = NULL,
                telegram_link_expires = NULL,
                telegram_connected_at = NULL
            WHERE id = %s
        """, (user_id,))
    
    logger.info(f"Unlinked Telegram from user {user_id}")
    return True, None


def get_user_telegram_status(user_id: int) -> Dict:
    """
    Get the current Telegram connection status for a user.
    """
    with get_cursor(commit=False) as cursor:
        cursor.execute("""
            SELECT telegram_chat_id, telegram_connected_at
            FROM users 
            WHERE id = %s
        """, (user_id,))
        row = cursor.fetchone()
        
        if not row:
            return {"connected": False, "chat_id": None, "connected_at": None}
        
        is_connected = row['telegram_chat_id'] is not None
        return {
            "connected": is_connected,
            "chat_id": row['telegram_chat_id'] if is_connected else None,
            "connected_at": row['telegram_connected_at'].isoformat() if row.get('telegram_connected_at') else None
        }


def handle_telegram_start(chat_id: str, start_param: Optional[str]) -> str:
    """
    Handle the /start command from Telegram.
    
    If start_param is provided (deep link), attempt to link the account.
    Otherwise, send a welcome message.
    
    Returns: Message to send back to user
    """
    if not start_param:
        return (
            "Welcome to EnergyRiskIQ Alerts!\n\n"
            "To receive alerts, please link your account:\n"
            "1. Go to your EnergyRiskIQ account settings\n"
            "2. Click 'Connect Telegram'\n"
            "3. You'll be redirected here automatically\n\n"
            "Or enter your Chat ID manually in your account settings.\n"
            f"Your Chat ID is: `{chat_id}`"
        )
    
    success, error, user_id = validate_and_link_telegram(start_param, chat_id)
    
    if success:
        return (
            "Your Telegram account has been successfully linked to EnergyRiskIQ!\n\n"
            "You will now receive:\n"
            "- Real-time energy risk alerts\n"
            "- Daily GERI (Global Energy Risk Index) updates\n\n"
            "Thank you for using EnergyRiskIQ."
        )
    else:
        return (
            f"Could not link your account: {error}\n\n"
            "Please try again from your EnergyRiskIQ account settings.\n"
            f"Your Chat ID is: `{chat_id}` (you can enter this manually)"
        )


def process_telegram_update(update: Dict) -> Optional[str]:
    """
    Process an incoming Telegram update (webhook).
    
    Returns: Response message to send, or None if no response needed
    """
    message = update.get('message')
    if not message:
        return None
    
    chat = message.get('chat', {})
    chat_id = str(chat.get('id', ''))
    text = message.get('text', '')
    
    if not chat_id or not text:
        return None
    
    if text.startswith('/start'):
        parts = text.split(' ', 1)
        start_param = parts[1] if len(parts) > 1 else None
        response = handle_telegram_start(chat_id, start_param)
        send_telegram_message(chat_id, response)
        return response
    
    elif text == '/status':
        response = (
            "EnergyRiskIQ Alerts Bot\n\n"
            f"Your Chat ID: `{chat_id}`\n\n"
            "Use this Chat ID in your account settings to link your account manually."
        )
        send_telegram_message(chat_id, response)
        return response
    
    elif text == '/help':
        response = (
            "EnergyRiskIQ Alerts Bot - Help\n\n"
            "Commands:\n"
            "/start - Link your account (use link from account settings)\n"
            "/status - Show your Chat ID\n"
            "/help - Show this help message\n\n"
            "For support, contact support@energyriskiq.com"
        )
        send_telegram_message(chat_id, response)
        return response
    
    return None


def send_telegram_message(chat_id: str, text: str, parse_mode: str = "Markdown") -> bool:
    """
    Send a message to a Telegram chat.
    """
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not set, cannot send message")
        return False
    
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode
            },
            timeout=30
        )
        
        if response.status_code == 200:
            logger.info(f"Telegram message sent to {chat_id}")
            return True
        else:
            logger.error(f"Telegram API error: {response.status_code} - {response.text}")
            return False
    
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return False
