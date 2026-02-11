# EnergyRiskIQ - Event Ingestion & Risk Intelligence Pipeline

## Overview
EnergyRiskIQ is an event ingestion, classification, AI analysis, and risk scoring pipeline for energy risk intelligence. It fetches news events, classifies them, enriches them with AI, and computes quantitative risk scores. The project aims to provide a comprehensive risk intelligence platform with a global alerts factory for fanout delivery, offering a complete risk intelligence platform for market advantage and a daily AI-powered briefing.

## User Preferences
The user prefers clear, concise communication. They value an iterative development approach, with a focus on delivering functional components incrementally. They prefer to be consulted before any major architectural changes or significant code refactoring. Detailed explanations of complex features are appreciated, especially regarding AI models and risk scoring logic.

## System Architecture

EnergyRiskIQ is built with a modular architecture, separating concerns into distinct services for ingestion, AI processing, risk scoring, and alerting.

**UI/UX Decisions:**
- The project includes marketing landing pages, user authentication flows, and an admin portal.
- User-facing dashboards provide event queries, risk summaries, and alert history.
- Admin UI allows management of plan settings.
- Public-facing SEO-optimized pages for indices like EERI and EGSI, including methodology and historical data.

**Technical Implementations:**
- **Event Ingestion:** RSS feeds are fetched and categorized using keyword classification.
- **AI Processing:** Utilizes OpenAI (gpt-4.1-mini) for event enrichment, summarization, impact analysis, and detailed daily index interpretations.
- **Risk Scoring:** A dedicated engine computes quantitative risk scores for events, regions, and assets, including trend analysis. This includes Global Energy Risk Index (GERI v1.1 with Regional Weighting Model), Regional Escalation Risk Index (RERI/EERI), and Europe Gas Stress Index (EGSI-M, EGSI-S).
- **GERI Regional Weighting Model (v1.1):** Pre-aggregation multipliers on risk scores based on region-cluster influence: Middle East (25%), Russia/Black Sea (20%), China (15%), United States (15%), Europe Internal (10%), LNG Exporters (10%), Emerging Supply Regions (5%). Russia keywords override Europe classification. LNG exporter keywords (Qatar, Australia, Norway) override to LNG cluster. Global/unattributed events get neutral 1.0x weight. Multipliers are scaled so the average equals 1.0, preserving overall index scale. Files: `src/geri/types.py` (config + mapping), `src/geri/compute.py` (application).
- **Alerting & Delivery:** A global alerts factory generates user-agnostic `alert_events`. Index & Digest delivery (`src/delivery/pro_delivery_worker.py`) sends daily GERI + EERI + EGSI + AI Digest to ALL plan tiers via email and Telegram, with plan-tiered content depth (Free=24h delayed/basic, Personal=realtime+trends, Trader=regime+probability, Pro=decomposition+scenarios, Enterprise=full institutional). GitHub Actions triggers at 07:00 UTC daily. AI digests are cached per plan tier to save API costs. Deduplication via `geri_date` unique index per user/channel.
- **User Delivery Preferences:** Users opt-in per index (GERI, EERI, EGSI, Daily Digest) for Email and/or Telegram delivery via `user_delivery_preferences` table. Settings page shows 4 toggle cards with auto-save. Telegram checkboxes disabled if account not linked. All plans can set up Telegram notifications. API: GET/PUT `/users/delivery-preferences`.
- **User & Plan Management:** Handles user signup, verification, password/PIN setup, and assigns subscription tiers based on `plan_settings`.
- **API:** A FastAPI application serves as the primary interface for events, risk intelligence, alerts, marketing content, and internal operations.
- **SEO Growth System:** Generates SEO-optimized daily alert pages with a 24-hour delay, dynamic sitemaps, and rich meta-data, including regional daily alerts and contextual linking.
- **Billing & Subscription:** Integrates with Stripe for subscription management and webhook handling.
- **GERI Plan-Tiered Dashboard:** Progressive intelligence depth across 5 subscription tiers (Free→Enterprise). Free: 24h delayed data via `/geri/public`, 14-day Brent chart, simplified 3-category drivers (Geopolitical/Energy Supply/Market Stress). Personal: real-time data, 90-day history, single asset selector, expanded drivers with regions/severity. Trader: full history, 2 simultaneous overlays, smoothing (Raw/3D MA/7D MA), regime markers, momentum panel. Pro: 4 overlays, AI narrative access. Enterprise: 5 overlays, team workspace. Feature gating via `GERI_PLAN_CONFIG` object. Contextual upgrade prompts replace hard lockouts.
- **EERI Pro Dashboard Module:** Provides Pro-tier users with real-time EERI display, component breakdown, asset stress panel, top risk drivers, historical intelligence, regime statistics, and daily AI-generated summaries.
- **Daily Geo-Energy Intelligence Digest:** AI-powered daily briefing on user dashboard (`/users/account`) with plan-tiered features. Free: executive snapshot + 2 alerts + GERI direction + 24h delay. Personal: multi-index + 7d trends + correlations. Trader: regime classification + probability scoring. Pro: beta sensitivities + scenario forecasts. Enterprise: full institutional intelligence. API endpoint at `/api/v1/digest/daily`. Uses OpenAI gpt-4.1-mini for narrative generation.
- **EGSI Indices:** EGSI-M (Market/Transmission) measures gas market stress, while EGSI-S (System) measures storage/refill/winter stress, incorporating real AGSI+ EU storage data and live TTF prices.
- **ERIQ Expert Analyst:** AI-powered interpretation intelligence bot accessible only at authenticated `/users/account` page. Uses GPT-5.1 (max_completion_tokens, no temperature param) with RAG from `/ERIQ/*.md` knowledge base (196 chunks from 6 methodology documents). Product Analytics & Feedback Layer: structured feedback tags (helpful, not_helpful, inaccurate, etc.), internal analytics endpoint (`GET /api/v1/eriq/analytics` secured by INTERNAL_RUNNER_TOKEN) tracking top questions, low-satisfaction responses, intent/mode distribution, plan usage, tag distribution, daily volume, 30-day summary. Analytics insights fed into CAL context for self-improvement. Context Assembly Layer (CAL) reads from production database via `execute_production_query` (uses `PRODUCTION_DATABASE_URL` env var if set, falls back to `DATABASE_URL`). CAL provides read-only, plan-gated database snapshots across all 10 integration domains: index engine outputs (GERI as `global:geo_energy_risk`, EERI as `europe:eeri` with full JSONB components/drivers parsing), alert intelligence, asset intelligence (Brent/WTI/TTF/VIX/EUR-USD/EU storage), methodology knowledge base (196 RAG chunks), regime classification, correlations/betas (rolling 14-day/30-day), data quality assessment, historical patterns, and plan-based entitlements. Free tier gets 24h-delayed data, 3 q/day (Explain only). Personal: realtime + 15 q/day + Interpret. Trader: 60 q/day + Decide-support + drivers/regime. Pro: 200 q/day + full suite. Enterprise: unlimited. EGSI tables use `index_date` column and `components_json` JSONB. Files: `src/eriq/context.py` (CAL), `src/eriq/knowledge_base.py` (RAG), `src/eriq/router.py` (intent routing), `src/eriq/agent.py` (answer generation), `src/api/eriq_routes.py` (API endpoints). API: POST `/api/v1/eriq/ask`, GET `/api/v1/eriq/status`, POST `/api/v1/eriq/feedback`, GET `/api/v1/eriq/history`.

