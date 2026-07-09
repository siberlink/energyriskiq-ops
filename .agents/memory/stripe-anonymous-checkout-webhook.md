---
name: Anonymous checkout webhook dispatch order
description: Sub-products whose Stripe checkout is anonymous (no main-app user) must be dispatched before user_id resolution in the checkout webhook chain.
---

The main `checkout.session.completed` handler resolves a main-app `user_id` early and returns if none is found. Sub-products that use anonymous checkout (Stripe collects email; no `metadata.user_id`, no existing customer) never resolve a user_id, so their dispatch check must run BEFORE that resolution block, or the webhook silently drops the event.

**Why:** The Brent Forecast product (dedicated user table, account created from checkout email) was initially registered after the user_id early-return and its checkout webhook could never fire; only the webhook-independent /confirm path saved it.

**How to apply:** Any new standalone paid product with anonymous checkout: put its `metadata.type` dispatch at the very top of `handle_checkout_session_completed`, before user_id lookup. Products tied to logged-in main-app users can stay in the normal chain.
