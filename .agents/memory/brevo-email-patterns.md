---
name: Brevo email-sending patterns
description: The two Brevo send mechanisms in this codebase (transactional vs list growth) and which to reuse.
---

# Brevo email in EnergyRiskIQ

Two distinct Brevo usages exist — pick the right one:

1. **Transactional send (one or few recipients)** — the canonical pattern.
   - Reference impl: admin "Users → send email" (`src/api/admin_routes.py`,
     `admin_send_email` / `POST /users/send-email`). Also `src/alerts/channels.py` `_send_brevo`.
   - `POST https://api.brevo.com/v3/smtp/email`, header `api-key: BREVO_API_KEY`.
   - Sender is parsed from env `EMAIL_FROM` (format `Name <addr@domain>` → `{name,email}`,
     else `{email}`). Default `EnergyRiskIQ <alerts@energyriskiq.com>`.
   - Body uses `htmlContent` (admin) or `textContent` (alerts). Success codes: 200/201/202.

2. **List subscribe (contact growth, not sending)** — `POST /v3/contacts`
   with `{email, listIds:[id], updateEnabled:true}`. Used by blog newsletter signup.
   List "Energy Intelligence" = id **7** (env `BREVO_BLOG_LIST_ID`, default 7).

## Sending an email to a whole list (e.g. new-article newsletter)
`/v3/smtp/email` does NOT accept a listId. Reuse the **transactional** pattern but:
- Fetch list members: `GET /v3/contacts/lists/{id}/contacts?limit=500&offset=…` (paginate),
  skip `emailBlacklisted` contacts.
- Send with **`messageVersions`** (one `{to:[{email}]}` per recipient, ≤1000 per call,
  batch the rest) so recipients are NOT exposed to each other (never dump everyone into a
  shared `to[]` — that leaks all addresses).
**Why:** keeps a single consistent sender/auth pattern, list-targeted, privacy-safe.