**System Design Choices:**
- **Database:** PostgreSQL is used for persistence.
- **Background Workers:** Ingestion, AI, Risk, and Alerts components are designed as separate, orchestratable workers.
- **Concurrency:** FastAPI with uvicorn for asynchronous API operations.
- **Alerting Production Safety:** Employs advisory locks, unique constraints, `FOR UPDATE SKIP LOCKED`, and robust retry/backoff mechanisms to ensure reliable delivery.
- **Digest System:** Consolidates multiple alert deliveries into periodic summary messages.
- **Daily Intelligence Digest:** AI-powered daily briefing synthesizing alerts into actionable intelligence, with tiered access.
- **Production Hardening:** Includes preflight checks, health checks, user allowlisting, and circuit breakers.
- **Observability:** Tracks engine runs and provides internal API endpoints for monitoring.

## Planned Features (High Importance)

### Source Weighting Calibration Model
**Priority:** High | **Status:** Waiting for data (need 60+ days of scored events and daily GERI values) | **Target:** When production DB has sufficient history

Adaptive source weighting system that calibrates feed weights based on measured contribution to predictive power, uniqueness, timeliness, and false-positive control.

**Step A — Per-Source Quality Score (0-1):**
`Q_s = 0.35*Cred_s + 0.25*Uniq_s + 0.20*Timely_s + 0.20*Impact_s`
- Cred_s: Source credibility (institutional > trade > general) — already in `signal_quality.py`
- Uniq_s: % of items not semantically duplicated within 24h — needs dedup tracker
- Timely_s: Median time-to-first-report vs other sources on same event cluster
- Impact_s: Correlation between source-driven events and subsequent GERI delta / asset moves

**Step B — Softmax Normalization:**
`w_s = (Q_s ^ γ) / Σ(Q_j ^ γ)` with γ = 1.5 (gentle sharpening)

**Step C — Guardrails:**
- Weight floor: w_s >= 0.03 for Tier 0/1 sources
- Weight cap: w_s <= 0.12 for any single source
- Region cap: no region cluster exceeds 0.35 of total weight

**Step D — Noise Tax:**
`w_s = w_s * (Precision_s ^ η)` with η = 0.7 (penalizes high-volume low-precision sources)

**Phased Implementation Plan:**
1. Phase 1 (after 30 days): Implement Steps B+C+D using existing SOURCE_CREDIBILITY as Q_s. Add title-based Jaccard similarity for Uniq_s. Track per-source precision.
2. Phase 2 (after 60 days): Add Timely_s (event clustering + time-to-report). Add Impact_s (GERI/asset correlation analysis).

**Key Dependencies:** Sufficient scored event history, daily GERI time-series, asset price alignment.
**Files to modify:** `src/ingest/signal_quality.py`, `src/config/feeds.json`, new `src/ingest/source_calibration.py`

## External Dependencies

- **Database:** PostgreSQL
- **AI:** OpenAI (gpt-4.1-mini)
- **Payment Processing:** Stripe (Live mode). Note: The Replit Stripe integration shows "Sandbox" but is NOT used — Live keys are stored directly as Replit Secrets (`STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`). The code in `stripe_client.py` checks environment variable secrets first, so the integration connector is bypassed. Webhook endpoint: `https://energyriskiq.com/api/v1/billing/webhook`.
- **Email Service:** Brevo
- **Messaging Service:** Telegram Bot API
- **SMS Service:** Twilio (optional)
- **Gas Storage Data:** AGSI+ (GIE API)
- **Gas Price Data:** OilPriceAPI (for TTF natural gas)
- **Oil Price Data:** OilPriceAPI (for Brent/WTI crude oil)
- **VIX Data:** Yahoo Finance (yfinance) primary, FRED (Federal Reserve Bank of St. Louis) fallback — no API key required
- **FX Data:** Oanda (for EUR/USD)
- **Python Libraries:** FastAPI, uvicorn, feedparser, psycopg2-binary, openai, stripe, requests, python-dotenv, yfinance.