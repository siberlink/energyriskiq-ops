"""Regenerate an honest activation/checkpoint report and self-contained source ZIP."""
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

from .data import readonly_snapshot
from .step7_setup import ROOT,OUT
from src.risk.shadow_monitor import capture


def dump(name,value):
    (OUT/name).write_text(json.dumps(value,default=str,indent=2)+"\n")


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    status=capture()
    dump("operating_snapshot.json",status)
    with readonly_snapshot() as c:
        c.execute("SELECT * FROM risk_pipeline_v2_control WHERE singleton")
        control=dict(c.fetchone())
        dump("control.json",control)
        c.execute("SELECT * FROM risk_pipeline_v2_usage ORDER BY id")
        usage=[dict(r) for r in c.fetchall()]
        dump("request_usage_ledger.json",usage)
        c.execute("SELECT * FROM geri_shadow_daily ORDER BY index_date,variant")
        shadow=[dict(r) for r in c.fetchall()]
        dump("geri_shadow_daily.json",shadow)
        c.execute("""SELECT observed_at,checkpoint,payload FROM risk_pipeline_v2_monitor
            ORDER BY observed_at""")
        monitoring=[dict(r) for r in c.fetchall()]
        dump("monitoring_history.json",monitoring)
        c.execute("""SELECT count(*) AS users,
            count(*) FILTER(WHERE COALESCE(alert_email_enabled,true)) AS email_alert_enabled,
            count(*) FILTER(WHERE NULLIF(trim(telegram_chat_id),'') IS NOT NULL) AS telegram_connected
            FROM users""")
        dump("notification_settings_unchanged.json",dict(c.fetchone()))
    latest={}
    simulated={}
    for row in monitoring:
        if row["checkpoint"]=="risk_panel":
            day=str(row["observed_at"].date())
            latest[day]=row
            simulated.setdefault(day,set()).update(
                row["payload"]["saturation"].get("simulated_alert_keys",[]))
    daily=[{"date":day,"asof":row["observed_at"],
            "saturation":row["payload"]["saturation"],
            "unique_simulated_daily_alert_candidates":len(simulated[day]),
            "simulated_keys":sorted(simulated[day]),"customer_alerts_created":0}
           for day,row in sorted(latest.items())]
    dump("daily_saturation_and_simulated_alerts.json",daily)
    checkpoints={}
    for hours in (24,72):
        saved=[r for r in monitoring if r["checkpoint"]==f"{hours}h"]
        checkpoint=(saved[0] if saved else {
            "status":"not_due" if status["elapsed_hours"]<hours else "due_not_yet_observed",
            "due_at":control["activated_at"]+timedelta(hours=hours),
            "note":"Real elapsed-time checkpoint; no future figures invented."})
        dump(f"operating_report_{hours}h.json",checkpoint)
        checkpoints[str(hours)]=checkpoint
    proof=json.loads((OUT/"isolation_proof.json").read_text())
    activation=json.loads((OUT/"activation.json").read_text())
    tests=(OUT/"tests.log").read_text()
    prospective=[r for r in shadow if not r["inputs"].get("seed")]
    floors=control["calibration"]["floors"]
    source_names=set(subprocess.check_output(
        ["git","diff","--name-only"],text=True).splitlines())
    source_names.update(subprocess.check_output(
        ["git","ls-files","--others","--exclude-standard"],text=True).splitlines())
    source_names={p for p in source_names if p.startswith(("src/","scripts/","tests/","docs/",".github/"))}
    dump("files_changed.json",sorted(source_names))
    floor_table="\n".join(f"| {k} | {v:.6f} |" for k,v in sorted(floors.items()))
    summary=f"""# GERI Step 7 — isolated V2 shadow activation

CONFIDENTIAL — internal. Generated {datetime.now(timezone.utc).isoformat()}.

## Executive status

- Durable mode: **{control['mode']}**; activation: **{control['activated_at']}**.
- Production GitHub/app shared settings use shadow, old boolean false, $5/day,
  conservative 20 RPM. Customer cut-over is **not approved or performed**.
- Calibrated from **{control['calibration']['eligible_days']} eligible historical days**.
- Marked **{activation['new_skipped_stale']:,}** retryable events older than 30 days
  as skipped_stale; no deletion. Exhausted cohort remains **{status['attempts_exhausted']:,}**.
- Enriched since activation: **{status['enriched_since_activation']}**;
  fresh retryable queue: **{status['fresh_queue']:,}**.
- Today's charged-or-conservatively-reserved commitment: **${status['today_committed_usd']:.6f} / $5**.
- Genuine prospective rows so far: **{len(prospective)}**, excluding historical seeds.
- 24h checkpoint: **{checkpoints['24'].get('status','observed')}**;
  72h checkpoint: **{checkpoints['72'].get('status','observed')}**.

## A. Isolation and verification

Full legacy row-content fingerprints, row counts and max IDs match the activation
baseline after real recent-event enrichment and private risk scoring:

```json
{json.dumps(proof,indent=2)}
```

All three legacy statement-write probes were rejected. Private risk events and
snapshots were written. No regional/asset customer alerts were created. Full
pipeline dispatch is unit-tested with mocked network/ingestion stages; the real
production hourly ingestion/catch-up run is separately tracked in GitHub.
Do not confuse the unit orchestration proof with a completed live RSS ingestion.

Final recorded tests:

```text
{tests.strip()}
```

The initial regression attempt inherited activated shadow settings and performed
14 real recent-event enrichments before it was terminated. Their provider usage
was durably recorded under the shared budget. The lab now strips inherited mode
settings and blocks real HTTP in offline tests. These calls are included in the
usage ledger, not hidden or treated as simulated.

## B. Production runner and catch-up

The approved supervised catch-up was dispatched on the operations repository.
It serializes on the existing ingestion lock, rather than overlapping an older
job. GitHub activation/run metadata in this archive is the source for its latest
observed state. If it is still waiting/running, this report is an initial report,
not a claim that all roughly 4,900 events have finished.

Only retryable, trailing-seven-day events are eligible. Durable original-cohort
controls permit bounded hourly continuation after a budget reset; older cohorts
and exhausted attempts are not reopened. The report's initial tiny sample does
not establish sustained throughput.

Usage ledger includes every response's actual tokens and raw output, failures,
and any conservative ambiguous charges/reservations. Stated dollar values are
rate-based usage, not an invoice. Full operational counts are in
operating_snapshot.json; hourly rates, fresh delay and queue depth are not
extrapolated into fabricated 24h/72h observations.

The app must be **republished** to expose the updated production /ops/status and
replace old app entry points. Database protection and the GitHub shadow runtime
are independent of that publish. Existing older risk writers fail explicitly
against the guard instead of leaking new risk values to customers.

## C. Reference floors and saturation

Period: 2026-01-14 through 2026-06-03; coverage >=50%, with missing coverage
excluded. Reference percentile: {control['calibration']['percentile']}.
This is the frozen Step 6 timely hindsight reconstruction, not a historical
point-in-time predictive result. Each entity/window has a separate denominator.

| Entity and window | Reference floor |
| --- | ---: |
{floor_table}

Full distributions, eligible dates, source hashes and provenance are retained in
reference_floors.json and control.json. Daily saturation and simulated unique
alert fingerprints are in daily_saturation_and_simulated_alerts.json.
Simulations use the existing >=70 threshold, >=90 severity-5 rule, and regional
+20% change condition against preceding private state. They assume the alert
generator is evaluated after private panels; daily keys are deduplicated. They
are not actual delivered alert counts and do not update public alert_state.

## D. Prospective private GERI

Variants: prod, integrity_v1, rel41, pillars_v2_continuous,
pillars_v2_continuous_rel41. Each candidate uses its own seeded history with
production health exclusions. GPT-4.1 labels use the unchanged Step 5 rubric and
cache identity. No storyline scoring deduplication.

Historical normalization seeds are explicitly marked seed=true. They are not
new prospective observations. A new day requires an actual published reference,
production health, exact-date private risk inputs and completed relevance labels.
The first full day is after activation; the partial activation date and later
reconstructions are excluded from prospective bootstrap comparisons.

At report time, absence of prospective rows is **pending**, not a zero-valued
signal. See geri_shadow_daily.json for all seeds/first observations, and
prospective_comparison.json for available observation counts. Run:

    python -m scripts.geri_lab.step7_compare

This uses Step 5's weekly paired bootstrap, with H1/H2 covering the prospective
interval only. No predictive improvement claim is possible yet.

## E. 24h / 72h reports and stability assessment

The true due times are recorded in operating_report_24h.json and
operating_report_72h.json. The private hourly monitor captures the first actual
observation after each due time and preserves its real timestamp. Regenerate:

    python scripts/geri_shadow_job.py monitor
    python -m scripts.geri_lab.package_step7

24h/72h will help establish capacity, delays, budget discipline, retries and
saturation. They cannot by themselves validate forward price prediction.
Before considering live, require sustained fresh-event coverage, stable
operating costs, no unexplained risk saturation, complete 7/30-day accumulation,
and adequately powered prospective market observations across independent weeks.
Any assessment now is **not ready for customer cut-over**.

## What a later cut-over would affect (separate approval)

| Consumer | Current isolation | Effect requiring review at cut-over |
| --- | --- | --- |
| Regional/asset risk APIs and dashboards | Legacy tables remain frozen | Timely calibrated scores replace stale legacy values |
| Alert generator | No V2 risk source | New regional/asset candidates and historical-state/cooldown behavior |
| Telegram and email | No V2 risk alerts; email pause preserved | Risk-alert volume could change; paid email policy remains separate |
| Public/paid digest and intelligence reports | No private-table reads | New alert composition could affect content and caches |
| GERI Daily/Live | Published values not replaced | New risk alerts could affect legacy R/A; candidate formulas need separate approval |
| EERI / EGSI | No private-table reads | Any alert-derived overlay needs consumer-specific replay; storage fundamentals are not replaced |
| Brent forecast and ERIQ | Continue existing public inputs/context | Indirect changes through upstream indices/risk context need validation |
| Private shadow variants | Non-public only | Must never become public through a mode-only toggle |

## Reproduction, safety and outstanding elapsed-time work

See docs/GERI_PIPELINE_V2_SHADOW.md in source/ for exact controls and source
locations. No public page redesign, customer email, Telegram, billing or report
template changes were made for this activation.

Keep guards active when pausing. Do NOT set the durable control row to off/live
or drop guards as a rollback: newly enriched events could saturate legacy maxima.
Review the actual 24h and 72h operating reports when due. Do not reset the 1,109
exhausted events or process older cohorts under this approval.
"""
    (OUT/"REPORT.md").write_text(summary)
    package=ROOT/"reports/geri_lab/GERI_Step7_Pipeline_V2_Shadow_Activation_Report.zip"
    source_paths=set(source_names)
    # Include prerequisite runtime sources, not just the local diff.
    payload=OUT/"github_tree_payload.json"
    if payload.exists():
        source_paths.update(row["path"] for row in json.loads(payload.read_text()))
    source_paths.update({"scripts/geri_lab/package_step7.py","scripts/geri_lab/conftest.py",
                         "docs/GERI_PIPELINE_V2_SHADOW.md","tests/test_risk_shadow_mode.py"})
    members={}
    for p in OUT.iterdir():
        if p.is_file() and p.name not in {"github_tree_payload.json","MANIFEST_SHA256.json"}:
            members["report/"+p.name]=p
    for name in sorted(source_paths):
        p=ROOT/name
        if p.is_file():
            members["source/"+name]=p
    manifest={name:{"bytes":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()}
              for name,p in members.items()}
    dump("MANIFEST_SHA256.json",manifest)
    with zipfile.ZipFile(package,"w",zipfile.ZIP_DEFLATED) as z:
        for name,p in sorted(members.items()):
            z.write(p,name)
        z.write(OUT/"MANIFEST_SHA256.json","MANIFEST_SHA256.json")
    with zipfile.ZipFile(package) as z:
        assert z.testzip() is None
    print(json.dumps({"zip":str(package.relative_to(ROOT)),"bytes":package.stat().st_size,
                      "files":len(members)+1,"prospective_rows":len(prospective)},indent=2))


if __name__=="__main__":
    main()
