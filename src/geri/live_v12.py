"""Private intraday v1.2; previous-day state, never yesterday's daily anchor."""
from datetime import datetime,time,timedelta,timezone
from copy import deepcopy
import json
from statistics import mean
from src.db.db import get_cursor
from src.geri.types import INDEX_ID,get_band
from src.geri.compute import compute_components
from src.geri.version12 import history_for,calculate_day,compute_day
from src.geri.v12_math import RAW_FIELDS


def fraction_before(alerts,cutoff):
    if not alerts:return None
    n=sum(a.created_at.replace(tzinfo=timezone.utc).time()<=cutoff for a in alerts)
    return n/len(alerts)


def cumulative_share(day,cutoff,prior_alerts,healthy_dates):
    """Prior 28 complete UTC dates only; same weekday only with >=4 usable days."""
    candidates=[(d,alerts) for d,alerts in prior_alerts.items()
                if day-timedelta(days=28)<=d<day and d in healthy_dates and alerts]
    same=[x for x in candidates if x[0].weekday()==day.weekday()]
    used=same if len(same)>=4 else candidates
    shares=[fraction_before(a,cutoff) for _,a in used]
    estimate=mean(shares) if shares else .25
    return max(.25,estimate),{"observations":len(shares),"same_weekday":len(same)>=4,
                              "floor":.25,"dates":[str(d) for d,_ in used]}


def estimate(at,alerts,rows,history,prior_alerts,healthy_dates,previous_live=None,complete=False,
             quality="OK",transition_seconds=None):
    """Pure replay/production kernel. Boundary hold does not change daily state."""
    at=at.replace(tzinfo=timezone.utc) if at.tzinfo is None else at.astimezone(timezone.utc)
    day=at.date()
    cutoff=at.time().replace(tzinfo=None)
    accepted=alerts if complete else [
        a for a in alerts if (a.created_at.replace(tzinfo=timezone.utc)
                             if a.created_at.tzinfo is None else
                             a.created_at.astimezone(timezone.utc))<=at]
    share,share_info=(1.,{"complete":True}) if complete else cumulative_share(
        day,cutoff,prior_alerts,healthy_dates)
    raw=[getattr(compute_components(accepted),f) for f in RAW_FIELDS]
    raw[0]/=share
    row=calculate_day(day,accepted,quality,rows,history,raw_override=raw)
    # A new day's cumulative sample is not an instantaneous replacement for
    # yesterday's state. Blend raw *inputs*, not the Daily score or its EWMA
    # mathematics, over the first two covered hours. At completion this weight
    # is exactly one and the calculation is identical to final Daily.
    elapsed=(at-datetime.combine(day,time.min,timezone.utc)).total_seconds()
    elapsed=elapsed if transition_seconds is None else transition_seconds
    weight=1. if complete else min(1.,max(0.,elapsed/7200.))
    projected_raw=list(raw)
    if not complete and rows and weight<1:
        prior=rows[-1]["smoothing_state"]["transform_state"].get("ewma")
        if prior is not None:
            steady=list(prior)
            steady[0]*=row["smoothing_state"]["weekday_factor_H"]
            raw=[(1-weight)*old+weight*new for old,new in zip(steady,raw)]
            row=calculate_day(day,accepted,quality,rows,history,raw_override=raw)
    row["metadata"]={"pro_rating_share":share,"share_inputs":share_info,
                     "alerts_received":len(accepted),"complete":complete,
                     "transition_weight":weight,"projected_raw":projected_raw,
                     "boundary_hold":not accepted and previous_live is not None
                         and not complete and weight==0}
    row["metadata"]["previous_daily_value"]=(rows[-1]["value"] if rows and
        rows[-1]["smoothing_state"]["data_quality"]=="OK" else None)
    # No-alert midnight ticks continue the preceding Live output, never a daily
    # table anchor. As actual alerts arrive the model's own projection takes over.
    if row["metadata"]["boundary_hold"]:
        row["value"]=int(previous_live)
        row["band"]=get_band(row["value"]).value
    return row


def finalize_close(row):
    """Reconcile a stored closing tick, preserving its original in the ledger.

    This is an explicit later close revision, NOT a fabricated real-time tick.
    Every changed close is excluded using the existing prospective gate rule.
    Original midnight observations are never changed.
    """
    from src.geri.v12_history import exclude_correction
    if row["smoothing_state"].get("data_quality")=="UNAVAILABLE":
        return False
    day=row["date"]
    with get_cursor() as c:
        c.execute("SELECT pg_advisory_xact_lock(12013,%s)",(day.toordinal(),))
        c.execute("""SELECT * FROM geri_live_v12_shadow WHERE computed_at>=%s
            AND computed_at<%s ORDER BY computed_at DESC LIMIT 1 FOR UPDATE""",
            (day,day+timedelta(days=1)))
        old=c.fetchone()
        if not old or old["value"]==row["value"]:
            return False
        metadata={**old["metadata"],"complete":True,"finalized_close":True,
            "observed_value":old["metadata"].get("observed_value",old["value"]),
            "close_available_at":datetime.now(timezone.utc).isoformat(),
            "observation_date":str(day),"excluded_from_prospective":True,
            "smoothing_state":row["smoothing_state"]}
        new={**dict(old),"value":row["value"],"band":row["band"],
             "components":row["components"],"metadata":metadata}
        c.execute("""INSERT INTO geri_v12_revisions
            (index_date,old_payload,new_payload,reason,applied)
            VALUES(%s,%s::jsonb,%s::jsonb,%s,true)""",
            (day,json.dumps(dict(old),default=str),json.dumps(new,default=str),
             "Live final close reconciliation; original observation retained; private only"))
        c.execute("""UPDATE geri_live_v12_shadow SET value=%s,band=%s,
            components=%s::jsonb,metadata=%s::jsonb WHERE id=%s""",
            (new["value"],new["band"],json.dumps(new["components"],default=str),
             json.dumps(metadata,default=str),old["id"]))
        exclude_correction(c,day,{"table":"geri_live_v12_shadow",
            "reason":"final close reconciliation","old_value":old["value"],
            "new_value":row["value"],"original_observed_at":str(old["computed_at"])})
    return True


