---
name: Dashboard V2 technical blueprint
description: Durable engineering decisions for the next Dashboard architecture and its first release.
---

Dashboard V2 should be built as a focused vertical slice around the daily intelligence workflow: Routine completion, return behavior, premium discovery, and safe subscription conversion. The first release must not expand into the future Widget Pack, Complete Intelligence plan, advanced personalization, automated Newsletter mapping, or a rebuilt external embedding platform.

**Why:** A parallel, feature-flagged V2 with the legacy Dashboard preserved avoids ambiguous mixed states for access, banners, Routine progress, and analytics, while allowing staged rollout and safe rollback.

**How to apply:** Keep V2 and legacy routing separate during rollout; retain legacy through the agreed stability window; make rollback disable presentation or new activations without modifying existing Stripe subscriptions or already-promised temporary access.

The three architectural backbones are an Intelligence Snapshot Service, an Entitlement Service, and a Routine Service. Intelligence must use a normalized snapshot envelope with explicit freshness and partial-failure states. Access must be capability-based and additive, with paid and temporary grants resolved server-side; internal Widget access must remain distinct from external embedding. Routine progress belongs to the account and must be snapshot-aware for cross-device continuation.

**Why:** These separations prevent each frontend component from inventing data freshness, access, or progress rules and make the Dashboard reversible, measurable, and ready for later personalization.

**How to apply:** Build the snapshot contract, capability vocabulary, temporary experience/grant records, audit trail, and server-side APIs before expanding the React surface. Never label stale data as current, silently fall back to Free on entitlement lookup failure, or let an expired temporary grant override paid access.

The canonical final decisions are stored in [Dashboard V2 Resolved Decisions.md](../../Dashboard%20V2%20Resolved%20Decisions.md). They lock meaningful-intent Welcome activation, the hybrid bootstrap API, the 14-day opt-in Migration Experience, a 24-hour last-known-good entitlement cache, deferred Widget Pack, behavior-triggered Bundle offers, and the definitive seven-group sidebar.

**Why:** This preserves editorial credibility, prevents URL parameters from changing funnel logic, and keeps conversion reporting trustworthy without requiring invasive cross-device tracking.

**How to apply:** Treat the resolved-decision document as authoritative for Release 1 behavior, the technical blueprint as the engineering structure, and the architecture document as the strategic context. Keep physical schema names and implementation details consistent with those sources rather than reopening locked product decisions in UI components.