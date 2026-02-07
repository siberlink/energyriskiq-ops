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
- **Risk Scoring:** A dedicated engine computes quantitative risk scores for events, regions, and assets, including trend analysis. This includes Global Energy Risk Index (GERI), Regional Escalation Risk Index (RERI/EERI), and Europe Gas Stress Index (EGSI-M, EGSI-S).
- **Alerting & Delivery:** A global alerts factory generates user-agnostic `alert_events` which are fanned out to eligible users via `user_alert_deliveries` supporting email, Telegram, and SMS with quotas and cooldowns. Features tiered delivery for Pro and Trader plans, with specific batching windows and prioritization.
- **User & Plan Management:** Handles user signup, verification, password/PIN setup, and assigns subscription tiers based on `plan_settings`.
- **API:** A FastAPI application serves as the primary interface for events, risk intelligence, alerts, marketing content, and internal operations.
- **SEO Growth System:** Generates SEO-optimized daily alert pages with a 24-hour delay, dynamic sitemaps, and rich meta-data, including regional daily alerts and contextual linking.
- **Billing & Subscription:** Integrates with Stripe for subscription management and webhook handling.
- **GERI Plan-Tiered Dashboard:** Progressive intelligence depth across 5 subscription tiers (Free→Enterprise). Free: 24h delayed data via `/geri/public`, 14-day Brent chart, simplified 3-category drivers (Geopolitical/Energy Supply/Market Stress). Personal: real-time data, 90-day history, single asset selector, expanded drivers with regions/severity. Trader: full history, 2 simultaneous overlays, smoothing (Raw/3D MA/7D MA), regime markers, momentum panel. Pro: 4 overlays, AI narrative access. Enterprise: 5 overlays, team workspace. Feature gating via `GERI_PLAN_CONFIG` object. Contextual upgrade prompts replace hard lockouts.
- **EERI Pro Dashboard Module:** Provides Pro-tier users with real-time EERI display, component breakdown, asset stress panel, top risk drivers, historical intelligence, regime statistics, and daily AI-generated summaries.
- **Daily Geo-Energy Intelligence Digest:** AI-powered daily briefing on user dashboard (`/users/account`) with plan-tiered features. Free: executive snapshot + 2 alerts + GERI direction + 24h delay. Personal: multi-index + 7d trends + correlations. Trader: regime classification + probability scoring. Pro: beta sensitivities + scenario forecasts. Enterprise: full institutional intelligence. API endpoint at `/api/v1/digest/daily`. Uses OpenAI gpt-4.1-mini for narrative generation.
- **EGSI Indices:** EGSI-M (Market/Transmission) measures gas market stress, while EGSI-S (System) measures storage/refill/winter stress, incorporating real AGSI+ EU storage data and live TTF prices.

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
- **Payment Processing:** Stripe
- **Email Service:** Brevo
- **Messaging Service:** Telegram Bot API
- **SMS Service:** Twilio (optional)
- **Gas Storage Data:** AGSI+ (GIE API)
- **Gas Price Data:** OilPriceAPI (for TTF natural gas)
- **Oil Price Data:** OilPriceAPI (for Brent/WTI crude oil)
- **VIX Data:** Yahoo Finance (yfinance)
- **FX Data:** Oanda (for EUR/USD)
- **Python Libraries:** FastAPI, uvicorn, feedparser, psycopg2-binary, openai, stripe, requests, python-dotenv, yfinance.