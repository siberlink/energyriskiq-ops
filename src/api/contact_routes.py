import os
import re
import html
import time
import random
import secrets
import logging
import threading
import requests
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, field_validator

from src.db.db import get_cursor

logger = logging.getLogger(__name__)

router = APIRouter(tags=["contact"])

CONTACT_EMAIL = "emil@energyriskiq.com"
CONFIRM_TTL_HOURS = 48


def run_contact_confirmation_migration():
    """Create tables for contact-page email confirmation (additive)."""
    with get_cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS contact_pending_messages (
                id SERIAL PRIMARY KEY,
                token TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                subject TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
                expires_at TIMESTAMP NOT NULL,
                confirmed_at TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS contact_visitors (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                first_contact_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
                last_contact_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
                messages_count INTEGER NOT NULL DEFAULT 1
            )
        """)
    logger.info("contact confirmation tables ready")


def _base_url() -> str:
    app_url = os.environ.get("APP_URL")
    if app_url:
        return app_url.rstrip("/")
    domain = os.environ.get("REPLIT_DOMAINS", "").split(",")[0]
    if domain:
        return f"https://{domain}"
    return "https://energyriskiq.com"

CHALLENGE_TTL_SECONDS = 15 * 60
_challenges: dict = {}
_challenges_lock = threading.Lock()


def _cleanup_challenges():
    now = time.time()
    expired = [k for k, v in _challenges.items() if v['expires'] < now]
    for k in expired:
        _challenges.pop(k, None)


def _issue_challenge() -> dict:
    a, b = random.randint(2, 9), random.randint(2, 9)
    challenge_id = secrets.token_urlsafe(24)
    with _challenges_lock:
        _cleanup_challenges()
        _challenges[challenge_id] = {'answer': a + b, 'expires': time.time() + CHALLENGE_TTL_SECONDS}
    return {'challenge_id': challenge_id, 'question': f"What is {a} + {b}?"}


def _verify_challenge(challenge_id: str, answer) -> bool:
    with _challenges_lock:
        _cleanup_challenges()
        entry = _challenges.pop(challenge_id or '', None)
    if not entry:
        return False
    try:
        return int(str(answer).strip()) == entry['answer']
    except (ValueError, TypeError):
        return False

class ContactForm(BaseModel):
    name: str
    email: str
    subject: str
    message: str
    
    @field_validator('email')
    @classmethod
    def validate_email(cls, v):
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, v):
            raise ValueError('Invalid email address')
        return v


def send_contact_email_brevo(form: ContactForm) -> dict:
    api_key = os.environ.get('BREVO_API_KEY')
    if not api_key:
        raise HTTPException(status_code=500, detail="Email service not configured")
    
    email_from = os.environ.get('EMAIL_FROM', 'EnergyRiskIQ <alerts@energyriskiq.com>')
    
    safe_name = html.escape(form.name)
    safe_email = html.escape(form.email)
    safe_subject = html.escape(form.subject)
    safe_message = html.escape(form.message)
    
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #1e293b;">New Contact Form Submission</h2>
        <hr style="border: 1px solid #e2e8f0;">
        <p><strong>From:</strong> {safe_name}</p>
        <p><strong>Email:</strong> {safe_email}</p>
        <p><strong>Subject:</strong> {safe_subject}</p>
        <hr style="border: 1px solid #e2e8f0;">
        <h3 style="color: #64748b;">Message:</h3>
        <p style="white-space: pre-wrap; background: #f8fafc; padding: 1rem; border-radius: 8px;">{safe_message}</p>
        <hr style="border: 1px solid #e2e8f0;">
        <p style="color: #94a3b8; font-size: 12px;">This message was sent via the EnergyRiskIQ contact form.</p>
    </div>
    """
    
    payload = {
        "sender": {"email": email_from.split('<')[1].rstrip('>') if '<' in email_from else email_from, "name": "EnergyRiskIQ Contact Form"},
        "to": [{"email": CONTACT_EMAIL, "name": "EnergyRiskIQ Support"}],
        "replyTo": {"email": form.email, "name": form.name},
        "subject": f"[Contact Form] {form.subject}",
        "htmlContent": html_content
    }
    
    headers = {
        "api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    response = requests.post(
        "https://api.brevo.com/v3/smtp/email",
        json=payload,
        headers=headers,
        timeout=30
    )
    
    if response.status_code in (200, 201):
        result = response.json()
        logger.info(f"Contact email sent successfully. Message ID: {result.get('messageId')}")
        return {"success": True, "message_id": result.get("messageId")}
    else:
        logger.error(f"Brevo API error: {response.status_code} - {response.text}")
        raise HTTPException(status_code=500, detail="Failed to send message. Please try again later.")


def _send_confirmation_email(name: str, email: str, subject: str, token: str):
    """Send the 'Confirm Email Address' email to the visitor."""
    api_key = os.environ.get('BREVO_API_KEY')
    if not api_key:
        raise HTTPException(status_code=500, detail="Email service not configured")

    email_from = os.environ.get('EMAIL_FROM', 'EnergyRiskIQ <alerts@energyriskiq.com>')
    confirm_link = f"{_base_url()}/contact/confirmation#token={token}"

    safe_name = html.escape(name)
    safe_subject = html.escape(subject)

    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #ffffff; padding: 24px;">
        <h2 style="color: #1e293b;">Confirm your email address</h2>
        <p style="color: #334155; font-size: 15px; line-height: 1.6;">Hi {safe_name},</p>
        <p style="color: #334155; font-size: 15px; line-height: 1.6;">
            You recently submitted a message to the EnergyRiskIQ team via our contact page
            (subject: &ldquo;{safe_subject}&rdquo;).
        </p>
        <p style="color: #334155; font-size: 15px; line-height: 1.6;">
            To make sure this email address belongs to you, please confirm it below.
            <strong>Your message will only be delivered to our team after you confirm.</strong>
        </p>
        <div style="text-align: center; margin: 32px 0;">
            <a href="{confirm_link}"
               style="background: #2563eb; color: #ffffff; text-decoration: none; font-weight: bold;
                      font-size: 16px; padding: 14px 32px; border-radius: 8px; display: inline-block;">
                Confirm Email Address
            </a>
        </div>
        <p style="color: #64748b; font-size: 13px; line-height: 1.6;">
            This link expires in {CONFIRM_TTL_HOURS} hours. If you did not submit a message on
            energyriskiq.com, you can safely ignore this email &mdash; nothing will be sent and no
            information will be stored.
        </p>
        <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0;">
        <p style="color: #94a3b8; font-size: 12px;">EnergyRiskIQ &middot; Energy Risk Intelligence</p>
    </div>
    """

    payload = {
        "sender": {"email": email_from.split('<')[1].rstrip('>') if '<' in email_from else email_from, "name": "EnergyRiskIQ"},
        "to": [{"email": email, "name": name}],
        "subject": "Confirm your email to deliver your message to EnergyRiskIQ",
        "htmlContent": html_content
    }
    headers = {"api-key": api_key, "Content-Type": "application/json", "Accept": "application/json"}
    response = requests.post("https://api.brevo.com/v3/smtp/email", json=payload, headers=headers, timeout=30)
    if response.status_code not in (200, 201):
        logger.error(f"Brevo confirmation email error: {response.status_code} - {response.text}")
        raise HTTPException(status_code=500, detail="Could not send the confirmation email. Please try again later.")
    logger.info(f"Contact confirmation email sent to visitor. Message ID: {response.json().get('messageId')}")


@router.get("/contact")
async def contact_page():
    """Serve the standalone Contact page."""
    static_path = os.path.join(os.path.dirname(__file__), "..", "static", "contact.html")
    return FileResponse(os.path.abspath(static_path), media_type="text/html")


@router.get("/api/contact/challenge")
async def contact_challenge():
    """Issue a human-check challenge for the contact page."""
    return _issue_challenge()


class ContactPageForm(ContactForm):
    challenge_id: str
    challenge_answer: str
    website: str = ""  # honeypot — must stay empty


@router.post("/api/contact/submit")
async def submit_contact_page_form(form: ContactPageForm):
    if form.website.strip():
        # Honeypot filled → bot. Pretend success, send nothing.
        return {"success": True, "message": "Your message has been sent successfully."}
    if not _verify_challenge(form.challenge_id, form.challenge_answer):
        raise HTTPException(status_code=400, detail="Human check failed. Please answer the question correctly and try again.")
    if not form.name.strip():
        raise HTTPException(status_code=400, detail="Name is required")
    if not form.subject.strip():
        raise HTTPException(status_code=400, detail="Subject is required")
    if not form.message.strip():
        raise HTTPException(status_code=400, detail="Message is required")
    if len(form.message) > 5000:
        raise HTTPException(status_code=400, detail="Message is too long (max 5000 characters)")

    # Store as a pending message; nothing is delivered or persisted permanently
    # until the visitor confirms their email address.
    token = secrets.token_urlsafe(32)
    with get_cursor() as cur:
        # Opportunistic cleanup of expired, never-confirmed submissions.
        cur.execute("""
            DELETE FROM contact_pending_messages
            WHERE confirmed_at IS NULL AND expires_at < (NOW() AT TIME ZONE 'UTC')
        """)
        cur.execute("""
            INSERT INTO contact_pending_messages (token, name, email, subject, message, expires_at)
            VALUES (%s, %s, %s, %s, %s, (NOW() AT TIME ZONE 'UTC') + make_interval(hours => %s))
        """, (token, form.name.strip(), form.email.strip(), form.subject.strip(), form.message, CONFIRM_TTL_HOURS))

    try:
        _send_confirmation_email(form.name.strip(), form.email.strip(), form.subject.strip(), token)
    except HTTPException:
        # Confirmation email failed — remove the pending row so nothing lingers.
        with get_cursor() as cur:
            cur.execute("DELETE FROM contact_pending_messages WHERE token = %s", (token,))
        raise

    return {
        "success": True,
        "requires_confirmation": True,
        "message": "Almost done! We've sent a confirmation email to your address. Click the \"Confirm Email Address\" button in that email to deliver your message to our team."
    }


class ConfirmTokenBody(BaseModel):
    token: str


@router.get("/contact/confirmation")
async def contact_confirmation_page():
    """Serve the contact email confirmation page."""
    static_path = os.path.join(os.path.dirname(__file__), "..", "static", "contact-confirmation.html")
    return FileResponse(os.path.abspath(static_path), media_type="text/html")


@router.post("/api/contact/confirm-message")
async def confirm_contact_message(body: ConfirmTokenBody):
    """Visitor clicked the confirmation link: deliver the message and save the visitor."""
    token = (body.token or "").strip()
    if not token or len(token) > 128:
        raise HTTPException(status_code=400, detail="Invalid confirmation link.")

    with get_cursor() as cur:
        cur.execute("""
            SELECT id, name, email, subject, message, confirmed_at,
                   expires_at < (NOW() AT TIME ZONE 'UTC') AS expired
            FROM contact_pending_messages
            WHERE token = %s
        """, (token,))
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=400, detail="This confirmation link is invalid or has already expired.")
    if row['confirmed_at'] is not None:
        return {"success": True, "already_confirmed": True,
                "message": "Your email was already confirmed and your message has been delivered to our team."}
    if row['expired']:
        with get_cursor() as cur:
            cur.execute("DELETE FROM contact_pending_messages WHERE id = %s", (row['id'],))
        raise HTTPException(status_code=410, detail="This confirmation link has expired. Please submit your message again.")

    # Atomically claim the row so double-clicks can't deliver twice.
    with get_cursor() as cur:
        cur.execute("""
            UPDATE contact_pending_messages
            SET confirmed_at = (NOW() AT TIME ZONE 'UTC')
            WHERE id = %s AND confirmed_at IS NULL
            RETURNING id
        """, (row['id'],))
        claimed = cur.fetchone()
    if not claimed:
        return {"success": True, "already_confirmed": True,
                "message": "Your email was already confirmed and your message has been delivered to our team."}

    try:
        send_contact_email_brevo(ContactForm(
            name=row['name'], email=row['email'], subject=row['subject'], message=row['message']
        ))
    except Exception:
        # Delivery failed — release the claim so the visitor can retry the link.
        with get_cursor() as cur:
            cur.execute("UPDATE contact_pending_messages SET confirmed_at = NULL WHERE id = %s", (row['id'],))
        raise HTTPException(status_code=500, detail="We could not deliver your message right now. Please try the link again in a few minutes.")

    # Only now is the visitor's name/email persisted.
    try:
        with get_cursor() as cur:
            cur.execute("""
                INSERT INTO contact_visitors (name, email)
                VALUES (%s, %s)
                ON CONFLICT (email) DO UPDATE SET
                    name = EXCLUDED.name,
                    last_contact_at = (NOW() AT TIME ZONE 'UTC'),
                    messages_count = contact_visitors.messages_count + 1
            """, (row['name'], row['email']))
    except Exception as e:
        logger.error(f"contact_visitors upsert failed (message already delivered): {e}")

    return {"success": True, "message": "Your email address is confirmed and your message has been delivered to our team."}


@router.post("/contact")
async def submit_contact_form(form: ContactForm):
    if not form.name.strip():
        raise HTTPException(status_code=400, detail="Name is required")
    if not form.subject.strip():
        raise HTTPException(status_code=400, detail="Subject is required")
    if not form.message.strip():
        raise HTTPException(status_code=400, detail="Message is required")
    if len(form.message) > 5000:
        raise HTTPException(status_code=400, detail="Message is too long (max 5000 characters)")
    
    result = send_contact_email_brevo(form)
    
    return {
        "success": True,
        "message": "Your message has been sent successfully."
    }
