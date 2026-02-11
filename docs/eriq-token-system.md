# ERIQ Token Economy — System Documentation

**Last Updated:** February 2026

---

## 1. Overview

The ERIQ Token Economy controls usage of the ERIQ Expert Analyst AI assistant. Every ERIQ question consumes tokens (based on the OpenAI API's `total_tokens` count for the request). Users receive a free monthly token allowance based on their subscription plan and can purchase additional tokens via Stripe.

**Core Principle:** Two-tier balance system — monthly allowance (resets each billing cycle) + purchased balance (never resets, persists indefinitely).

---

## 2. Plan Monthly Allowances

| Plan       | Monthly Allowance | Price to Purchase More     |
|------------|------------------:|----------------------------|
| Free       |        50,000     | N/A (no purchase option)   |
| Personal   |       100,000     | 1.35 EUR per 100K tokens   |
| Trader     |       300,000     | 1.35 EUR per 100K tokens   |
| Pro        |       500,000     | 1.35 EUR per 100K tokens   |
| Enterprise |     1,000,000     | 1.35 EUR per 100K tokens   |

**Configuration:** `PLAN_TOKEN_ALLOWANCE` dict in `src/eriq/tokens.py`

---

## 3. Token Purchase Packs

Users can purchase additional tokens in fixed packs at 1.35 EUR per 100K tokens:

| Pack Label | Tokens    | Price (EUR) |
|------------|----------:|------------:|
| 100K       |   100,000 |        1.35 |
| 300K       |   300,000 |        4.05 |
| 500K       |   500,000 |        6.75 |
| 1M         | 1,000,000 |       13.50 |

**Configuration:** `TOKEN_PACKS` list in `src/eriq/tokens.py`

---

## 4. Database Schema

### `eriq_token_balances` (one row per user)

| Column                  | Type      | Description                                          |
|-------------------------|-----------|------------------------------------------------------|
| `user_id`               | INTEGER   | Primary key, references `users(id)`                  |
| `plan_monthly_allowance`| INTEGER   | The user's current plan allowance (e.g. 100000)      |
| `allowance_remaining`   | INTEGER   | How much of this month's allowance is left            |
| `purchased_balance`     | INTEGER   | Purchased tokens that never reset                    |
| `period_start`          | TIMESTAMP | When the current billing period started               |
| `updated_at`            | TIMESTAMP | Last modification time                               |

### `eriq_token_ledger` (audit trail, append-only)

| Column         | Type        | Description                                        |
|----------------|-------------|----------------------------------------------------|
| `id`           | SERIAL      | Primary key                                        |
| `user_id`      | INTEGER     | References `users(id)`                             |
| `delta_tokens` | INTEGER     | Positive = credit, negative = deduction            |
| `source`       | VARCHAR(50) | Type of transaction (see Section 5)                |
| `ref_info`     | TEXT        | Reference for idempotency / traceability           |
| `created_at`   | TIMESTAMP   | When the transaction occurred                      |

**Index:** `idx_eriq_token_ledger_user_date` on `(user_id, created_at)`

---

## 5. Ledger Source Types

Every token transaction is recorded in `eriq_token_ledger` with a `source` field:

| Source            | Description                                              | `ref_info` Format                          |
|-------------------|----------------------------------------------------------|--------------------------------------------|
| `allowance_grant` | Initial allowance when balance row is first created       | `"Monthly allowance granted"`              |
| `stripe_renewal`  | Monthly allowance reset triggered by Stripe invoice.paid  | `"invoice:{stripe_invoice_id}"`            |
| `monthly_reset`   | Lazy monthly reset (fallback if webhook not received)     | `"Monthly reset for {YYYY-MM}"`            |
| `plan_upgrade`    | Difference tokens granted on plan upgrade                 | `"upgrade:{subscription_id}:{plan}:{YYYY-MM}"` |
| `purchase`        | One-time token purchase via Stripe                        | `"stripe:{checkout_session_id}"`           |
| `usage`           | Token deduction from ERIQ question                        | `"conversation:{id}"` or `"eriq_usage"`    |

---

## 6. Token Lifecycle — How It All Works

### 6.1 Initial Subscription (First-Time Plan Purchase)

**Trigger:** Stripe `checkout.session.completed` webhook (subscription mode)

**Flow:**
1. Webhook handler identifies the plan from the Stripe subscription price ID
2. Calls `reset_monthly_allowance_on_payment(user_id, plan_code, session_id)`
3. Creates or updates the `eriq_token_balances` row with the full plan allowance
4. Logs a `stripe_renewal` entry in the ledger with `ref_info = "invoice:{session_id}"`

**Example:** User subscribes to Personal plan → receives 100,000 tokens immediately.

**File:** `src/billing/webhook_handler.py` → `handle_checkout_session_completed()`

### 6.2 Monthly Renewal

**Trigger:** Stripe `invoice.paid` webhook (fires each billing cycle)

**Flow:**
1. Webhook handler retrieves subscription → determines plan from price ID
2. Calls `reset_monthly_allowance_on_payment(user_id, plan_code, invoice_id)`
3. Resets `allowance_remaining` to the full plan allowance
4. Updates `period_start` to current time
5. `purchased_balance` is NOT touched — purchased tokens persist
6. Idempotency: checks ledger for existing `stripe_renewal` with same invoice ID

**Example:** Trader user's monthly payment → `allowance_remaining` reset to 300,000. Their purchased tokens remain unchanged.

**File:** `src/billing/webhook_handler.py` → `handle_invoice_paid()`

### 6.3 Lazy Monthly Reset (Fallback)

**Trigger:** When a user makes an ERIQ query and `period_start` is from a previous month

**Purpose:** Safety net for cases where the Stripe webhook didn't fire or was missed. Ensures users always get their monthly reset even without the webhook.

**Flow:**
1. `get_token_status()` calls `_maybe_reset_monthly()`
2. Compares `period_start` against the first day of the current month
3. If `period_start` is from a previous month, resets the allowance

**File:** `src/eriq/tokens.py` → `_maybe_reset_monthly()`

### 6.4 Plan Upgrade

**Trigger:** Stripe `customer.subscription.updated` webhook

**Flow:**
1. Webhook handler determines the new plan from the updated subscription
2. Calls `handle_plan_upgrade_tokens(user_id, new_plan, subscription_id)`
3. Compares `new_allowance` vs current `plan_monthly_allowance`
4. If upgrade: credits the **difference** (bonus = new_allowance - old_allowance) to `allowance_remaining`
5. Updates `plan_monthly_allowance` to the new value
6. Idempotency: checks ledger for `plan_upgrade` with key `upgrade:{subscription_id}:{plan}:{YYYY-MM}`

**Upgrade Examples:**
- Personal (100K) → Trader (300K): user receives +200K tokens
- Personal (100K) → Pro (500K): user receives +400K tokens
- Trader (300K) → Enterprise (1M): user receives +700K tokens

**File:** `src/billing/webhook_handler.py` → `handle_subscription_updated()` / `src/eriq/tokens.py` → `handle_plan_upgrade_tokens()`

### 6.5 Plan Downgrade

**Trigger:** Stripe `customer.subscription.updated` webhook (when new plan allowance < old plan allowance)

**Flow:**
1. Same entry point as upgrade
2. Updates `plan_monthly_allowance` to the lower value
3. Clamps `allowance_remaining` so it does not exceed the new plan allowance
4. `purchased_balance` is NOT touched — purchased tokens are never removed

**Example:** Pro (500K) → Personal (100K): if user had 450K remaining, it is clamped to 100K. If they had 80K remaining, it stays at 80K.

### 6.6 Token Purchase

**Trigger:** User initiates purchase via `POST /api/v1/eriq/tokens/checkout` → Stripe `checkout.session.completed` webhook (one-time payment mode with `metadata.type = "eriq_tokens"`)

**Flow:**
1. User selects a token pack on the account page
2. API creates a Stripe Checkout Session (`mode="payment"`, not subscription)
3. Metadata includes `type: "eriq_tokens"`, `user_id`, and `token_pack`
4. On successful payment, webhook calls `handle_token_purchase_webhook()`
5. Idempotency: checks ledger for existing `purchase` with `ref_info = "stripe:{session_id}"`
6. Credits tokens to `purchased_balance` (not `allowance_remaining`)
7. Purchased tokens never reset — they persist across billing cycles

**File:** `src/api/eriq_routes.py` → `eriq_token_checkout()` + `handle_token_purchase_webhook()` / `src/eriq/tokens.py` → `credit_purchased_tokens()`

### 6.7 Token Deduction (ERIQ Usage)

**Trigger:** Every successful ERIQ question/answer

**Flow:**
1. Pre-flight: `check_can_use()` verifies `total_available > 0`
2. If balance exhausted → returns `token_limit` error with purchase prompt
3. If balance available → ERIQ processes the question
4. Post-response: `deduct_tokens()` subtracts `response.usage.total_tokens`
5. **Deduction priority:** allowance first, then purchased balance
6. Uses `FOR UPDATE` row lock for concurrency safety
7. Updated `token_status` is returned in the API response

**Deduction Example:**
- User has 5,000 allowance remaining + 10,000 purchased
- Question costs 6,000 tokens
- Deduction: 5,000 from allowance + 1,000 from purchased
- Result: 0 allowance remaining + 9,000 purchased

**File:** `src/eriq/agent.py` → `ask_eriq()` / `src/eriq/tokens.py` → `deduct_tokens()`

---

## 7. API Endpoints

### `GET /api/v1/eriq/tokens/status`
**Auth:** Required (session token via `X-User-Token` header)

**Response:**
```json
{
  "total_available": 95000,
  "allowance_remaining": 85000,
  "purchased_balance": 10000,
  "plan_monthly_allowance": 100000,
  "period_start": "2026-02-01T00:00:00",
  "low_balance": false,
  "low_balance_threshold": 3000,
  "packs": [
    {"tokens": 100000, "label": "100K", "price_eur": 1.35},
    {"tokens": 300000, "label": "300K", "price_eur": 4.05},
    {"tokens": 500000, "label": "500K", "price_eur": 6.75},
    {"tokens": 1000000, "label": "1M", "price_eur": 13.50}
  ]
}
```

### `POST /api/v1/eriq/tokens/checkout`
**Auth:** Required (session token via `X-User-Token` header)

**Request Body:**
```json
{
  "token_pack": 100000
}
```

**Response:**
```json
{
  "checkout_url": "https://checkout.stripe.com/...",
  "session_id": "cs_live_..."
}
```

### `POST /api/v1/eriq/ask` (token fields in response)
Each ERIQ response includes token information:
```json
{
  "success": true,
  "response": "...",
  "tokens_used": 1523,
  "token_status": {
    "total_available": 93477,
    "allowance_remaining": 83477,
    "purchased_balance": 10000,
    "low_balance": false,
    "low_balance_threshold": 3000
  }
}
```

When tokens are exhausted:
```json
{
  "success": false,
  "error": "token_limit",
  "message": "You've used all your ERIQ tokens for this month. Purchase additional tokens to continue using ERIQ.",
  "token_status": { "total_available": 0, "low_balance": true }
}
```

---

## 8. Idempotency & Safety

Every token-modifying operation has idempotency protection via the `eriq_token_ledger`:

| Operation          | Idempotency Check                                            |
|--------------------|--------------------------------------------------------------|
| Monthly renewal    | Ledger `source='stripe_renewal'`, `ref_info='invoice:{id}'`  |
| Token purchase     | Ledger `source='purchase'`, `ref_info='stripe:{session_id}'` |
| Plan upgrade       | Ledger `source='plan_upgrade'`, `ref_info='upgrade:{sub}:{plan}:{month}'` |

This ensures that duplicate Stripe webhook deliveries (which are common) never result in double-crediting.

Token deductions use PostgreSQL `FOR UPDATE` row locking to prevent race conditions from concurrent ERIQ requests.

---

## 9. Low Balance Warning

**Threshold:** 3,000 tokens (`LOW_BALANCE_THRESHOLD` in `src/eriq/tokens.py`)

When `total_available < 3000`, the `token_status` includes `low_balance: true`. The frontend can use this to show a warning and prompt the user to purchase more tokens before they run out completely.

---

## 10. Stripe Webhook Integration Points

The token system hooks into 3 Stripe webhook events, all processed in `src/billing/webhook_handler.py`:

| Stripe Event                      | Token Action                           | Handler Function                    |
|-----------------------------------|----------------------------------------|-------------------------------------|
| `checkout.session.completed`      | Grant initial allowance (new sub)      | `handle_checkout_session_completed` |
| `checkout.session.completed`      | Credit purchased tokens (one-time pay) | `handle_token_purchase_webhook`     |
| `customer.subscription.updated`   | Grant upgrade difference               | `handle_subscription_updated`       |
| `invoice.paid`                    | Reset monthly allowance                | `handle_invoice_paid`               |

**Distinguishing token purchases from subscriptions:** Token purchases use `metadata.type = "eriq_tokens"` on the Stripe Checkout Session. The webhook handler checks this first and routes accordingly.

---

## 11. File Map

| File                              | Responsibility                                     |
|-----------------------------------|----------------------------------------------------|
| `src/eriq/tokens.py`             | Core token logic: balances, deductions, resets, upgrades, purchases |
| `src/api/eriq_routes.py`         | API endpoints for token status, checkout, and webhook handling       |
| `src/eriq/agent.py`              | Pre-flight balance check + post-response deduction in ask_eriq flow |
| `src/billing/webhook_handler.py` | Stripe webhook routing: initial grant, monthly reset, upgrade delta  |
| `src/db/migrations.py`           | Database table creation for `eriq_token_balances` and `eriq_token_ledger` |

---

## 12. Edge Cases & Design Decisions

1. **Purchased tokens never expire.** They persist across billing cycles and plan changes. Only the monthly allowance resets.

2. **Deduction priority:** Allowance is consumed first. Purchased tokens are only used once the monthly allowance is fully depleted. This maximizes the value of purchased tokens.

3. **Downgrade behavior:** When a user downgrades, their remaining allowance is clamped to the new plan's limit (so they can't carry over a higher-tier allowance), but purchased tokens are never reduced.

4. **Upgrade mid-cycle:** The difference between old and new plan allowance is added immediately. The user doesn't have to wait until the next billing cycle to benefit from the higher allowance.

5. **Lazy reset fallback:** If the Stripe `invoice.paid` webhook is missed for any reason, the system will still reset the allowance the next time the user uses ERIQ (via `_maybe_reset_monthly`). This ensures no user is ever stuck without their tokens.

6. **Free plan:** Has a 50K token allowance but no option to purchase additional tokens (purchase is available to paid plans only).
