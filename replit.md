# EnergyRiskIQ - Event Ingestion & Risk Intelligence Pipeline

## Overview
EnergyRiskIQ is an event ingestion, classification, AI analysis, and risk scoring pipeline for energy risk intelligence. Its primary purpose is to provide a comprehensive risk intelligence platform with a global alerts factory, delivering market advantage and daily AI-powered briefings. The project aims to establish a leading platform for energy market insights.

## User Preferences
The user prefers clear, concise communication. They value an iterative development approach, with a focus on delivering functional components incrementally. They prefer to be consulted before any major architectural changes or significant code refactoring. Detailed explanations of complex features are appreciated, especially regarding AI models and risk scoring logic.

## System Architecture

EnergyRiskIQ employs a modular architecture, separating concerns into distinct services for ingestion, AI processing, risk scoring, and alerting.

**UI/UX Decisions:**
- The system includes marketing landing pages, user authentication flows, and an admin portal.
- User-facing dashboards provide event queries, risk summaries, and alert history.
- The landing page (`/`) and public index pages (GERI, EERI, EGSI) are fully dark-themed with specific color palettes.
- Public-facing SEO-optimized pages for indices feature methodology, historical data, and AI interpretations.
- A standardized loading functionality is implemented across all async data panels, featuring concentric spinning rings, cycling status messages, data source tags, and an animated progress bar.

**Technical Implementations:**
- **Event Ingestion:** Fetches and categorizes RSS feeds.
- **AI Processing:** Uses OpenAI for event enrichment, summarization, impact analysis, and daily index interpretations.
- **Risk Scoring:** Computes quantitative risk scores for events, regions, and assets, including trend analysis for indices like GERI, RERI/EERI, and EGSI-M/EGSI-S. GERI Live provides real-time intraday index values.
- **Alerting & Delivery:** Generates `alert_events` and delivers daily index summaries via email and Telegram, with plan-tiered content.
- **User & Plan Management:** Handles user lifecycle and subscription tiers.
- **API:** A FastAPI application serves as the primary interface.
- **SEO Growth System:** Generates SEO-optimized daily alert pages and manages sitemap.
- **Billing & Subscription:** Integrates with Stripe.
- **Plan-Tiered Dashboards:** Provides progressive intelligence depth across five subscription tiers.
- **Daily Geo-Energy Intelligence Digest:** An AI-powered daily briefing on the user dashboard.
- **ERIQ Expert Analyst:** An AI-powered interpretation intelligence bot with context-awareness and RAG.
- **ERIQ Token Economy:** Manages plan-based monthly token allowances.
- **ELSA Marketing Bot:** An AI-powered marketing and business intelligence advisor for the admin dashboard.
- **Ticketing System:** A support ticket module with user and admin interfaces.
- **Blog:** A public educational blog with user registration and article submission.
- **Global Energy Risk Forecast Page:** A SEO-optimised public page (`/data/global-energy-risk-forecast`) streaming AI-powered 24-hour Brent & TTF price forecasts using GPT-5.1.
- **JKM LNG Spot Price Page:** A SEO-optimised public page (`/data/jkm-lng-spot-price`) displaying JKM LNG spot prices with charts and historical data.
- **TTF Gas Price Today Page:** A SEO-optimised public page (`/data/ttf-gas-price-today`) displaying Dutch TTF European natural gas benchmark prices with real-time updates, charts, and market insights.

**System Design Choices:**
- **Database:** PostgreSQL is used for persistence with a single production database.
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