def persist(row,at,legacy_value,legacy_computed_at=None):
    row["metadata"]["legacy_value"]=legacy_value
    row["metadata"]["legacy_computed_at"]=str(legacy_computed_at) if legacy_computed_at else None
    if row["smoothing_state"]["data_quality"]=="UNAVAILABLE":
        row["value"]=None;row["band"]="UNAVAILABLE"
    with get_cursor() as c:
        c.execute("""INSERT INTO geri_live_v12_shadow
            (computed_at,value,legacy_value,band,components,metadata)
            VALUES(%s,%s,%s,%s,%s::jsonb,%s::jsonb) ON CONFLICT(computed_at) DO NOTHING""",
            (at,row["value"],legacy_value,row["band"],json.dumps(row["components"]),
             json.dumps({**row["metadata"],"smoothing_state":row["smoothing_state"]},default=str)))
    return row


def latest():
    with get_cursor(commit=False) as c:
        c.execute("SELECT * FROM geri_live_v12_shadow ORDER BY computed_at DESC LIMIT 1")
        r=c.fetchone()
    if not r:return None
    r=dict(r);r["value_raw"]=float(r["value"]) if r["value"] is not None else None
    r["model_version"]="geri_v1.2";r["methodology_version"]="v1.2"
    r["alert_count"]=r["metadata"].get("alerts_received",0)
    r["interpretation"]=r["metadata"].get("interpretation","")
    r["top_drivers"]=r["components"].get("top_drivers",[])
    r["top_regions"]=r["components"].get("top_regions",[])
    prev=r["metadata"].get("previous_daily_value")
    r["trend_vs_yesterday"]=r["value"]-prev if prev is not None and r["value"] is not None else None
    r["computed_at"]=r["computed_at"].astimezone(timezone.utc).replace(tzinfo=None)
    return r


def tick(legacy_value,at=None,legacy_computed_at=None):
    at=at or datetime.now(timezone.utc)
    if at.tzinfo is None:at=at.replace(tzinfo=timezone.utc)
    from src.geri.version12 import load_alert_days
    from src.geri.v12_history import FinalHealthPending,final_health,utc
    previous=latest()
    try:
        compute_day(at.date()-timedelta(days=1))
    except FinalHealthPending:
        # Do not publish a speculative Daily at midnight. Keep a clearly marked
        # carry-forward Live observation until the existing Daily health writer
        # has finalized yesterday. No second health writer is introduced.
        if not previous:
            return None
        row={"value":previous["value"],"band":previous["band"],
             "components":deepcopy(previous["components"]),
             "smoothing_state":deepcopy(previous["metadata"]["smoothing_state"]),
             "metadata":{**previous["metadata"],"awaiting_final_health":True,
                         "boundary_hold":True,"complete":False}}
        return persist(row,at,legacy_value,legacy_computed_at)
    rows,history=history_for(at.date())
    all_days=load_alert_days(at.date()-timedelta(days=28),at.date())
    prior={d:a for d,a in all_days.items() if d<at.date()}
    healthy={r["index_date"] for r in history if r["inputs"]["data_quality"]=="OK"}
    with get_cursor(commit=False) as c:
        health=final_health(c,at.date()-timedelta(days=1))
    origin=max(datetime.combine(at.date(),time.min,timezone.utc),utc(health["computed_at"]))
    row=estimate(at,all_days.get(at.date(),[]),rows,history,prior,healthy,
                 previous["value"] if previous else None,
                 transition_seconds=(at-origin).total_seconds())
    row["metadata"]["transition_origin"]=origin.isoformat()
    # No generated text while flag off. At cutover the same interpretation
    # routine receives the selected value and components; no prompt changes.
    from src.geri.model_selection import live_model
    if live_model()=="v1.2":
        from src.geri.live import generate_live_interpretation
        row["metadata"]["interpretation"]=generate_live_interpretation(
            value=row["value"],band=row["band"],
            top_drivers=row["components"].get("top_drivers",[]),
            top_regions=[r["region"] for r in row["components"].get("top_regions",[])[:3]],
            alert_count=row["metadata"]["alerts_received"],components=row["components"])
    return persist(row,at,legacy_value,legacy_computed_at)
