"""Explicit additive installation. Never run migrations as a read-side effect."""
from src.db.db import get_cursor

LEGACY_TABLES = ("risk_events", "risk_indices", "asset_risk")


def install():
    with get_cursor() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS risk_pipeline_v2_control (
                singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
                mode text NOT NULL CHECK(mode IN ('off','shadow','live')),
                activated_at timestamptz NOT NULL DEFAULT now(),
                start_date date NOT NULL,
                runner text NOT NULL,
                calibration jsonb NOT NULL,
                code_sha text NOT NULL
            );
            CREATE TABLE IF NOT EXISTS risk_pipeline_v2_usage (
                id bigserial PRIMARY KEY, requested_at timestamptz NOT NULL DEFAULT now(),
                budget_date date NOT NULL, purpose text NOT NULL, item_id bigint,
                model text NOT NULL, status text NOT NULL,
                reserved_usd numeric NOT NULL, charged_usd numeric NOT NULL DEFAULT 0,
                usage jsonb, raw_output text, error text,
                finished_at timestamptz
            );
            CREATE INDEX IF NOT EXISTS risk_pipeline_v2_usage_day
                ON risk_pipeline_v2_usage(budget_date);
            CREATE TABLE IF NOT EXISTS risk_pipeline_v2_labels (
                cache_key text PRIMARY KEY, alert_id bigint NOT NULL,
                labels jsonb NOT NULL, model text NOT NULL,
                provenance jsonb NOT NULL, computed_at timestamptz NOT NULL DEFAULT now()
            );
            CREATE TABLE IF NOT EXISTS geri_shadow_daily (
                index_date date NOT NULL, variant text NOT NULL, value integer NOT NULL,
                components jsonb NOT NULL, inputs jsonb NOT NULL,
                computed_at timestamptz NOT NULL DEFAULT now(), code_sha text NOT NULL,
                PRIMARY KEY(index_date,variant)
            );
            CREATE TABLE IF NOT EXISTS risk_pipeline_v2_monitor (
                observed_at timestamptz PRIMARY KEY DEFAULT now(),
                checkpoint text NOT NULL, payload jsonb NOT NULL
            );
            ALTER TABLE risk_pipeline_v2_control
                ADD COLUMN IF NOT EXISTS catchup_active boolean NOT NULL DEFAULT true;
            ALTER TABLE risk_pipeline_v2_control
                ADD COLUMN IF NOT EXISTS catchup_max_event_id bigint;
            ALTER TABLE risk_pipeline_v2_control
                ADD COLUMN IF NOT EXISTS catchup_floor timestamp;
        """)
        for table in LEGACY_TABLES:
            # Do NOT copy serial defaults: shadow ids must never use legacy sequences.
            c.execute(f"""CREATE TABLE IF NOT EXISTS {table}_v2
                (LIKE {table} INCLUDING CONSTRAINTS,
                 pipeline_version text NOT NULL DEFAULT 'v2',
                 mode text NOT NULL DEFAULT 'shadow' CHECK(mode='shadow'));
                CREATE SEQUENCE IF NOT EXISTS {table}_v2_id_seq OWNED BY {table}_v2.id;
                ALTER TABLE {table}_v2 ALTER COLUMN id SET DEFAULT nextval('{table}_v2_id_seq');
                CREATE UNIQUE INDEX IF NOT EXISTS {table}_v2_pk ON {table}_v2(id);
            """)
            timestamp = "created_at" if table == "risk_events" else "calculated_at"
            c.execute(f"ALTER TABLE {table}_v2 ALTER COLUMN {timestamp} SET DEFAULT (now() AT TIME ZONE 'UTC')")
        c.execute("""CREATE UNIQUE INDEX IF NOT EXISTS risk_events_v2_event
            ON risk_events_v2(event_id);
            CREATE INDEX IF NOT EXISTS risk_indices_v2_dates
                ON risk_indices_v2(calculated_at);
            CREATE INDEX IF NOT EXISTS asset_risk_v2_dates
                ON asset_risk_v2(calculated_at)""")
        # Last-line protection for old deployed processes that do not know shadow
        # mode yet. Raise explicitly; never silently pretend a legacy write worked.
        c.execute("""
            CREATE OR REPLACE FUNCTION protect_legacy_risk_in_shadow()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF EXISTS(SELECT 1 FROM risk_pipeline_v2_control WHERE mode='shadow') THEN
                    RAISE EXCEPTION 'Legacy risk writes blocked: V2 is shadow-only';
                END IF;
                RETURN NULL;
            END $$;
        """)
        for table in LEGACY_TABLES:
            c.execute(f"""DROP TRIGGER IF EXISTS risk_v2_shadow_guard ON {table};
                CREATE TRIGGER risk_v2_shadow_guard
                BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE ON {table}
                FOR EACH STATEMENT EXECUTE FUNCTION protect_legacy_risk_in_shadow()""")
        c.execute("""
            CREATE OR REPLACE FUNCTION protect_out_of_scope_enrichment()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF EXISTS(SELECT 1 FROM risk_pipeline_v2_control WHERE mode='shadow')
                   AND NOT OLD.processed
                   AND (OLD.ai_attempts>=3 OR OLD.inserted_at < (now() AT TIME ZONE 'UTC')-interval '7 days')
                   AND (NEW.processed IS DISTINCT FROM OLD.processed
                        OR NEW.ai_attempts IS DISTINCT FROM OLD.ai_attempts) THEN
                    RAISE EXCEPTION 'Enrichment outside approved seven-day retryable scope blocked';
                END IF;
                RETURN NEW;
            END $$;
            DROP TRIGGER IF EXISTS risk_v2_enrichment_scope_guard ON events;
            CREATE TRIGGER risk_v2_enrichment_scope_guard BEFORE UPDATE ON events
                FOR EACH ROW EXECUTE FUNCTION protect_out_of_scope_enrichment();
        """)
