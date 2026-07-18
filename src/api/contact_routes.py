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

logger = logging.getLogger(__name__)

router = APIRouter(tags=["contact"])

CONTACT_EMAIL = "emil@energyriskiq.com"

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
    send_contact_email_brevo(form)
    return {"success": True, "message": "Your message has been sent successfully."}


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
