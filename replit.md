# EnergyRiskIQ - Event Ingestion & Risk Intelligence Pipeline

## Overview
EnergyRiskIQ is an event ingestion, classification, AI analysis, and risk scoring pipeline designed for energy risk intelligence. Its primary purpose is to deliver a comprehensive risk intelligence platform with a global alerts factory, providing market advantage and daily AI-powered briefings. The project aims to establish a leading platform for energy market insights.

## User Preferences
The user prefers clear, concise communication. They value an iterative development approach, with a focus on delivering functional components incrementally. They prefer to be consulted before any major architectural changes or significant code refactoring. Detailed explanations of complex features are appreciated, especially regarding AI models and risk scoring logic.

## System Architecture

EnergyRiskIQ employs a modular architecture, separating concerns into distinct services for ingestion, AI processing, risk scoring, and alerting.

**UI/UX Decisions:**
- The system includes marketing landing pages, user authentication flows, and an admin portal.
- User-facing dashboards provide event queries, risk summaries, and alert history.
- Public-facing SEO-optimized pages for indices like GERI, EERI, and EGSI feature methodology and historical data, utilizing a digest-style dark theme and AI interpretations. The GERI public page canonical URL is `/indices/global-energy-risk-index` (old `/geri` redirects 301). The EERI public page canonical URL is `/indices/europe-energy-risk-index` (old `/eeri` redirects 301). Sub-routes like `/geri/history`, `/geri/methodology`, `/geri/{date}`, `/eeri/history`, `/eeri/methodology`, `/eeri/{date}` remain unchanged.

**Technical Implementations:**
- **Event Ingestion:** RSS feeds are fetched and categorized.
- **AI Processing:** Utilizes OpenAI for event enrichment, summarization, impact analysis, and detailed daily index interpretations.
- **Risk Scoring:** A dedicated engine computes quantitative risk scores for events, regions, and assets, including trend analysis for indices such as Global Energy Risk Index (GERI), Regional Escalation Risk Index (RERI/EERI), and Europe Gas Stress Index (EGSI-M, EGSI-S). GERI Live provides real-time intraday index values using an anchor-based continuity model.
- **Alerting & Delivery:** A global alerts factory generates `alert_events`, and a digest system delivers daily index summaries via email and Telegram, with plan-tiered content depth.
- **User & Plan Management:** Handles user lifecycle and assigns subscription tiers.
- **API:** A FastAPI application serves as the primary interface.
- **SEO Growth System:** Generates SEO-optimized daily alert pages and manages sitemap architecture.
- **Billing & Subscription:** Integrates with Stripe for subscription management.
- **Plan-Tiered Dashboards:** Provides progressive intelligence depth across five subscription tiers for GERI, EERI, and EGSI, ensuring feature cascading.
- **Daily Geo-Energy Intelligence Digest:** An AI-powered daily briefing on the user dashboard with plan-tiered features.
- **ERIQ Expert Analyst:** An AI-powered interpretation intelligence bot with context-awareness and RAG from a knowledge base, accessible on dashboards.
- **ERIQ Token Economy:** Manages plan-based monthly token allowances and purchased token balances.
- **ELSA Marketing Bot:** An AI-powered marketing and business intelligence advisor for the admin dashboard, providing strategic advice, accessing production database metrics, and offering image generation via DALL-E 3.
- **Ticketing System:** A support ticket module with user and admin interfaces, live unread notifications, and category filtering.
- **Blog:** A public educational blog with user registration, article submission (pending approval), commenting, and admin management. Features include a markdown editor with image uploads and a live preview.

**System Design Choices:**
- **Database:** PostgreSQL is used for persistence, with a single production database architecture.
- **Background Workers:** Ingestion, AI, Risk, and Alerts components are designed as separate, orchestratable workers.
- **Concurrency:** FastAPI with uvicorn for asynchronous API operations.
- **Alerting Production Safety:** Employs advisory locks, unique constraints, and robust retry/backoff mechanisms.
- **Production Hardening:** Includes preflight checks, health checks, user allowlisting, and circuit breakers.
- **Observability:** Tracks engine runs and provides internal API endpoints for monitoring.

## External Dependencies

- **Database:** PostgreSQL
- **AI:** OpenAI (gpt-4.1-mini, GPT-5.1)
- **Payment Processing:** Stripe
- **Email Service:** Brevo
- **Messaging Service:** Telegram Bot API
- **SMS Service:** Twilio
- **Gas Storage Data:** AGSI+ (GIE API)
- **Gas Price Data:** OilPriceAPI
- **Oil Price Data:** OilPriceAPI
- **VIX Data:** Yahoo Finance (yfinance), FRED
- **FX Data:** Oanda