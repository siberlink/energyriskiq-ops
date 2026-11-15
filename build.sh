#!/usr/bin/env bash
# Prepared for the owner. Never invoked automatically by website or schedules.
set -euo pipefail
test -f Dockerfile
test -f requirements.lock
COMMIT="$(git rev-parse HEAD)"
TAG="storage-history-20261115-${COMMIT:0:12}"
IMAGE="europe-west4-docker.pkg.dev/energyriskiq/energyriskiq-jobs/scheduled-jobs:${TAG}"
python - "$COMMIT" "$IMAGE" <<'PY'
import json,sys
from pathlib import Path
Path("src/ingest/storage_build_info.json").write_text(
    json.dumps({"commit":sys.argv[1],"image":sys.argv[2]},indent=2)+"\n")
PY
gcloud builds submit --project=energyriskiq --tag="$IMAGE" .
printf '\nBuilt %s\nNo Cloud jobs were updated.\n' "$IMAGE"
