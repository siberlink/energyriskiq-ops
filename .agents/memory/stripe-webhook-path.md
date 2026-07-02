---
name: Stripe webhook path mismatch
description: Why the billing webhook lives at two paths and how the 404 handler masks routing bugs
---

The Stripe **billing router prefix is `/billing`** (not `/api/v1`), so its
routes are `/billing/webhook`, `/billing/plans`, `/billing/checkout`,
`/billing/cancel`, `/billing/portal` — and the frontend calls those `/billing/*`
paths. Only some other routers (tickets, indices, digest, eriq) use an
`/api/v1/...` prefix.

The **live Stripe dashboard webhook is configured for
`https://energyriskiq.com/api/v1/billing/webhook`** (5 events:
checkout.session.completed, customer.subscription.deleted/updated, invoice.paid,
invoice.payment_failed). To satisfy that without a dashboard change, the same
`stripe_webhook` handler is aliased at `/api/v1/billing/webhook` via
`app.add_api_route(...)` in `src/api/app.py`, in addition to `/billing/webhook`.

**Why this bit us:** the global `StarletteHTTPException` handler in
`src/api/app.py` redirects **all 404s to `/` with a 302**. So any external POST
(Stripe, other webhooks) to a slightly-wrong path returns 302, which Stripe
counts as a delivery failure ("other errors while sending") — the real problem
(404 / no matching route) is hidden.

**How to apply:** when an external integration reports non-2xx/redirect
webhook failures, check the *exact* configured URL against the actual FastAPI
route prefix first; a 302→`/` almost always means the path 404'd. Live webhook
signing secret is `STRIPE_WEBHOOK_SECRET` (sandbox: `STRIPE_SANDBOX_WEBHOOK_SECRET`),
selected by `get_webhook_secret()` per the DB stripe_mode.
