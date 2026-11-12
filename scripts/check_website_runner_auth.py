"""Read-only token-binding check. Prints HTTP status only, never headers/body."""
import os
import requests
from urllib.parse import urlparse


def main():
    base = os.environ.get("WEBSITE_BASE_URL", "").rstrip("/")
    url = urlparse(base)
    if (url.scheme != "https" or not url.netloc or url.path or url.query
            or url.fragment or url.username or url.password):
        raise SystemExit("WEBSITE_BASE_URL must be an HTTPS origin")
    token = os.environ.get("INTERNAL_RUNNER_TOKEN")
    if not token:
        raise SystemExit("Runner token not configured")
    # This existing GET validates the same secret and only SELECTs audit rows.
    # Do not print response JSON: it contains operational information.
    try:
        response = requests.get(base + "/internal/alerts/engine/runs?limit=1",
                                headers={"X-Internal-Token": token},
                                timeout=(10, 10), allow_redirects=False)
    except requests.RequestException:
        print("Runner binding: transport failed")
        return 1
    print("Runner binding HTTP", response.status_code)
    return 0 if response.status_code == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
