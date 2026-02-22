import logging
from datetime import datetime, timedelta
from src.db.db import execute_query, execute_one, execute_production_one, execute_production_query

logger = logging.getLogger(__name__)


def build_elsa_context(question: str) -> str:
    parts = ["=== ELSA FULL PRODUCTION DATABASE CONTEXT (Live Data) ==="]
    parts.append(f"Timestamp: {datetime.utcnow().isoformat()}Z")

    context_sections = [
        ("User Metrics", _get_user_metrics),
        ("Plan Distribution", _get_plan_distribution),
        ("Revenue Metrics", _get_revenue_metrics),
        ("Content & Pipeline Metrics", _get_content_metrics),
        ("Index Values", _get_index_summary),
        ("Asset & Commodity Prices", _get_asset_prices),
        ("EGSI Component Details", _get_egsi_components),
        ("Delivery & Engagement", _get_delivery_metrics),
        ("ERIQ Bot Usage", _get_eriq_usage),
        ("ELSA Usage", _get_elsa_usage),
        ("Alert Metrics", _get_alert_metrics),
        ("Engine Health", _get_engine_health),
        ("Ticket Metrics", _get_ticket_metrics),
        ("SEO Metrics", _get_seo_metrics),
    ]

    for name, func in context_sections:
        try:
            result = func()
            if result:
                parts.append(result)
        except Exception as e:
            logger.error(f"ELSA {name} failed: {e}")

    return "\n\n".join([p for p in parts if p])


def _q(query, params=None):
    return execute_production_one(query, params or ())


def _qq(query, params=None):
    return execute_production_query(query, params or ()) or []


def _get_user_metrics() -> str:
    total = _q("SELECT COUNT(*) as cnt FROM users") or {}
    verified = _q("SELECT COUNT(*) as cnt FROM users WHERE verified = true") or {}
    recent_7d = _q("SELECT COUNT(*) as cnt FROM users WHERE created_at > NOW() - INTERVAL '7 days'") or {}
    recent_30d = _q("SELECT COUNT(*) as cnt FROM users WHERE created_at > NOW() - INTERVAL '30 days'") or {}
    with_telegram = _q("SELECT COUNT(*) as cnt FROM users WHERE telegram_chat_id IS NOT NULL") or {}
    with_pin = _q("SELECT COUNT(*) as cnt FROM users WHERE pin_hash IS NOT NULL") or {}

    return f"""## User Metrics
- Total Users: {total.get('cnt', 0)}
- Verified Users: {verified.get('cnt', 0)}
- Users with Telegram linked: {with_telegram.get('cnt', 0)}
- Users with PIN set: {with_pin.get('cnt', 0)}
- New Users (7 days): {recent_7d.get('cnt', 0)}
- New Users (30 days): {recent_30d.get('cnt', 0)}"""


def _get_plan_distribution() -> str:
    rows = _qq("""
        SELECT COALESCE(plan, 'free') as plan, COUNT(*) as cnt 
        FROM users GROUP BY COALESCE(plan, 'free') ORDER BY cnt DESC
    """)
    lines = ["## Plan Distribution"]
    for r in rows:
        lines.append(f"- {r['plan']}: {r['cnt']} users")
    return "\n".join(lines)


def _get_revenue_metrics() -> str:
    active_subs = _q("""
        SELECT COUNT(*) as cnt FROM users 
        WHERE stripe_subscription_id IS NOT NULL AND plan != 'free' AND plan IS NOT NULL
    """) or {}

    plan_prices = _qq("""
        SELECT plan_code, price, currency FROM plan_settings WHERE price > 0 ORDER BY price
    """)

    mrr = _q("""
        SELECT COALESCE(SUM(ps.price), 0) as mrr
        FROM users u
        JOIN plan_settings ps ON u.plan = ps.plan_code
        WHERE u.stripe_subscription_id IS NOT NULL AND u.plan != 'free' AND u.plan IS NOT NULL
    """) or {}

    lines = [f"## Revenue Metrics"]
    lines.append(f"- Active Paid Subscriptions: {active_subs.get('cnt', 0)}")
    lines.append(f"- Estimated MRR: €{mrr.get('mrr', 0)}")
    for p in plan_prices:
        lines.append(f"- {p['plan_code']}: {p.get('currency', 'EUR')} {p['price']}/mo")
    return "\n".join(lines)


