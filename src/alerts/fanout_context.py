"""Request-local optimization only; never shared across jobs or send-time reads."""
from contextvars import ContextVar

current = ContextVar("alerts_fanout_snapshot", default=None)
