---
name: Blog new-article newsletter auto-send
description: How publishing a blog article auto-emails the Energy Intelligence list, and how to later gate it to selected authors.
---

# New-article excerpt email

When a blog article becomes `published`, an excerpt email auto-sends to the Brevo
"Energy Intelligence" list (id 7). Subject: "New Energy Intelligence Article
Available"; body = title, cover image, excerpt, "Read Article" link.

## Key design
- **Trigger:** all three publish paths (admin create, admin update, admin
  update-status) enqueue the send via FastAPI `BackgroundTasks` when final
  status is `published`. Never blocks the admin request.
- **Send-once guard:** `blog_posts.newsletter_sent_at` (TIMESTAMP). Claimed
  atomically with `UPDATE ... WHERE newsletter_sent_at IS NULL RETURNING id`
  before sending; released (`clear_post_newsletter_sent`) only if the send
  fails, so editing/re-publishing an already-sent post never re-sends.
- **Gating for "selected authors":** `blog_users.newsletter_auto_send` BOOLEAN
  DEFAULT TRUE. `should_send_newsletter_for_author(author_id)` returns the flag
  (admin-authored posts have `author_id IS NULL` → always send today). To later
  restrict to selected authors, flip non-selected authors' flag to FALSE (or
  change the default + opt-in).
- **Send mechanism:** reuses transactional `/v3/smtp/email` with per-recipient
  `messageVersions` (batches of 500) — recipients never see each other.
  Considered success only when ALL batches succeed (partial failure releases the
  guard so a later publish retries).

**Why:** user wanted auto-send now for everyone, but the architecture must
support restricting auto-send to selected authors later without a refactor.
