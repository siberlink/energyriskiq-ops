import os
import logging
import requests
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException
from typing import Optional

from src.db.db import get_cursor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram", tags=["telegram"])

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "energyriskiq-tg-webhook")


def send_telegram_message(chat_id: str, text: str):
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not set")
        return False
    
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown"
            },
            timeout=30
        )
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return False


@router.post("/webhook/{secret}")
async def telegram_webhook(secret: str, request: Request):
    if secret != TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid webhook secret")
    
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    message = data.get("message", {})
    chat_id = str(message.get("chat", {}).get("id", ""))
    text = message.get("text", "").strip().upper()
    username = message.get("from", {}).get("username", "")
    first_name = message.get("from", {}).get("first_name", "User")
    
    if not chat_id or not text:
        return {"ok": True}
    
    if text == "/START":
        send_telegram_message(
            chat_id,
            f"Welcome to EnergyRiskIQ, {first_name}!\n\n"
            "To link your account:\n"
            "1. Go to your account dashboard at energyriskiq.com\n"
            "2. Click 'Link Telegram' to get a code\n"
            "3. Send that code here\n\n"
            "Once linked, you'll receive real-time alerts via Telegram!"
        )
        return {"ok": True}
    
    if text == "/HELP":
        send_telegram_message(
            chat_id,
            "*EnergyRiskIQ Bot Commands*\n\n"
            "/start - Get started\n"
            "/status - Check your account status\n"
            "/unlink - Unlink your account\n"
            "/help - Show this message\n\n"
            "To link your account, get a code from your dashboard and send it here."
        )
        return {"ok": True}
    
    if text == "/STATUS":
        with get_cursor() as cursor:
            cursor.execute("""
                SELECT u.email, up.plan
                FROM users u
                LEFT JOIN user_plans up ON u.id = up.user_id
                WHERE u.telegram_chat_id = %s
            """, (chat_id,))
            user = cursor.fetchone()
        
        if user:
            send_telegram_message(
                chat_id,
                f"*Account Linked*\n\n"
                f"Email: {user['email']}\n"
                f"Plan: {user['plan'].title()}\n\n"
                "You'll receive alerts based on your plan settings."
            )
        else:
            send_telegram_message(
                chat_id,
                "Your Telegram is not linked to any EnergyRiskIQ account.\n\n"
                "To link, go to your account dashboard and click 'Link Telegram'."
            )
        return {"ok": True}
    
    if text == "/UNLINK":
        with get_cursor() as cursor:
            cursor.execute("""
                UPDATE users SET telegram_chat_id = NULL, updated_at = NOW()
                WHERE telegram_chat_id = %s
                RETURNING email
            """, (chat_id,))
            result = cursor.fetchone()
        
        if result:
            send_telegram_message(
                chat_id,
                f"Account unlinked successfully.\n\n"
                "You will no longer receive alerts via Telegram."
            )
        else:
            send_telegram_message(
                chat_id,
                "No account was linked to this Telegram."
            )
        return {"ok": True}
    
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT id, email FROM users
            WHERE telegram_link_code = %s
              AND telegram_link_expires > NOW()
        """, (text,))
        user = cursor.fetchone()
        
        if user:
            cursor.execute("""
                UPDATE users SET 
                    telegram_chat_id = %s,
                    telegram_link_code = NULL,
                    telegram_link_expires = NULL,
                    updated_at = NOW()
                WHERE id = %s
            """, (chat_id, user['id']))
            
            send_telegram_message(
                chat_id,
                f"*Account Linked Successfully!*\n\n"
                f"Your Telegram is now connected to: {user['email']}\n\n"
                "You'll start receiving alerts based on your subscription plan."
            )
            logger.info(f"Telegram linked for user {user['id']} (chat_id: {chat_id})")
        else:
            send_telegram_message(
                chat_id,
                "Invalid or expired code.\n\n"
                "Please generate a new code from your account dashboard."
            )
    
    return {"ok": True}


def setup_webhook(app_url: str):
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("Cannot setup webhook: TELEGRAM_BOT_TOKEN not set")
        return False
    
    webhook_url = f"{app_url}/telegram/webhook/{TELEGRAM_WEBHOOK_SECRET}"
    
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook",
            json={"url": webhook_url},
            timeout=30
        )
        
        if response.status_code == 200:
            logger.info(f"Telegram webhook set to: {webhook_url}")
            return True
        else:
            logger.error(f"Failed to set webhook: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Error setting webhook: {e}")
        return False
