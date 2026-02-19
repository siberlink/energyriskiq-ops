import os
import re
import logging
import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator
from typing import Optional

logger = logging.getLogger(__name__)

router = APIRouter(tags=["signals"])

VALID_ROLES = {"Energy Analyst", "Portfolio Manager", "Risk Manager", "Trader", "Other"}


class SignalsSignupForm(BaseModel):
    email: str
    first_name: Optional[str] = None
    role: Optional[str] = None

    @field_validator('email')
    @classmethod
    def validate_email(cls, v):
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, v.strip()):
            raise ValueError('Invalid email address')
        return v.strip().lower()

    @field_validator('role')
    @classmethod
    def validate_role(cls, v):
        if v and v not in VALID_ROLES:
            raise ValueError(f'Invalid role. Must be one of: {", ".join(sorted(VALID_ROLES))}')
        return v


@router.post("/api/v1/signals/signup")
async def signals_signup(form: SignalsSignupForm):
    api_key = os.environ.get('BREVO_API_KEY')
    if not api_key:
        raise HTTPException(status_code=500, detail="Email service not configured")

    template_id = int(os.environ.get('BREVO_DOI_TEMPLATE_ID', '0'))
    list_id = int(os.environ.get('BREVO_SIGNALS_LIST_ID', '0'))

    if not template_id or not list_id:
        logger.error("BREVO_DOI_TEMPLATE_ID or BREVO_SIGNALS_LIST_ID not configured")
        raise HTTPException(status_code=500, detail="Signup service not fully configured. Please contact support.")

    base_url = os.environ.get('BASE_URL', 'https://energyriskiq.com')
    redirection_url = f"{base_url}/energy-risk-intelligence-signals?verified=true"

    attributes = {}
    if form.first_name and form.first_name.strip():
        attributes["FIRSTNAME"] = form.first_name.strip()[:100]
    if form.role:
        attributes["ROLE"] = form.role

    payload = {
        "email": form.email,
        "templateId": template_id,
        "redirectionUrl": redirection_url,
        "includeListIds": [list_id],
        "attributes": attributes
    }

    headers = {
        "api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    try:
        response = requests.post(
            "https://api.brevo.com/v3/contacts/doubleOptinConfirmation",
            json=payload,
            headers=headers,
            timeout=30,
        )

        logger.info(f"Brevo DOI response: {response.status_code}")

        if response.status_code in (200, 201, 204):
            logger.info(f"DOI signup initiated for {form.email}")
            return {
                "success": True,
                "message": "Please check your email to confirm your subscription."
            }
        elif response.status_code == 400:
            error_data = response.json() if response.text else {}
            error_msg = error_data.get("message", "")
            if "already exist" in error_msg.lower() or "Contact already in list" in error_msg:
                return {
                    "success": True,
                    "message": "You're already subscribed! Check your inbox for our latest signals."
                }
            logger.error(f"Brevo DOI error 400: {response.text}")
            raise HTTPException(status_code=400, detail="Could not process signup. Please check your email and try again.")
        else:
            logger.error(f"Brevo DOI error {response.status_code}: {response.text}")
            raise HTTPException(status_code=500, detail="Signup service temporarily unavailable. Please try again later.")
    except requests.RequestException as e:
        logger.error(f"Brevo DOI request failed: {e}")
        raise HTTPException(status_code=500, detail="Could not connect to signup service. Please try again later.")
