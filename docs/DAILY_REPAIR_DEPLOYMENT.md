# Cloud AI routing repair — review before building

This repair is a direct child of
`eccb528a1875c9bf9249328675b645883113b4c0` on
`storage/provider-writer-20261110`. It retains all Daily/storage/Decimal fixes.
No scoring, selector, dependency, schema, email-pause or Telegram-setting change.
Website source and existing observations are not modified by this repair.

## Review and build

The delivery report gives the new full commit SHA. Review the parent-to-child
diff before building. Never build the superseded eccb image for this rollout.

```bash
COMMIT='REPLACE_WITH_FULL_REVIEWED_CHILD_SHA'
git fetch origin storage/provider-writer-20261110
git diff eccb528a1875c9bf9249328675b645883113b4c0 "$COMMIT"
git show "$COMMIT:scripts/build_daily_repair.sh" > /tmp/build-daily-repair.sh
bash /tmp/build-daily-repair.sh "$COMMIT"
gcloud builds describe "$(cat ~/storage-decimal-build-id.txt)" \
  --project=energyriskiq --format='value(status,results.images[0].digest)'
```

The build script enforces the exact commit, direct parent, branch head and clean
detached checkout. It tags one image `cloud-ai-repair-20261111-<first12sha>`.
It does not update jobs. If Cloud Shell disconnects, inspect the existing build;
do not submit another. Require build SUCCESS and record the digest.

## One console edit per job: Alerts first, then Daily

Cloud Console > project **energyriskiq** > Cloud Run > Jobs > region
**europe-west4** > job > **View and edit job configuration**.

1. Edit **energyriskiq-alerts**:
   - In Container image URL, select the new image/digest.
   - In Variables & Secrets, delete references named
     `AI_INTEGRATIONS_OPENAI_API_KEY` and `AI_INTEGRATIONS_OPENAI_BASE_URL`.
   - Keep the existing `OPENAI_API_KEY` Secret Manager reference.
   - Keep `OPENAI_BASE_URL` unchanged if set; pre-check that it is an approved,
     reachable direct-provider endpoint, not localhost or the internal service.
     If it is wrong, STOP and report instead of silently routing paid traffic.
   - Keep every other setting, including selectors, delivery switches, email
     pause, Telegram, arguments, retries, timeout, resources, service account
     and Scheduler configuration.
   - Click Update once after BOTH the image and secret-reference edits.
2. Observe the **first three scheduled Alerts executions started on the new
   image**. Do not click Execute as a test. All three must finish successfully,
   with finished Phase A/final audit, correct image provenance, no provider
   storage writes, and no more than one ASSET_RISK_SPIKE storage event per
   provider gas day. Check AI flags on any digest actually attempted, zero
   alert emails sent, and unchanged Telegram settings.
3. Only after those three pass, make the **same single edit** on
   **energyriskiq-daily**: new image AND remove those two integration references,
   keep the direct-key reference and everything else unchanged.

No image changes to Ingestion, Intraday or Metadata in this rollout.
No website republish is required for this ops-only patch. Never remove the
Replit website's integration references as part of a Cloud configuration edit.

## AI and next scheduled Daily acceptance

GERI and EGSI-S choose the integration only when BOTH integration variables are
present. Otherwise they use OPENAI_API_KEY and optional OPENAI_BASE_URL.
Successful AI prose is stored normally. Missing credentials, transport errors
and empty responses retain deterministic text, but persist
`components.ai_section_missing=true` and sanitized interpretation diagnostics.
The internal stage result exposes that flag; the Daily pipeline treats it as
a failed stage, including an already-existing row bearing known fallback
provenance. GERI persistence still completes; dependent report/delivery remain
blocked when its stage fails. No automatic rewrite of older rows is authorized.
Historical rows without provenance are unknown, not retrospective proof of AI.

Next scheduled Daily must exit 0 with no failed stages: final health before
private computation, selected v1.2 persisted before report/delivery, Live close
consistent, publication_writer identifies the Cloud job/execution, last seven
PUBLISHED storage gas days with retained E/C provenance, and fresh delivery
audits identify GERI date/value/methodology and missing-AI flags.
Website EERI -> same-date EGSI-M remains the sole writer of those indices.

## Ingestion — configuration-only proposal, not applied

First collect that job's actual env-reference names and Cloud execution logs.
The shared database's successful enrichment ledger does not identify Cloud
versus the website/GitHub shadow runner. Do not call all enrichment broken
without per-execution evidence.

The older ingestion client already uses OPENAI_API_KEY if either integration
variable is absent; the OpenAI SDK honors OPENAI_BASE_URL. If Ingestion really
has both bad integration references and connection errors, wait for a current
run to finish and, without changing its image, remove just those two references
in one console edit. Keep the direct key, endpoint if approved, 50m timeout,
shadow mode, $5/day cap, 20 RPM, schedules and every other setting unchanged.
Observe the next scheduled run; do not reset attempts, reopen exhausted events
or trigger replay/spend. Any catch-up outside existing automatic retries needs
separate approval.

## Rollback

Record the pre-change image and reference names/version numbers for each job.
If the source must be rolled back, restore the previous image on both Alerts
and Daily, but retain direct-key routing: restoring the unreachable integration
references would deliberately restore the known connection failure.
Image 1639c2d additionally restores known GERI compatibility and old storage
writer bugs; it is not a healthy v1.2 fallback.
No data, selector or customer-message rollback is performed by this procedure.
