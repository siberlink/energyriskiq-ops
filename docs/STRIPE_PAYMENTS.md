# Stripe Payments — How It Works

This document explains how Stripe payments work across EnergyRiskIQ so that any
future payment feature follows the same patterns. Read this before implementing
anything that touches Stripe.

---

## 1. The Admin Live / Sandbox switch (read this first)

The whole app runs in **one global Stripe mode at a time**: either `live` or
`sandbox`. An admin flips this from the **Admin account screen** (it is not a
per-user setting). Everything Stripe-related follows whatever mode is currently
selected.

- **Where the mode is stored:** the `app_settings` table, key `stripe_mode`
  (value `live` or `sandbox`). Default is `live` if the row is missing.
- **Admin toggle endpoints:** `GET /admin/stripe-mode` and `PUT /admin/stripe-mode`
  in `src/api/admin_routes.py`.
- **Read / write the mode in code:** `get_stripe_mode()` and `set_stripe_mode(mode)`
  in `src/billing/stripe_client.py`. `set_stripe_mode()` writes the DB **and**
  calls `_reinit_stripe()` so the running process immediately uses the new key.

### Which credentials each mode uses
`get_stripe_credentials_for_mode(mode)` in `src/billing/stripe_client.py`:

| Mode | Publishable key | Secret key | Webhook secret |
|------|-----------------|------------|----------------|
| `live` | `STRIPE_PUBLISHABLE_KEY` | `STRIPE_SECRET_KEY` | `STRIPE_WEBHOOK_SECRET` |
| `sandbox` | `STRIPE_SANDBOX_PUBLISHABLE_KEY` | `STRIPE_SANDBOX_SECRET_KEY` | `STRIPE_SANDBOX_WEBHOOK_SECRET` |

(`live` mode can also fall back to Replit Stripe connector credentials if the
secrets are not set.) The webhook secret is chosen by `get_webhook_secret()`,
which also follows the current mode.

### The single most important consequence
**Every Stripe API call, customer ID, subscription ID, price ID, and webhook
signature is mode-specific.** A customer/subscription/price created in sandbox
does **not** exist in live, and vice versa. This is the root cause of almost
every payment bug in this app. Whenever you implement a payment feature you must:

1. Pick the price/product ID for the **current mode** (most tables store both a
   live column and a `_sandbox` column — see plans below).
2. Validate any stored `stripe_customer_id` against the current mode before
   reusing it, and recreate/look it up if it belongs to the other mode.
3. Tag any persisted subscription with the mode it belongs to (derive it from
   Stripe's own `livemode` flag, **not** from `get_stripe_mode()`, because the
   admin can flip the toggle after checkout). See the WTI Pro widget for the
   reference implementation of mode-tagged subscription rows.

### Known limitations
- **Multi-worker staleness:** the mode is cached in a module global
  (`_current_stripe_mode`). When an admin flips the mode, only the worker that
  handled the request reinitialises immediately; other workers pick up the new
  mode on their next `get_stripe_mode()` call (which re-reads the DB) or on
  restart. This is a pre-existing, app-wide limitation.
- **Webhooks are verified against the current mode's secret only.** If a live
  webhook arrives while the app is set to sandbox it will be rejected. For this
  reason, do not rely on webhooks alone for activation — provide a
  webhook-independent "confirm" path that lists the user's subscriptions in the
  current mode and activates from that (the WTI Pro widget does this).

---

## 2. Subscription plans (Personal / Trader / Pro / Enterprise)

This is the main tiered-subscription system. The user-facing pricing UI is
currently **hidden** but the backend is fully working and unchanged.

### Tiers and prices
`free`, `personal`, `trader`, `pro`, `enterprise`. Reference EUR prices live in
`PLAN_PRICE_EUR` in `src/billing/stripe_client.py` (Personal €9.95, Trader €29,
Pro €49, Enterprise €129). The authoritative prices and Stripe IDs live in the
DB.

### Where plans are stored
- Table: `plan_settings` (defined and seeded in `src/db/migrations.py` via
  `seed_plan_settings()`).
