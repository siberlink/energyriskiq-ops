# EnergyRiskIQ - Event Ingestion & Risk Intelligence Pipeline

## Overview
EnergyRiskIQ is an event ingestion, classification, AI analysis, and risk scoring pipeline for energy risk intelligence. It fetches news events from RSS feeds, classifies them, enriches them with AI, and computes quantitative risk scores. The project aims to provide a comprehensive risk intelligence platform with a global alerts factory for fanout delivery, offering a complete risk intelligence platform for market advantage.

## User Preferences
The user prefers clear, concise communication. They value an iterative development approach, with a focus on delivering functional components incrementally. They prefer to be consulted before any major architectural changes or significant code refactoring. Detailed explanations of complex features are appreciated, especially regarding AI models and risk scoring logic.

## System Architecture

EnergyRiskIQ is built with a modular architecture, separating concerns into distinct services for ingestion, AI processing, risk scoring, and alerting.

**UI/UX Decisions:**
- The project includes marketing landing pages, user authentication flows, and an admin portal.
- User-facing dashboards provide event queries, risk summaries, and alert history.
- Admin UI allows management of plan settings.

**Technical Implementations:**
- **Event Ingestion:** RSS feeds are fetched and categorized using keyword classification.
- **AI Processing:** Utilizes OpenAI (gpt-4.1-mini) for event enrichment, summarization, and impact analysis. Index interpretations (GERI, EERI, EGSI) use gpt-4.1 for detailed 2-3 paragraph daily analysis (250-400 words) with professional, humanizing tone.
- **Risk Scoring:** A dedicated engine computes quantitative risk scores for events, regions, and assets, including trend analysis.
- **Alerting:** A global alerts factory generates user-agnostic `alert_events` which are fanned out to eligible users via `user_alert_deliveries` supporting email, Telegram, and SMS with quotas and cooldowns.
- **Pro Plan Delivery System:** Tiered delivery for Pro Plan users with 15 emails/day limit (batch windows counted, not individual emails), unlimited Telegram alerts, risk-score prioritization, and 15-minute batching. Includes Telegram deep-link and manual Chat ID linking via @energyriskiq_bot. GERI emails count toward daily limit. GitHub Actions workflow: `alerts-engine-v2.yml` (10-min cron) automatically includes GERI delivery when a new index is available.
- **Trader Plan Delivery System:** Email delivery for Trader Plan users with 8 emails/day limit, 30-minute batching windows, and Telegram alerts. No GERI (Pro+ only). Triggered by the same `alerts-engine-v2.yml` workflow. One email per 30-min window enforced to prevent duplicates.
- **User & Plan Management:** Features user signup, verification, password/PIN setup, and assigns subscription tiers based on `plan_settings`.
- **API:** A FastAPI application serves as the primary interface for events, risk intelligence, alerts, marketing content, and internal operations.
- **SEO Growth System:** Generates SEO-optimized daily alert pages with a 24-hour delay for organic traffic acquisition, including dynamic sitemaps and rich meta-data.
- **Regional Daily Alerts:** Focused regional risk monitoring at `/alerts/region/{region}/{date}`. Stored in `seo_regional_daily_pages` table. Regions: `middle-east`, `europe`, `asia`, `africa`, `americas`. Backfill script: `python -m src.seo.regional_backfill --region middle-east --days 30`. Uses `REGION_SCOPE_MAPPINGS` to match database scope_region values to region slugs.
- **Contextual Linking System:** Smart internal linking that concentrates SEO authority upward. Utility module at `src/utils/contextual_linking.py`. Rules: Alert History pages link to Index pages (2-3 links via "Risk Context" block), Index History pages link to main Index + optionally Alert History ("Data Sources" section), Index pages link to Alert History (1-2 links via "source attribution"). Global rule: no duplicate index links per page. See ChatGPT design reference for SEO rationale.
- **Billing & Subscription:** Integrates with Stripe for subscription management, plan upgrades/dowgrades, and webhook handling for payment events.
- **GERI v1 (Global Energy Risk Index):** Encapsulated module that computes daily risk indices from alert data. Controlled by `ENABLE_GERI` feature flag. Reads from `alert_events` (INPUT) and writes to `intel_indices_daily` (OUTPUT). Formula: 0.40*high_impact + 0.25*regional_spike + 0.20*asset_risk + 0.15*region_concentration. Risk bands: LOW (0-25), MODERATE (26-50), ELEVATED (51-75), CRITICAL (76-100). Uses 90-day rolling baseline for normalization with fallback values when <14 days history.
- **RERI/EERI (Regional Escalation Risk Index / Europe Energy Risk Index):** Encapsulated module (`src/reri/`) for regional risk indices. Controlled by `ENABLE_EERI` feature flag. Reads from `alert_events` (INPUT) and writes to `reri_indices_daily` (OUTPUT). EERI v1 formula: 0.45*RERI_EU + 0.25*ThemePressure + 0.20*AssetTransmission + 0.10*Contagion. Canonical regions: `europe`, `middle-east`, `black-sea` stored in `reri_canonical_regions` table. Uses fallback caps for first 14 days, rolling normalization after 30+ days. See `docs/reri.md` for detailed architecture and `docs/reri-eeri-development-document.md` for complete development history.
- **EERI SEO Infrastructure:** Public EERI pages at `/eeri`, `/eeri/methodology`, `/eeri/history`, `/eeri/{date}`, `/eeri/{year}/{month}`. Shows 24h delayed data publicly with: level, band, trend, interpretation, top 3 drivers, affected assets, methodology hints. All EERI pages automatically included in sitemap.xml and sitemap.html. Service layer: `src/reri/eeri_history_service.py`, SEO routes: `src/reri/seo_routes.py`. See `docs/eeri-development.md` for complete implementation details.
- **EERI Pro Dashboard Module:** Encapsulated Pro-tier module in `/users/account` with full component transparency. Located at `src/reri/pro_routes.py` with dedicated API endpoints under `/api/v1/eeri-pro/`. Features include:
  - **Real-time EERI Display:** Live index value with band color, 7-day trend indicator
  - **Component Breakdown:** Visual stacked bar showing RERI_EU, Theme Pressure, Asset Transmission, Contagion contributions (normalized, never raw weights)
  - **Asset Stress Panel:** Grid of all energy asset classes (gas, oil, freight, fx, power, lng) with stress scores, status labels, and trend indicators
  - **Top Risk Drivers:** Full driver details with rank, headline, theme, severity, confidence, and affected assets
  - **Historical Intelligence:** Interactive Chart.js visualization with time range controls (7D/30D/90D/All) and smoothing options (Raw/3D MA/7D MA)
  - **Regime Statistics:** 90-day band distribution bars and recent regime transition history
  - **Daily Intelligence Summary:** AI-generated interpretation with key drivers and exposed assets
  - **API Endpoints:** `/realtime`, `/component-breakdown`, `/asset-stress`, `/top-drivers`, `/history`, `/regime-stats`, `/daily-summary`, `/comparison/{date1}/{date2}`
  - Pro/Enterprise plan gating with locked state for non-Pro users. See `docs/eeri-pro-plan-features.md` for feature documentation.
