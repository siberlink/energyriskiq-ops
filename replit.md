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
- Public-facing SEO-optimized pages for indices like EERI and EGSI, including methodology and historical data.

**Technical Implementations:**
- **Event Ingestion:** RSS feeds are fetched and categorized using keyword classification.
- **AI Processing:** Utilizes OpenAI (gpt-4.1-mini) for event enrichment, summarization, impact analysis, and detailed daily index interpretations.
- **Risk Scoring:** A dedicated engine computes quantitative risk scores for events, regions, and assets, including trend analysis. This includes Global Energy Risk Index (GERI v1.1 with Regional Weighting Model), Regional Escalation Risk Index (RERI/EERI), and Europe Gas Stress Index (EGSI-M, EGSI-S). The GERI Regional Weighting Model applies pre-aggregation multipliers based on region-cluster influence.
- **Alerting & Delivery:** A global alerts factory generates `alert_events`. Index & Digest delivery sends daily GERI + EERI + EGSI + AI Digest to all plan tiers via email and Telegram, with plan-tiered content depth. User delivery preferences are configurable.
- **User & Plan Management:** Handles user signup, verification, password/PIN setup, and assigns subscription tiers based on `plan_settings`.
- **API:** A FastAPI application serves as the primary interface.
- **SEO Growth System:** Generates SEO-optimized daily alert pages, dynamic sitemaps, and rich meta-data.
- **Billing & Subscription:** Integrates with Stripe for subscription management.
- **Plan-Tiered Dashboards:** Progressive intelligence depth across 5 subscription tiers for GERI, EERI, and EGSI dashboards, offering varying levels of data, history, analytics, and tactical intelligence modules (e.g., regime analysis, correlations, shock detectors).
- **Daily Geo-Energy Intelligence Digest:** AI-powered daily briefing on the user dashboard with plan-tiered features, generated using OpenAI gpt-4.1-mini.
- **ERIQ Expert Analyst:** An AI-powered interpretation intelligence bot accessible at `/users/account` using GPT-5.1 (with gpt-4.1-mini fallback) and RAG from a knowledge base. It includes a Product Analytics & Feedback Layer and a Context Assembly Layer (CAL) for plan-gated database snapshots and contextual information.
- **ERIQ Token Economy:** Manages plan-based monthly token allowances and purchased token balances, resetting on Stripe subscription payment events.

**System Design Choices:**
- **Database:** PostgreSQL is used for persistence.
- **Background Workers:** Ingestion, AI, Risk, and Alerts components are designed as separate, orchestratable workers.
- **Concurrency:** FastAPI with uvicorn for asynchronous API operations.
- **Alerting Production Safety:** Employs advisory locks, unique constraints, and robust retry/backoff mechanisms.
- **Digest System:** Consolidates multiple alert deliveries into periodic summary messages.
- **Production Hardening:** Includes preflight checks, health checks, user allowlisting, and circuit breakers.
- **Observability:** Tracks engine runs and provides internal API endpoints for monitoring.

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