# EnergyRiskIQ - Event Ingestion & Risk Intelligence Pipeline

## ⚠️ CRITICAL RULES — READ BEFORE EVERY TASK

1. **ALWAYS USE THE PRODUCTION DATABASE.** All data queries must use `execute_production_query()` or `get_production_cursor()` from `src.db.db`. Never use `execute_query()` or `get_cursor()` for reading index/market data. `PRODUCTION_DATABASE_URL` is now set as a shared env var pointing to the Neon PostgreSQL production database. This takes priority over `DATABASE_URL` (the local Helium dev DB). The pattern is established in `src/geri/repo.py` — follow it.

2. **VERIFY DATA FROM PRODUCTION FIRST.** Before building any feature that displays data, query the production DB using `executeSql({ environment: "production", sqlQuery: "..." })` in the code execution sandbox to confirm what data exists and in which tables.

3. **24H DELAY RULE FOR PUBLIC INDEX CARDS.** When displaying a "24h delayed" value for any index on a public page, always fetch the **second-to-last** (OFFSET 1) row from the table — NOT the most recent row, and NOT filtered by `date <= yesterday`. The most recent row is today's freshly computed value (not yet public). The second-most-recent row is the 24h-delayed public value.
   - **EERI** → `SELECT ... FROM reri_indices_daily WHERE index_id='europe:eeri' ORDER BY date DESC OFFSET 1 LIMIT 1`
   - **EGSI-M** → `SELECT ... FROM egsi_m_daily WHERE region='Europe' ORDER BY index_date DESC OFFSET 1 LIMIT 1`
   - **GERI** → `SELECT ... FROM intel_indices_daily WHERE index_id='global:geo_energy_risk' ORDER BY date DESC OFFSET 1 LIMIT 1`
   - Example: today=2026-03-12 → latest row has index_date=2026-03-11 (skip, not yet public) → second row has index_date=2026-03-10 (show as 24h delayed).

---

## Overview
EnergyRiskIQ is an event ingestion, classification, AI analysis, and risk scoring pipeline designed for energy risk intelligence. Its primary purpose is to deliver a comprehensive risk intelligence platform with a global alerts factory, providing market advantage and daily AI-powered briefings. The project aims to establish a leading platform for energy market insights.

## User Preferences
The user prefers clear, concise communication. They value an iterative development approach, with a focus on delivering functional components incrementally. They prefer to be consulted before any major architectural changes or significant code refactoring. Detailed explanations of complex features are appreciated, especially regarding AI models and risk scoring logic.

## System Architecture

EnergyRiskIQ employs a modular architecture, separating concerns into distinct services for ingestion, AI processing, risk scoring, and alerting.

**UI/UX Decisions:**
- The system includes marketing landing pages, user authentication flows, and an admin portal.
- User-facing dashboards provide event queries, risk summaries, and alert history.
- Public-facing SEO-optimized pages for indices like GERI, EERI, and EGSI feature methodology and historical data, utilizing a digest-style dark theme and AI interpretations. The GERI public page canonical URL is `/indices/global-energy-risk-index` (old `/geri` redirects 301). The EERI public page canonical URL is `/indices/europe-energy-risk-index` (old `/eeri` redirects 301). The EGSI public page canonical URL is `/indices/europe-gas-stress-index` (old `/egsi` redirects 301). Sub-routes like `/geri/history`, `/geri/methodology`, `/geri/{date}`, `/eeri/history`, `/eeri/methodology`, `/eeri/{date}`, `/egsi/history`, `/egsi/methodology`, `/egsi/{date}` remain unchanged.

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

## Standard Loading Functionality

All async data panels on the platform use a unified **Standard Loading Functionality** pattern. When adding a new data panel that loads via `fetch()`, always implement this pattern — do not use spinners, plain "Loading..." text, or skeleton shimmers.

### Visual Components
1. **Concentric spinning rings** — three arcs at different radii, counter-rotating at different speeds, with a pulsing gold centre dot.
2. **Cycling status messages** — a `<div id="pl-status">` element whose text cycles through contextually relevant messages every 2 seconds with a fade transition.
3. **Data source tags** — small pill badges naming the data sources being loaded (e.g. GERI, EERI, Brent, TTF).
4. **Animated progress bar** — a thin 2px bar that animates from 2% → 94% over ~4 s using a CSS `@keyframes` `pl-bar-progress` rule (intentionally never reaches 100% — resolves when data arrives).

