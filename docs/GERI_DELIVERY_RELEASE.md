# GERI delivery alignment and joint cutover

This is preparation only. Keep `GERI_PUBLISHED_MODEL=v1.1` and
`GERI_LIVE_MODEL=legacy` until the owner's separately authorized go-live.
The website runbook `docs/GERI_V12_GO_LIVE.md` is the complete gate/smoke policy.
These worker requirements supersede older standalone-worker deployment notes.

## Preparation

Build **one image from the exact tested ops commit** and update only:
`energyriskiq-daily`, `energyriskiq-ingestion`, `energyriskiq-alerts`.
Use project `energyriskiq`, region `europe-west4`.

```bash
IMAGE=europe-west4-docker.pkg.dev/energyriskiq/energyriskiq-jobs/scheduled-jobs:$(git rev-parse --short=7 HEAD)
gcloud builds submit . --project=energyriskiq --tag="$IMAGE"
for job in energyriskiq-daily energyriskiq-ingestion energyriskiq-alerts; do
  gcloud run jobs update "$job" --project=energyriskiq --region=europe-west4 \
    --image="$IMAGE" \
    --update-env-vars=GERI_PUBLISHED_MODEL=v1.1,GERI_LIVE_MODEL=legacy
done
```

Before updating, inspect the actual image, named selectors and
`ALERTS_EMAIL_ENABLED` without exporting complete secret configuration.
If email is explicitly enabled or the flag is secret-backed/unknown, **stop
and obtain an owner decision**; do not silently change an existing setting.
Missing email flag defaults OFF in the corrected sender. The seven-day audit
showed that the old image's ON default did not enforce the owner's pause.

Do not use `--set-env-vars`, which replaces unrelated environment entries.
`--update-env-vars` preserves them. Do not modify ingestion's existing 50-minute
timeout, shadow mode, $5/day budget or 20 RPM; do not alter delivery flags,
secrets, retries, schedules, Telegram preferences, destinations, or opt-ins.
Do not update intraday/metadata. Do not execute jobs for testing.
Trader delivery source is unchanged.

## What is corrected

- Standalone delivery readers explicitly apply selected-methodology SQL;
  ordinary ops DB cursors do not do that automatically.
- Pro/index and Daily report prompts use the website's identical
  `interpretation_context` / inactive-component wording and never request
  component decomposition.
- Telegram and diagnostic email renders identify the selected methodology.
- Daily report cache keys use the website's v1.2 namespace; in-process delivery
  narrative keys include methodology and observation date.
- The alert email sender defaults OFF, including legacy sender imports.
  Transactional mail and Telegram remain independent.

## Future joint go-live

All current website gates must pass with owner G5/G6 approval. Verify the
installed corrected images and rendered worker evidence separately; unchanged
website hashes are not proof of installed Cloud images.

Use an owner-authorized quiet window and existing operational controls to hold
new launches of the three Scheduler triggers. Let all in-flight jobs finish.
Also inventory any GitHub alert/delivery runner: the database recorded such
runs in the audit period. Do not disable or change any scheduler without the
owner's authorization.

In that same window, set both **website** selectors to v1.2, set the actual
UTC release date and have the owner publish the website configuration. Set both
selectors on **all three Cloud jobs**:

```bash
for job in energyriskiq-daily energyriskiq-ingestion energyriskiq-alerts; do
  gcloud run jobs update "$job" --project=energyriskiq --region=europe-west4 \
    --update-env-vars=GERI_PUBLISHED_MODEL=v1.2,GERI_LIVE_MODEL=v1.2
done
```

Verify website, API, Live/Daily, private observation dates, cache separation and
downloaded delivery renders in 15 minutes or less. Do not send test messages or
announcements. Resume held triggers only when the website and all three job
templates agree. Cross-service changes are not atomic; an in-flight execution
retains its original settings.

## Rollback

Keep the corrected image. Restore **both website selectors** to v1.1/legacy,
clear the release date and have the owner publish that rollback. In the same
held window restore **all three Cloud templates**, not just Daily:

```bash
for job in energyriskiq-daily energyriskiq-ingestion energyriskiq-alerts; do
  gcloud run jobs update "$job" --project=energyriskiq --region=europe-west4 \
    --update-env-vars=GERI_PUBLISHED_MODEL=v1.1,GERI_LIVE_MODEL=legacy
done
```

Verify legacy observations and downloaded renders before resuming triggers.
Never restore the September alerts image: that would reintroduce the email
pause defect. Never delete history, replay emails, change Telegram preferences,
or re-enable paused email as part of rollback.
