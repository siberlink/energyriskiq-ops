"""LinkedIn Posts Builder.

Generates a daily LinkedIn-ready post for EnergyRiskIQ from the latest
Daily Intelligence Report. Hooks and CTAs rotate so the content does not feel
repetitive; the analysis prose is written by an LLM constrained to the report
data (no invented facts), in a human, analyst-native tone.
"""

import os
import re
import json
import logging
from datetime import date, timedelta

from src.db.db import execute_query, execute_one

logger = logging.getLogger(__name__)

TARGET_MIN_CHARS = 1200
TARGET_MAX_CHARS = 1800

HASHTAGS = (
    "#EnergyMarkets #EnergyRisk #OilMarkets #NaturalGas "
    "#LNG #CommodityTrading #RiskManagement #EnergyRiskIQ"
)

# Hook categories (buckets) and their rotating options.
THEME_HOOKS = {
    "geopolitical": [
        "Markets may be underpricing geopolitical risk.",
        "Risk often moves before headlines.",
        "Energy markets rarely wait for tomorrow's headlines.",
        "Political risk can move faster than prices.",
    ],
    "oil": [
        "Brent's risk premium is shifting again.",
        "Oil markets are calm, but risk signals are still moving.",
        "Brent prices do not always reflect the full risk picture.",
        "The oil market may be pricing today, not tomorrow.",
    ],
    "natural_gas": [
        "European gas storage is improving, but vulnerabilities remain.",
        "Gas market comfort can disappear quickly.",
        "Storage levels alone do not guarantee winter security.",
        "Natural gas risk is rarely visible in one headline number.",
    ],
    "lng": [
        "LNG markets can change direction faster than most expect.",
        "LNG prices can remain stable right until they suddenly don't.",
        "One LNG disruption can reshape regional pricing quickly.",
        "LNG risk is often global before it becomes local.",
    ],
    "contrarian": [
        "The biggest energy market risks are often invisible in today's prices.",
        "Calm prices do not always mean low risk.",
        "Stability can be misleading in energy markets.",
        "The market may be quiet, but the risk picture is not.",
    ],
    "volatility": [
        "Volatility often begins long before prices react.",
        "Market stress usually builds before it becomes visible.",
        "Risk indicators can move before volatility appears.",
        "Low volatility does not always mean low uncertainty.",
    ],
}

# Maps the detected dominant theme to a hook bucket.
THEME_TO_HOOK_BUCKET = {
    "geopolitical": "geopolitical",
    "supply_disruption": "geopolitical",
    "oil": "oil",
    "natural_gas": "natural_gas",
    "gas_storage": "natural_gas",
    "lng": "lng",
    "volatility": "volatility",
    "risk_underpricing": "contrarian",
    "risk_premium_fading": "contrarian",
}

CTA_QUESTIONS = [
    "What risk do you believe energy markets are currently underpricing?",
    "Which energy risk are you watching most closely today?",
    "Do current prices fully reflect the risk picture?",
    "Which indicator would you monitor first this week?",
    "What could trigger the next major move in energy markets?",
    "Are markets too comfortable with current supply conditions?",
]

HYPE_TERMS = [
    "game-changing", "game changing", "explosive", "must-read", "must read",
    "shocking", "groundbreaking", "ground-breaking", "revolutionary",
]


# ──────────────────────────────────────────────────────────────────────────
# Report access & freshness
# ──────────────────────────────────────────────────────────────────────────
def _get_report():
    """Fetch the full Daily Intelligence Report data (enterprise level)."""
    from src.api.daily_digest_routes import get_linkedin_report_data
    return get_linkedin_report_data()


def _report_is_fresh(report) -> bool:
    """A usable report exists when core risk data is present and recent."""
    if not report:
        return False
    geri = report.get("geri")
    if not geri or geri.get("value") is None:
        return False
    geri_date = geri.get("date")
    if geri_date:
        try:
            gd = date.fromisoformat(str(geri_date)[:10])
            if (date.today() - gd).days > 3:
                return False
        except Exception:
            pass
    if not report.get("executive_summary"):
        return False
    return True


