# Anti-Scraping Utility — EnergyRiskIQ

## Overview

`src/utils/anti_scraping.py` is a server-side bot-filtering module applied to EnergyRiskIQ's highest-value public data pages. It blocks automated data scrapers and harvesters while keeping all search engines, AI crawlers, and social preview bots fully unrestricted.

---

## Design Principles

| Principle | Detail |
|---|---|
| **SEO-safe** | All Google, Bing, Yandex, Baidu and other search crawlers bypass all checks |
| **AI-indexing friendly** | GPTBot, ClaudeBot, PerplexityBot and other AI services are explicitly allowed |
| **Social-safe** | Facebook, Twitter/X, LinkedIn, Slack, WhatsApp and Discord preview bots pass freely |
| **No cookies / no JS** | Pure server-side; no client-side challenge scripts required |
| **Stateless** | In-memory rate limit store; no database calls on the hot path |
| **Non-fatal** | Raises `HTTPException`; normal FastAPI error handling sends the 403/429 response |

---

## Detection Layers

The gate runs five checks in strict order. The first matching rule wins.

```
Request in
    │
    ▼
┌─────────────────────────────────┐
│ 1. Good-bot UA allowlist?       │──YES──► ALLOW immediately (bypass all)
└─────────────────────────────────┘
    │ NO
    ▼
┌─────────────────────────────────┐
│ 2. UA empty or < 10 chars?      │──YES──► 403 Forbidden
└─────────────────────────────────┘
    │ NO
    ▼
┌─────────────────────────────────┐
│ 3. UA matches bad-bot list?     │──YES──► 403 Forbidden
└─────────────────────────────────┘
    │ NO
    ▼
┌─────────────────────────────────┐
│ 4. Header fingerprint score ≥ 6?│──YES──► 403 Forbidden
└─────────────────────────────────┘
    │ NO
    ▼
┌─────────────────────────────────┐
│ 5. Rate limit exceeded?         │──YES──► 429 Too Many Requests
└─────────────────────────────────┘
    │ NO
    ▼
ALLOW — request continues normally
```

---

### Layer 1 — Good-Bot Allowlist

Any request whose `User-Agent` contains a known-good substring is **immediately passed** with no further checks and no rate limiting.

#### Search Engines (always allowed)

| Engine | UA substring(s) |
|---|---|
| Google | `googlebot`, `adsbot-google`, `apis-google`, `google-inspectiontool`, `googlebot-image`, `googlebot-news`, `googlebot-video`, `mediapartners-google`, `google-safety`, `storebot-google`, `google-read-aloud` |
| Bing / Microsoft | `bingbot`, `msnbot`, `adidxbot`, `bingpreview`, `microsoft url preview` |
| Yahoo | `slurp` |
| DuckDuckGo | `duckduckbot`, `duckduckgo-favicons-bot` |
| Baidu | `baiduspider`, `baiduspider-plus`, `baiduspider-image` |
| Yandex | `yandexbot`, `yandexmobilebot`, `yandeximageresizer`, `yandexdirect`, `yandexmetrika`, `yandexwebmaster`, `yandexfeedparser` |
| Sogou | `sogou page spider`, `sogoubot` |
| Apple | `applebot` |
| Exalead | `exabot` |
| Mojeek | `mojeekbot` |
| Qwant | `qwantify` |
| Huawei | `petalbot` |
| Internet Archive | `ia_archiver`, `archive.org_bot`, `wayback` |

#### AI & LLM Indexing Services (always allowed — site policy)

| Service | UA substring(s) |
|---|---|
| OpenAI | `gptbot`, `chatgpt-user`, `oai-searchbot` |
| Anthropic | `claudebot`, `claude-web`, `anthropic-ai` |
| Perplexity | `perplexitybot` |
| Amazon | `amazonbot` |
| Meta | `meta-externalagent`, `meta-externalfetcher` |
| Cohere | `cohere-ai` |
| Diffbot | `diffbot` |
| You.com | `youbot` |
| Neeva | `neevabot` |
| Timpi | `timpibot` |
| ByteDance AI | `bytedance-inspectiontool` |

#### Social Preview Bots (always allowed)

`facebookexternalhit`, `facebot`, `twitterbot`, `linkedinbot`, `pinterestbot`, `slackbot`, `whatsapp`, `telegrambot`, `discordbot`, `skypeuripreview`, `vkshare`, `redditbot`, `tumblr`, `embedly`, `quora link preview`

