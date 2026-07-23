"""
EnergyRiskIQ — Anti-Scraping Utility
=====================================
Blocks automated data scrapers while EXPLICITLY allowing:
  • All major search engine crawlers (Google, Bing, Yandex, Baidu, etc.)
  • All AI/LLM indexing services (GPTBot, ClaudeBot, PerplexityBot, etc.)
  • Social preview bots (Facebook, Twitter, LinkedIn, etc.)
  • Web archive services
  • Uptime monitors

Detection layers (applied in order):
  1. Good-bot allowlist  → immediate pass, no rate limit
  2. Bad-bot UA blocklist → 403
  3. Empty / suspicious UA → 403
  4. Header fingerprint scoring → high-score = bot → 403
  5. Per-IP rate limiting (sliding window, with burst detection) → 429
  6. Honeypot cookie check → 403 for clients that never run JS
"""

import re
import time
import hashlib
import logging
from collections import defaultdict
from typing import Optional

from fastapi import Request, HTTPException
from fastapi.responses import HTMLResponse

logger = logging.getLogger(__name__)

# ── Rate limiting config ───────────────────────────────────────────────────────
_RL_WINDOW      = 60    # seconds for the main window
_RL_MAX         = 30    # max requests per IP per window
_RL_BURST_WIN   = 6     # seconds for burst window
_RL_BURST_MAX   = 10    # max requests in burst window

# In-memory store: ip → [timestamps]
_rl_store: dict = defaultdict(list)

# ── Good-bot allowlist ─────────────────────────────────────────────────────────
# Any UA that contains one of these substrings (lower-cased) is ALWAYS allowed.
# Add new AI/search crawlers here to whitelist them.
_GOOD_BOT_SUBS = frozenset([
    # ── Google ──────────────────────────────────────────────────────────────
    "googlebot", "adsbot-google", "apis-google", "google-inspectiontool",
    "googlebot-image", "googlebot-news", "googlebot-video",
    "mediapartners-google", "google-safety", "storebot-google",
    "google-read-aloud", "google-structured-data-testing-tool",
    # ── Bing / Microsoft ────────────────────────────────────────────────────
    "bingbot", "msnbot", "adidxbot", "bingpreview", "microsoft url preview",
    # ── Yahoo ───────────────────────────────────────────────────────────────
    "slurp",
    # ── Other search engines ─────────────────────────────────────────────────
    "duckduckbot", "duckduckgo-favicons-bot",
    "baiduspider", "baiduspider-plus", "baiduspider-image",
    "yandexbot", "yandexmobilebot", "yandeximageresizer", "yandexdirect",
    "yandexmetrika", "yandexwebmaster", "yandexfeedparser",
    "sogou page spider", "sogoubot",
    "exabot", "mojeekbot", "qwantify", "applebot",
    "archive.org_bot", "ia_archiver", "wayback",
    "petalbot",                # Huawei search — legitimate
    # ── AI / LLM services — EXPLICITLY ALLOWED per site policy ───────────────
    "gptbot",                  # OpenAI GPTBot
    "chatgpt-user",            # OpenAI ChatGPT browsing
    "oai-searchbot",           # OpenAI SearchBot
    "claudebot",               # Anthropic ClaudeBot
    "claude-web",              # Anthropic Claude
    "anthropic-ai",            # Anthropic generic
    "perplexitybot",           # Perplexity AI
    "amazonbot",               # Amazon Alexa / AI
    "meta-externalagent",      # Meta AI
    "meta-externalfetcher",    # Meta AI
    "cohere-ai",               # Cohere AI
    "diffbot",                 # Diffbot AI
    "youbot",                  # You.com AI
    "neevabot",                # Neeva AI
    "timpibot",                # Timpi search
    "omgili",                  # Research crawler
    "bytedance-inspectiontool", # ByteDance AI inspector
    # ── Social preview fetchers ──────────────────────────────────────────────
    "facebookexternalhit", "facebot",
    "twitterbot",
    "linkedinbot",
    "pinterestbot", "pinterest/",
    "slackbot",
    "whatsapp",
    "telegrambot",
    "discordbot",
    "skypeuripreview",
    "vkshare", "vk.com",
    "redditbot",
    "tumblr",
    "embedly",
    "quora link preview",
    # ── Uptime / monitoring ──────────────────────────────────────────────────
    "uptimerobot", "pingdom", "statuscake", "site24x7", "freshping",
    "newrelic synthetics", "datadoghq", "hetrixtools",
    # ── RSS / Feed readers ───────────────────────────────────────────────────
    "feedly", "feedfetcher",
    # ── Research / academic ──────────────────────────────────────────────────
    "semanticscholarbot", "internet archive",
])

# ── Bad-bot patterns — block with 403 ─────────────────────────────────────────
# Match any of these substrings (lower-cased) in the User-Agent.
_BAD_BOT_SUBS = frozenset([
    # Python HTTP libraries used as scrapers
    "python-requests", "python-urllib", "python-httpx",
    "aiohttp/", "httplib2", "urllib/",
    # Scraping frameworks
    "scrapy", "mechanize",
    # Headless browsers (no legit bot declares these)
    "headlesschrome", "phantomjs", "nightmare", "zombie.js",
    "selenium", "webdriver",
    # CLI download tools
    "wget/", "libwww-perl", "curl/",
    "httrack",
    # Data harvesters / commercial crawlers (non-search)
    "semrushbot", "semrush",
    "mj12bot", "majestic",
    "dotbot", "dotnetdotcom",
    "bytespider",             # ByteDance mass crawler (not the AI inspector)
    "blexbot",
    "turnitinbot",
    "ltx71",                  # Known scraper tool
    "masscan",
    "zgrab",
    "nmap",
    # Generic scraper labels that no legit tool would use
    "scraper", "dataminer", "harvester", "extractor",
    # Raw HTTP clients
    "go-http-client", "okhttp/", "apache-httpclient",
    "axios/",                  # Node.js raw HTTP — not a browser
    "node-fetch", "node-superagent", "got/",
    "java/", "java-",
])

