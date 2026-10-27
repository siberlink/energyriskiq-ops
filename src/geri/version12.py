"""Staged GERI v1.2: causal weekday/raw EWMA, own history, no private LLM."""
from datetime import date,datetime,timedelta,timezone
import json
import logging
from psycopg2.extras import execute_values
from src.db.db import get_cursor
from src.geri.types import INDEX_ID,get_band
from src.geri.compute import compute_components
from src.geri.v12_math import RAW_FIELDS,NORMAL_FIELDS,PILLARS,vector

log=logging.getLogger(__name__)
MODEL="geri_v1.2"
UP_SQL="""
CREATE TABLE IF NOT EXISTS intel_indices_daily_v12
 (LIKE intel_indices_daily INCLUDING ALL);
CREATE SEQUENCE IF NOT EXISTS geri_v12_id_seq;
ALTER SEQUENCE geri_v12_id_seq OWNED BY intel_indices_daily_v12.id;
ALTER TABLE intel_indices_daily_v12 ALTER COLUMN id SET DEFAULT nextval('geri_v12_id_seq');
ALTER TABLE intel_indices_daily_v12 ADD COLUMN IF NOT EXISTS smoothing_state JSONB NOT NULL DEFAULT '{}';
ALTER TABLE intel_indices_daily_v12 ADD COLUMN IF NOT EXISTS backfilled BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE intel_indices_daily_v12 ADD COLUMN IF NOT EXISTS backfilled_at TIMESTAMPTZ;
CREATE TABLE IF NOT EXISTS geri_v12_revisions (
 id BIGSERIAL PRIMARY KEY,index_date DATE NOT NULL,old_payload JSONB,new_payload JSONB NOT NULL,
 reason TEXT NOT NULL CHECK(length(trim(reason))>0),applied BOOLEAN NOT NULL DEFAULT FALSE,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS geri_v12_ops (
 index_date DATE NOT NULL,kind TEXT NOT NULL,details JSONB NOT NULL,
 observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),PRIMARY KEY(index_date,kind));
CREATE TABLE IF NOT EXISTS geri_live_v12_shadow (
 id BIGSERIAL PRIMARY KEY,computed_at TIMESTAMPTZ NOT NULL,value INTEGER,
 legacy_value INTEGER,band TEXT,components JSONB NOT NULL,metadata JSONB NOT NULL,
 UNIQUE(computed_at));
"""


def migrate():
    with get_cursor() as c:c.execute(UP_SQL)


def history_for(day):
    with get_cursor(commit=False) as c:
        c.execute("""SELECT * FROM intel_indices_daily_v12 WHERE index_id=%s
            AND date>=%s AND date<%s ORDER BY date""",(INDEX_ID,day-timedelta(days=90),day))
        rows=[dict(r) for r in c.fetchall()]
    history=[]
    for r in rows:
        s=r["smoothing_state"]
        history.append({"index_date":r["date"],"components":s["normalized_raw"],
                        "inputs":{"original_raw":s["original_raw"],"data_quality":s["data_quality"]}})
    return rows,history


def health_for(day):
    from src.geri.health import load_health_counts,evaluate_day
    with get_cursor(commit=False) as c:
        from src.geri.health_finalization import is_provisional
        c.execute("SELECT * FROM geri_daily_health WHERE index_date=%s",(day,))
        recorded=c.fetchone()
        if recorded and not is_provisional(recorded):
            return dict(recorded)
        counts,events,first=load_health_counts(c,day,day)
        return evaluate_day(day,counts,events,first)


def calculate_day(day,alerts,quality,rows,history,raw_override=None):
    raw_components=compute_components(alerts)
    original=raw_override or [getattr(raw_components,f) for f in RAW_FIELDS]
    if rows and rows[-1]["date"]!=day-timedelta(days=1):
        raise ValueError("v1.2 requires the immediately preceding daily smoothing state")
    previous=rows[-1]["smoothing_state"]["transform_state"] if rows else None
    value,output,state,diag=vector(day,quality,original,history,previous)
    for p,f,n in zip(PILLARS,RAW_FIELDS,NORMAL_FIELDS):
        setattr(raw_components,f,output["raw_"+p])
        setattr(raw_components,n,output["norm_"+p])
    raw_components.insufficient_history=diag["fallback_used"]
    components=raw_components.to_dict()
    previous_values=[r["value"] for r in reversed(rows) if r["smoothing_state"]["data_quality"]=="OK"]
    from src.geri.normalize import calculate_trends
    trend1,trend7=calculate_trends(value,previous_values[:7])
    return {"index_id":INDEX_ID,"date":day,"value":value,"band":get_band(value).value,
            "trend_1d":trend1,"trend_7d":trend7,"components":components,"model_version":MODEL,
            "interpretation":"","smoothing_state":{
                "transform_state":state,"original_raw":list(original),"normalized_raw":output,
                "data_quality":quality,"alert_ids":[a.id for a in alerts],
                "baseline_dates":[str(r["index_date"]) for r in history
                                  if r["inputs"]["data_quality"]=="OK"],
                "inputs_used":diag,"weekday_factor_H":state["weekday_factor"]}}


