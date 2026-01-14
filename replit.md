# EnergyRiskIQ - Event Ingestion & Risk Intelligence Pipeline

## Overview
EnergyRiskIQ is an event ingestion, classification, AI analysis, and risk scoring pipeline for energy risk intelligence. It fetches news events from RSS feeds, classifies them, enriches them with AI, and computes quantitative risk scores. The project aims to provide a comprehensive risk intelligence platform with a global alerts factory for fanout delivery.

## User Preferences
The user prefers clear, concise communication. They value an iterative development approach, with a focus on delivering functional components incrementally. They prefer to be consulted before any major architectural changes or significant code refactoring. Detailed explanations of complex features are appreciated, especially regarding AI models and risk scoring logic.

## System Architecture

EnergyRiskIQ is built with a modular architecture, separating concerns into distinct services for ingestion, AI processing, risk scoring, and alerting.

**UI/UX Decisions:**
- The project includes marketing landing pages, user authentication flows, and an admin portal.
- User-facing dashboards provide event queries, risk summaries, and alert history.
- Admin UI allows management of plan settings.

**Technical Implementations:**
- **Event Ingestion:** RSS feeds are fetched, categorized using keyword classification with hint tie-breaking.
- **AI Processing:** Uses OpenAI (gpt-4.1-mini) for event enrichment, generating summaries, and impact analysis.
- **Risk Scoring:** A dedicated engine computes quantitative risk scores for events, regions, and assets, and derives trends.
- **Alerting (v2):** A global alerts factory generates `alert_events` (user-agnostic) which are then fanned out to eligible users via `user_alert_deliveries`. This supports email, Telegram, and SMS channels with per-user quotas and cooldowns.
- **User Management:** Includes user signup, email verification, password/PIN setup, and plan assignment.
- **Plan Management:** `plan_settings` is the authoritative source for subscription tier features, which are synced with `user_plans`.
- **API:** A FastAPI application provides endpoints for events, risk intelligence, alerts, marketing content, and internal operations.

**Feature Specifications:**
- **Core Pipeline:** RSS Ingestion -> Classification -> AI Enrichment -> Risk Scoring.
- **Alert Types:** Supports `HIGH_IMPACT_EVENT`, `REGIONAL_RISK_SPIKE`, `ASSET_RISK_SPIKE`, and `DAILY_DIGEST`.
- **Delivery Channels:** Email (Resend/Brevo), Telegram Bot API.
- **User Plans:** Configurable subscription tiers (Free, Personal, Trader, Pro, Enterprise) with varying features, alert quotas, and delivery options.
- **Admin Interface:** Secure portal for managing plan settings and monitoring.

**System Design Choices:**
- **Database:** PostgreSQL is used for persistence, with a structured schema designed for events, ingestion runs, risk data, user management, and the new global alerts system.
- **Background Workers:** Ingestion, AI, Risk, and Alerts components are designed as separate workers that can be run independently or orchestrated.
- **Concurrency:** FastAPI with uvicorn for the API server, enabling asynchronous operations.
- **Production Safety (Alerts v2):** Advisory locks prevent concurrent phase execution, `event_fingerprint` unique constraint prevents duplicate alerts, `fanout_completed_at` ensures idempotent fanout, and `FOR UPDATE SKIP LOCKED` prevents delivery races.
- **Retry & Backoff (Alerts v2):** Exponential backoff with jitter for transient failures, max attempts enforcement, failure classification (transient vs permanent), and channel config validation (skips gracefully when secrets missing).

## Environment Variables (Alerts v2)

| Variable | Default | Description |
|----------|---------|-------------|
| `ALERTS_MAX_ATTEMPTS` | 5 | Max delivery attempts before permanent failure |
| `ALERTS_RETRY_BASE_SECONDS` | 60 | Base delay for exponential backoff |
| `ALERTS_RETRY_MAX_SECONDS` | 3600 | Maximum retry delay cap |
| `ALERTS_RATE_LIMIT_EMAIL_PER_MINUTE` | 0 | Optional per-channel throttle (0=unlimited) |
| `ALERTS_RATE_LIMIT_TELEGRAM_PER_MINUTE` | 0 | Optional per-channel throttle (0=unlimited) |
| `ALERTS_RATE_LIMIT_SMS_PER_MINUTE` | 0 | Optional per-channel throttle (0=unlimited) |

## External Dependencies

- **Database:** PostgreSQL (Replit-provided)
- **AI:** OpenAI via Replit AI Integrations (gpt-4.1-mini)
- **Email Service:** Resend or Brevo
- **Messaging Service:** Telegram Bot API
- **SMS Service:** Twilio (optional, for SMS delivery)
- **Python Libraries:**
    - `FastAPI`: Web framework
    - `uvicorn`: ASGI server
    - `feedparser`: RSS feed parsing
    - `psycopg2-binary`: PostgreSQL adapter
    - `openai`: OpenAI API client
    - `requests`: HTTP client
    - `python-dotenv`: Environment variable management