- **EGSI (Europe Gas Stress Index):** Encapsulated module (`src/egsi/`) for gas-specific stress indices. Controlled by `ENABLE_EGSI` feature flag. Two index families:
  - **EGSI-M (Market/Transmission):** Daily index measuring gas market stress signal. Formula: `100 * (0.35*RERI_EU/100 + 0.35*ThemePressure_norm + 0.20*AssetTransmission_norm + 0.10*ChokepointFactor_norm)`. Reads from `alert_events` + RERI_EU, writes to `egsi_m_daily`. Runs automatically alongside GERI/EERI in the alerts engine workflow.
  - **EGSI-S (System):** Daily index for storage/refill/winter stress. Formula: `100 * (0.25*SupplyPressure + 0.20*TransitStress + 0.20*StorageStress + 0.20*PriceVolatility + 0.15*PolicyRisk)`. Uses composite data source: real AGSI+ EU storage data (GIE_API_KEY) + live OilPriceAPI TTF prices (OIL_PRICE_API_KEY). Writes to `egsi_s_daily`. Runs automatically in alerts-engine-v2.yml every 10 minutes.
  - **Chokepoints v1:** Versioned config of high-signal Europe gas infrastructure entities (Ukraine transit, TurkStream, Norway pipelines, major LNG terminals) used for ChokepointFactor calculation.
  - **EGSI-M API Endpoints:** `/api/v1/indices/egsi-m/public` (24h delayed), `/api/v1/indices/egsi-m/latest` (realtime), `/api/v1/indices/egsi-m/status`, `/api/v1/indices/egsi-m/history`.
  - **EGSI-S API Endpoints:** `/api/v1/indices/egsi-s/status`, `/api/v1/indices/egsi-s/latest`, `/api/v1/indices/egsi-s/history`, `/api/v1/indices/egsi-s/compute`.
  - **EGSI SEO Pages:** `/egsi`, `/egsi/methodology`, `/egsi/history`, `/egsi/{date}`, `/egsi/{year}/{month}`. All included in sitemap.xml.
  - **Risk Bands:** LOW (0-20), NORMAL (21-40), ELEVATED (41-60), HIGH (61-80), CRITICAL (81-100).
  - See `docs/EGSI.md` for specification and `docs/egsi-development.md` for development history.

**System Design Choices:**
- **Database:** PostgreSQL is used for persistence, with a structured schema for all core data.
- **Background Workers:** Ingestion, AI, Risk, and Alerts components are designed as separate, orchestratable workers.
- **Concurrency:** FastAPI with uvicorn for asynchronous API operations.
- **Alerting Production Safety:** Employs advisory locks, unique constraints for idempotency, `FOR UPDATE SKIP LOCKED` for race condition prevention, and robust retry/backoff mechanisms.
- **Digest System:** Consolidates multiple alert deliveries into periodic summary messages (daily/hourly) for efficient user communication.
- **Production Hardening:** Includes preflight checks, health checks, user allowlisting for controlled rollouts, and circuit breakers (`ALERTS_MAX_SEND_PER_RUN`) to prevent runaway processes.
- **Observability:** Tracks engine runs and provides internal API endpoints for monitoring health metrics and re-queueing failed items.

## External Dependencies

- **Database:** PostgreSQL (Replit-provided)
- **AI:** OpenAI via Replit AI Integrations (gpt-4.1-mini)
- **Payment Processing:** Stripe via Replit Connector
- **Email Service:** Brevo (max 1000 emails/batch, recommend 700-800 for safety)
- **Messaging Service:** Telegram Bot API
- **SMS Service:** Twilio (optional)
- **Gas Storage Data:** AGSI+ (GIE API) for EU gas storage levels
- **Gas Price Data:** OilPriceAPI for live TTF natural gas prices
- **Python Libraries:** FastAPI, uvicorn, feedparser, psycopg2-binary, openai, stripe, requests, python-dotenv.