- Each row stores BOTH modes' Stripe IDs: `stripe_product_id` / `stripe_price_id`
  (live) and `stripe_product_id_sandbox` / `stripe_price_id_sandbox` (sandbox),
  plus `monthly_price_usd`, `currency`, and feature limits
  (`allowed_alert_types`, `max_regions`, `max_email_alerts_per_day`,
  `delivery_config`, `is_active`).
- `get_plan_stripe_ids(plan_code)` / `get_plan_with_stripe_ids(plan_code)` return
  the correct IDs for the **current mode**.

### Plans API and UI
- `GET /billing/plans` (`src/billing/billing_routes.py`) returns active plans
  (mode-aware), plus free-trial days and promo-banner state.
- The pricing/plan cards UI lives in `src/static/users-account.html` (the
  `ws-plan-card` billing section). It is the page the admin asked to hide for now;
  the endpoints behind it remain live.

### Checkout flow (`POST /billing/checkout`)
1. Authenticate the user from their session token.
2. Look up the plan's price ID for the current mode.
3. **If the user already has an active/trialing subscription** → update it in
   place with `update_subscription()` (proration `always_invoice`) and apply the
   new plan immediately. If that fails because the stored sub belongs to the
   other mode, clear it and fall through to a fresh checkout.
4. **Validate `stripe_customer_id`** against the current mode; if it's invalid
   (wrong mode / deleted) clear it and create a new customer with
   `create_customer(email, user_id)` (sets `metadata.user_id`).
5. Create a Stripe Checkout Session (`create_checkout_session`) with
   `metadata.user_id`, success URL `/users/account?billing=success&plan=...`,
   cancel URL `/users/account?billing=cancelled`, and a trial period if
   `free_trial_days` is set.
6. Return the checkout URL; the frontend redirects to Stripe.

### Other billing endpoints
- `POST /billing/portal` → Stripe Billing Portal session for self-service
  management.
- `GET /billing/subscription` → current plan + live subscription status.
- `POST /billing/cancel` → cancel at period end (sets local status `canceling`).
- `GET /billing/config` → publishable key for Stripe.js (mode-aware).

---

## 3. Webhooks

- **Endpoint:** `POST /billing/webhook` (`src/billing/billing_routes.py`).
  Verifies the signature with `construct_webhook_event()` using the current
  mode's secret, then dispatches via `process_webhook_event()`.
- **Dispatcher:** `process_webhook_event()` in `src/billing/webhook_handler.py`
  routes by event type:
  - `checkout.session.completed` → set the user's plan + grant initial token
    allowance. **Branches early for non-plan products by `metadata.type`**
    (`eriq_tokens`, `wti_pro_widget`).
  - `customer.subscription.updated` → update status / plan (widget handler gets
    first refusal).
  - `customer.subscription.deleted` → downgrade user to `free` (widget handler
    gets first refusal).
  - `invoice.paid` → mark active + reset monthly token allowance.
  - `invoice.payment_failed` → mark `past_due`.
- **Product isolation:** widget and token subscriptions must NOT touch main
  `user_plans` state. Handlers check `metadata.type` and the `user_pro_widgets`
  table before applying plan logic. Any new product type must follow this same
  isolation pattern.

---

## 4. Stripe customer lifecycle

- One Stripe customer per user, created lazily during checkout via
  `create_customer(email, user_id)` with `metadata.user_id`.
- The ID is stored on `users.stripe_customer_id`.
- Because customers are mode-specific, both checkout and the widget confirm flow
  validate the stored ID against the current mode and, if it's wrong, either
  recreate it or look it up with `stripe.Customer.search(metadata['user_id'])`.

---

## 5. Checklist for adding a new paid feature

1. Decide the product type and give it a `metadata.type` so webhooks can route /
   isolate it.
2. Store any price/product IDs for **both** modes (live + `_sandbox`).
3. On checkout: pick IDs for the current mode, validate/create the customer,
   set `metadata.user_id` (and `metadata.type`).
4. Persist any subscription row **tagged with the mode**, derived from the
   subscription's `livemode` flag.
5. Provide a **webhook-independent confirm** path (list current-mode subs and
   activate) so activation does not depend on webhook delivery/mode alignment.
6. In webhook handlers, isolate the new product from `user_plans` plan logic.
7. Make any "is this active?" check that drives the **management UI** mode-aware,
   but keep public/runtime checks status-only so paying customers aren't affected
   when the admin toggles modes.
