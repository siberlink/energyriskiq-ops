# EnergyRiskIQ - Event Ingestion & Risk Intelligence Pipeline

## Overview
EnergyRiskIQ is an event ingestion, classification, AI analysis, and risk scoring pipeline for energy risk intelligence. It aims to provide a comprehensive risk intelligence platform with a global alerts factory for fanout delivery, offering a complete risk intelligence platform for market advantage and a daily AI-powered briefing.

## User Preferences
The user prefers clear, concise communication. They value an iterative development approach, with a focus on delivering functional components incrementally. They prefer to be consulted before any major architectural changes or significant code refactoring. Detailed explanations of complex features are appreciated, especially regarding AI models and risk scoring logic.

## System Architecture

EnergyRiskIQ is built with a modular architecture, separating concerns into distinct services for ingestion, AI processing, risk scoring, and alerting.

**UI/UX Decisions:**
- Marketing landing pages, user authentication flows, and an admin portal are included.
- User-facing dashboards provide event queries, risk summaries, and alert history.
- Admin UI allows management of plan settings.
- Public-facing SEO-optimized pages for indices like GERI, EERI and EGSI, including methodology and historical data. GERI, EERI, and EGSI public pages use digest-style dark theme (get_digest_dark_styles, render_digest_footer) with full 2-paragraph AI interpretation. Nav: GERI, EERI, EGSI, Digest, History, Get FREE Access. EGSI page shows both EGSI-M (Market Stress) and EGSI-S (System Stress) cards with 24h delay, plus 5 Chart.js charts (7-day and 30-day for each index, plus 30-day comparison).

