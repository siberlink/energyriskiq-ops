"""Shared queue and conservative retry evidence; SELECT-only operational policy."""

FRESH_QUEUE_SQL = """SELECT count(*) AS fresh_queue FROM events
    WHERE NOT processed AND ai_attempts<3
    AND inserted_at >= (SELECT activated_at FROM risk_pipeline_v2_control WHERE singleton)"""

RECOVERED_ERROR_SQL = """(
    u.purpose='enrichment' AND EXISTS (
        SELECT 1 FROM risk_pipeline_v2_usage s
        JOIN events e ON e.id=u.item_id
        JOIN job_runs r ON r.job_name='shadow_enrichment_delivery'
        WHERE s.item_id=u.item_id AND s.purpose=u.purpose AND s.status='completed'
          AND s.requested_at>u.requested_at AND s.finished_at IS NOT NULL
          AND r.finished_at IS NOT NULL AND r.status IN ('success','error')
          AND u.requested_at>=r.started_at AND u.finished_at<=r.finished_at
          AND s.requested_at>=r.started_at AND s.finished_at<=r.finished_at
          AND e.processed AND e.ai_processed_at IS NOT NULL
          AND (e.ai_processed_at AT TIME ZONE 'UTC')>=s.requested_at
          AND (e.ai_processed_at AT TIME ZONE 'UTC')<=r.finished_at
    ))"""


def spend_sql():
    """Count only proven same-run enrichment recoveries as non-blocking.

    Keep the original error ledger and charge. Different-run recovery, missing
    evidence, other purposes and unresolved attempts remain blocking.
    """
    return f"""SELECT u.budget_date AS day,
        sum(u.charged_usd+CASE WHEN u.status='reserved' THEN u.reserved_usd ELSE 0 END) AS committed_usd,
        count(*) FILTER(WHERE u.status='error' AND NOT {RECOVERED_ERROR_SQL}) AS failures,
        count(*) FILTER(WHERE u.status='error' AND {RECOVERED_ERROR_SQL}) AS recovered_errors,
        count(*) FILTER(WHERE u.status='reserved' AND u.requested_at<NOW()-interval '1 hour') AS stale_reservations
        FROM risk_pipeline_v2_usage u WHERE u.budget_date>=%s AND u.budget_date<=%s
        GROUP BY 1 ORDER BY 1"""