def _get_content_metrics() -> str:
    events = _q("SELECT COUNT(*) as cnt FROM events") or {}
    events_7d = _q("SELECT COUNT(*) as cnt FROM events WHERE created_at > NOW() - INTERVAL '7 days'") or {}
    alerts = _q("SELECT COUNT(*) as cnt FROM alert_events") or {}
    alerts_7d = _q("SELECT COUNT(*) as cnt FROM alert_events WHERE created_at > NOW() - INTERVAL '7 days'") or {}
    daily_pages = _q("SELECT COUNT(*) as cnt FROM seo_daily_pages") or {}
    sources = _q("SELECT COUNT(*) as cnt FROM sources WHERE is_active = true") or {}
    regions = _q("SELECT COUNT(*) as cnt FROM reri_canonical_regions WHERE is_active = true") or {}

    return f"""## Content & Pipeline Metrics
- Total Events Ingested: {events.get('cnt', 0)} (last 7d: {events_7d.get('cnt', 0)})
- Total Alert Events: {alerts.get('cnt', 0)} (last 7d: {alerts_7d.get('cnt', 0)})
- SEO Daily Pages: {daily_pages.get('cnt', 0)}
- Active RSS Sources: {sources.get('cnt', 0)}
- Active EERI Regions: {regions.get('cnt', 0)}"""


def _fmt_trend(curr, prev, key='value', fmt='.1f'):
    if curr and prev:
        try:
            diff = float(curr.get(key, 0)) - float(prev.get(key, 0))
            return f", change: {diff:+{fmt}} from previous day"
        except (TypeError, ValueError):
            pass
    return ""


def _get_index_summary() -> str:
    geri = _q("SELECT date, value, band FROM intel_indices_daily WHERE index_id = 'global:geo_energy_risk' ORDER BY date DESC LIMIT 1")
    geri_prev = _q("SELECT date, value, band FROM intel_indices_daily WHERE index_id = 'global:geo_energy_risk' ORDER BY date DESC LIMIT 1 OFFSET 1")

    eeri = _q("SELECT date, value, band FROM reri_indices_daily WHERE index_id = 'europe:eeri' ORDER BY date DESC LIMIT 1")
    eeri_prev = _q("SELECT date, value, band FROM reri_indices_daily WHERE index_id = 'europe:eeri' ORDER BY date DESC LIMIT 1 OFFSET 1")

    egsi_m = _q("SELECT index_date, index_value, band FROM egsi_m_daily ORDER BY index_date DESC LIMIT 1")
    egsi_m_prev = _q("SELECT index_date, index_value, band FROM egsi_m_daily ORDER BY index_date DESC LIMIT 1 OFFSET 1")

    egsi_s = _q("SELECT index_date, index_value, band FROM egsi_s_daily ORDER BY index_date DESC LIMIT 1")
    egsi_s_prev = _q("SELECT index_date, index_value, band FROM egsi_s_daily ORDER BY index_date DESC LIMIT 1 OFFSET 1")

    gas = _q("SELECT date, eu_storage_percent, risk_score, risk_band FROM gas_storage_snapshots ORDER BY date DESC LIMIT 1")

    geri_7d = _qq("SELECT date, value, band FROM intel_indices_daily WHERE index_id = 'global:geo_energy_risk' ORDER BY date DESC LIMIT 7")
    eeri_7d = _qq("SELECT date, value, band FROM reri_indices_daily WHERE index_id = 'europe:eeri' ORDER BY date DESC LIMIT 7")

    lines = ["## LIVE INDEX VALUES (use these EXACT numbers — never approximate or invent)"]

    if geri:
        lines.append(f"- GERI: {geri['value']} | Band: {geri['band']} | Date: {geri['date']}{_fmt_trend(geri, geri_prev)}")
    else:
        lines.append("- GERI: data unavailable")

    if eeri:
        lines.append(f"- EERI: {eeri['value']} | Band: {eeri['band']} | Date: {eeri['date']}{_fmt_trend(eeri, eeri_prev)}")
    else:
        lines.append("- EERI: data unavailable")

    if egsi_m:
        lines.append(f"- EGSI-M (Market): {egsi_m['index_value']} | Band: {egsi_m['band']} | Date: {egsi_m['index_date']}{_fmt_trend(egsi_m, egsi_m_prev, 'index_value', '.2f')}")
    else:
        lines.append("- EGSI-M: data unavailable")

    if egsi_s:
        lines.append(f"- EGSI-S (System): {egsi_s['index_value']} | Band: {egsi_s['band']} | Date: {egsi_s['index_date']}{_fmt_trend(egsi_s, egsi_s_prev, 'index_value', '.2f')}")
    else:
        lines.append("- EGSI-S: data unavailable")

    if gas:
        lines.append(f"- EU Gas Storage: {gas['eu_storage_percent']}% full | Risk: {gas['risk_score']} ({gas['risk_band']}) | Date: {gas['date']}")

    if geri_7d and len(geri_7d) > 1:
        vals = [f"{r['date']}: {r['value']}" for r in geri_7d]
        lines.append(f"- GERI 7-day trend: {', '.join(vals)}")

    if eeri_7d and len(eeri_7d) > 1:
        vals = [f"{r['date']}: {r['value']}" for r in eeri_7d]
        lines.append(f"- EERI 7-day trend: {', '.join(vals)}")

    return "\n".join(lines)


