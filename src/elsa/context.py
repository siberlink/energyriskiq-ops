import logging
from datetime import datetime, timedelta
from src.db.db import execute_query, execute_one

logger = logging.getLogger(__name__)


def build_elsa_context(question: str) -> str:
    parts = ["=== ELSA BUSINESS & MARKETING CONTEXT (Live Production Data) ==="]
    parts.append(f"Timestamp: {datetime.utcnow().isoformat()}Z")

    try:
        parts.append(_get_user_metrics())
    except Exception as e:
        logger.error(f"ELSA user metrics failed: {e}")

    try:
        parts.append(_get_plan_distribution())
    except Exception as e:
        logger.error(f"ELSA plan distribution failed: {e}")

    try:
        parts.append(_get_revenue_metrics())
    except Exception as e:
        logger.error(f"ELSA revenue metrics failed: {e}")

    try:
        parts.append(_get_content_metrics())
    except Exception as e:
        logger.error(f"ELSA content metrics failed: {e}")

    try:
        parts.append(_get_index_summary())
    except Exception as e:
        logger.error(f"ELSA index summary failed: {e}")

    try:
        parts.append(_get_eriq_usage())
    except Exception as e:
        logger.error(f"ELSA ERIQ usage failed: {e}")

    try:
        parts.append(_get_alert_metrics())
    except Exception as e:
        logger.error(f"ELSA alert metrics failed: {e}")

    try:
        parts.append(_get_seo_metrics())
    except Exception as e:
        logger.error(f"ELSA SEO metrics failed: {e}")

    return "\n\n".join([p for p in parts if p])


def _get_user_metrics() -> str:
    total = execute_one("SELECT COUNT(*) as cnt FROM users") or {}
    verified = execute_one("SELECT COUNT(*) as cnt FROM users WHERE verified = true") or {}
    recent_7d = execute_one("SELECT COUNT(*) as cnt FROM users WHERE created_at > NOW() - INTERVAL '7 days'") or {}
    recent_30d = execute_one("SELECT COUNT(*) as cnt FROM users WHERE created_at > NOW() - INTERVAL '30 days'") or {}

    return f"""## User Metrics
- Total Users: {total.get('cnt', 0)}
- Verified Users: {verified.get('cnt', 0)}
- New Users (7 days): {recent_7d.get('cnt', 0)}
- New Users (30 days): {recent_30d.get('cnt', 0)}"""


def _get_plan_distribution() -> str:
    rows = execute_query("""
        SELECT COALESCE(plan, 'free') as plan, COUNT(*) as cnt 
        FROM users GROUP BY COALESCE(plan, 'free') ORDER BY cnt DESC
    """) or []
    lines = ["## Plan Distribution"]
    for r in rows:
        lines.append(f"- {r['plan']}: {r['cnt']} users")
    return "\n".join(lines)


def _get_revenue_metrics() -> str:
    active_subs = execute_one("""
        SELECT COUNT(*) as cnt FROM users 
        WHERE stripe_subscription_id IS NOT NULL AND plan != 'free' AND plan IS NOT NULL
    """) or {}

    plan_prices = execute_query("""
        SELECT plan_code, price, currency FROM plan_settings WHERE price > 0 ORDER BY price
    """) or []

    lines = [f"## Revenue Metrics", f"- Active Paid Subscriptions: {active_subs.get('cnt', 0)}"]
    for p in plan_prices:
        lines.append(f"- {p['plan_code']}: {p.get('currency', 'EUR')} {p['price']}/mo")
    return "\n".join(lines)


def _get_content_metrics() -> str:
    events = execute_one("SELECT COUNT(*) as cnt FROM events") or {}
    alerts = execute_one("SELECT COUNT(*) as cnt FROM alert_events") or {}
    daily_pages = execute_one("SELECT COUNT(*) as cnt FROM seo_daily_pages") or {}
    digests = execute_one("""
        SELECT COUNT(DISTINCT DATE(created_at)) as cnt FROM daily_digest_results
    """) or {}

    return f"""## Content Metrics
- Total Events Ingested: {events.get('cnt', 0)}
- Total Alert Events: {alerts.get('cnt', 0)}
- SEO Daily Pages: {daily_pages.get('cnt', 0)}
- Daily Digests Generated: {digests.get('cnt', 0)}"""


def _get_index_summary() -> str:
    geri = execute_one("""
        SELECT score, band, created_at FROM geri_snapshots ORDER BY created_at DESC LIMIT 1
    """)
    eeri = execute_one("""
        SELECT score, band, snapshot_date FROM eeri_snapshots ORDER BY snapshot_date DESC LIMIT 1
    """)

    lines = ["## Latest Index Values"]
    if geri:
        lines.append(f"- GERI: {geri.get('score', 'N/A')} ({geri.get('band', 'N/A')})")
    if eeri:
        lines.append(f"- EERI: {eeri.get('score', 'N/A')} ({eeri.get('band', 'N/A')})")
    return "\n".join(lines) if len(lines) > 1 else ""


def _get_eriq_usage() -> str:
    total_convos = execute_one("SELECT COUNT(*) as cnt FROM eriq_conversations") or {}
    recent = execute_one("""
        SELECT COUNT(*) as cnt FROM eriq_conversations 
        WHERE created_at > NOW() - INTERVAL '7 days'
    """) or {}
    avg_rating = execute_one("""
        SELECT ROUND(AVG(rating), 2) as avg_r, COUNT(rating) as rated 
        FROM eriq_conversations WHERE rating IS NOT NULL
    """) or {}

    return f"""## ERIQ Bot Usage
- Total Conversations: {total_convos.get('cnt', 0)}
- Conversations (7 days): {recent.get('cnt', 0)}
- Average Rating: {avg_rating.get('avg_r', 'N/A')} (from {avg_rating.get('rated', 0)} rated)"""


def _get_alert_metrics() -> str:
    today_alerts = execute_one("""
        SELECT COUNT(*) as cnt FROM alert_events 
        WHERE created_at > NOW() - INTERVAL '24 hours'
    """) or {}
    severity_dist = execute_query("""
        SELECT severity, COUNT(*) as cnt FROM alert_events 
        WHERE created_at > NOW() - INTERVAL '7 days'
        GROUP BY severity ORDER BY cnt DESC
    """) or []

    lines = [f"## Alert Metrics (7 days)"]
    lines.append(f"- Alerts Today: {today_alerts.get('cnt', 0)}")
    for s in severity_dist:
        lines.append(f"- {s['severity']}: {s['cnt']}")
    return "\n".join(lines)


def _get_seo_metrics() -> str:
    try:
        from src.seo.seo_generator import generate_sitemap_entries
        entries = generate_sitemap_entries()
        return f"""## SEO Metrics
- Total Sitemap Pages: {len(entries)}"""
    except Exception:
        return ""


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