def store(row,backfilled=False,reason=None,apply_revision=False):
    if apply_revision and not (reason and reason.strip()):
        raise ValueError("Applying a v1.2 revision requires a nonempty reason")
    with get_cursor() as c:
        # Transaction lock serializes first publication and revisions for this date.
        c.execute("SELECT pg_advisory_xact_lock(12012,%s)",(row["date"].toordinal(),))
        c.execute("SELECT * FROM intel_indices_daily_v12 WHERE index_id=%s AND date=%s FOR UPDATE",
                  (INDEX_ID,row["date"]))
        old=c.fetchone()
        if reason:
            c.execute("""INSERT INTO geri_v12_revisions(index_date,old_payload,new_payload,reason,applied)
                VALUES(%s,%s::jsonb,%s::jsonb,%s,%s)""",
                (row["date"],json.dumps(old,default=str) if old else None,
                 json.dumps(row,default=str),reason.strip(),apply_revision))
        if (old or reason) and not apply_revision:return False
        fields=["index_id","date","value","band","trend_1d","trend_7d",
                "components","model_version","interpretation","smoothing_state"]
        params=[json.dumps(row[k],default=str) if k in ("components","smoothing_state") else row[k]
                for k in fields]
        sql=f"""INSERT INTO intel_indices_daily_v12({','.join(fields)},backfilled,backfilled_at)
            VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s::jsonb,%s,%s)
            ON CONFLICT(index_id,date) """
        sql+=("DO UPDATE SET "+",".join(f"{f}=EXCLUDED.{f}" for f in fields[2:])+
              ",computed_at=now()" if apply_revision else "DO NOTHING")
        c.execute(sql,params+[backfilled,datetime.now(timezone.utc) if backfilled else None])
    return True


def parity_monitor(day):
    with get_cursor() as c:
        c.execute("""SELECT v.value,s.value AS shadow_value FROM intel_indices_daily_v12 v
            LEFT JOIN geri_shadow_daily s ON s.index_date=v.date AND s.variant='wk_carry15'
            WHERE v.index_id=%s AND v.date=%s""",(INDEX_ID,day))
        r=c.fetchone()
        if not r:return None
        status="pending_shadow" if r["shadow_value"] is None else (
            "match" if r["value"]==r["shadow_value"] else "MISMATCH")
        c.execute("""INSERT INTO geri_v12_ops(index_date,kind,details) VALUES(%s,'parity',%s::jsonb)
            ON CONFLICT(index_date,kind) DO UPDATE SET details=EXCLUDED.details,observed_at=now()""",
            (day,json.dumps({"status":status,**dict(r)})))
        if status=="MISMATCH":log.critical("INTERNAL GERI v1.2/shadow mismatch: %s %s",day,dict(r))
    return status


def compute_day(day,force=False,reason=None,apply_revision=False):
    if day>=datetime.now(timezone.utc).date():
        raise ValueError("Daily v1.2 requires a closed UTC day")
    if force and not (reason and reason.strip()):
        raise ValueError("Forced v1.2 computation requires a reason")
    with get_cursor(commit=False) as c:
        c.execute("SELECT * FROM intel_indices_daily_v12 WHERE index_id=%s AND date=%s",(INDEX_ID,day))
        old=c.fetchone()
    if old and not force:
        parity_monitor(day)
        return dict(old)
    from src.geri.repo import get_alerts_for_date
    rows,history=history_for(day)
    if not rows and day>date(2026,1,14):
        raise ValueError("Missing v1.2 historical seed; refusing cold restart")
    alerts=get_alerts_for_date(day)
    row=calculate_day(day,alerts,health_for(day)["data_quality"],rows,history)
    from src.geri.model_selection import published_model
    if published_model()=="v1.2" and row["smoothing_state"]["data_quality"]!="UNAVAILABLE":
        from src.geri.interpretation import generate_interpretation
        row["interpretation"]=generate_interpretation(
            value=row["value"],band=row["band"],top_drivers=row["components"].get("top_drivers",[]),
            top_regions=[r["region"] for r in row["components"].get("top_regions",[])[:3]],
            index_date=day.isoformat(),components=row["components"])
        row["components"]["interpretation"]=row["interpretation"]
    store(row,reason=reason if force else None,apply_revision=apply_revision)
    parity_monitor(day)
    return row


def load_alert_days(start,end):
    from src.geri.types import VALID_ALERT_TYPES
    from src.geri.repo import AlertRecord
    from src.geri.health import utc_bounds
    lo,_=utc_bounds(start);_,hi=utc_bounds(end)
    with get_cursor(commit=False) as c:
        c.execute("""SELECT id,alert_type,severity,confidence AS risk_score,scope_region AS region,
            created_at,headline,body,raw_input FROM alert_events
            WHERE alert_type=ANY(%s) AND created_at>=%s AND created_at<%s
            ORDER BY created_at,id""",(VALID_ALERT_TYPES,lo,hi))
        records=c.fetchall()
    output={}
    for r in records:
        raw=r["raw_input"] or {}
        if isinstance(raw,str):raw=json.loads(raw)
        category=raw.get("category")
        if not category and raw.get("driver_events"):category=raw["driver_events"][0].get("category")
        a=AlertRecord(id=r["id"],alert_type=r["alert_type"],severity=r["severity"],
            risk_score=float(r["risk_score"]) if r["risk_score"] is not None else None,
            region=r["region"],weight=1.,created_at=r["created_at"],headline=r["headline"],
            body=r["body"],category=category)
        output.setdefault(a.created_at.date(),[]).append(a)
    return output