#### Uptime & Monitoring (always allowed)

`uptimerobot`, `pingdom`, `statuscake`, `site24x7`, `freshping`, `newrelic synthetics`, `datadoghq`, `hetrixtools`

#### Feed Readers (always allowed)

`feedly`, `feedfetcher`

---

### Layer 2 — Empty / Missing User-Agent

Requests with no `User-Agent` header, or one shorter than 10 characters, are blocked with **403 Forbidden**. Legitimate clients — browsers, apps, and well-behaved bots — always send a meaningful UA string.

---

### Layer 3 — Bad-Bot UA Blocklist

The UA string is matched (case-insensitive substring) against a blocklist of known data-harvesting tools. Any match → **403 Forbidden**.

#### Python HTTP Libraries
`python-requests`, `python-urllib`, `python-httpx`, `aiohttp/`, `httplib2`, `urllib/`

#### Scraping Frameworks
`scrapy`, `mechanize`

#### Headless / Automation Browsers
`headlesschrome`, `phantomjs`, `nightmare`, `zombie.js`, `selenium`, `webdriver`

#### CLI Download Tools
`wget/`, `libwww-perl`, `curl/`, `httrack`

#### Commercial Data Harvesters
`semrushbot`, `semrush`, `mj12bot`, `majestic`, `dotbot`, `dotnetdotcom`, `bytespider`, `blexbot`, `turnitinbot`, `ltx71`, `masscan`, `zgrab`, `nmap`

#### Generic Scraper Labels
`scraper`, `dataminer`, `harvester`, `extractor`

#### Raw HTTP Clients (non-browser)
`go-http-client`, `okhttp/`, `apache-httpclient`, `axios/`, `node-fetch`, `node-superagent`, `got/`, `java/`, `java-`

---

### Layer 4 — Header Fingerprint Scoring

Real browsers always include a predictable set of HTTP headers. Programmatic clients frequently omit them. Each missing or suspicious signal adds to a score; if the score reaches **≥ 6**, the request is blocked with **403 Forbidden**.

| Signal | Score | Reason |
|---|---|---|
| Missing `Accept` header | +4 | All browsers always send Accept |
| Missing `Accept-Language` | +3 | All browsers send Accept-Language |
| `Accept` is exactly `*/*` (no quality values) | +2 | Typical of `curl`/`requests` defaults |
| Missing `Accept-Encoding` | +2 | All browsers send gzip at minimum |
| Missing both `Sec-Fetch-Mode` and `Sec-Fetch-Site` | +1 | Sent by Chrome/Firefox since 2019 |
| `Connection: close` | +1 | Typical of raw HTTP clients |
| No `Referer` AND no `Sec-Fetch-Site` | +1 | Direct programmatic access pattern |

**Threshold: 6.** A single missing `Accept` header (score 4) combined with a missing `Accept-Language` (score 3) already triggers the block. A Chrome browser with all headers sends score 0.

---

### Layer 5 — Per-IP Rate Limiting

Applied only to requests that passed all previous checks (i.e., not a known good bot and not already blocked). Uses a **dual sliding-window** algorithm:

| Window | Limit | Purpose |
|---|---|---|
| **Main** | 30 requests / 60 seconds | Sustained scraping |
| **Burst** | 10 requests / 6 seconds | Rapid-fire scripts |

If either limit is exceeded: **429 Too Many Requests** with `Retry-After: 60` header.

The in-memory store (`_rl_store`) is cleaned every 5 minutes to prevent unbounded memory growth. Client IP is extracted from `X-Forwarded-For` (first address) when present, falling back to the direct connection IP.

---

## Protected Pages

The utility is applied to these 10 high-value data pages:

| URL | Route file |
|---|---|
| `/data/brent-crude-oil-price-today` | `src/api/brent_routes.py` |
| `/gas-storage-levels-in-europe` | `src/api/gas_storage_routes.py` |
| `/data/natural-gas-price-today-europe` | `src/api/natgas_routes.py` |
| `/data/wti-crude-oil-price-today` | `src/api/wti_routes.py` |
| `/data/jkm-lng-price-chart` | `src/api/jkm_chart_routes.py` |
| `/data/jkm-lng-spot-price` | `src/api/jkm_routes.py` |
| `/gas-storage-levels-germany` | `src/api/gas_storage_germany_routes.py` |
| `/data/global-energy-risk-forecast` | `src/api/forecast_routes.py` |
| `/indices/global-energy-risk-index` | `src/api/seo_routes.py` |
| `/research/global-energy-risk-index` | `src/api/seo_routes.py` |

