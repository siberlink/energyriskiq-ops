"""
Engine Observability Module for Alerts v2

Provides run tracking, health metrics, and observability for the alerts engine.
Designed to be failure-tolerant - logging failures should never break engine runs.
"""

import os
import json
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from contextlib import contextmanager

from src.db.db import get_cursor

logger = logging.getLogger(__name__)


def get_triggered_by() -> str:
    """Determine how the run was triggered based on environment."""
    if os.environ.get("GITHUB_ACTIONS") == "true":
        event_name = os.environ.get("GITHUB_EVENT_NAME", "")
        if event_name == "schedule":
            return "github_actions_schedule"
        return "github_actions_manual"
    return "local"


def get_git_sha() -> Optional[str]:
    """Get git SHA from environment if available."""
    return os.environ.get("GITHUB_SHA")


def generate_run_id() -> str:
    """Generate a unique run ID."""
    return str(uuid.uuid4())


def truncate_error(error: Optional[str], max_len: int = 2000) -> Optional[str]:
    """Truncate error message to max length."""
    if not error:
        return None
    if len(error) <= max_len:
        return error
    return error[:max_len - 3] + "..."


class EngineRunTracker:
    """
    Context manager for tracking engine run execution.
    Failures in tracking should not affect the engine run itself.
    """
    
    def __init__(self, phase: str, dry_run: bool = False):
        self.run_id = generate_run_id()
        self.phase = phase
        self.dry_run = dry_run
        self.triggered_by = get_triggered_by()
        self.git_sha = get_git_sha()
        self.started_at = datetime.now(timezone.utc)
        self.phase_items: List[Dict[str, Any]] = []
        self._db_initialized = False
    
    def start(self) -> str:
        """Create initial run record with status='running'."""
        try:
            with get_cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO alerts_engine_runs (
                        run_id, triggered_by, phase, started_at, status, git_sha
                    ) VALUES (%s, %s, %s, %s, 'running', %s)
                    """,
                    (self.run_id, self.triggered_by, self.phase, self.started_at, self.git_sha)
                )
            self._db_initialized = True
            logger.info(f"Engine run started: {self.run_id} (phase={self.phase}, triggered_by={self.triggered_by})")
        except Exception as e:
            logger.warning(f"Failed to create run record (continuing anyway): {e}")
        return self.run_id
    
    def record_phase_start(self, phase: str) -> Dict[str, Any]:
        """Record when a phase starts execution."""
        phase_item = {
            "phase": phase,
            "started_at": datetime.now(timezone.utc),
            "finished_at": None,
            "duration_ms": None,
            "status": "running",
            "counts": None,
            "error_summary": None
        }
        self.phase_items.append(phase_item)
        return phase_item
    
    def record_phase_end(self, phase_item: Dict[str, Any], status: str, counts: Optional[Dict] = None, error: Optional[str] = None):
        """Record when a phase ends execution."""
        phase_item["finished_at"] = datetime.now(timezone.utc)
        phase_item["duration_ms"] = int((phase_item["finished_at"] - phase_item["started_at"]).total_seconds() * 1000)
        phase_item["status"] = status
        phase_item["counts"] = counts
        phase_item["error_summary"] = truncate_error(error)
        
        try:
            if self._db_initialized:
                with get_cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO alerts_engine_run_items (
                            run_id, phase, started_at, finished_at, duration_ms, status, counts, error_summary
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            self.run_id,
                            phase_item["phase"],
                            phase_item["started_at"],
                            phase_item["finished_at"],
                            phase_item["duration_ms"],
                            phase_item["status"],
                            json.dumps(counts) if counts else None,
                            phase_item["error_summary"]
                        )
                    )
        except Exception as e:
            logger.warning(f"Failed to record phase item (continuing anyway): {e}")
    
    def finish(self, status: str, counts: Optional[Dict] = None, error: Optional[str] = None):
        """Finalize the run record."""
        finished_at = datetime.now(timezone.utc)
        duration_ms = int((finished_at - self.started_at).total_seconds() * 1000)
        
        try:
            if self._db_initialized:
                with get_cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE alerts_engine_runs
                        SET finished_at = %s, duration_ms = %s, status = %s, counts = %s, error_summary = %s
                        WHERE run_id = %s
                        """,
                        (
                            finished_at,
                            duration_ms,
                            status,
                            json.dumps(counts) if counts else None,
                            truncate_error(error),
                            self.run_id
                        )
                    )
                logger.info(f"Engine run finished: {self.run_id} (status={status}, duration_ms={duration_ms})")
        except Exception as e:
            logger.warning(f"Failed to update run record (continuing anyway): {e}")