def _get_asset_prices() -> str:
    oil = _q("SELECT date, brent_price, brent_change_pct, wti_price, wti_change_pct, brent_wti_spread FROM oil_price_snapshots ORDER BY date DESC LIMIT 1")
    oil_prev = _q("SELECT date, brent_price, wti_price FROM oil_price_snapshots ORDER BY date DESC LIMIT 1 OFFSET 1")

    ttf = _q("SELECT date, ttf_price, currency, unit FROM ttf_gas_snapshots ORDER BY date DESC LIMIT 1")
    ttf_prev = _q("SELECT date, ttf_price FROM ttf_gas_snapshots ORDER BY date DESC LIMIT 1 OFFSET 1")

    lng = _q("SELECT date, jkm_price, jkm_change_pct FROM lng_price_snapshots ORDER BY date DESC LIMIT 1")
    lng_prev = _q("SELECT date, jkm_price FROM lng_price_snapshots ORDER BY date DESC LIMIT 1 OFFSET 1")

    fx = _q("SELECT date, rate, currency_pair FROM eurusd_snapshots ORDER BY date DESC LIMIT 1")
    fx_prev = _q("SELECT date, rate FROM eurusd_snapshots ORDER BY date DESC LIMIT 1 OFFSET 1")

    vix = _q("SELECT date, vix_close, vix_open, vix_high, vix_low FROM vix_snapshots ORDER BY date DESC LIMIT 1")
    vix_prev = _q("SELECT date, vix_close FROM vix_snapshots ORDER BY date DESC LIMIT 1 OFFSET 1")

    bdi = _q("SELECT date, bdi_close, bdi_open, bdi_high, bdi_low FROM freight_snapshots ORDER BY date DESC LIMIT 1")

    oil_7d = _qq("SELECT date, brent_price, wti_price FROM oil_price_snapshots ORDER BY date DESC LIMIT 7")
    ttf_7d = _qq("SELECT date, ttf_price FROM ttf_gas_snapshots ORDER BY date DESC LIMIT 7")

    lines = ["## ASSET & COMMODITY PRICES (use these EXACT numbers)"]

    if oil:
        brent_trend = ""
        if oil_prev:
            try:
                diff = float(oil['brent_price']) - float(oil_prev['brent_price'])
                brent_trend = f", day change: {diff:+.2f}"
            except: pass
        lines.append(f"- Brent Crude: ${oil['brent_price']} ({oil.get('brent_change_pct', 0):+.2f}%) | Date: {oil['date']}{brent_trend}")
        lines.append(f"- WTI Crude: ${oil['wti_price']} ({oil.get('wti_change_pct', 0):+.2f}%) | Brent-WTI Spread: ${oil.get('brent_wti_spread', 'N/A')}")
    else:
        lines.append("- Oil prices: data unavailable")

    if ttf:
        ttf_trend = ""
        if ttf_prev:
            try:
                diff = float(ttf['ttf_price']) - float(ttf_prev['ttf_price'])
                ttf_trend = f", day change: {diff:+.2f}"
            except: pass
        lines.append(f"- TTF Natural Gas: €{ttf['ttf_price']}/{ttf.get('unit', 'MWh')} | Date: {ttf['date']}{ttf_trend}")
    else:
        lines.append("- TTF Gas: data unavailable")

    if lng:
        lng_trend = ""
        if lng_prev:
            try:
                diff = float(lng['jkm_price']) - float(lng_prev['jkm_price'])
                lng_trend = f", day change: {diff:+.2f}"
            except: pass
        lines.append(f"- LNG JKM (Asia): ${lng['jkm_price']}/MMBtu ({lng.get('jkm_change_pct', 0):+.2f}%) | Date: {lng['date']}{lng_trend}")
    else:
        lines.append("- LNG: data unavailable")

    if fx:
        fx_trend = ""
        if fx_prev:
            try:
                diff = float(fx['rate']) - float(fx_prev['rate'])
                fx_trend = f", day change: {diff:+.6f}"
            except: pass
        lines.append(f"- EUR/USD: {fx['rate']} | Date: {fx['date']}{fx_trend}")
    else:
        lines.append("- EUR/USD: data unavailable")

    if vix:
        vix_trend = ""
        if vix_prev:
            try:
                diff = float(vix['vix_close']) - float(vix_prev['vix_close'])
                vix_trend = f", day change: {diff:+.2f}"
            except: pass
        lines.append(f"- VIX: {vix['vix_close']} (O: {vix['vix_open']}, H: {vix['vix_high']}, L: {vix['vix_low']}) | Date: {vix['date']}{vix_trend}")
    else:
        lines.append("- VIX: data unavailable")

    if bdi:
        lines.append(f"- Baltic Dry Index: {bdi['bdi_close']} (O: {bdi['bdi_open']}, H: {bdi['bdi_high']}, L: {bdi['bdi_low']}) | Date: {bdi['date']}")

    if oil_7d and len(oil_7d) > 1:
        vals = [f"{r['date']}: B${r['brent_price']}/W${r['wti_price']}" for r in oil_7d]
        lines.append(f"- Oil 7-day: {', '.join(vals)}")

    if ttf_7d and len(ttf_7d) > 1:
        vals = [f"{r['date']}: €{r['ttf_price']}" for r in ttf_7d]
        lines.append(f"- TTF 7-day: {', '.join(vals)}")

    return "\n".join(lines)