**Technical Implementations:**
- **Event Ingestion:** RSS feeds are fetched and categorized using keyword classification.
- **AI Processing:** Utilizes OpenAI (gpt-4.1-mini) for event enrichment, summarization, impact analysis, and detailed daily index interpretations.
- **Risk Scoring:** A dedicated engine computes quantitative risk scores for events, regions, and assets, including trend analysis. This includes Global Energy Risk Index (GERI v1.1 with Regional Weighting Model), Regional Escalation Risk Index (RERI/EERI), and Europe Gas Stress Index (EGSI-M, EGSI-S). The GERI Regional Weighting Model applies pre-aggregation multipliers based on region-cluster influence.
- **GERI Live:** Real-time intraday GERI index for Pro/Enterprise users. Recomputes as alerts are processed (60s debounce). Backend: `src/geri/live.py` (engine) + `src/geri/live_routes.py` (REST/SSE). Frontend: `section-geri-live` in users-account.html with sparkline, drivers, regions, activity feed. SSE streaming via `asyncio.Queue` per client. AI interpretation regenerates on ≥2pt change or band change. DB: `geri_live` table (intraday history). Quick Insights strip: velocity indicator (pts/hr momentum), band proximity warning (within 5pts of threshold), day high/low with timestamps. Professional Intelligence Modules: 6 profile cards (Traders, Risk Managers, Hedge Fund, Analysts, Procurement, Insurance). Energy Commodity Trader module (`src/geri/live_trader_intel.py`) has 5 live features: (1) Price-Risk Correlation Signal (Brent/WTI/TTF/VIX prices + GERI divergence detection + 7-day correlation), (2) Trading Risk Heatmap (Oil/Gas/Freight/Power risk intensity from today's alerts), (3) Position Risk Alerts (band proximity, velocity, commodity-specific exposure warnings with actions), (4) Intraday Risk Windows (Asia/London/NY/After Hours sessions with GERI avg/delta/alert counts), (5) Flash Headline Feed (severity ≥4 alerts with GERI impact and asset tags). API: `GET /api/v1/indices/geri/live/trader-intel`. Docs: `docs/geri-live.md`.
- **Alerting & Delivery:** A global alerts factory generates `alert_events`. Index & Digest delivery sends daily GERI + EERI + EGSI + AI Digest to all plan tiers via email and Telegram, with plan-tiered content depth. User delivery preferences are configurable.
- **User & Plan Management:** Handles user signup, verification, password/PIN setup, and assigns subscription tiers based on `plan_settings`.
- **API:** A FastAPI application serves as the primary interface.
- **SEO Growth System:** Generates SEO-optimized daily alert pages, dynamic sitemaps, and rich meta-data.
- **Billing & Subscription:** Integrates with Stripe for subscription management.
- **Plan-Tiered Dashboards:** Progressive intelligence depth across 5 subscription tiers for GERI, EERI, and EGSI dashboards. Each upgraded plan inherits all previous plan features plus unique tier-specific capabilities (proper feature cascading). EGSI example: Trader gets 9 base modules (momentum, divergence, drivers, radar, scenarios, regime history, asset overlay, storage seasonal, analog finder). Pro adds rolling correlations, component decomposition, regime transition probability. Enterprise adds cross-index contagion/spillover analysis.
- **Daily Geo-Energy Intelligence Digest:** AI-powered daily briefing on the user dashboard with plan-tiered features, generated using OpenAI gpt-4.1-mini.
- **ERIQ Expert Analyst:** An AI-powered interpretation intelligence bot using GPT-5.1 (with gpt-4.1-mini fallback) and RAG from a knowledge base. Accessible from the dedicated ERIQ section and as contextual widgets on GERI, EERI, and EGSI dashboard pages. Context-aware: passes `page_context` (geri/eeri/egsi) to the AI so responses focus on the index the user is viewing. Includes Product Analytics & Feedback Layer, Context Assembly Layer (CAL) for plan-gated database snapshots, and per-page conversation history.
- **ERIQ Token Economy:** Manages plan-based monthly token allowances and purchased token balances, resetting on Stripe subscription payment events.
- **ELSA Marketing Bot:** An AI-powered marketing and business intelligence advisor (GPT-5.1 with gpt-4.1-mini fallback) for the admin dashboard. Provides strategic advice on marketing, SEO, content strategy, user growth, and revenue optimization. Has full access to production database metrics, all documentation (/docs, /ERIQ), and conversation history organized by topics. Located in `src/elsa/` with agent, knowledge_base, context, and routes modules. Database tables: `elsa_topics`, `elsa_conversations`. Features: SSE streaming responses (word-by-word like ChatGPT), cross-topic memory (pulls insights from ALL past topics into every conversation), and image upload/interpretation (vision API for analyzing screenshots, charts, competitor pages). Image generation via DALL-E 3 with platform-specific presets (LinkedIn post/banner/cover, Facebook post/cover, X/Twitter post/header, custom square/landscape/portrait/wide banner), quality (standard/HD) and style (vivid/natural) options, download capability.
- **Ticketing System:** Encapsulated support ticket module in `src/tickets/` (db.py, routes.py). Database tables: `tickets`, `ticket_messages`. User-side UI in users-account.html with create/list/detail views, category filtering (Support, Billing, Feature Suggestion, Other), and 30-second unread polling. Admin-side UI in admin.html with stats dashboard, status/category filters, ticket list with unread indicators, detail view with message thread, reply, and status management. Admin auth uses shared `X-Admin-Token` via `verify_admin_token`. Both sides have live unread badge notifications.
- **Blog:** Public educational blog at `/blog` with separate blog user system (`blog_users` table, cookie-based auth). Blog users can register, sign in, write articles (submitted as `pending`), and comment. Visitors can also comment as guests. Admin manages articles from `/admin` (Blog section): create/publish directly, approve/reject user submissions, delete posts. Database tables: `blog_posts` (with slug, status workflow, categories, tags, Markdown content), `blog_comments`, `blog_users`. Module: `src/blog/` (db.py, routes.py). Server-rendered HTML pages with dark/light theme toggle (CSS custom properties, localStorage persistence, dark default matching GERI/EERI public page background #0f172a), responsive design. Markdown rendering for article content. Categories: Energy Markets, Geopolitics, Risk Management, Oil & Gas, Renewables, Climate & ESG, Trading Strategies, Industry Analysis, General.

**System Design Choices:**
- **Database:** PostgreSQL is used for persistence. Single production database architecture: `get_database_url()` in `src/db/db.py` always prefers `PRODUCTION_DATABASE_URL` over `DATABASE_URL`. This means ALL queries everywhere — `get_cursor`, `execute_query`, `execute_one`, and all production variants — always connect to the production database. No development database queries exist.
- **Background Workers:** Ingestion, AI, Risk, and Alerts components are designed as separate, orchestratable workers.
- **Concurrency:** FastAPI with uvicorn for asynchronous API operations.
- **Alerting Production Safety:** Employs advisory locks, unique constraints, and robust retry/backoff mechanisms.
- **Digest System:** Consolidates multiple alert deliveries into periodic summary messages.
- **Production Hardening:** Includes preflight checks, health checks, user allowlisting, and circuit breakers.
- **Observability:** Tracks engine runs and provides internal API endpoints for monitoring.

## Test Credentials
- **Email:** emil.siberlink@gmail.com
- **Password:** Regen@3010
- **PIN:** 221967
- **Testing approach:** Always test on Production DB. User tests in production.

## External Dependencies

- **Database:** PostgreSQL
- **AI:** OpenAI (gpt-4.1-mini, GPT-5.1)
- **Payment Processing:** Stripe (Live mode)
- **Email Service:** Brevo
- **Messaging Service:** Telegram Bot API
- **SMS Service:** Twilio (optional)
- **Gas Storage Data:** AGSI+ (GIE API)
- **Gas Price Data:** OilPriceAPI (for TTF natural gas)
- **Oil Price Data:** OilPriceAPI (for Brent/WTI crude oil)
- **VIX Data:** Yahoo Finance (yfinance), FRED
- **FX Data:** Oanda (for EUR/USD)
- **Python Libraries:** FastAPI, uvicorn, feedparser, psycopg2-binary, openai, stripe, requests, python-dotenv, yfinance.

## Planned Future Upgrades

### ELSA Intelligence Upgrade — Curated Product Knowledge Layer
Rather than feeding the entire codebase into every ELSA conversation (which would be too expensive and dilute context), build a smarter middle ground:
1. **App Capabilities Summary** — A structured document describing each page, what each plan tier actually gets, which features exist vs. are planned. This gives ELSA strategic context without the token cost of raw code.
2. **Page/Route Inventory** — A simple list of all routes and what they do, so ELSA knows the full product surface.
This approach makes ELSA significantly smarter about the product (feature suggestions, gap identification, better business advice) without the downsides of raw code access (context window limits, cost, diminishing returns).