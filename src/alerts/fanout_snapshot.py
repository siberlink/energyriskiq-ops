"""Bulk fanout reads and durable quota/uniqueness checks on one connection."""
from collections import defaultdict
from datetime import datetime, timezone
import time

from psycopg2.extras import RealDictCursor

from src.alerts.fanout_context import current
from src.db.db import get_connection

FANOUT_BUDGET_SECONDS = 20 * 60


class FanoutSnapshot:
    def __enter__(self):
        self.started = time.monotonic()
        self.queries = 0
        self.last_reason = None
        self.connection = get_connection()
        self.conn = self.connection.__enter__()
        self.cursor = self.conn.cursor(cursor_factory=RealDictCursor)
        try:
            self.run("SET statement_timeout='5s'", fetch=False)
            self.run("SET lock_timeout='1s'", fetch=False)
            from src.alerts import alerts_engine_v2 as engine
            self.events = self.run("""
                SELECT id,alert_type,scope_region,scope_assets,severity,headline,body,created_at
                FROM alert_events WHERE created_at >= NOW()-INTERVAL '24 hours'
                AND fanout_completed_at IS NULL ORDER BY created_at ASC
            """)
            self.users = self.run("""
                SELECT u.id,u.email,u.telegram_chat_id,u.phone_number,
                       COALESCE(up.plan,'free') AS plan
                FROM users u LEFT JOIN user_plans up ON up.user_id=u.id
                WHERE u.email_verified=TRUE OR u.email_verified IS NULL
            """) if self.events else []
            allowlist = engine.get_allowlisted_user_ids()
            if allowlist:
                self.users = [u for u in self.users if u["id"] in allowlist]
            ids = [u["id"] for u in self.users]
            self.plans = {r["plan_code"]: r for r in self.run("SELECT * FROM plan_settings")} if ids else {}
            self.prefs = defaultdict(list)
            for r in self.run("SELECT * FROM user_alert_prefs WHERE user_id=ANY(%s)", (ids,)) if ids else []:
                if r["enabled"]:
                    self.prefs[r["user_id"]].append(r)
            self.counts = defaultdict(int)
            self.count_day = self.start_of_day().date()
            for r in self.run("""
                SELECT user_id,channel,delivery_kind,count(*) n FROM user_alert_deliveries
                WHERE user_id=ANY(%s) AND created_at >= %s
                AND status IN ('queued','sending','sent')
                GROUP BY user_id,channel,delivery_kind
            """, (ids, self.start_of_day())) if ids else []:
                self.counts[(r["user_id"], r["channel"], r["delivery_kind"])] = r["n"]
            event_ids = [e["id"] for e in self.events]
            self.existing = {(r["user_id"], r["alert_event_id"], r["channel"])
                             for r in self.run("""
                SELECT user_id,alert_event_id,channel FROM user_alert_deliveries
                WHERE user_id=ANY(%s) AND alert_event_id=ANY(%s)
            """, (ids, event_ids))} if ids else set()
            self.conn.commit()
            self.token = current.set(self)
            return self
        except BaseException:
            self.cursor.close()
            self.connection.__exit__(*__import__("sys").exc_info())
            raise

    def __exit__(self, *error):
        current.reset(self.token)
        self.cursor.close()
        self.connection.__exit__(*error)

    @staticmethod
    def start_of_day():
        return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    def run(self, sql, params=(), fetch=True):
        self.queries += 1
        self.cursor.execute(sql, params)
        return self.cursor.fetchall() if fetch and self.cursor.description else []

    def expired(self):
        return time.monotonic() - self.started >= FANOUT_BUDGET_SECONDS

    def settings(self, plan):
        if plan not in self.plans:
            raise ValueError("Unknown plan")
        return self.plans[plan]

    def values(self, uid, name, default):
        values = list(dict.fromkeys(r[name] for r in self.prefs[uid] if r.get(name)))
        return values or default

    def aggregate_preferences(self, uid):
        rows = self.prefs[uid]
        if not rows:
            return None
        cooldowns = [r["cooldown_minutes"] for r in rows if r.get("cooldown_minutes")]
        return {"alert_types": self.values(uid, "alert_type", []),
                "regions": self.values(uid, "region", []),
                "cooldown_minutes": min(cooldowns) if cooldowns else 60,
                "email_enabled": True, "telegram_enabled": True, "sms_enabled": True}

    def count(self, uid, channel, kind):
        if self.start_of_day().date() != self.count_day:
            self.counts.clear()
            self.count_day = self.start_of_day().date()
            for r in self.run("""
                SELECT user_id,channel,delivery_kind,count(*) n FROM user_alert_deliveries
                WHERE user_id=ANY(%s) AND created_at >= %s
                AND status IN ('queued','sending','sent')
                GROUP BY user_id,channel,delivery_kind
            """, ([u["id"] for u in self.users], self.start_of_day())):
                self.counts[(r["user_id"], r["channel"], r["delivery_kind"])] = r["n"]
            self.conn.commit()
        return self.counts[(uid, channel, kind)]

    def insert(self, uid, event_id, channel, status, reason, kind):
        """One short transaction; no provider I/O or locks across users."""
        from src.alerts.quota_helpers import get_plan_quotas
        self.last_reason = None
        user = next(u for u in self.users if u["id"] == uid)
        plan = (user["plan"] or "free").lower().strip()
        if plan not in {"free", "personal", "trader", "pro", "enterprise"}:
            plan = "free"
        try:
            if channel != "account":
                # Digest item fanout is not an aggregate-digest quota unit. Its
                # legacy sentinel counter remains compatible; aggregate claims
                # are checked atomically again at send time.
                quota_channel = channel if kind == "instant" else "digest"
                lock = f"alerts-quota:{uid}:{quota_channel}:{kind}:{self.start_of_day().date()}"
                self.run("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (lock,))
                rows = self.run("""
                    SELECT count(*) n FROM user_alert_deliveries WHERE user_id=%s
                    AND channel=%s AND delivery_kind=%s
                    AND status IN ('queued','sending','sent') AND created_at >= %s
                """, (uid, quota_channel, kind, self.start_of_day()))
                n = rows[0]["n"]
                self.counts[(uid, quota_channel, kind)] = n
                quotas = get_plan_quotas(plan)
                limit = quotas.get(f"instant_{channel}_per_day", 0) if kind == "instant" else quotas.get("digest_per_day", 0)
                if n >= limit:
                    self.last_reason = "quota_exceeded"
                    self.conn.commit()
                    return None
            rows = self.run("""
                INSERT INTO user_alert_deliveries
                    (user_id,alert_event_id,channel,status,reason,delivery_kind)
                VALUES(%s,%s,%s,%s,%s,%s)
                ON CONFLICT(alert_event_id,user_id,channel,delivery_kind) DO NOTHING
                RETURNING id
            """, (uid, event_id, channel, status, reason, kind))
            self.conn.commit()
            if rows:
                self.existing.add((uid, event_id, channel))
                self.counts[(uid, channel, kind)] += 1
                return rows[0]["id"]
            self.last_reason = "already_exists"
            return None
        except BaseException:
            self.conn.rollback()
            raise

    def mark_completed(self, event_id):
        self.run("UPDATE alert_events SET fanout_completed_at=NOW() WHERE id=%s",
                 (event_id,), fetch=False)
        self.conn.commit()