def _get_egsi_components() -> str:
    components = _qq("""
        SELECT component_key, raw_value, norm_value, weight, contribution
        FROM egsi_components_daily
        WHERE index_family = 'egsi_m' AND index_date = (SELECT MAX(index_date) FROM egsi_components_daily WHERE index_family = 'egsi_m')
        ORDER BY contribution DESC
    """)
    drivers = _qq("""
        SELECT driver_type, headline, severity, score, signal_key, signal_value, signal_unit
        FROM egsi_drivers_daily
        WHERE index_family = 'egsi_m' AND index_date = (SELECT MAX(index_date) FROM egsi_drivers_daily WHERE index_family = 'egsi_m')
        ORDER BY score DESC LIMIT 5
    """)
    signals = _qq("""
        SELECT signal_key, value, unit, source
        FROM egsi_signals_daily
        WHERE signal_date = (SELECT MAX(signal_date) FROM egsi_signals_daily)
        ORDER BY signal_key LIMIT 15
    """)

    lines = ["## EGSI Component Breakdown (latest)"]
    if components:
        lines.append("### EGSI-M Components:")
        for c in components:
            lines.append(f"  - {c['component_key']}: raw={c['raw_value']}, norm={c['norm_value']}, weight={c['weight']}, contribution={c['contribution']}")

    if drivers:
        lines.append("### Top EGSI-M Drivers:")
        for d in drivers:
            lines.append(f"  - [{d.get('severity', 'N/A')}] {d.get('headline', 'N/A')} (score: {d.get('score', 'N/A')})")
            if d.get('signal_key'):
                lines.append(f"    Signal: {d['signal_key']} = {d.get('signal_value', 'N/A')} {d.get('signal_unit', '')}")

    if signals:
        lines.append("### Latest EGSI Signals:")
        for s in signals:
            lines.append(f"  - {s['signal_key']}: {s['value']} {s.get('unit', '')} (src: {s.get('source', 'N/A')})")

    if not components and not drivers and not signals:
        return ""

    return "\n".join(lines)