def get_delivery_health_metrics(hours: int = 24) -> Dict[str, Any]:
    """
    Get delivery health metrics for the specified time window.
    Returns counts grouped by channel, status, and delivery_kind.
    """
    try:
        with get_cursor() as cursor:
            cursor.execute(
                """
                SELECT 
                    channel,
                    status,
                    delivery_kind,
                    COUNT(*) as count
                FROM user_alert_deliveries
                WHERE created_at >= NOW() - INTERVAL '%s hours'
                GROUP BY channel, status, delivery_kind
                ORDER BY channel, status, delivery_kind
                """,
                (hours,)
            )
            rows = cursor.fetchall()
            
            metrics = {}
            for row in rows:
                channel = row["channel"]
                if channel not in metrics:
                    metrics[channel] = {}
                
                status = row["status"]
                kind = row["delivery_kind"] or "unknown"
                key = f"{status}_{kind}"
                metrics[channel][key] = row["count"]
            
            cursor.execute(
                """
                SELECT 
                    EXTRACT(EPOCH FROM (NOW() - MIN(created_at))) / 60 as oldest_queued_minutes
                FROM user_alert_deliveries
                WHERE status = 'queued'
                """
            )
            result = cursor.fetchone()
            oldest_queued_minutes = result["oldest_queued_minutes"] if result else None
            
            return {
                "period_hours": hours,
                "by_channel": metrics,
                "oldest_queued_delivery_minutes": round(oldest_queued_minutes, 2) if oldest_queued_minutes else None
            }
    except Exception as e:
        logger.error(f"Failed to get delivery health metrics: {e}")
        return {"error": str(e)}


def get_digest_health_metrics(days: int = 7) -> Dict[str, Any]:
    """
    Get digest health metrics for the specified time window.
    Returns counts grouped by channel and status.
    """
    try:
        with get_cursor() as cursor:
            cursor.execute(
                """
                SELECT 
                    channel,
                    status,
                    COUNT(*) as count
                FROM user_alert_digests
                WHERE created_at >= NOW() - INTERVAL '%s days'
                GROUP BY channel, status
                ORDER BY channel, status
                """,
                (days,)
            )
            rows = cursor.fetchall()
            
            metrics = {}
            for row in rows:
                channel = row["channel"]
                if channel not in metrics:
                    metrics[channel] = {}
                metrics[channel][row["status"]] = row["count"]
            
            cursor.execute(
                """
                SELECT 
                    EXTRACT(EPOCH FROM (NOW() - MIN(created_at))) / 60 as oldest_queued_minutes
                FROM user_alert_digests
                WHERE status = 'queued'
                """
            )
            result = cursor.fetchone()
            oldest_queued_minutes = result["oldest_queued_minutes"] if result else None
            
            return {
                "period_days": days,
                "by_channel": metrics,
                "oldest_queued_digest_minutes": round(oldest_queued_minutes, 2) if oldest_queued_minutes else None
            }
    except Exception as e:
        logger.error(f"Failed to get digest health metrics: {e}")
        return {"error": str(e)}


def get_engine_runs(limit: int = 50) -> List[Dict[str, Any]]:
    """Get the latest engine run records."""
    try:
        with get_cursor() as cursor:
            cursor.execute(
                """
                SELECT 
                    run_id, triggered_by, phase, started_at, finished_at, 
                    duration_ms, status, counts, error_summary, git_sha, created_at
                FROM alerts_engine_runs
                ORDER BY started_at DESC
                LIMIT %s
                """,
                (limit,)
            )
            rows = cursor.fetchall()
            
            runs = []
            for row in rows:
                runs.append({
                    "run_id": row["run_id"],
                    "triggered_by": row["triggered_by"],
                    "phase": row["phase"],
                    "started_at": row["started_at"].isoformat() if row["started_at"] else None,
                    "finished_at": row["finished_at"].isoformat() if row["finished_at"] else None,
                    "duration_ms": row["duration_ms"],
                    "status": row["status"],
                    "counts": row["counts"],
                    "error_summary": row["error_summary"],
                    "git_sha": row["git_sha"],
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None
                })
            
            return runs
    except Exception as e:
        logger.error(f"Failed to get engine runs: {e}")
        return []


