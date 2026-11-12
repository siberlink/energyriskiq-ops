"""Disposable Unix-socket PostgreSQL; no application database or TCP listener."""
from contextlib import contextmanager
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

import psycopg2
from psycopg2.extras import RealDictCursor
import pytest


@pytest.fixture(scope="module")
def disposable_pg():
    assert shutil.which("initdb"), "Disposable PostgreSQL is required, not skipped"
    with tempfile.TemporaryDirectory(prefix="storage-sql-") as directory:
        data = str(Path(directory) / "pg")
        port = 20000 + os.getpid() % 30000
        subprocess.run(["initdb", "-D", data, "-A", "trust", "-U", "storage_test",
                        "--no-locale", "--encoding=UTF8"], check=True, capture_output=True)
        subprocess.run(["pg_ctl", "-D", data, "-l", directory + "/server.log",
                        "-o", f"-k {directory} -p {port} -c listen_addresses=''",
                        "-w", "start"], check=True, capture_output=True)
        try:
            yield {"dbname": "postgres", "user": "storage_test",
                   "host": directory, "port": port}
        finally:
            subprocess.run(["pg_ctl", "-D", data, "-m", "immediate", "-w", "stop"],
                           check=True, capture_output=True)


@contextmanager
def sql_cursor(settings, commit=True):
    conn = psycopg2.connect(**settings)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
        if commit:
            conn.commit()
    finally:
        conn.close()
