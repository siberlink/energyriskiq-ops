"""Cloud-side adapter only: the website owns every storage provider/database write."""
import json
import os
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse

import requests


def run_website_storage(x_runner_token=None, target_date=None):
    base = os.environ.get("WEBSITE_BASE_URL", "").rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        raise ValueError("WEBSITE_BASE_URL must be an HTTPS origin")
    token = x_runner_token or os.environ.get("INTERNAL_RUNNER_TOKEN")
    if not token:
        raise ValueError("Website runner authentication is not configured")
    path = Path(__file__).parents[1] / "ingest" / "storage_build_info.json"
    build = json.loads(path.read_text()) if path.exists() else {}
    headers = {"X-Runner-Token": token, "X-Cloud-Job": os.environ.get("CLOUD_RUN_JOB", "energyriskiq-daily"),
               "X-Cloud-Execution": os.environ.get("CLOUD_RUN_EXECUTION", "unavailable"),
               "X-Cloud-Commit": build.get("commit", "unavailable"),
               "X-Cloud-Image": build.get("image", "unavailable")}
    # No automatic POST retries: a timeout can mean the website is still committing.
    # A manual retry is idempotent and protected by the shared storage writer lock.
    response = requests.post(base + "/internal/run/storage-pipeline",
                             headers=headers, params={"target_date": str(target_date)} if target_date else {},
                             timeout=(10, 300), allow_redirects=False)
    if response.status_code != 200:
        raise RuntimeError(f"Website storage pipeline HTTP {response.status_code}")
    result = response.json()
    details = result.get("details", {})
    if result.get("status") != "ok" or details.get("status") != "success" or details.get("observations") != 77:
        raise RuntimeError("Website storage pipeline returned incomplete result")
    return details
