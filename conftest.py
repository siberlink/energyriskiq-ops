"""Offline test boundary, installed before collecting application test modules.

No real TCP/UDP, production credentials, or application PostgreSQL connections.
ASGI transports and the disposable storage SQL fixture remain available.
This file is test infrastructure only; it is not imported by the application.
"""
import os
from pathlib import Path
import socket

import psycopg2
from psycopg2.extensions import parse_dsn


# Do not let child processes inherit application DB/provider credentials.
for _key in list(os.environ):
    if (
        _key in {
            "DATABASE_URL", "PRODUCTION_DATABASE_URL", "PGHOST", "PGPORT",
            "PGDATABASE", "PGUSER", "PGPASSWORD", "PGSERVICE", "PGSERVICEFILE",
            "PGPASSFILE", "AI_INTEGRATIONS_OPENAI_BASE_URL",
        }
        or _key.endswith(("_API_KEY", "_SECRET_KEY", "_PASSWORD", "_TOKEN"))
    ):
        os.environ.pop(_key, None)
os.environ["RISK_PIPELINE_V2_MODE"] = "off"
os.environ["GERI_PUBLISHED_MODEL"] = "v1.1"
os.environ["GERI_LIVE_MODEL"] = "legacy"

_connect = psycopg2.connect
_socket_connect = socket.socket.connect
_socket_connect_ex = socket.socket.connect_ex


def _offline_database(*args, **kwargs):
    # A DSN may hide a production host even when kwargs look innocuous.
    options = parse_dsn(args[0]) if args and args[0] else {}
    options.update(kwargs)
    host = str(options.get("host", ""))
    path = Path(host)
    allowed = (
        path.is_absolute()
        and path.parent == Path("/tmp")
        and path.name.startswith("storage-sql-")
        and not path.is_symlink()
        and (path / "pg" / "PG_VERSION").is_file()
        and options.get("user") == "storage_test"
        and options.get("dbname") == "postgres"
        and not options.get("hostaddr")
        and not options.get("service")
    )
    if not allowed:
        raise RuntimeError("Test isolation: application/production database access blocked")
    return _connect(*args, **kwargs)


def _offline_connect(sock, address):
    if sock.family != socket.AF_UNIX:
        raise RuntimeError("Test isolation: real network and paid API access blocked")
    return _socket_connect(sock, address)


def _offline_connect_ex(sock, address):
    if sock.family != socket.AF_UNIX:
        raise RuntimeError("Test isolation: real network and paid API access blocked")
    return _socket_connect_ex(sock, address)


def _offline_sendto(*args, **kwargs):
    raise RuntimeError("Test isolation: datagram network access blocked")


psycopg2.connect = _offline_database
socket.socket.connect = _offline_connect
socket.socket.connect_ex = _offline_connect_ex
socket.socket.sendto = _offline_sendto