---

## Integration — How to Apply to a New Route

**1. Add imports** to the route file:

```python
from fastapi import APIRouter, Request
from src.utils.anti_scraping import check_scraping
```

**2. Add `request: Request`** to the handler signature:

```python
@router.get("/your/path")
async def my_handler(request: Request):
    ...
```

**3. Call `check_scraping(request)`** as the first line of the handler body, before any data computation or streaming generator:

```python
@router.get("/your/path")
async def my_handler(request: Request):
    check_scraping(request)          # ← raises HTTPException if blocked
    async def generate():
        yield ...
    return StreamingResponse(generate(), media_type="text/html")
```

The call must come **before** the `return StreamingResponse(...)` so that a 403/429 can be sent as a proper HTTP response (not inside a stream).

---

## Response Headers

The helper `anti_scraping_headers()` returns a dict of response headers that can be added to any `Response` to further discourage caching and archiving by proxy scrapers:

```python
from src.utils.anti_scraping import anti_scraping_headers

return Response(content=html, headers=anti_scraping_headers())
```

| Header | Value | Purpose |
|---|---|---|
| `X-Robots-Tag` | `noarchive` | Tells crawlers not to cache a snapshot |
| `Cache-Control` | `no-store, max-age=0` | Prevents proxy/CDN caching of live data |
| `X-Content-Type-Options` | `nosniff` | Prevents MIME-type sniffing |
| `X-Frame-Options` | `SAMEORIGIN` | Prevents embedding in third-party iframes |

---

## Test Results

Verified live against the production API server:

| Client | Expected | Result |
|---|---|---|
| Googlebot | 200 | ✅ |
| Bingbot | 200 | ✅ |
| YandexBot | 200 | ✅ |
| GPTBot (OpenAI) | 200 | ✅ |
| ClaudeBot (Anthropic) | 200 | ✅ |
| PerplexityBot | 200 | ✅ |
| Chrome browser (full headers) | 200 | ✅ |
| `python-requests/2.31.0` | 403 | ✅ |
| `Scrapy/2.11` | 403 | ✅ |
| Empty User-Agent | 403 | ✅ |
| `curl/8.1.2` (no browser headers) | 403 | ✅ |
| `SemrushBot/7` | 403 | ✅ |

---

## Extending the Lists

### Allow a new bot
Add a lowercase substring to `_GOOD_BOT_SUBS` in `src/utils/anti_scraping.py`. The check is a simple `in` test on the lowercased UA string — no regex required.

```python
_GOOD_BOT_SUBS = frozenset([
    ...
    "mynewbot",   # My New Bot — description
])
```

### Block a new scraper
Add a lowercase substring to `_BAD_BOT_SUBS`:

```python
_BAD_BOT_SUBS = frozenset([
    ...
    "badtool/",   # BadTool scraping framework
])
```

### Tune rate limits
Edit the four constants at the top of the module:

```python
_RL_WINDOW    = 60   # main window length (seconds)
_RL_MAX       = 30   # max requests per IP in the main window
_RL_BURST_WIN = 6    # burst window length (seconds)
_RL_BURST_MAX = 10   # max requests per IP in the burst window
```

### Tune fingerprint sensitivity
Edit `_FP_THRESHOLD` (default `6`) and the per-signal scores inside `_header_bot_score()`. Lower the threshold to block more aggressively; raise it to be more permissive.

---

## Limitations & Future Improvements

| Limitation | Notes |
|---|---|
| **UA spoofing** | A scraper that sends a real browser UA and all required headers will bypass layers 1–4. Rate limiting (layer 5) is the backstop. |
| **Shared IPs** | Rate limiting by IP can occasionally affect users behind corporate NAT sharing an IP. The threshold (30/min) is set conservatively to avoid this. |
| **In-memory store** | The rate limit state resets on server restart and is not shared across multiple worker processes. For multi-process deployments, replace `_rl_store` with Redis. |
| **No IP reputation** | Known datacenter / VPN IP ranges are not currently blocked. This could be added using a CIDR blocklist. |
| **JS challenge** | Headless browsers that send realistic headers can pass layer 4. A CAPTCHA or JS-cookie challenge would close this gap entirely at the cost of added complexity. |
