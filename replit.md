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
- **EERI Pro Dashboard Module:** Provides Pro-tier users with real-time EERI display, component breakdown, asset stress panel, top risk drivers, historical intelligence, regime statistics, and daily AI-generated summaries.
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