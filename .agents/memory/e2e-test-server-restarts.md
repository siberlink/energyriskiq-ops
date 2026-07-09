---
name: E2E tests vs workflow restarts
description: Why Playwright e2e runs fail spuriously if files are edited around the test window
---
Editing project files near/around a running Playwright e2e test can trigger a workflow restart mid-test. The API server takes ~45s to boot (full migration chain runs on startup), so any in-flight fetch dies or hangs — producing false UI bugs (stuck disabled buttons, stale lists) even though the backend call actually committed.

**Why:** Two e2e runs "failed" on a save flow that was provably working (rows existed in DB); both failures aligned exactly with server restart timestamps in logs.

**How to apply:** Never edit files while an e2e test is running; before re-debugging a UI failure, check workflow logs for a restart during the test window and check the DB for whether the action actually succeeded.
