"""
Postgres Advisory Locks for Alerts v2 concurrency safety.

Uses pg_try_advisory_lock(bigint) for non-blocking lock acquisition.
Locks are automatically released when the connection/session closes.
"""

import hashlib
import logging
from typing import Optional

from src.db.db import get_cursor

logger = logging.getLogger(__name__)

LOCK_KEYS = {
    'alerts_v2_phase_a': 'alerts_v2_phase_a',
    'alerts_v2_phase_b': 'alerts_v2_phase_b',
    'alerts_v2_phase_c': 'alerts_v2_phase_c',
}


def _key_to_bigint(key: str) -> int:
    """
    Convert a string key to a 64-bit integer deterministically.
    Uses first 8 bytes of MD5 hash to get a consistent bigint.
    """
    hash_bytes = hashlib.md5(key.encode('utf-8')).digest()[:8]
    return int.from_bytes(hash_bytes, byteorder='big', signed=True)


def acquire_lock(cursor, key: str) -> bool:
    """
    Attempt to acquire an advisory lock (non-blocking).
    
    Args:
        cursor: A database cursor (must be within same transaction/session)
        key: Lock key string (e.g., 'alerts_v2_phase_a')
    
    Returns:
        True if lock acquired, False if lock is held by another session
    """
    lock_id = _key_to_bigint(key)
    cursor.execute("SELECT pg_try_advisory_lock(%s) AS acquired", (lock_id,))
    result = cursor.fetchone()
    acquired = result['acquired'] if result else False
    
    if acquired:
        logger.info(f"Advisory lock acquired: {key} (id={lock_id})")
    else:
        logger.warning(f"Advisory lock NOT acquired (held by another session): {key} (id={lock_id})")
    
    return acquired


def release_lock(cursor, key: str) -> bool:
    """
    Explicitly release an advisory lock.
    
    Note: Locks are automatically released when the session closes,
    so this is optional but can be used for early release.
    
    Args:
        cursor: A database cursor
        key: Lock key string
    
    Returns:
        True if lock was released, False otherwise
    """
    lock_id = _key_to_bigint(key)
    cursor.execute("SELECT pg_advisory_unlock(%s) AS released", (lock_id,))
    result = cursor.fetchone()
    released = result['released'] if result else False
    
    if released:
        logger.info(f"Advisory lock released: {key} (id={lock_id})")
    else:
        logger.debug(f"Advisory lock release failed (not held?): {key} (id={lock_id})")
    
    return released


class AdvisoryLock:
    """
    Context manager for advisory locks.
    
    Usage:
        with AdvisoryLock('alerts_v2_phase_a') as lock:
            if lock.acquired:
                # Do work
            else:
                # Skip (lock not acquired)
    """
    
    def __init__(self, key: str):
        self.key = key
        self.acquired = False
        self._connection = None
        self._cursor = None
    
    def __enter__(self):
        import psycopg2
        from psycopg2.extras import RealDictCursor
        from src.db.db import get_database_url
        
        try:
            self._connection = psycopg2.connect(get_database_url())
            self._cursor = self._connection.cursor(cursor_factory=RealDictCursor)
            
            lock_id = _key_to_bigint(self.key)
            self._cursor.execute("SELECT pg_try_advisory_lock(%s) AS acquired", (lock_id,))
            result = self._cursor.fetchone()
            self.acquired = result['acquired'] if result else False
            
            if self.acquired:
                logger.info(f"Advisory lock acquired via context manager: {self.key}")
            else:
                logger.warning(f"Advisory lock NOT acquired via context manager: {self.key}")
        except Exception as e:
            logger.error(f"Error acquiring advisory lock: {e}")
            self.acquired = False
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if self.acquired and self._cursor:
                lock_id = _key_to_bigint(self.key)
                self._cursor.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))
                logger.debug(f"Advisory lock released via context manager: {self.key}")
        except Exception as e:
            logger.error(f"Error releasing advisory lock: {e}")
        finally:
            if self._cursor:
                self._cursor.close()
            if self._connection:
                self._connection.close()
        
        return False
