---
name: Bundled bonus entitlements
description: How to bundle other paid features as a "bonus" of one parent subscription so access auto-revokes
---

Rule: when one subscription grants bonus access to other paid features, never copy/flag entitlements into the bonus features' own tables. Derive them live at every gate: `own_sub_active(row) or parent_sub_active(user_id)`.

**Why:** copied flags require cleanup on cancel (webhooks can be missed); live derivation makes bonus access revoke automatically the instant the parent sub cancels.

**How to apply:** wire the parent check (e.g. `user_has_geri_live()`) into every enforcement point of each bonus feature — status endpoints (also expose a `*_bonus` field for UI), runtime/embed checks, and download/API gates. Import lazily inside a small helper with try/except to avoid circular imports. Status endpoints stay mode-aware for account management; the bonus check is mode-agnostic like other runtime entitlements.
