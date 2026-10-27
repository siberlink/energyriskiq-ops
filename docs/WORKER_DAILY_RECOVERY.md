# Daily worker recovery — 27 October 2026

## Scope

This is an operations-worker change. It does not require publishing the website.
Cloud builds this repository, not the website checkout.

The existing Daily handler now uses yesterday's **UTC** date. When that date's
GERI is already published, it still calls `record_existing_skip`, which:

1. Records/finalizes that closed day's health through the existing health writer.
2. Computes the private v1.2 methodology through `version12.compute_day`.
3. Records a successful skip only after both operations finish.

Private failures propagate to the job instead of producing a false success.
The normal first-publication branch also invokes the private computation after
the existing public writer completes. Neither branch forces index revisions.
The health upsert preserves immutable final health and only finalizes provisional
rows. No new scheduler, Daily public writer or messaging operation was added.

The previously missing frozen private helpers are included from the tested
application source: version12, v12_math, model_selection and health_finalization.
No selector environment variables or public scoring formulas were changed.

## Dependency installation

`requirements.txt` pins all direct worker requirements, including the seven
owner-specified versions. `constraints.txt` pins the runtime dependency closure.
`requirements.lock` contains the complete resolved runtime installation with
SHA-256 hashes. Docker installs that lock with `--require-hashes`.

The package firewall rejected the old baseline's anyio 4.12.1 and certifi 2026.1.4.
They are replaced by anyio 4.15.1 and certifi 2026.10.23; typing-extensions 4.16.0
satisfies the newer anyio dependency. All seven owner-specified versions remain
unchanged. The final lock passes pip's clean, ignore-installed resolution/hash
check through the firewall.

Regenerate deliberately, review, then repeat offline tests:

```sh
uv pip compile requirements.txt --python-version 3.11 --generate-hashes \
  --no-emit-index-url --output-file requirements.lock
python -m pip install --dry-run --ignore-installed --require-hashes \
  -r requirements.lock
env -u RISK_PIPELINE_V2_MODE RISK_PIPELINE_V2_ENABLED=false \
  PYTHONPATH=. python -m pytest tests -q
```

Tests passed: **118**, including eight new worker regression tests.
The complete suite also passed with the three updated transitive dependencies
loaded in the test process. No installed website dependencies were changed.

## Production repair performed

October 26 health is final/OK and explicitly `late_repair=true`,
`prospective_eligible=false`. A `health_finalization_correction` audit record
excludes that date under the existing release gate predicate.

All eleven missing shadow variants were written for that date. The selected
`wk_carry15` comparison is **22**, matching the existing private Daily value.
The new shadow rows are also explicitly marked late and non-prospective.

Full-table fingerprints before and after the repair were identical for both
`intel_indices_daily` and `intel_indices_daily_v12`: published v1.1 and private
v1.2 Daily values were not revised. This repair is not seven-day gate evidence.

## Cloud update boundaries

Build the reviewed commit, then update **only** `energyriskiq-daily` and
`energyriskiq-ingestion`. Keep existing secrets, service accounts, commands,
schedules, retries and other environment variables. On ingestion explicitly
retain 3000 seconds / 50 minutes and shadow mode; preserve the $5 shared cap.

Do **not** run the all-five-jobs deployment script: that would exceed this update's
scope and contains older job defaults. Do not change alerts, intraday or metadata.
Do not enable GitHub Daily Index.

This repository commit and an image build are not proof of rollout. The owner
must perform the two Cloud updates, then verify image/config and execution logs.
Use a manual Daily execution with `INCLUDE_DELIVERY=false` as a per-execution
override if testing manually, rather than sending subscriber messages.

After the next scheduled Daily run, check the closed day's final health,
`intel_indices_daily_v12` row and `wk_carry15` shadow comparison. Shadow comparison
is still owned by the existing private-shadow workflow; Daily does not add a
second comparison writer.
