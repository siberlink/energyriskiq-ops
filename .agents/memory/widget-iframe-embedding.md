---
name: Embeddable widget iframe headers
description: How to make /embed/* widgets framable everywhere, including local file:// test pages
---

# Embeddable widget iframe framing

Public embeddable widgets (e.g. `/embed/europe-gas-storage-widget`, `/embed/wti-crude-oil-widget`, and their `-pro` variants) must be framable from ANY context, including a user's local `file:///...html` test page.

**Rule:** Do NOT send `X-Frame-Options` and do NOT send `Content-Security-Policy: frame-ancestors ...` on these embed responses. Send only `Cache-Control`. With no framing headers, browsers allow framing from any origin.

**Why:**
- `X-Frame-Options: ALLOWALL` is invalid (only DENY/SAMEORIGIN are valid). Browsers reject it and fall back to blocking → "refused to connect".
- `Content-Security-Policy: frame-ancestors *;` looks permissive but the `*` source only matches **network schemes** (http/https/ws/wss/ftp). It does NOT match the opaque `file://` origin, so embedding from a local HTML file still gets blocked ("refused to connect"). Users very commonly test embed snippets from a local `file://` page first, then report the widget "not displaying".

**How to apply:** Any new `/embed/*` widget route should return `HTMLResponse(..., headers={"Cache-Control": "public, max-age=120"})` with no frame headers. There is no global X-Frame-Options middleware in `src/api/app.py`, so omitting per-route framing headers is sufficient. Note a proxy rewrites `Cache-Control: public` → `private` in production; that is unrelated to framing.