# ──────────────────────────────────────────────────────────────────────────
# Theme detection
# ──────────────────────────────────────────────────────────────────────────
def _f(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def determine_dominant_theme(report) -> str:
    """Deterministically pick the dominant market theme from the report."""
    scores = {
        "geopolitical": 0.0, "oil": 0.0, "natural_gas": 0.0, "lng": 0.0,
        "gas_storage": 0.0, "supply_disruption": 0.0, "volatility": 0.0,
        "risk_underpricing": 0.0, "risk_premium_fading": 0.0,
    }

    geri = report.get("geri") or {}
    geri_val = _f(geri.get("value"))
    geri_trend7 = _f(geri.get("trend_7d"))

    asset_changes = report.get("asset_changes") or {}
    brent_pct = abs(_f((asset_changes.get("brent") or {}).get("pct_change")))
    ttf_pct = abs(_f((asset_changes.get("ttf") or {}).get("pct_change")))

    vol = report.get("volatility_outlook") or {}
    vol_regime = (vol.get("regime") or "").lower()
    vix_level = _f(vol.get("vix_level"))

    prob = report.get("probability_scoring") or {}
    esc_prob = _f(prob.get("escalation_probability"))
    de_esc_prob = _f(prob.get("de_escalation_probability"))

    storage = report.get("storage_context") or {}
    storage_pct = _f(storage.get("current"), 50.0)
    storage_band = (storage.get("risk_band") or "").lower()

    alerts = report.get("alerts") or []
    geo_hits = supply_hits = lng_hits = 0
    for a in alerts:
        cat = (a.get("category") or "").lower()
        text = (a.get("headline") or "").lower()
        sev = _f(a.get("severity"))
        if any(k in cat or k in text for k in ("geopolit", "conflict", "war", "sanction", "military", "attack")):
            geo_hits += 1 + (1 if sev >= 4 else 0)
        if any(k in cat or k in text for k in ("supply", "outage", "disruption", "pipeline", "shutdown", "strike")):
            supply_hits += 1
        if "lng" in text or "lng" in cat:
            lng_hits += 1

    # Geopolitical
    scores["geopolitical"] += geo_hits * 6 + max(0.0, geri_val - 50) * 0.4
    # Supply disruption
    scores["supply_disruption"] += supply_hits * 6
    # Oil
    scores["oil"] += brent_pct * 4
    # Natural gas
    scores["natural_gas"] += ttf_pct * 4
    # LNG
    scores["lng"] += lng_hits * 6
    # Gas storage stress
    if storage_pct < 45 or "high" in storage_band or "critical" in storage_band:
        scores["gas_storage"] += (50 - storage_pct) * 0.6 + 6
    # Volatility
    if vol_regime in ("high", "extreme"):
        scores["volatility"] += 10
    if vix_level >= 22:
        scores["volatility"] += (vix_level - 18) * 0.8
    # Risk premium fading (de-escalation / GERI trending down)
    if de_esc_prob >= 55 or geri_trend7 < -2:
        scores["risk_premium_fading"] += 6 + abs(min(0.0, geri_trend7))
    # Risk underpricing: elevated risk but calm prices
    if geri_val >= 55 and brent_pct < 1.0 and ttf_pct < 1.5:
        scores["risk_underpricing"] += 8 + (geri_val - 50) * 0.3

    dominant = max(scores, key=scores.get)
    if scores[dominant] <= 0:
        # Calm, balanced day -> lead with the contrarian/underpricing angle.
        dominant = "risk_underpricing"
    return dominant


# ──────────────────────────────────────────────────────────────────────────
# Hook / CTA rotation
# ──────────────────────────────────────────────────────────────────────────
def _recent_hooks(days: int = 14):
    rows = execute_query(
        "SELECT selected_hook FROM linkedin_posts WHERE post_date >= %s",
        (date.today() - timedelta(days=days),),
    )
    return {r["selected_hook"] for r in (rows or []) if r.get("selected_hook")}


def _recent_ctas(days: int = 7):
    rows = execute_query(
        "SELECT selected_cta FROM linkedin_posts WHERE post_date >= %s",
        (date.today() - timedelta(days=days),),
    )
    return {r["selected_cta"] for r in (rows or []) if r.get("selected_cta")}


def select_hook(theme: str, exclude=None) -> str:
    exclude = exclude or set()
    bucket = THEME_TO_HOOK_BUCKET.get(theme, "geopolitical")
    options = THEME_HOOKS[bucket]
    fresh = [h for h in options if h not in exclude]
    pool = fresh if fresh else options
    # Rotate by day so repeated same-day calls without exclusion still vary.
    idx = date.today().toordinal() % len(pool)
    return pool[idx]


def select_cta(exclude=None) -> str:
    exclude = exclude or set()
    fresh = [c for c in CTA_QUESTIONS if c not in exclude]
    pool = fresh if fresh else CTA_QUESTIONS
    idx = date.today().toordinal() % len(pool)
    return pool[idx]


# ──────────────────────────────────────────────────────────────────────────
# AI prose generation
# ──────────────────────────────────────────────────────────────────────────
def _build_report_context(report) -> dict:
    """Compact, AI-facing slice of the report (only real data)."""
    def slim_alerts(items, n=6):
        out = []
        for a in (items or [])[:n]:
            out.append({
                "headline": a.get("headline"),
                "region": a.get("region"),
                "severity": a.get("severity"),
                "category": a.get("category"),
            })
        return out

    return {
        "executive_summary": report.get("executive_summary"),
        "regime": report.get("regime"),
        "risk_tone": report.get("risk_tone"),
        "geri": report.get("geri"),
        "eeri": report.get("eeri"),
        "egsi": report.get("egsi"),
        "asset_changes": report.get("asset_changes"),
        "storage_context": report.get("storage_context"),
        "actionable_takeaways": report.get("actionable_takeaways"),
        "forward_watchlist": report.get("forward_watchlist"),
        "scenario_forecasts": report.get("scenario_forecasts"),
        "probability_scoring": report.get("probability_scoring"),
        "volatility_outlook": report.get("volatility_outlook"),
        "key_geopolitical_developments": slim_alerts(report.get("alerts")),
    }


_SYSTEM_PROMPT = (
    "You are a senior energy market analyst writing a daily LinkedIn post for "
    "EnergyRiskIQ. Write like an experienced human analyst, not like an AI "
    "summary. Tone: professional, analytical, clear, and LinkedIn-native. "
    "Rules: do not invent data — use only the report provided; never use hype "
    "language such as 'game-changing', 'explosive', 'must-read', or 'shocking'; "
    "do not use emojis; keep paragraphs short (1-3 sentences); avoid sounding "
    "promotional. Return strict JSON only."
)


def _ai_generate(report, theme: str, hook: str):
    """Return (paragraphs:list[str], takeaways:list[str]) from the LLM."""
    from src.ai.ai_worker import get_openai_client, OPENAI_MODEL

    context = _build_report_context(report)
    user_prompt = (
        f"Dominant market theme today: {theme}.\n"
        f"The post will open with this exact hook line (do NOT repeat it): \"{hook}\"\n\n"
        "Write the body of the post using ONLY the report data below.\n"
        "Return JSON with two keys:\n"
        '  "paragraphs": an array of 2 to 4 short analysis paragraphs that explain '
        "what changed, why it matters, what markets may be underpricing, and what "
        "energy professionals should monitor next.\n"
        '  "takeaways": an array of 3 to 4 concise, concrete one-line takeaways '
        "drawn from the report (no leading bullet characters).\n\n"
        "Keep the combined length so the final post reads tightly "
        f"(aim for {TARGET_MIN_CHARS}-{TARGET_MAX_CHARS} characters total once "
        "the header, hook, takeaways, CTA and hashtags are added).\n\n"
        f"REPORT DATA (JSON):\n{json.dumps(context, default=str)}"
    )

    client = get_openai_client()
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content or "{}"
    data = json.loads(raw)

    paragraphs = [str(p).strip() for p in (data.get("paragraphs") or []) if str(p).strip()]
    takeaways = [str(t).strip().lstrip("•-* ").strip() for t in (data.get("takeaways") or []) if str(t).strip()]

    if not paragraphs or not takeaways:
        raise ValueError("AI returned empty paragraphs or takeaways")

    paragraphs = [_clean_text(p) for p in paragraphs][:4]
    takeaways = [_clean_text(t) for t in takeaways][:4]
    return paragraphs, takeaways


# ──────────────────────────────────────────────────────────────────────────
# Cleaning, assembly & validation
# ──────────────────────────────────────────────────────────────────────────
_EMOJI_RE = re.compile(
    "[" 
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F000-\U0001F0FF"
    "\U00002190-\U000021FF"
    "\U0000FE00-\U0000FE0F"
    "]+",
    flags=re.UNICODE,
)


def _clean_text(text: str) -> str:
    text = _EMOJI_RE.sub("", text)
    # Strip any stray hashtags from the prose so the post keeps exactly the
    # fixed 8 hashtags appended at the end.
    text = re.sub(r"#\w+", "", text)
    for term in HYPE_TERMS:
        text = re.sub(re.escape(term), "", text, flags=re.IGNORECASE)
    text = re.sub(r"[ \t]{2,}", " ", text).strip()
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    return text


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower().rstrip(".")


def _dedupe_hook(paragraphs, hook):
    """Drop a leading hook echo from the first paragraph (the model sometimes
    repeats the hook line even when told not to)."""
    if not paragraphs:
        return paragraphs
    h = _norm(hook)
    first = paragraphs[0]
    if _norm(first) == h:
        return paragraphs[1:] or paragraphs
    trimmed = re.sub(
        r"^\s*" + re.escape(hook.rstrip(".")) + r"[.!?]?\s+", "", first, flags=re.IGNORECASE
    ).strip()
    if trimmed and trimmed != first:
        return [trimmed] + paragraphs[1:]
    return paragraphs


def _format_date(d: date) -> str:
    return f"{d.day} {d.strftime('%B %Y')}"


def _assemble(post_date: date, hook: str, paragraphs, takeaways, cta: str) -> str:
    parts = [f"EnergyRiskIQ Daily Intelligence | {_format_date(post_date)}", "", hook, ""]
    parts.append("\n\n".join(paragraphs))
    parts.append("")
    parts.append("Today's key takeaways:")
    parts.append("")
    parts.extend(f"• {t}" for t in takeaways)
    parts.append("")
    parts.append(cta)
    parts.append("")
    parts.append(HASHTAGS)
    return "\n".join(parts).strip()


def _assemble_and_fit(post_date, hook, paragraphs, takeaways, cta) -> str:
    """Assemble and trim content so the post stays within the char limit."""
    paras = list(paragraphs)
    takes = list(takeaways)
    body = _assemble(post_date, hook, paras, takes, cta)

    # Trim from the bottom: drop a 4th takeaway, then trailing paragraphs.
    while len(body) > TARGET_MAX_CHARS:
        if len(takes) > 3:
            takes.pop()
        elif len(paras) > 2:
            paras.pop()
        else:
            break
        body = _assemble(post_date, hook, paras, takes, cta)

    # Last resort: hard-trim the final paragraph.
    if len(body) > TARGET_MAX_CHARS and paras:
        overflow = len(body) - TARGET_MAX_CHARS
        last = paras[-1]
        if len(last) > overflow + 1:
            paras[-1] = last[: len(last) - overflow - 1].rstrip(" ,.;:") + "."
            body = _assemble(post_date, hook, paras, takes, cta)

    return body


# ──────────────────────────────────────────────────────────────────────────
# Persistence & public entry points
# ──────────────────────────────────────────────────────────────────────────
def _upsert_post(post_date, report_date, theme, hook, cta, post_body, source):
    rows = execute_query(
        """
        INSERT INTO linkedin_posts
            (post_date, report_date, selected_theme, selected_hook, selected_cta,
             post_body, char_count, status, source, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'draft', %s, NOW(), NOW())
        ON CONFLICT (post_date) DO UPDATE SET
            report_date = EXCLUDED.report_date,
            selected_theme = EXCLUDED.selected_theme,
            selected_hook = EXCLUDED.selected_hook,
            selected_cta = EXCLUDED.selected_cta,
            post_body = EXCLUDED.post_body,
            char_count = EXCLUDED.char_count,
            status = 'draft',
            source = EXCLUDED.source,
            updated_at = NOW()
        RETURNING *
        """,
        (post_date, report_date, theme, hook, cta, post_body, len(post_body), source),
    )
    return rows[0] if rows else None


def generate_and_store_post(source: str = "manual", force_new_hook: bool = False) -> dict:
    """Generate today's LinkedIn post as a draft and store it.

    Returns {"ok": True, "post": {...}} or {"ok": False, "error": "..."}.
    """
    report = _get_report()
    if not _report_is_fresh(report):
        return {"ok": False, "error": "No Daily Intelligence Report available for today."}

    today = date.today()
    theme = determine_dominant_theme(report)

    exclude = _recent_hooks(14)
    if force_new_hook:
        existing = execute_one(
            "SELECT selected_hook FROM linkedin_posts WHERE post_date = %s", (today,)
        )
        if existing and existing.get("selected_hook"):
            exclude = set(exclude) | {existing["selected_hook"]}

    hook = select_hook(theme, exclude)
    cta = select_cta(_recent_ctas(7))

    try:
        paragraphs, takeaways = _ai_generate(report, theme, hook)
    except Exception as exc:
        logger.error(f"LinkedIn post AI generation failed: {exc}")
        return {"ok": False, "error": f"AI generation failed: {exc}"}

    paragraphs = _dedupe_hook(paragraphs, hook)

    post_body = _assemble_and_fit(today, hook, paragraphs, takeaways, cta)
    report_date = report.get("alerts_date") or report.get("digest_date")

    post = _upsert_post(today, report_date, theme, hook, cta, post_body, source)
    return {"ok": True, "post": post}


def scheduled_generate() -> dict:
    """Idempotent daily entry point used by the internal runner / GitHub Actions."""
    today = date.today()
    existing = execute_one("SELECT id, status FROM linkedin_posts WHERE post_date = %s", (today,))
    if existing:
        return {"generated": False, "skipped": True, "reason": "Post already exists for today"}

    result = generate_and_store_post(source="scheduled")
    if result.get("ok"):
        return {"generated": True, "post_id": result["post"]["id"]}
    # Not an error to GitHub Actions: lets the cron retry later in the window.
    return {"generated": False, "reason": result.get("error")}
