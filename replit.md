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
- **Daily Geo-Energy Intelligence Digest:** An AI-powered daily briefing on the user dashboard. The account-page view ("Daily Intelligence Report" in the left nav) is gated behind a standalone €2.99/month EUR Stripe subscription (mirrors the WTI Pro Widget / Indices History technique: `src/api/daily_report_routes.py`, table `user_daily_report_subs`, metadata.type `daily_report`). Non-subscribers see a persuasive paywall; the full digest API `/api/v1/digest/daily` is enforced server-side (402 without an active sub).
- **ERIQ Expert Analyst:** An AI-powered interpretation intelligence bot with context-awareness and RAG.
- **ERIQ Token Economy:** Manages plan-based monthly token allowances.
- **ELSA Marketing Bot:** An AI-powered marketing and business intelligence advisor for the admin dashboard.
- **Ticketing System:** A support ticket module with user and admin interfaces.
- **Blog:** A public educational blog with user registration and article submission.
- **Global Energy Risk Forecast Page:** A SEO-optimised public page (`/data/global-energy-risk-forecast`) streaming AI-powered 24-hour Brent & TTF price forecasts using GPT-5.1.
- **JKM LNG Spot Price Page:** A SEO-optimised public page (`/data/jkm-lng-spot-price`) displaying JKM LNG spot prices with charts and historical data.
- **TTF Gas Price Today Page:** A SEO-optimised public page (`/data/ttf-gas-price-today`) displaying Dutch TTF European natural gas benchmark prices with real-time updates, charts, and market insights.
- **Data License Page:** A public page (`/data-license`) setting usage terms for all EnergyRiskIQ public dataset pages. Contains a WebPage schema, attribution guidance, permitted/prohibited uses, and links to all covered data pages. Added to sitemap.
- **GSC Dataset Schema Fix:** All public data pages now include `license`, `isAccessibleForFree`, and `publisher` fields in their Dataset structured data schemas, referencing `https://energyriskiq.com/data-license`. Affected pages: JKM, LNG, gas storage, TTF, GERI index, GERI research, EERI index, EGSI, global-energy-risk-timeline, and global-energy-risk-forecast.
- **What Drives LNG Prices Research Page:** New SEO authority research page (`/research/what-drives-lng-prices`) with featured-snippet quick-answer block, LNG market explainer with flow visual (Producer→Tanker→Terminal), 7-driver section (weather, supply, shipping, geopolitics, oil linkage, Europe vs Asia, gas storage) each with live data pills, live market context cards (JKM/TTF/Brent/Storage/VIX), JKM-TTF arbitrage signal strip, GERI/EERI/EGSI-M/EGSI-S risk index cards with interpretation, 6-event historical timeline (2021 demand surge, 2021-22 energy crisis, Russia-Ukraine war, Freeport outage, Red Sea crisis, EU storage depletion), daily insight (3 sections, Custom Algorithms), newsletter capture strip, conversion CTA, 7-question FAQ accordion, internal link hub (LNG/Gas/Oil/Indices/Research/License), citation block, sticky insight bar (LNG Market Risk Level/GERI). Anti-copy JS. Schemas: Article, Dataset, BreadcrumbList, FAQPage. Added to sitemap-research.xml.
- **JKM LNG Price Chart Page:** New SEO-optimised public page (`/data/jkm-lng-price-chart`) with live JKM price hero card, sentiment badge, sticky price bar, 6 chart time ranges (7D/30D/90D/YTD/1Y/Since Launch), overlay toggle buttons (TTF/Brent/Storage/VIX), today's market snapshot prose (3 sections), global LNG context (3 sections), cross-asset navigation cards, 5-driver authority block (Asian demand/European competition/shipping/weather/oil-indexed), energy risk intelligence panel (GERI/EERI/EGSI-M), JKM-TTF spread analysis (3 sections), historical key levels (30D/YTD), today's LNG market insight (3 sections, Custom Algorithms), conversion CTA, 6-question FAQ accordion, internal link footer, citation block. Anti-copy JS protection. Schemas: WebPage, Dataset (with variableMeasured/license/measurementTechnique), BreadcrumbList, FinancialProduct, FAQPage. Added to sitemap-data.xml.
- **WTI Crude Oil Widget Landing & Embed:** New SEO + distribution + SaaS-funnel page at `/widgets/wti-crude-oil-price` promoting an embeddable WTI widget. 12-section blueprint: hero with dual CTA + 5-item trust micro-bar, live free-widget preview (iframe-rendered), iframe embed code block with one-click copy button, 4-card "why use this widget" grid, free-vs-pro comparison table (10 features, €1.49/mo Pro tier), live Pro unbranded preview, SEO content block (What is WTI / Why oil prices matter / What moves WTI / related-pages cluster), 6-use-case grid, backlink-engine attribution section linking to `/data/wti-crude-oil-price-today`, 6-question FAQ accordion, Citation & Reference card, final conversion block, data-license footer. Anti-copy JS (copy-event watermark + contextmenu block on `.wti-w-protected`). Schemas: WebPage, SoftwareApplication (with Free + Pro offers in EUR), BreadcrumbList, FAQPage. Two iframe endpoints: `/embed/wti-crude-oil-widget` (free, branded) and `/embed/wti-crude-oil-widget-pro` (unbranded preview) — both return `X-Frame-Options: ALLOWALL` and `CSP frame-ancestors *;` for embedding on any external site, `Cache-Control: public, max-age=120`. Widget shows live WTI price (intraday_wti with daily fallback), day-over-day change from oil_price_snapshots, intraday sparkline SVG, live GERI risk pill (geri_live), Brent-WTI spread (brent_wti_spread column or computed from intraday_brent). Added to sitemap-data.xml.
- **WTI Crude Oil Price Today Page:** New SEO-optimised public page (`/data/wti-crude-oil-price-today`) targeting the US WTI (West Texas Intermediate) crude oil benchmark. Sticky price bar, live hero card with intraday status tag (from `intraday_wti`), today's intraday SVG chart, main multi-range chart (1M/3M/YTD/1Y/MAX) with 5 toggleable overlays (Brent/VIX/GERI/TTF/NatGas) date-aligned to the WTI x-axis, 6-cell market snapshot with risk-regime label, why-it-matters explainer, 6 driver cards (OPEC+/Geopolitical/US Inventory/China Demand/Financial/NatGas-LNG), 4-card risk panel (GERI/EERI/EGSI-M/EGSI-S), dedicated Brent-vs-WTI spread card (3-column grid), deterministic Custom Algorithm commentary with directional bias badge, 30-day historical table with CSV download (`/api/wti-prices.csv`), 12-card internal-link hub, conversion block, 6-question FAQ accordion, citation card, data-license footer. Anti-copy JS (copy-event watermark + contextmenu block on `.wti-protected`). Schemas: WebPage, Dataset (with variableMeasured/license/measurementTechnique), FinancialProduct, BreadcrumbList, FAQPage. WTI color theme: cyan #22d3ee. Added to sitemap-data.xml.
- **Natural Gas Price Today Europe Page:** New SEO-optimised public page (`/data/natural-gas-price-today-europe`) targeting the European TTF natural gas benchmark. Live hero price card with sentiment badge, sticky price bar, multi-range SVG chart (7D/30D/90D/YTD/MAX) with toggleable overlays (Brent/VIX/EU Storage) date-aligned to the TTF x-axis, 6-cell market snapshot, why-it-matters explainer, 6 price-driver cards, 4-card risk-signals panel (EERI/EGSI-M/EGSI-S/GERI), deterministic Custom Algorithm commentary with directional bias badge (bullish/bearish/neutral), 30-day historical data table with CSV download (`/api/natgas-ttf-prices.csv`), 12-card internal-link hub, conversion block, 6-question FAQ accordion, citation block and data-license footer. Anti-copy JS (copy-event watermark + contextmenu block on `.ng-protected`). Schemas: WebPage, Dataset (with variableMeasured/license/measurementTechnique), FinancialProduct, BreadcrumbList, FAQPage. Added to sitemap-data.xml.
- **Brent Crude Oil Price Page:** New SEO-optimised public page (`/data/brent-crude-oil-price-today`) with live Brent price card, sentiment badge, sticky price bar, 1D/7D/30D/90D interactive SVG charts, daily market snapshot prose, context hub internal links, 5-driver authority block, GERI/EERI/EGSI risk intelligence panel, cross-market analysis (Brent vs Gas/LNG), historical key levels (30D/YTD), daily AI-powered market insight (3 sections), conversion CTA, 6-question FAQ accordion, internal link footer, citation block. Schemas: WebPage, Dataset (with variableMeasured/license/measurementTechnique), BreadcrumbList, FinancialProduct, FAQPage. Added to sitemap-data.xml.
- **Gas Storage SEO Optimisation:** `/gas-storage-levels-in-europe` fully optimised for target keyword "europe gas storage levels": new title/meta/OG/Twitter metadata, updated H1 ("Europe Gas Storage Levels Today"), hero refresh badges, Today's Snapshot 8-item card (daily change, gap to target, days to Nov 1, required injection rate, risk score, last updated), "What Europe's Gas Storage Level Means Today" section with 4 key-point grid, trend chart H2 updated, mid-page and bottom CTA blocks, new "Related EnergyRiskIQ Data and Risk Indices" 7-card grid, 6-question FAQ section with accordion, FAQPage JSON-LD schema, updated Dataset schema with variableMeasured/measurementTechnique/dateModified, BreadcrumbList (Home→Data→Europe Gas Storage Levels), and WebPage schema.

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