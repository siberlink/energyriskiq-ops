---
name: GitHub ops workflow silent failures
description: How to diagnose the energyriskiq-ops GitHub Actions workflows that curl production /internal/run endpoints
---

The ops repo workflows (`siberlink/energyriskiq-ops`, public) curl `${APP_URL}/internal/run/*` with `X-Runner-Token`. Most steps only warn on non-200 and still report step "success" — historically only the GERI step did `exit 1`, so a run can look mostly green while nothing actually executed.

**Diagnosis signals:**
- Step durations from the public GH API (`/actions/runs/<id>/jobs`) are the best free signal: healthy curl steps take 3–40s; 0–1s across the board means the calls never executed jobs (empty APP_URL secret, DNS, or connectivity failure).
- Cross-check with prod data: latest dates in `reri_indices_daily`, `egsi_m_daily`, `intel_indices_daily`, `vix_snapshots` show whether jobs really ran.
- Step logs require auth (403 on public repo); run/step conclusions and timings do not.
- Deployment logs can miss requests (autoscale multi-instance + retention) — absence of a POST line is weak evidence on its own.

**Recovery:** the same endpoints can be called directly from the workspace with `$INTERNAL_RUNNER_TOKEN` (available locally) against https://energyriskiq.com to backfill missed daily computes; order: market-data → geri-compute → eeri-compute → lng-price-capture → egsi-compute → egsi-s-compute → daily-report. Delivery (pro-delivery) emails real users — get user sign-off before triggering manually.

**Hardening applied (geri-daily.yml):** first step validates APP_URL/INTERNAL_RUNNER_TOKEN secrets + /health probe; all curls use `--retry 3 --retry-all-errors -m 180`; final step fails the run if any step recorded status=failed. GitHub pushes require the user (embedded PAT expired).
