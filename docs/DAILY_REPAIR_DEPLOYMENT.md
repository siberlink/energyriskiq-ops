# Daily repair: owner-approved sequence, 11 November 2026

Review the repair commit's diff against
`6f2ca678abc677f732172a0d6dcf1ff3dbbd1c72` before building.
Run `bash scripts/build_daily_repair.sh <full-reviewed-commit>` from Cloud Shell.
It builds one image, on any day, and changes no jobs or settings.
There is no DAILY_SUCCEEDED prompt and no 11-November calendar check.
Do not rebuild blindly after disconnecting: inspect the saved Cloud Build ID.

## Website, separately

Review and publish the website-only EERI -> same-date EGSI-M orchestration and
Live fill-only recovery diff. No selectors, scoring kernels or customer messages
change. No historical EGSI-M backfill is authorized by publishing this change.
The existing GitHub EERI workflow remains the website trigger.

## Cloud sequence

1. Build the reviewed repair commit; require SUCCESS and record image digest.
2. Cloud Run > Jobs > energyriskiq-alerts > View and edit job configuration >
   Container image URL: select the new tag, then Update (not Execute).
3. First three scheduled executions STARTED on the new image must succeed,
   exit 0, have finished successful phase A and final audits, correct image/source
   provenance, no provider-storage writes and no duplicate storage events.
   At most one ASSET_RISK_SPIKE storage event per provider gas day.
4. Only then update energyriskiq-daily to the SAME new image via the same console path.
5. Next Daily run: exit 0, no stage errors, Cloud stores closed-day v1.2 before
   any delivery read, 77/77 E/C observations over the latest published seven
   gas days (EU + 10 countries), EU provider precision retained, and the
   Telegram audit records the new GERI date/value/methodology.
6. Next morning after the GitHub EERI workflow: same-date website EERI TTF-v3
   and EGSI-M must both exist. The workflow reports failure if EGSI-M save fails,
   including when EERI already existed.

Missing AI narratives are now explicit failures, not green warming results.
Until the owner fixes the confirmed Cloud provider connection/configuration,
Daily may continue to exit 1 for daily_report/delivery despite correct GERI.
No Cloud environment configuration is changed by this repair.

Only Alerts and Daily images change. Leave ingestion, intraday, metadata,
schedules, timeouts, retries, service accounts, resources, delivery preferences,
the email pause and all GERI selectors unchanged. Do not manually execute a
delivery job to test it.

## Image-only rollback: both jobs

Console: repeat the image URL update for Alerts and Daily using
`europe-west4-docker.pkg.dev/energyriskiq/energyriskiq-jobs/scheduled-jobs:1639c2d`.

```bash
gcloud run jobs update energyriskiq-alerts --project=energyriskiq --region=europe-west4 \
  --image=europe-west4-docker.pkg.dev/energyriskiq/energyriskiq-jobs/scheduled-jobs:1639c2d
gcloud run jobs update energyriskiq-daily --project=energyriskiq --region=europe-west4 \
  --image=europe-west4-docker.pkg.dev/energyriskiq/energyriskiq-jobs/scheduled-jobs:1639c2d
```

WARNING: this restores the known broken v1.2 interpretation interface and old
storage-writing behavior. It is containment, not a healthy v1.2 rollback.
No data is restored by an image rollback. No schema changes are part of this repair.
