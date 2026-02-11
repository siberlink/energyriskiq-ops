import os
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager

logger = logging.getLogger(__name__)

def get_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL environment variable is not set")
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
    try:
        conn = psycopg2.connect(get_database_url())
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT pg_try_advisory_lock(%s)", (lock_id,))
        result = cursor.fetchone()
        acquired = result['pg_try_advisory_lock'] if result else False
        cursor.close()
        yield acquired
    except Exception as e:
        logger.error(f"Advisory lock error for {lock_id}: {e}")
        yield False
    finally:
        if conn:
            try:
                if acquired:
                    cursor = conn.cursor()
                    cursor.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))
                    cursor.close()
                conn.close()
            except Exception as e:
                logger.error(f"Failed to release advisory lock {lock_id}: {e}")