def _get_delivery_metrics() -> str:
    total_deliveries = _q("SELECT COUNT(*) as cnt FROM user_alert_deliveries") or {}
    recent_deliveries = _q("SELECT COUNT(*) as cnt FROM user_alert_deliveries WHERE delivered_at > NOW() - INTERVAL '7 days'") or {}

    channel_dist = _qq("""
        SELECT channel, COUNT(*) as cnt FROM user_alert_deliveries
        WHERE delivered_at > NOW() - INTERVAL '7 days'
        GROUP BY channel ORDER BY cnt DESC
    """)

    prefs = _qq("""
        SELECT 
            SUM(CASE WHEN geri_email THEN 1 ELSE 0 END) as geri_email,
            SUM(CASE WHEN geri_telegram THEN 1 ELSE 0 END) as geri_tg,
            SUM(CASE WHEN eeri_email THEN 1 ELSE 0 END) as eeri_email,
            SUM(CASE WHEN eeri_telegram THEN 1 ELSE 0 END) as eeri_tg,
            SUM(CASE WHEN egsi_email THEN 1 ELSE 0 END) as egsi_email,
            SUM(CASE WHEN egsi_telegram THEN 1 ELSE 0 END) as egsi_tg,
            SUM(CASE WHEN digest_email THEN 1 ELSE 0 END) as digest_email,
            SUM(CASE WHEN digest_telegram THEN 1 ELSE 0 END) as digest_tg,
            COUNT(*) as total
        FROM user_delivery_preferences
    """)

    digests = _q("SELECT COUNT(*) as cnt FROM user_alert_digests WHERE created_at > NOW() - INTERVAL '7 days'") or {}

    lines = ["## Delivery & Engagement"]
    lines.append(f"- Total Deliveries (all time): {total_deliveries.get('cnt', 0)}")
    lines.append(f"- Deliveries (7 days): {recent_deliveries.get('cnt', 0)}")
    lines.append(f"- Digests Sent (7 days): {digests.get('cnt', 0)}")

    if channel_dist:
        for c in channel_dist:
            lines.append(f"- Channel '{c['channel']}' (7d): {c['cnt']}")

    if prefs and len(prefs) > 0:
        p = prefs[0]
        lines.append(f"### User Delivery Preferences ({p.get('total', 0)} users configured):")
        lines.append(f"  - GERI: {p.get('geri_email', 0)} email, {p.get('geri_tg', 0)} telegram")
        lines.append(f"  - EERI: {p.get('eeri_email', 0)} email, {p.get('eeri_tg', 0)} telegram")
        lines.append(f"  - EGSI: {p.get('egsi_email', 0)} email, {p.get('egsi_tg', 0)} telegram")
        lines.append(f"  - Digest: {p.get('digest_email', 0)} email, {p.get('digest_tg', 0)} telegram")

    return "\n".join(lines)


def _get_eriq_usage() -> str:
    total_convos = _q("SELECT COUNT(*) as cnt FROM eriq_conversations") or {}
    recent = _q("SELECT COUNT(*) as cnt FROM eriq_conversations WHERE created_at > NOW() - INTERVAL '7 days'") or {}
    avg_rating = _q("""
        SELECT ROUND(AVG(rating), 2) as avg_r, COUNT(rating) as rated 
        FROM eriq_conversations WHERE rating IS NOT NULL
    """) or {}
    tokens = _q("""
        SELECT SUM(tokens_used) as total_tokens FROM eriq_conversations
    """) or {}

    return f"""## ERIQ Bot Usage
- Total Conversations: {total_convos.get('cnt', 0)}
- Conversations (7 days): {recent.get('cnt', 0)}
- Average Rating: {avg_rating.get('avg_r', 'N/A')} (from {avg_rating.get('rated', 0)} rated)
- Total Tokens Used: {tokens.get('total_tokens', 0)}"""


