---
name: Stripe sub-product mode-awareness split
description: How standalone €-priced Stripe sub-products (WTI Pro Widget, Indices History) must split mode-aware vs mode-agnostic entitlement checks
---

EnergyRiskIQ has small standalone Stripe subscription products separate from the main user plan (e.g. WTI Pro Widget, Indices History downloads). Each gets its own table + routes module mirroring `wti_pro_widget_routes.py`.

Rule — two distinct active-checks per sub-product:
- **Mode-aware** (`_active_for_mode`: status active AND row stripe_mode == get_stripe_mode(), NULL mode = current) → used ONLY for account management: status endpoint, checkout (avoid duplicate sub), cancel.
- **Mode-agnostic** (`_is_active`: status in active/trialing/canceling) → used for the actual RUNTIME entitlement (WTI widget embed render; Indices History `/download`).

**Why:** a paying subscriber must never be denied the service they paid for just because the app's Stripe mode was toggled live↔sandbox. But account management stays mode-aware so a throwaway sandbox test sub doesn't block a real live purchase.

**How to apply:** tag rows with stripe_mode derived from the Stripe object's `livemode` (NOT get_stripe_mode()) at activation, in BOTH the webhook-independent `/confirm` and the webhook checkout handler. Webhook routing in `webhook_handler.py` branches on `session.metadata.type`; every new sub-product MUST add its table to the invoice-isolation checks in BOTH `handle_invoice_paid` AND `handle_invoice_payment_failed` (easy to miss the failed one) so its billing never mutates the main user_plans state.
