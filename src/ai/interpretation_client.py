"""Credential routing and explicit provenance for index narrative generation.

No connection is made here. Callers retain their deterministic fallback and
return a plain string, while optionally collecting diagnostics for stage audits.
"""
import os


def client_options():
    key = os.getenv("AI_INTEGRATIONS_OPENAI_API_KEY")
    url = os.getenv("AI_INTEGRATIONS_OPENAI_BASE_URL")
    if key and url:
        return {"api_key": key, "base_url": url}, "integration"
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return None, "none"
    options = {"api_key": key}
    if os.getenv("OPENAI_BASE_URL"):
        options["base_url"] = os.environ["OPENAI_BASE_URL"]
    return options, "direct"


def record_status(status, *, missing, source, reason=None):
    if status is not None:
        status.clear()
        status.update(ai_section_missing=missing, ai_source=source)
        if reason:
            # Never include URLs, credentials, exception messages or response bodies.
            status["ai_fallback_reason"] = reason
