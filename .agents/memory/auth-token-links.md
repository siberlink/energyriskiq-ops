---
name: Auth token links in emails
description: How to send login/reset tokens via email links without leaking them
---
Rule: email-delivered auth tokens (magic login, password reset) must be single-use (atomic DELETE..RETURNING on exchange), short-lived, and must NOT sit in URL query strings on pages that load analytics.

**Why:** users.html loads Google Analytics in <head> before any JS scrub runs, so `?token=` leaks to third parties; a live token = account takeover. Architect review blocked query-string tokens twice.

**How to apply:** put tokens in the URL fragment (`#rt=...` — never sent to servers/analytics/Referer), scrub with history.replaceState on load, exchange via JS POST (email scanners only GET, so they don't burn single-use tokens). Throttle request endpoints (per-email + per-IP) and always return a generic message to prevent account enumeration. Invalidate sessions + outstanding magic-login tokens on password reset.