def get_engine_run_detail(run_id: str) -> Optional[Dict[str, Any]]:
    """Get detailed information about a specific engine run including phase items."""
    try:
        with get_cursor() as cursor:
            cursor.execute(
                """
                SELECT 
                    run_id, triggered_by, phase, started_at, finished_at, 
                    duration_ms, status, counts, error_summary, git_sha, created_at
                FROM alerts_engine_runs
                WHERE run_id = %s
                """,
                (run_id,)
            )
            row = cursor.fetchone()
            
            if not row:
                return None
            
            run = {
                "run_id": row["run_id"],
                "triggered_by": row["triggered_by"],
                "phase": row["phase"],
                "started_at": row["started_at"].isoformat() if row["started_at"] else None,
                "finished_at": row["finished_at"].isoformat() if row["finished_at"] else None,
                "duration_ms": row["duration_ms"],
                "status": row["status"],
                "counts": row["counts"],
                "error_summary": row["error_summary"],
                "git_sha": row["git_sha"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "phase_items": []
            }
            
            cursor.execute(
                """
                SELECT 
                    phase, started_at, finished_at, duration_ms, status, counts, error_summary
                FROM alerts_engine_run_items
                WHERE run_id = %s
                ORDER BY started_at
                """,
                (run_id,)
            )
            items = cursor.fetchall()
            
            for item in items:
                run["phase_items"].append({
                    "phase": item["phase"],
                    "started_at": item["started_at"].isoformat() if item["started_at"] else None,
                    "finished_at": item["finished_at"].isoformat() if item["finished_at"] else None,
                    "duration_ms": item["duration_ms"],
                    "status": item["status"],
                    "counts": item["counts"],
                    "error_summary": item["error_summary"]
                })
            
            return run
    except Exception as e:
        logger.error(f"Failed to get engine run detail: {e}")
        return None


def retry_failed_deliveries(kind: str = "deliveries", since_hours: int = 24, dry_run: bool = True) -> Dict[str, Any]:
    """
    Re-queue failed deliveries or digests that are eligible for retry.
    Only re-queues items where attempts < max_attempts and error is not permanent.
    """
    from src.alerts.channel_adapters import ALERTS_MAX_ATTEMPTS
    
    permanent_errors = ['invalid_recipient', 'channel_disabled', 'config_missing', 'batched_into_digest']
    
    try:
        with get_cursor() as cursor:
            if kind == "deliveries":
                if dry_run:
                    cursor.execute(
                        """
                        SELECT COUNT(*) as count
                        FROM user_alert_deliveries
                        WHERE status = 'failed'
                          AND created_at >= NOW() - INTERVAL '%s hours'
                          AND attempts < %s
                          AND (last_error IS NULL OR NOT (last_error = ANY(%s)))
                        """,
                        (since_hours, ALERTS_MAX_ATTEMPTS, permanent_errors)
                    )
                    result = cursor.fetchone()
                    return {
                        "kind": kind,
                        "dry_run": True,
                        "eligible_count": result["count"] if result else 0,
                        "requeued": 0
                    }
                else:
                    cursor.execute(
                        """
                        UPDATE user_alert_deliveries
                        SET status = 'queued', next_retry_at = NULL
                        WHERE status = 'failed'
                          AND created_at >= NOW() - INTERVAL '%s hours'
                          AND attempts < %s
                          AND (last_error IS NULL OR NOT (last_error = ANY(%s)))
                        """,
                        (since_hours, ALERTS_MAX_ATTEMPTS, permanent_errors)
                    )
                    requeued = cursor.rowcount
                    return {
                        "kind": kind,
                        "dry_run": False,
                        "requeued": requeued
                    }
            
            elif kind == "digests":
                if dry_run:
                    cursor.execute(
                        """
                        SELECT COUNT(*) as count
                        FROM user_alert_digests
                        WHERE status = 'failed'
                          AND created_at >= NOW() - INTERVAL '%s hours'
                          AND attempts < %s
                        """,
                        (since_hours, ALERTS_MAX_ATTEMPTS)
                    )
                    result = cursor.fetchone()
                    return {
                        "kind": kind,
                        "dry_run": True,
                        "eligible_count": result["count"] if result else 0,
                        "requeued": 0
                    }
                else:
                    cursor.execute(
                        """
                        UPDATE user_alert_digests
                        SET status = 'queued', next_retry_at = NULL
                        WHERE status = 'failed'
                          AND created_at >= NOW() - INTERVAL '%s hours'
                          AND attempts < %s
                        """,
                        (since_hours, ALERTS_MAX_ATTEMPTS)
                    )
                    requeued = cursor.rowcount
                    return {
                        "kind": kind,
                        "dry_run": False,
                        "requeued": requeued
                    }
            
            return {"error": f"Unknown kind: {kind}"}
    except Exception as e:
        logger.error(f"Failed to retry failed items: {e}")
        return {"error": str(e)}
