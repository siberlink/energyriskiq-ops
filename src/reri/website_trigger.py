"""Cloud orchestrates; the authenticated website remains the pair's only writer."""
from datetime import datetime, timedelta, timezone
import math
import os
import time
from urllib.parse import urlparse

import requests


def run_website_pair(x_runner_token=None):
    base = os.environ.get("WEBSITE_BASE_URL", "").rstrip("/")
    parsed = urlparse(base)
    if (parsed.scheme != "https" or not parsed.netloc or parsed.username
            or parsed.password or parsed.query or parsed.fragment or parsed.path):
        raise ValueError("WEBSITE_BASE_URL must be an HTTPS origin")
    token = x_runner_token or os.environ.get("INTERNAL_RUNNER_TOKEN")
    if not isinstance(token, str) or not token:
        raise ValueError("Website runner authentication is not configured")
    day = str(datetime.now(timezone.utc).date() - timedelta(days=1))
    for attempt in range(3):
        retryable = False
        try:
            response = requests.post(
                base + "/api/v1/indices/eeri/compute-yesterday",
                headers={"X-Runner-Token": token}, timeout=(10, 90),
                allow_redirects=False,
            )
            retryable = response.status_code in {408, 409, 429, 500, 502, 503, 504}
            if response.status_code != 200:
                raise ValueError("Website pair HTTP " + str(response.status_code))
            try:
                result = response.json()
            except ValueError:
                raise ValueError("Website pair returned invalid JSON") from None
            if not isinstance(result, dict):
                raise ValueError("Website pair returned invalid result")
            if result.get("success") is not True:
                retryable = result.get("status") == "busy" and result.get("retryable") is True
                raise ValueError("Website pair did not succeed")
            observations = {}
            for name in ("eeri", "egsi_m"):
                stage = result.get("stages", {}).get(name, {})
                value = stage.get("value")
                if (stage.get("date") != day
                        or stage.get("status") not in {"stored", "existing", "repaired"}
                        or isinstance(value, bool) or not isinstance(value, (int, float))
                        or not math.isfinite(value) or not 0 <= value <= 100
                        or (name == "eeri" and stage.get("model_version") != "eeri_ttf_v3")):
                    raise ValueError("Website pair returned invalid " + name + " observation")
                observations[name] = {"date": day, "value": value, "status": stage["status"]}
            return {"status": "success", "target_date": day,
                    "index_observations": observations, "attempts": attempt + 1}
        except (requests.Timeout, requests.ConnectionError):
            retryable = True
        except ValueError:
            if not retryable:
                raise
        if not retryable or attempt == 2:
            raise RuntimeError("Website EERI/EGSI-M unavailable after bounded retries") from None
        time.sleep((10, 30)[attempt])