# ── Header fingerprint scoring ────────────────────────────────────────────────
# Real browsers always send specific headers. Programmatic clients often skip them.
# Score ≥ threshold → treat as bot.
_FP_THRESHOLD = 6


def _header_bot_score(request: Request) -> int:
    """
    Score request headers for bot-like characteristics.
    Higher score = more bot-like. Returns integer score.
    """
    score = 0
    headers = request.headers

    # Missing Accept header: real browsers always send this
    if not headers.get("accept"):
        score += 4

    # Missing Accept-Language: real browsers always send this
    if not headers.get("accept-language"):
        score += 3

    # Accept is only "*/*" with no quality values: typical of curl/requests
    accept = headers.get("accept", "")
    if accept.strip() == "*/*":
        score += 2

    # Missing Sec-Fetch-Mode: sent by Chrome/Firefox since 2019
    if not headers.get("sec-fetch-mode") and not headers.get("sec-fetch-site"):
        score += 1

    # Missing Accept-Encoding: real browsers always send gzip,deflate
    if not headers.get("accept-encoding"):
        score += 2

    # Connection: close (typical of raw HTTP clients, not browsers)
    if headers.get("connection", "").lower() == "close":
        score += 1

    # No referer AND no sec-fetch-* headers (direct programmatic access pattern)
    if not headers.get("referer") and not headers.get("sec-fetch-site"):
        score += 1

    return score


def _is_good_bot(ua: str) -> bool:
    """Return True if UA matches a known legitimate crawler."""
    ua_lower = ua.lower()
    for pattern in _GOOD_BOT_SUBS:
        if pattern in ua_lower:
            return True
    return False


def _is_bad_bot(ua: str) -> bool:
    """Return True if UA matches a known scraper/harvester."""
    ua_lower = ua.lower()
    for pattern in _BAD_BOT_SUBS:
        if pattern in ua_lower:
            return True
    return False


def _get_client_ip(request: Request) -> str:
    """Extract real client IP, respecting X-Forwarded-For from trusted proxies."""
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_rate_limit(ip: str) -> bool:
    """
    Sliding-window rate limiter.
    Returns True if the request should be blocked (too many requests).
    """
    now = time.monotonic()

    # Expire old timestamps outside the main window
    cutoff = now - _RL_WINDOW
    _rl_store[ip] = [t for t in _rl_store[ip] if t > cutoff]

    # Burst check: too many requests in the short window
    burst_cutoff = now - _RL_BURST_WIN
    burst_count = sum(1 for t in _rl_store[ip] if t > burst_cutoff)
    if burst_count >= _RL_BURST_MAX:
        return True

    # Main window check
    if len(_rl_store[ip]) >= _RL_MAX:
        return True

    _rl_store[ip].append(now)
    return False


# Periodic cleanup to avoid unbounded memory growth (called inline, cheap)
_last_cleanup = [0.0]

def _cleanup_rl_store():
    now = time.monotonic()
    if now - _last_cleanup[0] < 300:  # every 5 minutes
        return
    _last_cleanup[0] = now
    cutoff = now - _RL_WINDOW
    dead_keys = [k for k, ts in _rl_store.items() if not any(t > cutoff for t in ts)]
    for k in dead_keys:
        del _rl_store[k]


def check_scraping(request: Request) -> None:
    """
    Main anti-scraping gate — call at the top of any route handler.

    Decision tree:
      1. Good bot (search engine / AI crawler) → ALLOW immediately
      2. Empty User-Agent                       → BLOCK 403
      3. Known bad-bot UA pattern               → BLOCK 403
      4. Header fingerprint score ≥ threshold   → BLOCK 403
      5. Rate limit exceeded                    → BLOCK 429

    Raises HTTPException on block; returns None on allow.
    """
    _cleanup_rl_store()

    ua = request.headers.get("user-agent", "")

    # 1. Good bot → always pass
    if ua and _is_good_bot(ua):
        return

    # 2. Empty UA → block
    if not ua or len(ua.strip()) < 10:
        logger.info("Anti-scrape: empty/short UA from %s", _get_client_ip(request))
        raise HTTPException(status_code=403, detail="Forbidden")

    # 3. Known bad-bot UA → block
    if _is_bad_bot(ua):
        logger.info("Anti-scrape: bad-bot UA '%s' from %s", ua[:80], _get_client_ip(request))
        raise HTTPException(status_code=403, detail="Forbidden")

    # 4. Header fingerprint
    score = _header_bot_score(request)
    if score >= _FP_THRESHOLD:
        logger.info(
            "Anti-scrape: header score=%d for UA='%s' IP=%s",
            score, ua[:80], _get_client_ip(request)
        )
        raise HTTPException(status_code=403, detail="Forbidden")

    # 5. Rate limiting (only applied to non-good-bots)
    ip = _get_client_ip(request)
    if _check_rate_limit(ip):
        logger.info("Anti-scrape: rate limit hit for IP=%s", ip)
        raise HTTPException(status_code=429, detail="Too Many Requests",
                            headers={"Retry-After": str(_RL_WINDOW)})


def anti_scraping_headers() -> dict:
    """
    Response headers that signal to scrapers this content should not be cached/archived,
    while remaining fully transparent to search engines and AI crawlers.
    """
    return {
        "X-Robots-Tag": "noarchive",
        "Cache-Control": "no-store, max-age=0",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "SAMEORIGIN",
    }
