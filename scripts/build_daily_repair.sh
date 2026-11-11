#!/usr/bin/env bash
# Build only. No calendar gate and no requirement that broken 1639c2d succeeds.
set -euo pipefail
PROJECT=energyriskiq
REGION=europe-west4
COMMIT="${1:?Supply the full reviewed repair commit hash}"
PARENT=6f2ca678abc677f732172a0d6dcf1ff3dbbd1c72
BRANCH=storage/provider-writer-20261110
[[ "$COMMIT" =~ ^[0-9a-f]{40}$ ]] || exit 1
IMAGE="europe-west4-docker.pkg.dev/$PROJECT/energyriskiq-jobs/scheduled-jobs:daily-repair-20261111-${COMMIT:0:12}"
read -r -p 'After reviewing the exact source diff, type build: ' APPROVAL
[[ "$APPROVAL" == build ]] || exit 1
SOURCE="$HOME/energyriskiq-ops"
[[ -d "$SOURCE/.git" ]] || git clone https://github.com/siberlink/energyriskiq-ops.git "$SOURCE"
git -C "$SOURCE" fetch origin "$BRANCH"
[[ "$(git -C "$SOURCE" rev-parse FETCH_HEAD)" == "$COMMIT" ]]
[[ "$(git -C "$SOURCE" rev-parse "$COMMIT^")" == "$PARENT" ]]
BUILD_DIR="$(mktemp -d /tmp/energyriskiq-daily-repair.XXXXXX)"
git -C "$SOURCE" worktree add --detach "$BUILD_DIR" "$COMMIT"
cd "$BUILD_DIR"
[[ -z "$(git status --porcelain)" ]]
git diff --stat "$PARENT" "$COMMIT"
git diff --name-only "$PARENT" "$COMMIT"
python3 - "$COMMIT" "$IMAGE" <<'PY'
import json, pathlib, sys
pathlib.Path("src/ingest/storage_build_info.json").write_text(
    json.dumps({"commit":sys.argv[1],"image":sys.argv[2]},sort_keys=True)+"\n")
PY
BUILD_ID="$(gcloud builds submit . --project="$PROJECT" --tag="$IMAGE" --async --format='value(id)')"
printf '%s\n' "$BUILD_ID" > "$HOME/storage-decimal-build-id.txt"
printf 'Build submitted: %s\nImage: %s\n' "$BUILD_ID" "$IMAGE"
printf 'gcloud builds describe "%s" --project=%s --format="value(status,results.images[0].digest)"\n' "$BUILD_ID" "$PROJECT"
echo "No jobs updated. Wait for build SUCCESS, then Alerts -> 3 good executions -> Daily."
