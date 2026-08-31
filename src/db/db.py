import os
import logging
import threading
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager

logger = logging.getLogger(__name__)

def get_database_url() -> str:
    url = os.environ.get("PRODUCTION_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise ValueError("Neither PRODUCTION_DATABASE_URL nor DATABASE_URL environment variable is set")
    return url

@contextmanager
def get_connection():
    conn = None
    try:
        conn = psycopg2.connect(get_database_url())
        yield conn
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        raise
    finally:
        if conn:
            conn.close()

@contextmanager
def get_cursor(commit=True):
    with get_connection() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            yield cursor
            if commit:
                conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            cursor.close()

def execute_query(query: str, params: tuple = None, fetch: bool = True):
    with get_cursor() as cursor:
        cursor.execute(query, params)
        if fetch:
            return cursor.fetchall()
        return None

def execute_one(query: str, params: tuple = None):
    with get_cursor() as cursor:
        cursor.execute(query, params)
        return cursor.fetchone()


def get_production_database_url() -> str:
    url = os.environ.get("PRODUCTION_DATABASE_URL")
    if url:
        return url
    return get_database_url()

@contextmanager
def get_production_connection():
    conn = None
    try:
        conn = psycopg2.connect(get_production_database_url())
        yield conn
    except Exception as e:
        logger.error(f"Production database connection error: {e}")
        raise
    finally:
        if conn:
            conn.close()

@contextmanager
def get_production_cursor(commit=False):
    with get_production_connection() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            yield cursor
            if commit:
                conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Production database error: {e}")
            raise
        finally:
            cursor.close()


def execute_production_query(query: str, params: tuple = None):
    with get_production_connection() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cursor.execute(query, params)
            return cursor.fetchall()
        finally:
            cursor.close()

def execute_production_one(query: str, params: tuple = None):
    with get_production_connection() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cursor.execute(query, params)
            return cursor.fetchone()
        finally:
            cursor.close()


@contextmanager
def advisory_lock(lock_id: int):
    conn = None
    acquired = False
    heartbeat_stop = threading.Event()
    heartbeat_failed = threading.Event()
    heartbeat_thread = None

    def heartbeat():
        interval = max(
            5,
            int(os.environ.get("ADVISORY_LOCK_HEARTBEAT_SECONDS", "30")),
        )
        while not heartbeat_stop.wait(interval):
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.close()
            except Exception as error:
                heartbeat_failed.set()
                logger.error(
                    "Advisory lock heartbeat failed for %s: %s",
                    lock_id,
                    error,
                )
                return

    try:
        conn = psycopg2.connect(
            get_database_url(),
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=10,
            keepalives_count=3,
        )
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT pg_try_advisory_lock(%s)", (lock_id,))
        result = cursor.fetchone()
        acquired = result['pg_try_advisory_lock'] if result else False
        cursor.close()

        if acquired:
            heartbeat_thread = threading.Thread(
                target=heartbeat,
                name=f"advisory-lock-{lock_id}-heartbeat",
                daemon=True,
            )
            heartbeat_thread.start()
    except Exception as error:
        logger.error("Advisory lock acquisition failed for %s: %s", lock_id, error)
        yield False
        return

    try:
        yield acquired
        if acquired and heartbeat_failed.is_set():
            raise RuntimeError(
                f"Advisory lock {lock_id} connection was lost while the job ran"
            )
    finally:
        heartbeat_stop.set()
        if heartbeat_thread:
            heartbeat_thread.join(timeout=5)
        if conn:
            try:
                if acquired and not heartbeat_failed.is_set():
                    cursor = conn.cursor()
                    cursor.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))
                    cursor.close()
                conn.close()
            except Exception as error:
                logger.error(
                    "Failed to release advisory lock %s: %s",
                    lock_id,
                    error,
                )