### Colour Tokens
| Element | Value |
|---|---|
| Arc 1 (outer) | `#d4a017` (gold) top + right |
| Arc 2 (mid)   | `#3b82f6` (blue) bottom + left |
| Arc 3 (inner) | `rgba(251,191,36,0.6)` top |
| Centre dot    | `#d4a017` with glow `rgba(212,160,23,0.8)` |
| Progress bar  | `linear-gradient(90deg, #d4a017, #fbbf24)` |

### CSS Classes (defined in `src/static/index.html` `<style>` block)
- `.snap-panel-loader` — flex column, centred, `padding: 32px 20px 28px`, `gap: 14px`
- `.pl-ring-wrap` — `52×52px` relative container
- `.pl-ring-bg`, `.pl-arc1`, `.pl-arc2`, `.pl-arc3`, `.pl-dot` — ring parts
- `.pl-label-main` — "Loading latest data" text, `0.78rem`, `#e2e8f0`
- `.pl-label-sub` — cycling status text, `0.7rem`, `#475569`, `transition: opacity 0.3s`
- `.pl-tags` / `.pl-tag` — data-source pills; first tag gets gold, second gets blue
- `.pl-bar-wrap` / `.pl-bar-fill` — progress bar container + fill
- `.snap-panel-loader.pl-hidden` — `display: none` (applied by JS on load complete)
- `.snap-panel-content` — `opacity: 0`, `transition: opacity 0.35s ease` (content hidden during load)
- `.snap-panel-content.pl-loaded` — `opacity: 1` (applied by JS on load complete)

### Animation Keyframes
- `@keyframes pl-spin-cw` / `@keyframes pl-spin-ccw` — full rotation for arcs
- `@keyframes pl-pulse-dot` — scale 1→0.4→1 for centre dot
- `@keyframes pl-tag-pop` — `opacity 0 + translateY(4px)` → normal, staggered per tag
- `@keyframes pl-bar-progress` — width 2%→45%→72%→88%→94% over 4 s

### HTML Structure
```html
<div class="snap-panel">
  <div class="snap-panel-header">...</div>

  <!-- Loader: visible by default -->
  <div class="snap-panel-loader" id="MY-loader">
    <div class="pl-ring-wrap">
      <div class="pl-ring-bg"></div>
      <div class="pl-arc1"></div>
      <div class="pl-arc2"></div>
      <div class="pl-arc3"></div>
      <div class="pl-dot"></div>
    </div>
    <div class="pl-label-main">Loading latest data</div>
    <div class="pl-label-sub" id="MY-status">Connecting to production pipeline&hellip;</div>
    <div class="pl-tags">
      <span class="pl-tag">SOURCE A</span>
      <span class="pl-tag">SOURCE B</span>
    </div>
    <div class="pl-bar-wrap"><div class="pl-bar-fill"></div></div>
  </div>

  <!-- Content: hidden until loaded -->
  <div class="snap-panel-content" id="MY-content">
    <!-- ...data rows... -->
  </div>
</div>
```

### JavaScript Pattern
```javascript
(function(){
  var msgs = [
    'Connecting to production pipeline\u2026',
    'Fetching [source A]\u2026',
    'Loading [source B]\u2026',
    'Analysing risk environment\u2026'
  ];
  var idx = 0, el = document.getElementById('MY-status');
  var timer = setInterval(function(){
    idx = (idx + 1) % msgs.length;
    if(el){ el.style.opacity='0'; setTimeout(function(){ el.textContent=msgs[idx]; el.style.opacity='1'; },200); }
  }, 2000);

  fetch('/api/MY-endpoint')
    .then(function(r){ return r.json(); })
    .then(function(d){
      clearInterval(timer);
      // ...populate DOM values...
      document.getElementById('MY-loader').classList.add('pl-hidden');
      document.getElementById('MY-content').classList.add('pl-loaded');
    })
    .catch(function(){
      clearInterval(timer);
      document.getElementById('MY-loader').classList.add('pl-hidden');
      document.getElementById('MY-content').classList.add('pl-loaded');
    });
})();
```

### Currently Implemented
| Location | Loader ID | Content ID | API Endpoint |
|---|---|---|---|
| `/` hero panel (`src/static/index.html`) | `snap-panel-loader` | `snap-panel-content` | `/api/hero-snapshot` |

### Full-Screen Variant
The `/data/energy-risk-snapshot` page uses a **full-screen** variant of the same pattern: the loader is `position:fixed; inset:0; background:#0f172a; z-index:9999` and is streamed as the first HTML chunk before AI generation completes. The ring sizes are larger (84px), the bar animation runs for 12 s, and the pattern includes a logo and footer. This full-screen variant lives in `_LOADER_HTML` inside `src/api/snapshot_routes.py`. For in-panel loading, always use the compact panel variant described above.

---

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