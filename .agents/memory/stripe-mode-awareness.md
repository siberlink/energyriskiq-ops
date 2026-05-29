---
name: Stripe mode awareness (widgets / billing)
description: How the admin-switchable live/sandbox Stripe mode interacts with subscription state
---
There is a single global Stripe mode (live|sandbox) stored in `app_settings.stripe_mode`, read via
`get_stripe_mode()`, switchable by admin. All Stripe API calls and webhook secret selection follow
the CURRENT mode. This causes mode contamination: a sandbox test sub on an account can block a real
live purchase unless rows are tagged by mode.

**Rule:** Tag each subscription row with the mode it belongs to, derived from Stripe's own `livemode`
flag (NOT `get_stripe_mode()`, which is mutable and can drift if admin flips mode after checkout).
Keep two distinct activeness checks:
- status-only check for the PUBLIC EMBED runtime, so a paying customer's widget keeps rendering even
  when the admin toggles modes.
- mode-aware check (status active AND row.mode == current mode; NULL legacy => current) for the ACCOUNT
  management flow: status `active` field, checkout short-circuit, confirm short-circuit, cancel guard.

**Why:** User priority was "live widget payments activate reliably and cancellation works" on an app
where the same account had a leftover sandbox sub. Webhook signature verification only uses the current
mode's secret, so the webhook-independent confirm endpoint (frontend polls it on checkout return) is the
reliable activation path; do not rely on webhooks alone.

**Known remaining limitation (not implemented, would be a larger refactor — consult user):** single row
per (user_id, widget_code) stores only one sub; it cannot hold both a live and sandbox sub simultaneously.
Latest activation overwrites. Per-mode rows (unique on user_id+widget_code+stripe_mode) would fully fix it.