def _get_elsa_usage() -> str:
    topics = _q("SELECT COUNT(*) as cnt FROM elsa_topics") or {}
    convos = _q("SELECT COUNT(*) as cnt FROM elsa_conversations") or {}
    recent = _q("SELECT COUNT(*) as cnt FROM elsa_conversations WHERE created_at > NOW() - INTERVAL '7 days'") or {}

    return f"""## ELSA Usage
- Total Topics: {topics.get('cnt', 0)}
- Total Conversations: {convos.get('cnt', 0)}
- Conversations (7 days): {recent.get('cnt', 0)}"""


def _get_alert_metrics() -> str:
    today_alerts = _q("SELECT COUNT(*) as cnt FROM alert_events WHERE created_at > NOW() - INTERVAL '24 hours'") or {}
    severity_dist = _qq("""
        SELECT severity, COUNT(*) as cnt FROM alert_events 
        WHERE created_at > NOW() - INTERVAL '7 days'
        GROUP BY severity ORDER BY cnt DESC
    """)
    category_dist = _qq("""
        SELECT category, COUNT(*) as cnt FROM alert_events
        WHERE created_at > NOW() - INTERVAL '7 days'
        GROUP BY category ORDER BY cnt DESC LIMIT 10
    """)
    region_dist = _qq("""
        SELECT region, COUNT(*) as cnt FROM alert_events
        WHERE created_at > NOW() - INTERVAL '7 days'
        GROUP BY region ORDER BY cnt DESC LIMIT 10
    """)

    lines = ["## Alert Metrics"]
    lines.append(f"- Alerts Today: {today_alerts.get('cnt', 0)}")

    if severity_dist:
        lines.append("### By Severity (7d):")
        for s in severity_dist:
            lines.append(f"  - {s['severity']}: {s['cnt']}")

    if category_dist:
        lines.append("### Top Categories (7d):")
        for c in category_dist:
            lines.append(f"  - {c.get('category', 'unknown')}: {c['cnt']}")

    if region_dist:
        lines.append("### Top Regions (7d):")
        for r in region_dist:
            lines.append(f"  - {r.get('region', 'unknown')}: {r['cnt']}")

    return "\n".join(lines)


def _get_engine_health() -> str:
    latest_runs = _qq("""
        SELECT phase, status, started_at, duration_ms, error_summary
        FROM alerts_engine_runs 
        ORDER BY started_at DESC LIMIT 5
    """)
    ingestion_runs = _qq("""
        SELECT started_at, status, total_fetched, total_new, total_errors
        FROM ingestion_runs ORDER BY started_at DESC LIMIT 3
    """)

    lines = ["## Engine Health"]

    if latest_runs:
        lines.append("### Recent Engine Runs:")
        for r in latest_runs:
            err = f" | Error: {r['error_summary']}" if r.get('error_summary') else ""
            dur = f" | {r.get('duration_ms', '?')}ms" if r.get('duration_ms') else ""
            lines.append(f"  - [{r.get('status', '?')}] {r.get('phase', '?')} at {r.get('started_at', '?')}{dur}{err}")

    if ingestion_runs:
        lines.append("### Recent Ingestion Runs:")
        for r in ingestion_runs:
            lines.append(f"  - [{r.get('status', '?')}] {r.get('started_at', '?')} | fetched: {r.get('total_fetched', 0)}, new: {r.get('total_new', 0)}, errors: {r.get('total_errors', 0)}")

    if not latest_runs and not ingestion_runs:
        lines.append("- No engine run data available")

    return "\n".join(lines)


