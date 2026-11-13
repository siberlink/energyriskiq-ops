-- Source-only migration: apply only during the separately approved rollout.
-- This is separate from the existing date-level delivery/idempotency ledger.
CREATE TABLE IF NOT EXISTS index_digest_attempts (
    id BIGSERIAL PRIMARY KEY,
    attempt_id UUID NOT NULL,
    user_id BIGINT,
    channel TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (
        outcome IN ('started','rendered','completed','sent','pending','skipped','failed')
    ),
    target_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    metadata JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS index_digest_attempts_target_date
    ON index_digest_attempts (target_date, created_at);
CREATE OR REPLACE FUNCTION prevent_index_digest_attempt_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'index_digest_attempts is append-only';
END;
$$;
DROP TRIGGER IF EXISTS index_digest_attempts_append_only ON index_digest_attempts;
CREATE TRIGGER index_digest_attempts_append_only
    BEFORE UPDATE OR DELETE OR TRUNCATE ON index_digest_attempts
    FOR EACH STATEMENT EXECUTE FUNCTION prevent_index_digest_attempt_mutation();
