"""Fresh policy checks. Never authorize a send from the fanout snapshot."""
from datetime import datetime, timezone

from src.db.db import get_cursor
from src.alerts.quota_helpers import _parse_delivery_config_to_quotas
from src.plans.plan_helpers import ALL_ALERT_TYPES


def current_send_permission(user_id, channel, event_ids, kind="instant", claim_id=None):
    """Return current recipient + skip reason, with quota claims read atomically.

    Existing queued/sending rows are the reservations, not a new counter table.
    Digest *items* are not messages: aggregate quotas apply to digest claims.
    """
    with get_cursor() as c:
        day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        key = f"alerts-quota:{user_id}:{channel}:{kind}:{day.date()}"
        c.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (key,))
        c.execute("""
            SELECT u.id,u.email,u.telegram_chat_id,u.phone_number,u.email_verified,
                   COALESCE(up.plan,'free') plan FROM users u
            LEFT JOIN user_plans up ON up.user_id=u.id WHERE u.id=%s
        """, (user_id,))
        user = c.fetchone()
        if not user or user["email_verified"] is False:
            return None, "user_not_eligible"
        c.execute("SELECT * FROM plan_settings WHERE plan_code=%s", (user["plan"] or "free",))
        settings = c.fetchone()
        if not settings or not settings["is_active"]:
            return None, "channel_not_allowed"
        allowed = settings["allowed_alert_types"]
        if "ALL" in allowed:
            allowed = ALL_ALERT_TYPES
        c.execute("SELECT * FROM user_alert_prefs WHERE user_id=%s", (user_id,))
        prefs = c.fetchall()
        enabled = [p for p in prefs if p["enabled"]]
        regions = {p["region"] for p in enabled if p.get("region")} or {"Europe"}
        types = {p["alert_type"] for p in enabled if p.get("alert_type")} or {"HIGH_IMPACT_EVENT"}
        assets = {p["asset"] for p in enabled if p.get("asset")} or {"oil", "gas"}
        c.execute("SELECT id,alert_type,scope_region,scope_assets FROM alert_events WHERE id=ANY(%s)",
                  (list(event_ids),))
        events = c.fetchall()
        if len(events) != len(set(event_ids)) or not events:
            return None, "event_unavailable"
        for event in events:
            if event["alert_type"] not in allowed:
                return None, "channel_not_allowed"
            # Explicit disabled matching preference is an opt-out, not a default.
            if any(not p["enabled"] and p["alert_type"] == event["alert_type"]
                   and (not p.get("region") or p["region"] == event["scope_region"])
                   and (event["alert_type"] != "ASSET_RISK_SPIKE" or not p.get("asset")
                        or p["asset"] in (event["scope_assets"] or []))
                   for p in prefs):
                return None, "channel_disabled_by_user"
            if (event["alert_type"] not in types or
                    (event["scope_region"] and event["scope_region"] not in regions and "global" not in regions)
                    or (event["alert_type"] == "ASSET_RISK_SPIKE" and event["scope_assets"]
                        and not assets.intersection(event["scope_assets"]))):
                return None, "channel_disabled_by_user"
        config = settings.get("delivery_config") or {}
        channel_config = config.get(channel, {})
        if isinstance(channel_config, dict) and channel_config.get("enabled") is False:
            return None, "channel_disabled_by_user"
        destination = {"email": "email", "telegram": "telegram_chat_id", "sms": "phone_number"}.get(channel)
        if not destination or not user.get(destination):
            return None, "missing_destination"
        quotas = _parse_delivery_config_to_quotas(settings)
        if channel == "sms" and not quotas["sms_enabled"]:
            return None, "sms_not_in_plan"
        limit = quotas.get(f"instant_{channel}_per_day", 0) if kind == "instant" else quotas.get("digest_per_day", 0)
        if kind == "instant" and quotas.get("digest_only"):
            return None, "plan_digest_only"
        if limit <= 0:
            return None, "channel_not_allowed"
        if kind == "instant" and claim_id is not None:
            c.execute("""
                SELECT count(*) n FROM user_alert_deliveries WHERE user_id=%s
                AND channel=%s AND delivery_kind='instant'
                AND ((status='sent' AND sent_at >= %s)
                     OR (status='sending' AND id <= %s))
            """, (user_id, channel, day, claim_id))
        elif kind == "instant":
            c.execute("""
                SELECT count(*) n FROM user_alert_deliveries WHERE user_id=%s
                AND channel=%s AND delivery_kind='instant'
                AND status IN ('queued','sending','sent') AND created_at >= %s
            """, (user_id, channel, day))
        else:
            # Claims are acquired by FOR UPDATE/SKIP LOCKED before this check.
            # Earlier claim IDs reserve capacity; later claims cannot oversend.
            c.execute("""
                SELECT count(*) n FROM user_alert_digests WHERE user_id=%s AND channel=%s
                AND ((status='sent' AND sent_at >= %s)
                     OR (status='sending' AND id <= %s))
            """, (user_id, channel, day, claim_id))
        if c.fetchone()["n"] > limit:
            return None, "quota_exceeded"
        return dict(user), None
