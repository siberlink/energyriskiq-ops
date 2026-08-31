"""
Postgres Advisory Locks for Alerts v2 concurrency safety.

Uses pg_try_advisory_lock(bigint) for non-blocking lock acquisition.
Locks are automatically released when the connection/session closes.
"""

import hashlib
import logging
from typing import Optional

from src.db.db import advisory_lock, get_cursor

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
        self._context = None
    
    def __enter__(self):
        self._context = advisory_lock(_key_to_bigint(self.key))
        self.acquired = self._context.__enter__()
        if self.acquired:
            logger.info(
                "Advisory lock acquired via context manager: %s",
                self.key,
            )
        else:
            logger.warning(
                "Advisory lock NOT acquired via context manager: %s",
                self.key,
            )
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self._context:
            return False
        return self._context.__exit__(exc_type, exc_val, exc_tb)