def _get_ticket_metrics() -> str:
    total = _q("SELECT COUNT(*) as cnt FROM tickets") or {}
    open_tickets = _q("SELECT COUNT(*) as cnt FROM tickets WHERE status = 'open'") or {}
    in_progress = _q("SELECT COUNT(*) as cnt FROM tickets WHERE status = 'in_progress'") or {}
    closed = _q("SELECT COUNT(*) as cnt FROM tickets WHERE status = 'closed'") or {}
    archived = _q("SELECT COUNT(*) as cnt FROM tickets WHERE status = 'archived'") or {}

    cat_dist = _qq("""
        SELECT category, COUNT(*) as cnt FROM tickets
        GROUP BY category ORDER BY cnt DESC
    """)

    recent = _qq("""
        SELECT subject, category, status, created_at
        FROM tickets ORDER BY created_at DESC LIMIT 5
    """)

    lines = ["## Support Tickets"]
    lines.append(f"- Total: {total.get('cnt', 0)} | Open: {open_tickets.get('cnt', 0)} | In Progress: {in_progress.get('cnt', 0)} | Closed: {closed.get('cnt', 0)} | Archived: {archived.get('cnt', 0)}")

    if cat_dist:
        lines.append("### By Category:")
        for c in cat_dist:
            lines.append(f"  - {c.get('category', 'unknown')}: {c['cnt']}")

    if recent:
        lines.append("### Recent Tickets:")
        for t in recent:
            lines.append(f"  - [{t.get('status', '?')}] {t.get('subject', '?')} ({t.get('category', '?')}) - {t.get('created_at', '?')}")

    return "\n".join(lines)


def _get_seo_metrics() -> str:
    daily_pages = _q("SELECT COUNT(*) as cnt FROM seo_daily_pages") or {}
    regional_pages = _q("SELECT COUNT(*) as cnt FROM seo_regional_daily_pages") or {}
    page_views = _q("SELECT COUNT(*) as cnt FROM seo_page_views") or {}
    recent_views = _q("SELECT COUNT(*) as cnt FROM seo_page_views WHERE viewed_at > NOW() - INTERVAL '7 days'") or {}

    lines = ["## SEO Metrics"]
    lines.append(f"- Daily Alert Pages: {daily_pages.get('cnt', 0)}")
    lines.append(f"- Regional Daily Pages: {regional_pages.get('cnt', 0)}")
    lines.append(f"- Total Page Views: {page_views.get('cnt', 0)} (7d: {recent_views.get('cnt', 0)})")

    return "\n".join(lines)


def get_past_elsa_conversations(topic_id: int = None, limit: int = 10) -> str:
    parts = []

    if topic_id:
        current_rows = execute_query("""
            SELECT question, response, created_at FROM elsa_conversations
            WHERE topic_id = %s ORDER BY created_at DESC LIMIT %s
        """, (topic_id, limit)) or []

        if current_rows:
            parts.append("=== CURRENT TOPIC CONVERSATION HISTORY ===")
            for r in reversed(current_rows):
                parts.append(f"[{r['created_at']}] Q: {r['question']}")
                resp = r['response'] or ""
                if len(resp) > 500:
                    resp = resp[:500] + "..."
                parts.append(f"A: {resp}")

    cross_topic_rows = execute_query("""
        SELECT c.question, c.response, c.created_at, t.title as topic_title
        FROM elsa_conversations c
        JOIN elsa_topics t ON c.topic_id = t.id
        WHERE (%s IS NULL OR c.topic_id != %s)
        ORDER BY c.created_at DESC
        LIMIT 20
    """, (topic_id, topic_id)) or []

    if cross_topic_rows:
        parts.append("\n=== ELSA CROSS-TOPIC MEMORY (Insights from all past discussions) ===")
        parts.append("Use these past insights to maintain continuity across topics and build on previous recommendations.")
        seen_topics = set()
        for r in cross_topic_rows:
            topic_title = r.get('topic_title', 'Unknown')
            if topic_title not in seen_topics:
                seen_topics.add(topic_title)
                parts.append(f"\n--- Topic: {topic_title} ---")
            parts.append(f"[{r['created_at']}] Q: {r['question']}")
            resp = r['response'] or ""
            if len(resp) > 400:
                resp = resp[:400] + "..."
            parts.append(f"A: {resp}")

    if not parts:
        return ""

    return "\n".join(parts)
