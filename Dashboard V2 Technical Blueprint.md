# Dashboard V2 Technical Blueprint

## Document status

**Status:** Technical design baseline for Release 1

**Purpose:** Translate the approved New Dashboard Architecture and implementation answer set into an engineering-ready blueprint for Dashboard V2 development.

**Companion documents:**

- [New Dashboard Architecture.md](New%20Dashboard%20Architecture.md) — strategic architecture across seven layers.
- [New Dashboard Implementation Decisions.md](New%20Dashboard%20Implementation%20Decisions.md) — product, commercial, entitlement, Newsletter, and rollout decisions.
- [Full implementation answer set](#appendix-a--full-implementation-answer-set) — preserved at the end of this document.

This document is the bridge between strategy and implementation. It distinguishes decisions that are already locked from technical details that should be confirmed while the first vertical slice is built.

## 1. Release 1 objective and boundary

Release 1 must prove one product loop:

> A registered user completes a useful daily intelligence routine, returns, discovers premium depth, and can upgrade safely.

Everything that does not directly support that loop should be simplified or postponed.

### Required in Release 1

| Capability | Treatment |
|---|---|
| Dashboard V2 shell | Required |
| New left navigation | Required |
| Five-step 3-Minute Intelligence Routine | Core product |
| Free versus Premium depth | Required |
| Server-side capability-based entitlement service | Required; security-critical |
| 7-Day Premium Welcome Experience | Required |
| Existing-user Migration Experience | Required |
| Temporary entitlement system | Required |
| Existing GERI Live and DIR subscriptions | Preserve without automatic changes |
| Intelligence Bundle at €29/month | Real product and price |
| Individual €4.95 Widgets | Existing commercial layer; internal access in V2 |
| Internal Widget access and previews | Required |
| Contextual Newsletter deep links | Basic version |
| Newsletter attribution | Basic first-touch, last-touch, and conversion touch |
| Canonical analytics events | Required |
| Rules-based contextual offers | Simple version |
| Advanced Newsletter Companion | Basic Release 1 version; expand later |

### Explicitly deferred

Full personalization scoring, the €9.95 Widget Pack, Complete Intelligence, event-driven 24-hour passes, the external Widget embedding overhaul, embedded Widget usage analytics, Saved Widget Presets, automated Newsletter mapping, AI recommendations, agency licensing, extensive customization, and user-defined Routine structures must not block Release 1.

Internal WTI, LNG, and Gas Storage intelligence is in scope. Existing external embeds must continue to work where customers already depend on them, but a new embed-management platform is not a Release 1 blocker.

## 2. Parallel Dashboard architecture and rollout

Dashboard V2 must be built in parallel with the legacy Dashboard, not spliced into it and not destructively replacing it.

Conceptual routing:

    /dashboard
        ↓
    dashboard_v2_enabled(user)
        YES → Dashboard V2
        NO  → Legacy Dashboard

Administrators need a temporary way to force Legacy Dashboard for diagnosis and rollback. Retain the legacy implementation through at least two stable production releases, ideally about 30 days after full migration.

Rollout order: internal users → two existing paid accounts → approximately ten existing Free users → remaining existing users → new registrations → Newsletter traffic.

Independent controls should exist for Dashboard V2 rendering, Welcome activation, Migration activation, Bundle checkout visibility, Newsletter contextual routing, internal Widget access, and contextual offer rules. These controls must not alter existing Stripe subscriptions.

## 3. Backbone service architecture

Dashboard V2 has three core backend services. Everything else is presentation or an integration around them.

### Intelligence Snapshot Service
Answers: **What intelligence exists right now?** It normalizes source data, identifies the snapshot, evaluates freshness, represents partial failures, and preserves the historical snapshot identity used by the Routine and Newsletter evidence.

### Entitlement Service
Answers: **How much of the intelligence may this user access?** It resolves Free baseline access, paid subscriptions, temporary experiences, and separate internal versus external Widget permissions. The browser never decides access.

### Routine Service
Answers: **Where is this user in today's workflow?** It identifies the current intelligence snapshot, persists step completion, supports cross-device continuation, and reports honest progress during partial failure.

The Dashboard should conceptually request today's intelligence, effective entitlements, Routine state, Newsletter context, and current offer state, then render the appropriate experience.

## 4. Normalized intelligence data model

Every Routine dataset must use a common semantic envelope containing:

- snapshot_id
- intelligence_date
- generated_at_utc
- data_as_of_utc
- status: fresh, delayed, stale, partial, or unavailable
- freshness: expected interval, maximum age, and delay reason
- payload
- available sections
- errors

Freshness is evaluated by a server-side dataset registry with dataset identifier, expected cadence, maximum age, grace period, source, fallback policy, and status rules. Frontend components must not contain supplier-specific age thresholds.

Hard rule: never display older data as though it were today's current intelligence. When data is late, show the actual data-as-of time and a delayed message. When one input fails, show a partial state and allow independent work to continue. When all inputs for one step fail, show that step as unavailable and report progress honestly, such as 4 of 5 available steps completed.

## 5. Five-step Routine contracts

### Step 1 — What's happening to risk?
Sources: GERI, EERI, EGSI-M, and EGSI-S. Required normalized fields: index code, current value, previous value, absolute change, methodologically valid percentage change, direction, regime, intelligence date, and data-as-of time. Free includes the daily reading, regime, direction, change, and concise explanation. Premium may add intraday context, acceleration, regime-transition context, and relevant GERI Live intelligence.

### Step 2 — Is risk accelerating?
Sources: GERI Live, daily GERI movement, and recent intraday trajectory. Required fields: current value, session-start value, change, change rate, direction, recent high, recent low, regime, regime-changed state, and last update. Initially classify movement as Rising, Rising rapidly, Stable, Falling, or Falling rapidly using documented thresholds. Do not expose an acceleration metric until its methodology is defensible.

### Step 3 — Are markets confirming it?
Use a normalized Market Confirmation Engine for Brent, WTI, TTF, JKM, EU Gas Storage, and VIX. Each market provides value, unit, previous value, change, percentage change, data-as-of time, direction, and confirmation state: confirms, partially confirms, contradicts, neutral, or insufficient data. The step should explain relationships among markets, not merely display six prices.

### Step 4 — What does it mean?
DIR provides headline, summary, drivers, implications, oil/gas/LNG market groups, scenarios, risk-management notes, generated time, and data-as-of time. Free receives one short interpretation. DIR access adds full interpretation, scenarios, implications, and actionable takeaways.

### Step 5 — What should I watch next?
Each watch item contains ID, title, market, category, why it matters, condition, time horizon, importance, and source product. Free receives two or three principal watch items. DIR, GERI Live, and Bundle users receive deeper Watch and Scenario context.

## 6. Entitlement architecture

Use capability-based permissions rather than product-name checks. Initial capabilities include risk_daily, risk_intraday, dir_full, forecast_brent_full, widget_wti_internal, widget_lng_internal, widget_storage_internal, widget_wti_embed, widget_lng_embed, widget_storage_embed, alerts_basic, and alerts_advanced.

Effective access is additive: account suspension/security block first, then active paid subscription, active temporary entitlement, and Free baseline. A capability is available when at least one valid non-blocked source grants it. Do not create casual DENY records when a temporary grant expires; the expired grant simply stops contributing.

The authoritative browser-facing contract should be conceptually similar to GET /api/me/entitlements and return allowed state, access level, source, expiration, and subscription/product context per capability.

Store temporary access in an experience record and separate entitlement-grant records. Experience types include welcome, migration, promotion, event pass, and admin grant. Retain expired records permanently for analytics, debugging, migration, abuse detection, support, and audit history. Maintain an entitlement audit log.

If entitlement resolution fails, do not silently assume Free and remove a paying user's access. Show that subscription verification is temporarily unavailable, preserve account state, retry server-side, and alert on persistent failure.

## 7. Billing and product catalog

Maintain one authoritative Product Catalog. Initial product codes are DIR, GERI_LIVE, INTELLIGENCE_BUNDLE, WIDGET_WTI, WIDGET_LNG, and WIDGET_STORAGE. Configuration supplies display name, billing model, currency, display price, tax behavior, Stripe Product ID, Stripe Price ID, and active state.

The €29/month Intelligence Bundle is a real Stripe Product and Price mapping to risk_intraday, dir_full, and forecast_brent_full. Actual Stripe IDs must come from the configured Stripe account, never invented in application code.

Stripe is billing authority; EnergyRiskIQ is effective-entitlement authority. Recommended behavior: GERI Live or DIR to Bundle is an immediate prorated upgrade; Bundle downgrades occur at period end; cancellation retains access through current_period_end; failed payment uses a configurable retry/grace policy; tax and VAT stay in Stripe/billing infrastructure.

Run periodic reconciliation across Stripe subscription state, internal billing state, and effective entitlements. Alert and reconcile safely on disagreement; do not rely only on webhooks.

## 8. Dashboard V2 presentation contract

Above the fold: greeting/date, latest intelligence time, at most one priority banner, the 3-Minute Routine, progress, and Step 1. Pricing, multiple Widget cards, and product advertisements must not appear before the user sees intelligence.

During the seven-day experience use a compact status such as Premium Intelligence · 5 days remaining. Escalate to a primary banner only when 24 hours or less remain.

Every intelligence component supports loading, ready, partial, delayed, stale, unavailable, locked, and subscription-error states. Use skeletons rather than spinner-only loading. Locked states show genuine Free information before premium depth.

On mobile, one primary Routine step is expanded at a time; Continue collapses the current step, expands the next, and scrolls naturally; deep links open the requested step; a small sticky Continue action is allowed only during an active step; permanent Buy Premium actions are not fixed to the bottom; primary banners should occupy less than approximately 20% of the initial viewport.

Target WCAG 2.2 AA. Accordions must be keyboard-operable, aria-expanded must be correct, focus must move logically, color must not be the only signal, contrast must be sufficient, live updates must be restrained, reduced motion must be honored, loading and locked states must be announced, and countdowns must have readable date/time equivalents.

Keep Routine names, methodology, product names, entitlement explanations, capability mapping, completion behavior, access/security wording, and structural navigation version-controlled. Admin may edit safe campaign, expiry, Newsletter Companion, product-mapping, offer, badge, deadline, and campaign-date content.

Authenticated offer dismissals are stored per user, offer, and offer version with suppression timing and dismissal type. Anonymous visitors may use temporary browser storage until authentication.

## 9. Newsletter context and attribution

Use a stable first-party redirect such as /n/ERIQ-2026-01 or /go/newsletter/2026-01. Keep optional UTM and CTA parameters for analytics, but let the database determine entry step, featured product, and Companion context.

A Newsletter edition record contains ID, slug, publication time, title, topic, entry step, featured and optional secondary products, Free and Premium Companion copy, and draft/scheduled/published/archived status. Release 1 mapping is manual through Admin.

Anonymous visitors preserve context through signup and return to the contextual Routine. Logged-in visitors open the selected step directly. Invalid or deleted editions fall back to the current Routine and record a diagnostic event. Historical editions retain historical editorial evidence while the click-through Dashboard can show current intelligence.

Published Newsletter images use frozen historical snapshots. Store edition, image role, generation time, data-as-of time, dataset snapshot ID, and version. Corrections create a new version instead of silently overwriting the original.

The Newsletter Companion answers what has changed relative to the article topic. Free gets context, a relevant indicator, one interpretation, and Continue Routine. Entitled users receive the relevant temporarily unlocked or paid depth.

## 10. Widgets

Internal WTI, LNG, and Storage intelligence is in scope. Internal Widget permission and external embed permission are separate capabilities. Welcome users may receive internal access while embed access remains false.

When embedding is expanded, use allowed domains, revocable site keys, signed short-lived bootstrap authorization, server-side subscription checks, origin validation, rate limits, revocation, graceful inactive rendering, and key rotation. Do not rely on Referer alone.

The first Widget value milestone is What Changed? rather than Saved Presets. It should explain movement against yesterday or a recent baseline and turn the Widget into decision support.

## 11. Analytics and privacy

Use one versioned event envelope with event ID, event name, event version, UTC occurrence time, nullable user and visitor IDs, session ID, source, campaign, Newsletter edition, topic, product, Routine step, entitlement state, experience type, experiment variant, and properties.

Use stable names such as dashboard_viewed, routine_started, routine_step_completed, premium_experience_started, offer_viewed, checkout_started, subscription_started, newsletter_context_opened, and widget_opened. Server-generate commercial and entitlement events; client events may record UI interactions.

Create a first-party random visitor ID, store Newsletter touch data, associate it with user ID after authentication, and retain first acquisition and last meaningful acquisition separately. Do not fingerprint users. The core product works without persistent attribution when cookies or consent are unavailable.

Separate essential telemetry, product analytics, and marketing attribution/personalization. Store consent version, analytics permission, marketing permission, and update time. Avoid email addresses in event payloads and support removal or pseudonymization of behavioral and visitor-linkage data where required.

## 12. Operations, rollback, and migration safety

Alert immediately on unexpected paid-access loss, mass entitlement discrepancies, or temporary-entitlement corruption. Alert at high severity for late daily intelligence, stale GERI Live, and Stripe synchronization failure. Monitor Newsletter deep-link errors, valid embed rejection, and analytics ingestion failures.

Rollback sequence: disable Dashboard V2; disable new Welcome activations if needed; disable new Migration activations if needed; preserve grants already promised; suppress affected Bundle checkout if billing is implicated; never modify existing Stripe subscriptions during UI rollback.

Prefer additive, backward-compatible schema changes so Legacy Dashboard can continue while V2 uses new entitlement, experience, Newsletter context, Routine, and analytics structures.

## 13. Routine persistence and acceptance gates

Routine progress belongs to the account. Persist user ID, Routine ID, intelligence date, start/completion times, and per-step completion times. This enables cross-device continuation, time-to-complete, abandonment, and retention analysis.

Mandatory acceptance coverage includes Welcome and Migration lifecycles, preserved paid subscriptions, GERI-to-Bundle and DIR-to-Bundle billing, cancellation period-end access, failed-payment grace/restriction, internal-versus-embed Widget permissions, Newsletter routing and invalid-edition fallback, all freshness/failure states, cross-device Routine state, and cross-device offer dismissals.

The UI must never label old intelligence as current.

## 14. Recommended implementation sequence

1. Define and version the capability vocabulary.
2. Define the normalized snapshot envelope and dataset registry.
3. Add persistence for experiences, grants, audit events, Newsletter context, and Routine progress.
4. Implement effective entitlement resolution and its server-side API.
5. Implement the Routine service and snapshot-aware progress persistence.
6. Build Dashboard V2 in parallel behind the Dashboard V2 flag.
7. Add basic Newsletter redirect/context flow.
8. Add Product Catalog and Bundle billing mapping without changing existing subscriptions.
9. Add canonical analytics events and operational alerts.
10. Run lifecycle, freshness, billing, Newsletter, mobile, and cross-device acceptance tests.
11. Roll out by cohort while retaining Legacy Dashboard rollback.

## 15. Non-goals for the first implementation

AI recommendations, sophisticated product-interest scores, embedded Widget analytics, agency licensing, Widget Pack, Complete Intelligence, automatic Newsletter mapping, dynamic event passes, extensive customization, drag-and-drop cards, and user-defined Routine structures must not delay the first vertical slice.

> Routine → return → premium discovery → subscription.

## Appendix A — Full implementation answer set

The complete answer set supplied for this blueprint is preserved below so that no implementation nuance is lost during summarization.

---

Yes. These questions are the point where the strategy becomes an engineering specification. The attached set correctly identifies the remaining implementation blockers.

My strongest recommendation is to resist building every part of the long-term architecture in the first release. Release 1 should prove one thing:

Can EnergyRiskIQ turn a registered user into someone who completes a useful daily intelligence routine, returns, discovers premium depth, and can upgrade safely?

Everything that doesn't directly support that outcome should either be simplified or postponed.

1. Exact Release 1 boundary

I would lock Release 1 as follows.

Capability	Release 1?	Decision
New Dashboard shell	✅	Required
New left navigation	✅	Required
Five-step 3-Minute Routine	✅	Core product
Free vs Premium depth	✅	Required
Server-side entitlement service	✅	Absolutely required
7-Day Premium Welcome Experience	✅	Required
Existing-user Migration Experience	✅	Required
Temporary entitlement system	✅	Required
Existing GERI/DIR subscriptions preserved	✅	Required
Intelligence Bundle €29	✅	Yes
Individual €4.95 Widgets	✅	Existing commercial layer
Internal Widget access/previews	✅	Yes
Newsletter contextual deep links	✅	Basic version
Newsletter attribution	✅	Basic first/last/conversion touch
Canonical analytics events	✅	Required
Rules-based contextual offers	✅	Simple version
Full personalization scoring engine	❌	Phase 2
€9.95 Widget Pack	❌	Phase 2
Complete Intelligence plan	❌	Phase 2
Event-driven 24h passes	❌	Architecture only
Advanced Newsletter Companion	◐	Basic R1, advanced later
External Widget embedding overhaul	❌*	Phase 1.1 unless already commercially required
Usage analytics for embedded Widgets	❌	Later
Saved Widget Presets	❌	Later
Automated Newsletter-product mapping	❌	Later
Important distinction on Widgets

I would not delay the internal Pro Widgets.

I would delay building a sophisticated external embedding platform.

So Release 1 can expose:

WTI Intelligence
LNG Intelligence
Gas Storage Intelligence

inside EnergyRiskIQ.

If existing customers already depend on external embedding, preserve what exists. But don't make a complete new embed-management infrastructure a blocker for Dashboard V2.

That keeps Release 1 focused.

2. What happens to the existing Dashboard?

Do not replace it destructively.

And do not gradually splice V2 components into the old Dashboard.

Build Dashboard V2 in parallel.

Conceptually:

/dashboard

        ↓

dashboard_v2_enabled(user)

       YES → New Dashboard
       NO  → Legacy Dashboard

Keep the old implementation intact behind:

dashboard_v2_enabled

for the rollout period.

I would also maintain an administrator-only way to force Legacy Dashboard temporarily.

Rollout
Internal users
      ↓
2 existing paid accounts
      ↓
~10 existing Free users
      ↓
Remaining existing users
      ↓
New registrations
      ↓
Newsletter traffic

This is much safer than replacing components one-by-one.

A half-old/half-new Dashboard creates especially dangerous ambiguity around:

access;
premium status;
banners;
Routine completion;
analytics.
How long to retain Legacy?

I would keep the legacy implementation available through at least:

two stable production releases, ideally around 30 days after full migration.

Then retire it.

3. The canonical data architecture for the Routine

Do not let each React component independently call GERI, Brent, TTF, DIR, Storage, etc.

Create a normalized intelligence layer.

Every Routine dataset should conform to a common envelope:

snapshot_id
intelligence_date
generated_at_utc
data_as_of_utc

status:
  fresh
  delayed
  stale
  partial
  unavailable

freshness:
  expected_interval
  max_age
  delay_reason

payload:
  ...

available_sections:
  ...

errors:
  ...

That gives the Dashboard one consistent way of answering:

Is this intelligence safe to display as current?

4. Exact contracts for the five Routine steps
Step 1 — What's happening to risk?

Primary data:

GERI
EERI
EGSI-M
EGSI-S

Required normalized fields:

index_code
current_value
previous_value
absolute_change
percentage_change   // when methodologically valid
direction
regime
intelligence_date
data_as_of

Free should get:

current daily reading;
regime;
direction;
daily change;
concise explanation.

Premium can add:

intraday/live context;
acceleration;
regime-transition context;
relevant GERI Live intelligence.
Step 2 — Is risk accelerating?

Primary:

GERI Live
daily GERI movement
recent intraday trajectory

Contract:

current_value
session_start_value
change
change_rate
direction
recent_high
recent_low
regime
regime_changed
last_update

I would avoid exposing a mathematically impressive-looking acceleration number until you have a methodology you are comfortable defending.

The application can initially classify:

Rising
Rising rapidly
Stable
Falling
Falling rapidly

using your own documented thresholds.

Free:

daily change.

Premium:

intraday trajectory + live acceleration/change.

Step 3 — Are markets confirming it?

This should be a normalized Market Confirmation Engine, rather than six unrelated cards.

Inputs:

Brent
WTI
TTF
JKM
EU Gas Storage
VIX

Each market produces:

market
value
unit
previous_value
change
change_pct
data_as_of

direction:
  higher
  lower
  unchanged

confirmation_state:
  confirms
  partially_confirms
  contradicts
  neutral
  insufficient_data

Then Step 3 can say something like:

Market confirmation: Mixed

followed by the evidence.

The intelligence lies in the relationship between markets—not simply showing six prices.

This Step can later become extremely valuable.

Step 4 — What does it mean?

This is where DIR integrates naturally.

Normalized contract:

headline
summary

drivers[]
implications[]

markets:
  oil
  gas
  lng

scenarios[]
risk_management_notes[]

generated_at
data_as_of

Free:

one short interpretation.

Example:

Rising geopolitical risk is being partially confirmed by oil while European gas remains comparatively stable.

DIR:

full interpretation:

Oil
Gas
LNG
scenarios
implications
actionable takeaways.
Step 5 — What should I watch next?

Contract:

watch_items[]

watch_item:
  id
  title
  market
  category
  why_it_matters
  condition
  time_horizon
  importance
  source_product

Examples:

GERI regime transition

Brent breaks recent high

Storage injection pace deteriorates

LNG premium versus Europe widens

Free gets perhaps:

2–3 principal watch items.

DIR/GERI/Bundle users receive deeper Watch/Scenario context.

5. Data freshness must be metadata-driven

Do not write frontend logic such as:

if Brent older than 15 minutes → stale

Create a dataset registry:

Dataset        Expected cadence    Max allowed age
GERI           configured          configured
GERI Live      configured          configured
Brent          configured          configured
TTF            configured          configured
JKM            configured          configured
Storage        configured          configured
DIR            daily              configured
...

Then your backend decides the state.

That means if you later change a data supplier or cadence, you don't change Dashboard code.

6. What happens when today's intelligence is late?

This deserves a hard rule:

Never replace missing current intelligence with yesterday's value without explicitly labelling it.

Suppose today's GERI pipeline is late.

Show:

Latest available intelligence

GERI 24
As of August 29, 2026, 01:30 UTC

Today's update is delayed.

Never simply show:

GERI 24

on August 30 as though it were August 30 data.

Routine behaviour during delayed data

Do not disable the entire Routine.

Users should be able to complete a Routine using the latest available intelligence when reasonable.

Example:

STEP 1
⚠ Latest available GERI data
As of Aug 29

Continue →

Completion remains possible.

Why?

Because making your entire product unavailable because one pipeline is late is worse than transparently showing slightly older intelligence.

Partial failure

Suppose:

GERI ✅
Brent ✅
WTI ✅
TTF ❌
LNG ✅

Step 3 should say:

Market confirmation: Partial

TTF data is temporarily unavailable.

Don't fail Step 3.

Complete core failure

Suppose all Risk indices fail.

Then Step 1 becomes:

Risk intelligence is temporarily unavailable.

The user can still open other independent sections.

Routine completion can be marked:

4 of 5 available steps completed

rather than pretending everything worked.

7. The authoritative entitlement API

This is perhaps the single most important backend rule:

The browser must never decide whether someone has access.

Create something conceptually like:

GET /api/me/entitlements

Response:

daily_risk:
  allowed: true
  level: free

intraday_risk:
  allowed: true
  level: premium
  source: welcome_experience
  expires_at: ...

dir_full:
  allowed: true
  source: subscription

brent_forecast_full:
  allowed: true
  source: geri_live_subscription

widget_lng_internal:
  allowed: false

widget_lng_embed:
  allowed: false
8. Recommended capability names

I would make entitlements capability-based, not product-name-based.

For example:

risk_daily

risk_intraday

dir_full

forecast_brent_full

widget_wti_internal
widget_lng_internal
widget_storage_internal

widget_wti_embed
widget_lng_embed
widget_storage_embed

alerts_basic
alerts_advanced

Why separate:

widget_lng_internal

from:

widget_lng_embed?

Because Welcome users may receive:

widget_lng_internal = true
widget_lng_embed = false

Exactly what you want.

9. Entitlement precedence

Use an additive model.

Highest priority

Security/account suspension.

Then:

Paid subscription

Then:

Temporary entitlement

Then:

Free baseline.

Conceptually:

effective_access =
max(
  free_entitlement,
  active_subscription,
  temporary_entitlement
)

Example:

DIR subscriber:

DIR → paid subscription
GERI → migration experience

Migration expires.

Result:

DIR → still paid
GERI → removed

No Stripe changes.

10. Don't use explicit DENY records casually

A temporary entitlement expiring should not create:

GERI = DENIED

Because the user might simultaneously have purchased GERI.

Instead, that grant simply ceases to contribute.

Access exists if at least one valid access source exists.

That's much safer.

11. Temporary entitlement storage

Use two layers.

Experience
access_experience

id
user_id

type:
 welcome
 migration
 promotion
 event_pass
 admin_grant

status:
 eligible
 active
 expired
 revoked

eligible_at
activation_deadline
started_at
ends_at
consumed_at

created_at
updated_at

And then:

Grants
entitlement_grant

experience_id
capability
starts_at
ends_at
status

Example Welcome Experience:

welcome_123

  risk_intraday
  dir_full
  forecast_brent_full
  widget_wti_internal
  widget_lng_internal
  widget_storage_internal

Notice:

No Widget embedding entitlement.

12. Never delete expired entitlement records

Keep them permanently for:

analytics;
debugging;
migration;
abuse detection;
customer support;
audit history.

Mark them:

expired

rather than deleting them.

Also maintain an entitlement audit log.

Example:

WELCOME_ACTIVATED
DIR_GRANTED
GERI_GRANTED
WELCOME_EXPIRED
DIR_TEMPORARY_GRANT_ENDED

This will save you considerable debugging time.

13. Stripe product architecture

There should be one Product Catalog inside EnergyRiskIQ.

Not price literals scattered throughout React components.

Example:

product_code:
  DIR

display_name:
  Daily Intelligence Report

billing_model:
  monthly

stripe_product_id:
  prod_...

stripe_price_id:
  price_...

status:
  active

Same for:

GERI_LIVE
INTELLIGENCE_BUNDLE
WIDGET_WTI
WIDGET_LNG
WIDGET_STORAGE

The actual Stripe IDs must be populated from your live Stripe account before deployment; they should not be invented in application code.

14. €29 Bundle Stripe architecture

Create it as a real Stripe product/price.

Not:

GERI €27 + dynamically discount DIR.

Prefer:

INTELLIGENCE_BUNDLE
€29/month

whose internal entitlement mapping grants:

risk_intraday
dir_full
forecast_brent_full

If future capabilities become included, you change the entitlement mapping—not every Dashboard component.

15. Upgrade behaviour

GERI €27 → Bundle €29:

Immediate upgrade + proration.

DIR €8 → Bundle €29:

Immediate upgrade + proration.

Access becomes available as soon as the subscription change succeeds.

16. Downgrades

Schedule for:

end of billing period

Example:

Bundle → DIR.

User keeps Bundle access until period end.

Then entitlements change to DIR only.

17. Cancellation

If Stripe says:

cancel_at_period_end = true

EnergyRiskIQ should still treat the subscription as active until:

current_period_end.

Do not immediately remove access.

18. Failed payments

Do not let the frontend interpret Stripe statuses directly.

Your billing service maps Stripe state into:

active
grace
restricted
cancelled

I would permit a configurable payment-retry/grace policy instead of instantly removing access on the first failed charge.

Stripe remains billing authority.

EnergyRiskIQ remains entitlement authority.

19. VAT and tax

Do not build custom EU VAT logic into the Dashboard.

Keep taxation in Stripe/billing infrastructure.

Product configuration should carry things such as:

tax_behavior
currency
display_price
billing_interval

For EU consumer/business treatment, VAT IDs and whether your displayed consumer price includes VAT, configure Stripe appropriately and confirm the accounting treatment with your accountant.

The Dashboard should receive:

€29/month

from the product catalog—not calculate it.

20. Exact above-the-fold Dashboard layout

For normal Dashboard traffic:

┌──────────────────────────────────────────────┐
│ Good morning                     30 Aug 2026 │
│ Latest intelligence: 01:30 UTC              │
├──────────────────────────────────────────────┤
│ [ONE PRIORITY BANNER — only if required]     │
├──────────────────────────────────────────────┤
│ TODAY'S 3-MINUTE INTELLIGENCE                │
│                                              │
│  ● Risk                                      │
│  ○ Change                                    │
│  ○ Confirm                                   │
│  ○ Interpret                                 │
│  ○ Watch                                     │
│                                              │
│  0 / 5 complete                              │
├──────────────────────────────────────────────┤
│ STEP 1 — WHAT'S HAPPENING TO RISK?           │
│                                              │
│ GERI     EERI      EGSI                      │
│ ...                                          │
│                                              │
│                         Continue →           │
└──────────────────────────────────────────────┘

That is the above-the-fold priority.

Not pricing.

Not four Pro Widget cards.

Not product advertisements.

21. Premium Experience status

Do not use a giant banner during all seven days.

Instead show a compact status:

Premium Intelligence · 5 days remaining

Only escalate to a primary banner when:

24 hours or less remain.

Example:

Your Premium Intelligence Experience ends tomorrow.

That preserves Dashboard calm.

22. Newsletter traffic changes the layout slightly

If the user arrived from an LNG Newsletter:

From this week's EnergyRiskIQ Newsletter:
LNG Tightness Is Increasing

Continue today's analysis ↓

Then open:

Step 3 — Confirm

with LNG already emphasized.

The Newsletter context should not replace the Dashboard.

It should orient the Dashboard.

23. Component state model

Every intelligence component should support the same core states:

loading
ready
partial
delayed
stale
unavailable
locked
subscription_error

Do not improvise separate error UX in each feature.

Examples:

Loading

Skeleton—not spinner-only.

Delayed

Today's update is delayed. Showing the latest available intelligence.

Stale

Data as of Aug 29, 18:00 UTC.

Partial

TTF unavailable. Other market signals remain current.

Unavailable

This intelligence is temporarily unavailable.

Locked

Show genuine Free information first, followed by contextual premium depth.

Subscription lookup failure

Do not assume Free.

This is important.

If entitlement service temporarily fails, avoid accidentally stripping a paying customer's UI.

Show:

We're having trouble verifying your subscription. Your account has not been changed.

Retry server-side.

24. Mobile Routine model

On mobile:

one primary Routine step expanded at a time.

User can still open another.

When they tap Continue:

Step 1 collapses
Step 2 expands
viewport scrolls naturally to Step 2.

Deep-link to Step 3:

Step 3 opens directly.

Sticky mobile action

A small bottom action is useful:

Continue →

But only while a Routine step is active.

Do not keep:

BUY PREMIUM €29

permanently stuck to the bottom of the screen.

Banner rule on mobile

Primary banners should ideally occupy less than roughly 20% of the initial viewport.

Countdown banners should compress.

No giant sales hero before users can see their intelligence.

25. Accessibility

Target:

WCAG 2.2 AA

from the start.

Particularly:

every accordion keyboard operable;
proper aria-expanded;
focus moves logically after Continue;
no information communicated solely by red/green;
sufficient contrast;
live data updates should not constantly interrupt screen readers;
reduced-motion preference honoured;
loading state announced properly;
locked controls described;
countdown expressed textually.

Instead of only:

17:23:41

also provide:

Premium access ends Monday, September 7 at 18:27.

This is both more accessible and clearer.

26. What Admin may edit

I would not make everything CMS-configurable.

Version controlled

Keep these in application/product configuration:

Five Routine step names;
methodological meaning;
core product names;
entitlement explanations;
capability mapping;
completion behaviour;
access/security wording;
structural navigation.

For example:

WHAT'S HAPPENING TO RISK?

shouldn't accidentally become:

CHECK TODAY'S HOT TRADES 🚀

because someone edited an Admin field.

Admin configurable

Safe marketing/editorial content:

campaign banners;
expiry-support text;
Newsletter Companion editorial copy;
featured product;
Newsletter mappings;
offer copy;
campaign CTA;
NEW badge;
migration deadline;
temporary campaign dates.
27. Dismissals should be per-user

For authenticated users store:

user_id
offer_id
offer_version
dismissed_at
suppress_until
dismissal_type

Thus:

Mobile dismissal

→ also suppressed on Desktop.

If the commercial offer changes materially, increment:

offer_version

so the new proposition may be shown.

Anonymous visitors can use browser storage temporarily.

Once they authenticate, user-level state becomes authoritative.

28. Canonical Newsletter link

I would actually simplify your proposed query-string design.

Do not expose all business logic in URLs like:

/dashboard?
entry_step=3&
featured_product=lng&
...

Use a canonical EnergyRiskIQ redirect:

energyriskiq.com/n/ERIQ-2026-01

or:

energyriskiq.com/go/newsletter/2026-01

Optional:

?cta=primary

Your database knows:

edition_id
topic
entry_step
featured_product
companion_id

Therefore someone changing:

featured_product=GERI

in their browser doesn't modify your intended funnel.

UTMs can remain:

utm_source=linkedin
utm_medium=newsletter
utm_campaign=...

for external analytics.

29. Newsletter context record

Create:

newsletter_edition

id
slug
published_at
title
topic_id

entry_step
featured_product
secondary_product

companion_free
companion_premium

status:
 draft
 scheduled
 published
 archived

The Newsletter redirect looks up this object.

That becomes your editorial-to-product control layer.

30. Invalid or deleted Newsletter links

Never show:

Invalid Edition ID

to a visitor.

Fallback:

Invalid Newsletter context
          ↓
Current EnergyRiskIQ Dashboard
          ↓
Today's Routine

Record:

newsletter_context_invalid

for diagnostics.

31. Old Newsletter links

Old Editions should still work years later.

But distinguish:

Historical editorial claim

In the September 2026 edition we discussed...

from:

Current market intelligence

Today's GERI is...

Do not silently replace the historical chart inside an old Newsletter with new data.

The click-through Dashboard can, however, show current intelligence.

That's an important distinction.

32. Newsletter-to-product mapping workflow

Release 1 should be manual through Admin.

Before publishing each Edition:

Edition
↓
Topic
↓
Primary Routine Step
↓
Featured Product
↓
Secondary Product (optional)
↓
Primary CTA

Example:

Edition:
Europe's Gas Storage...

Topic:
EU_STORAGE

Entry Step:
3 — Confirm

Featured Product:
STORAGE_WIDGET

Secondary Product:
DIR

You should control this editorially while learning what converts.

Automation comes later.

33. Newsletter images

Use frozen historical snapshots.

Once an Edition is published, do not replace its rendered Widget evidence with a new market snapshot.

Workflow:

Current Widget/Data
        ↓
Generate editorial image
        ↓
Stamp "Data as of..."
        ↓
Manual approval
        ↓
Publish
        ↓
Store immutable version

Recommended metadata:

edition_id
image_role
generated_at
data_as_of
dataset_snapshot_id
version

If correcting an error:

create:

v2

rather than overwriting v1 invisibly.

This creates editorial credibility.

34. Newsletter Companion

The Companion should answer:

What has changed since / relative to the topic you just read about?

Not simply reproduce the article.

Free
Article Context
↓
Today's relevant indicator
↓
One interpretation
↓
Continue Routine
Welcome Experience

Adds all temporarily unlocked relevant intelligence.

DIR

Adds full interpretation/scenarios where relevant.

GERI Live

Adds live risk movement.

Widget owner

Adds full corresponding market intelligence.

Bundle

Adds GERI Live + DIR interpretation.

This means the Companion is entitlement-aware without becoming six entirely separate components.

35. Separate internal Widget permission from embedding

Hard requirement:

widget_lng_internal

is completely different from:

widget_lng_embed

The Welcome Experience grants the former.

It does not grant the latter.

Likewise:

widget_storage_internal = true
widget_storage_embed = false

during Welcome.

36. External Widget minimum security model

I would not make this a Release-1 Dashboard blocker.

But when you implement embedding, minimum acceptable architecture should include:

Allowed domains
example.com
www.example.com
Site/embed key

Each installation receives a revocable identifier.

Signed bootstrap

Widget requests receive short-lived authorization from EnergyRiskIQ.

Server-side subscription verification

Never rely on Javascript hiding the data.

Domain/origin validation

Validate the requesting embedding context against the permitted domain.

Rate limits

Per subscription/site key.

Revocation

Disable domain or embed key immediately.

Expired subscription

Embed should render gracefully:

EnergyRiskIQ Widget subscription inactive.

Do not simply produce JavaScript errors.

Token rotation

Allow keys to be replaced if exposed.

And importantly:

Don't rely on Referer alone as your security model.

37. Future Widget Pack billing

Do not build it yet.

When introduced:

Individual widgets:

WTI €4.95
LNG €4.95
Storage €4.95

If a user purchases multiple:

eventually offer:

Market Tools Pack €9.95

Upgrade:

Individual → Pack = immediate/prorated.

Downgrade:

Pack → individual = period-end.

Never temporarily remove the customer's existing Widget while the billing transition occurs.

38. First Widget value milestone

This should unquestionably be:

WHAT CHANGED?

not Saved Presets.

Why?

Saved Presets make the software more convenient.

What Changed? makes the intelligence more valuable.

Example Storage:

Instead of:

EU Storage: 68.3%

show:

What changed?

+0.31 percentage points since yesterday.

Injection pace has slowed versus the recent 7-day average.

LNG:

JKM rose 4.2% over seven days while TTF was broadly stable.

WTI:

WTI is rising while Brent-WTI spread is narrowing.

That moves these products from widgets into decision-support tools.

39. Canonical analytics schema

Do not allow developers to invent random event properties.

Every event uses a standard envelope:

event_id
event_name
event_version

occurred_at_utc

user_id          nullable
visitor_id       nullable
session_id

source
campaign

newsletter_edition_id
topic_id

product_code
routine_step

entitlement_state
experience_type

experiment_variant

properties {}

Not every field must contain a value.

But every event uses the same structure.

40. Event naming

Use stable machine names.

Examples:

dashboard_viewed

routine_started
routine_step_viewed
routine_step_completed
routine_completed

premium_experience_started
premium_experience_expired

product_opened
premium_feature_encountered

offer_viewed
offer_clicked
offer_dismissed

checkout_started
subscription_started
subscription_upgraded

newsletter_context_opened

widget_opened
widget_interacted

Don't mix:

GERI clicked

geriOpen

open_geri

across different developers.

41. Critical events should be server-generated

Commercial events such as:

subscription_started

must come from server/Stripe state.

Not browser Javascript.

Likewise:

premium_experience_started

should be created server-side.

Client analytics are appropriate for:

card opened;
accordion viewed;
CTA clicked;
Routine UI behaviour.

This reduces analytics corruption.

42. Anonymous Newsletter attribution

At first EnergyRiskIQ visit create:

visitor_id = random UUID

Prefer a first-party/server-managed identifier.

Store Newsletter touch:

visitor_id
edition_id
timestamp
cta

Signup later:

visitor_id
      ↓
user_id

Then persist:

first acquisition touch

and:

last meaningful acquisition touch

separately.

43. Cross-device attribution

Before login:

You cannot reliably know that:

Phone visitor X

=

Desktop visitor Y.

Do not fingerprint users to solve this.

Once they authenticate:

both sessions become associated with:

user_id.

If they read LinkedIn on a phone and subscribe three days later on an unrelated desktop without ever logging in on the phone, attribution may be lost.

That's acceptable.

Don't build invasive tracking to solve a minor attribution problem.

44. Cookies blocked / consent unavailable

The core user experience must still work.

At minimum, URL context can survive:

Newsletter
↓
Signup
↓
immediate redirect

within the current flow.

If persistent attribution isn't permitted/available:

Don't persist it.

The person should still be able to use EnergyRiskIQ normally.

45. Privacy/consent architecture

Separate:

Essential product telemetry

Needed for:

entitlement security;
billing;
system reliability;
fraud/security;
core session behaviour.

from:

Product analytics

Used to understand behaviour.

from:

Marketing attribution/personalization

Used for campaign measurement and offers.

Store consent state:

consent_version
analytics_allowed
marketing_allowed
updated_at

Then analytics ingestion honours the state.

For GDPR/privacy implementation, retention periods and cookie classification should ultimately be checked against your actual implementation and legal/accounting requirements rather than relying only on product design assumptions.

46. Data deletion

Prepare for:

User requests deletion

You should be able to:

remove/pseudonymize behavioural history linked to the individual where required;
remove visitor→user linkage;
remove personalization data;
preserve only records you are legally required to retain, such as applicable accounting records.

This is easier if analytics does not contain raw personal information everywhere.

Avoid storing email addresses inside event payloads.

Use:

user_id.

47. Operational alerts

I would divide them by severity.

Critical — immediate
Paid entitlement disappears unexpectedly

Stripe says active:

EnergyRiskIQ says no access.

Mass entitlement discrepancy

Several users simultaneously affected.

Temporary entitlement system corrupt

Users gaining/losing capabilities incorrectly.

High
Daily intelligence late

Expected snapshot missed its grace window.

GERI Live stale

No updates within defined threshold.

Stripe webhook failures

Internal billing state not synchronized.

Medium
Newsletter deep-link error rate increases

For example > a defined percentage within a window.

Widget embed unexpectedly rejected

Valid subscriber/domain failing repeatedly.

Analytics event pipeline failure

Conversion funnel data missing.

These should go into operational monitoring—not merely logs that nobody reads.

48. Stripe reconciliation job

Do not depend only on webhooks.

Run a periodic reconciliation process:

Stripe subscription state
          ↕
Internal billing state
          ↕
Effective entitlements

If disagreement occurs:

alert + reconcile safely.

This is especially important because access to paid products becomes central to the Dashboard.

49. Rollback procedure

The rollback should be documented before rollout.

Problem detected

↓

1. Disable new Dashboard
dashboard_v2_enabled = false

Users return to Legacy Dashboard.

↓

2. Stop new Welcome activations if necessary
welcome_experience_enabled = false

↓

3. Stop Migration activations
migration_experience_enabled = false

↓

4. Preserve existing temporary grants

This is important.

A rollback should not automatically cancel Premium Experiences already promised to users.

↓

5. Disable affected checkout if necessary

If Bundle billing itself is the issue, temporarily suppress new Bundle purchases.

↓

6. Never modify existing Stripe subscriptions during UI rollback.

This should be a hard operational rule.

50. Database changes must be backward-compatible

Especially early on, prefer additive schema migrations:

CREATE entitlement_grants
CREATE access_experiences
CREATE newsletter_context
...

rather than destructively changing existing billing/user fields immediately.

Legacy Dashboard can continue functioning while V2 learns to use the new infrastructure.

Later, old fields can be retired.

This is effectively a strangler migration, and it's ideal here.

51. Automated acceptance tests

I would make these mandatory before production.

Entitlement lifecycle
Free
→ Welcome eligible
→ Welcome activated
→ Premium access
→ 168h expiry
→ Free
Existing Free
→ Migration eligible
→ Migration activated
→ Premium
→ Free
DIR subscriber
→ Migration GERI grant
→ expiry
→ DIR preserved
GERI subscriber
→ Migration DIR grant
→ expiry
→ GERI preserved
Billing
GERI → Bundle

Expected:

GERI remains available
DIR appears
Forecast remains
Stripe transition succeeds
no duplicate subscription.

And:

DIR → Bundle

Same checks.

Cancellation

Bundle cancellation:

access remains until billing-period end.

Then falls back to correct Free state.

Failed payment

Test:

active
→ payment failure
→ configured grace state
→ recovery

and:

active
→ failed retries
→ restricted
52. Welcome Widget tests

During Welcome:

widget_lng_internal = true
widget_lng_embed = false

After expiry:

widget_lng_internal = preview/free state
widget_lng_embed = false

Paid LNG subscriber:

widget_lng_internal = true
widget_lng_embed = true

if embedding is part of the paid entitlement.

53. Newsletter tests

Anonymous:

Newsletter LNG
→ EnergyRiskIQ
→ Signup
→ Dashboard
→ Step 3 open
→ LNG emphasized

Logged-in:

Newsletter LNG
→ Dashboard
→ Step 3 directly

Existing LNG subscriber:

Same experience—but no LNG upgrade offer.

Existing Bundle subscriber:

Full intelligence.

Invalid Edition:

Current Routine opens normally.

54. Data-failure tests

Must test:

GERI late

TTF unavailable

Storage stale

DIR generation missing

GERI Live API timeout

mixed stale/current signals

complete Step-3 partial failure.

The UI must never label old intelligence as current.

55. Device/state tests

Test:

Desktop → dismiss offer → mobile.

Expected:

offer remains suppressed.

Desktop → start Routine → mobile.

I would sync completion server-side.

So:

Step 1–3 completed on desktop

→ mobile shows:

3/5 completed.

That means Routine state belongs to the account—not browser local storage.

56. Routine persistence contract

Store:

user_id
routine_id
intelligence_date

started_at
completed_at

step_1_completed_at
step_2_completed_at
step_3_completed_at
step_4_completed_at
step_5_completed_at

You can later derive:

time to complete
abandonment step
cross-device continuation
retention.

Much better than keeping Routine progress purely in React state.

57. A practical Release-1 backend structure

I would expect something conceptually like:

USERS
  ↓

SUBSCRIPTIONS
  ↓
PRODUCT CATALOG
  ↓
PAID ENTITLEMENTS
        +
ACCESS EXPERIENCES
  ↓
TEMPORARY ENTITLEMENTS
        ↓
EFFECTIVE ENTITLEMENT SERVICE

--------------------------------

INTELLIGENCE DATA
        ↓
NORMALIZED SNAPSHOT SERVICE
        ↓
ROUTINE API
        ↓
DASHBOARD

--------------------------------

NEWSLETTER EDITIONS
        ↓
CONTEXT ROUTER
        ↓
VISITOR / USER ATTRIBUTION
        ↓
DASHBOARD ROUTINE

--------------------------------

EVENTS
        ↓
ANALYTICS
        ↓
CONVERSION FUNNEL

That's the architecture I would develop around.

58. What I would deliberately not build yet

This list is just as important.

Do not let Release 1 get delayed by:

AI recommendation engine;
sophisticated product-interest scores;
external Widget analytics dashboard;
agency Widget licenses;
Widget Pack;
Complete Intelligence plan;
automatic Newsletter mapping;
dynamic event passes;
dozens of Dashboard customizations;
complicated drag-and-drop cards;
user-defined Routine structures.

First prove:

Routine → return → premium discovery → subscription.

59. The ten implementation decisions are therefore resolved
1. Release 1

Routine + entitlement + Welcome/Migration + Newsletter context + analytics + safe billing.

Not every long-term commercial feature.

2. Current Dashboard

Keep it intact behind a feature flag as rollback. Build V2 in parallel.

3. Data contract

One normalized snapshot envelope + defined contract for each of the five Routine steps.

4. Entitlements

One server-side capability API. Additive grants. Paid access never overwritten by temporary access.

5. Stripe

Authoritative Product Catalog, real €29 Bundle product, individual Widget products, immediate prorated upgrades, period-end downgrades.

6. Newsletter identity

First-party anonymous visitor ID → user association after authentication. No fingerprinting. Graceful behaviour without tracking.

7. Widget security

Separate internal and embed permissions. Sophisticated external embedding does not block Dashboard R1.

8. Analytics

One versioned event envelope shared by acquisition, Routine, products and billing.

9. Rollback

Feature flags disable V2/activation while preserving subscriptions and already granted temporary access.

10. Tests

Entitlement lifecycle + billing + Newsletter context + stale data + mobile/multi-device tests are deployment gates.

The most important architectural consequence

We now have three things that must become the backbone of Dashboard V2:

1. INTELLIGENCE SNAPSHOT SERVICE
   "What intelligence exists right now?"

2. ENTITLEMENT SERVICE
   "How much of it may this user access?"

3. ROUTINE SERVICE
   "Where is this user in today's workflow?"

Everything else becomes presentation.

The React Dashboard should essentially ask:

GET today's intelligence
GET my entitlements
GET my Routine state
GET my current context

and then render the appropriate experience.

That separation is what will make the Dashboard stable, reversible, personalization-ready and commercially flexible.

At this point, I would consider the strategic architecture sufficiently locked to begin technical design. The next artifact I would create before writing frontend code is a Dashboard V2 Technical Blueprint containing the database tables, API endpoints and response schemas, entitlement mappings for every plan, Routine state machine, feature flags, Newsletter context schema, Stripe webhook flows, and the exact React component tree. That would bridge these decisions directly into development.
