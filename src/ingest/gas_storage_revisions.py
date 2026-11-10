"""Seven-provider-gas-day refresh, provenance and measurement-only revisions."""
import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from src.db.db import get_cursor
from src.ingest.gie_agsi import (
    _make_api_request, fetch_eu_storage_data, normalize_storage_entry,
    MAJOR_EU_COUNTRIES, COUNTRY_NAMES,
    select_eu_entry,
)

logger = logging.getLogger(__name__)
SCHEMA = """
CREATE TABLE IF NOT EXISTS gas_storage_revision_log (
    id BIGSERIAL PRIMARY KEY,
    area TEXT NOT NULL,
    gas_day DATE NOT NULL,
    old_values JSONB,
    new_values JSONB NOT NULL,
    status TEXT,
    provider_updated_at TEXT,
    changed_fields JSONB NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""


def run_storage_revision_migration():
    with get_cursor() as cur:
        cur.execute(SCHEMA)
    managed = os.environ.get("DATABASE_URL")
    if managed and managed != os.environ.get("PRODUCTION_DATABASE_URL"):
        import psycopg2
        with psycopg2.connect(managed, connect_timeout=15) as conn:
            with conn.cursor() as cur:
                cur.execute(SCHEMA)


def _raw(row):
    value = (row or {}).get("raw_data") or {}
    return json.loads(value) if isinstance(value, str) else value


def _existing(cur, area, day, locked=False):
    if area == "EU":
        cur.execute(
            "SELECT date,eu_storage_percent,raw_data FROM gas_storage_snapshots "
            "WHERE COALESCE(NULLIF(raw_data->>'gasDayStart','')::date,"
            "NULLIF(raw_data->>'date','')::date,date)=%s "
            "ORDER BY date DESC LIMIT 1" + (" FOR UPDATE" if locked else ""), (day,))
    else:
        cur.execute(
            "SELECT date,storage_percent,gas_in_storage_twh,working_gas_volume_twh,"
            "injection_twh,withdrawal_twh,trend,raw_data FROM gas_storage_country_snapshots "
            "WHERE level='country' AND country_code=%s AND date=%s "
            "AND operator_code='' AND facility_code=''" + (" FOR UPDATE" if locked else ""), (area,day))
    return cur.fetchone()


def values(row, area):
    if row is None:
        return None
    raw = _raw(row)
    result = {"full_percent":float(row["eu_storage_percent" if area=="EU" else "storage_percent"])}
    for name in ["gas_in_storage_twh","working_gas_volume_twh","injection_twh","withdrawal_twh","trend","consumption_twh"]:
        v = raw.get(name) if area=="EU" or name=="consumption_twh" else row.get(name)
        result[name] = float(v) if v is not None else None
    for name in ["gasDayStart","status","updatedAt"]:
        result[name] = raw.get(name)
    return result


def _new_values(data, old=None):
    result = {name:data.get(name) for name in [
        "full_percent","gas_in_storage_twh","working_gas_volume_twh","injection_twh",
        "withdrawal_twh","trend","consumption_twh","gasDayStart","status","updatedAt"]}
    if "updatedAt" not in data:
        result["updatedAt"] = (old or {}).get("updatedAt")
    return result


def changes(old, new):
    return {key:{"old":(old or {}).get(key),"new":value} for key,value in new.items()
            if old is None or (old or {}).get(key)!=value}


def runtime_identity():
    """Build metadata is baked into COPY src, never taken from a mutable image tag."""
    path = Path(__file__).with_name("storage_build_info.json")
    info = json.loads(path.read_text()) if path.exists() else {}
    return {
        "triggered_by": os.environ.get("CLOUD_RUN_JOB") or "website_or_manual",
        "execution": os.environ.get("CLOUD_RUN_EXECUTION"),
        "git_sha": info.get("commit") or os.environ.get("GITHUB_SHA"),
        "image": info.get("image"),
    }


def _timestamp(value):
    if not value:
        return None
    stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp


def _stale(data, row):
    stored = _timestamp(_raw(row).get("updatedAt"))
    incoming = _timestamp(data.get("updatedAt"))
    # Unknown freshness cannot replace a timestamped observation either.
    return stored is not None and (incoming is None or incoming < stored)


def _validate(data):
    day = data.get("gasDayStart")
    if not day or str(day) != str(data.get("date")):
        raise ValueError("Provider gasDayStart is required and must match the gas day")
    date.fromisoformat(str(day))
    if data.get("status") not in ("E", "C"):
        raise ValueError("Provider E/C status is required")


def _record_revision(cur, area, data, old):
    new = _new_values(data, old)
    changed = changes(old, new)
    cur.execute("""
        INSERT INTO gas_storage_revision_log
        (area,gas_day,old_values,new_values,status,provider_updated_at,changed_fields)
        VALUES(%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s::jsonb) RETURNING id
    """, (area, data["date"], json.dumps(old),
          json.dumps({**new, "_writer": runtime_identity()}), data.get("status"),
          data.get("updatedAt"), json.dumps(changed)))
    return {"id": cur.fetchone()["id"], "area": area, "gas_day": data["date"],
            "old": old, "new": new, "flag": data.get("status"), "changed_fields": changed}


def _audit_refresh(cur, plan, result):
    # Existing job_runs schema: run_key carries JSON provenance, with a unique nonce.
    identity = {**runtime_identity(), "audit_id": str(uuid4()), "stage": "storage_refresh",
                "gas_days": [plan.get("start"), plan["end"]], **result}
    cur.execute("""
        INSERT INTO job_runs(job_name,index_date,finished_at,status,run_key)
        VALUES('gas_storage_refresh',%s,NOW(),%s,%s)
    """, (plan["end"], "partial" if plan["errors"] else "success",
          json.dumps(identity, default=str, sort_keys=True)))
    # A REFRESH is an audit event, not a provider observation/value revision.
    cur.execute("""
        INSERT INTO gas_storage_revision_log
        (area,gas_day,new_values,status,changed_fields)
        VALUES('REFRESH',%s,%s::jsonb,%s,'{}'::jsonb)
    """, (plan["end"], json.dumps(identity, default=str, sort_keys=True),
          "PARTIAL" if plan["errors"] else "OK"))
    return identity


def prepare_revision_plan(countries=None, end_day=None):
    """Only provider GETs and DB SELECTs. Never extrapolates or substitutes dates."""
    head = fetch_eu_storage_data()
    if not head:
        raise RuntimeError("AGSI+ did not return an authoritative EU gas day")
    end = date.fromisoformat(head["date"])
    if end_day:
        end = min(end, date.fromisoformat(str(end_day)))
    start = end-timedelta(days=6)
    observations=[]; errors=[]
    for area in ["EU"]+list(countries or MAJOR_EU_COUNTRIES):
        params={"from":str(start),"to":str(end),"size":30}
        if area!="EU":
            params["country"]=area
        if area=="EU":
            # /api/eu returns an empty dataset for from/to, despite HTTP 200.
            # Its single-date requests do return the requested provider gas day.
            entries=[]
            for i in range(7):
                response=_make_api_request("eu",{"date":str(start+timedelta(days=i))})
                entry=select_eu_entry((response or {}).get("data") or [])
                if entry:
                    entries.append(entry)
        else:
            response=_make_api_request("",params)
            entries=(response or {}).get("data") or []
        days={}
        for entry in entries:
            data=normalize_storage_entry(entry,area)
            if data and start<=date.fromisoformat(data["date"])<=end:
                try:
                    _validate(data)
                except ValueError as exc:
                    logger.warning("AGSI_REJECT area=%s gas_day=%s reason=%s", area, data["date"], exc)
                    continue
                if area!="EU":
                    data["country"]=area
                if data["date"] in days and _stale(data, {"raw_data": days[data["date"]]}):
                    logger.warning("AGSI_STALE_REJECT duplicate area=%s gas_day=%s", area, data["date"])
                    continue
                days[data["date"]]=data
        missing=[str(start+timedelta(days=i)) for i in range(7) if str(start+timedelta(days=i)) not in days]
        if missing:
            errors.append({"area":area,"missing_gas_days":missing})
            logger.warning("AGSI revision refresh area=%s missing_days=%s",area,missing)
        observations.extend({"area":area,"data":days[day]} for day in sorted(days))
    with get_cursor(commit=False) as cur:
        for obs in observations:
            old=values(_existing(cur,obs["area"],obs["data"]["date"]),obs["area"])
            obs["old"]=old
            obs["new"]=_new_values(obs["data"], old)
            obs["changes"]=changes(old,obs["new"])
    return {"start":str(start),"end":str(end),"observations":observations,"errors":errors}


def _write_observation(cur, area, data, row):
    _validate(data)
    if _stale(data, row):
        logger.warning("AGSI_STALE_REJECT area=%s gas_day=%s stored=%s incoming=%s",
                       area, data["date"], _raw(row).get("updatedAt"), data.get("updatedAt"))
        return False
    raw = dict(data)
    # Missing optional fields must not erase previously recorded provenance.
    if not raw.get("updatedAt"):
        raw.pop("updatedAt", None)
    if area=="EU" and row:
        # Preserve all existing dates, scores, bands and scoring-derived columns.
        cur.execute("""
            UPDATE gas_storage_snapshots SET eu_storage_percent=%s,
            raw_data=COALESCE(raw_data,'{}'::jsonb) || %s::jsonb
            WHERE date=%s AND
            (NULLIF(raw_data->>'updatedAt','') IS NULL OR
             %s::timestamptz >= NULLIF(raw_data->>'updatedAt','')::timestamptz)
        """, (data["full_percent"], json.dumps(raw), row["date"], data.get("updatedAt")))
    elif area=="EU":
        raise RuntimeError("New EU observations belong to the existing capture/scoring writer")
    else:
        cur.execute("""
            INSERT INTO gas_storage_country_snapshots
            (date,level,country_code,country_name,operator_code,facility_code,storage_percent,
             gas_in_storage_twh,working_gas_volume_twh,injection_twh,withdrawal_twh,trend,raw_data)
            VALUES (%s,'country',%s,%s,'','',%s,%s,%s,%s,%s,%s,%s::jsonb)
            ON CONFLICT(date,level,country_code,operator_code,facility_code) DO UPDATE SET
             storage_percent=EXCLUDED.storage_percent,gas_in_storage_twh=EXCLUDED.gas_in_storage_twh,
             working_gas_volume_twh=EXCLUDED.working_gas_volume_twh,injection_twh=EXCLUDED.injection_twh,
             withdrawal_twh=EXCLUDED.withdrawal_twh,trend=EXCLUDED.trend,
             raw_data=COALESCE(gas_storage_country_snapshots.raw_data,'{}'::jsonb) || EXCLUDED.raw_data
            WHERE NULLIF(gas_storage_country_snapshots.raw_data->>'updatedAt','') IS NULL
               OR NULLIF(EXCLUDED.raw_data->>'updatedAt','')::timestamptz >=
                  NULLIF(gas_storage_country_snapshots.raw_data->>'updatedAt','')::timestamptz
        """,(data["date"],area,COUNTRY_NAMES.get(area,area),data["full_percent"],
             data["gas_in_storage_twh"],data["working_gas_volume_twh"],data["injection_twh"],
             data["withdrawal_twh"],data["trend"],json.dumps(raw)))
    if cur.rowcount == 0:
        logger.warning("AGSI_STALE_REJECT concurrent area=%s gas_day=%s", area, data["date"])
        return False
    return True


def apply_revision_plan(plan, backup=False):
    run_storage_revision_migration()
    revisions=[]
    deferred=[]
    rejected=[]
    with get_cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(%s,%s)",(82633,0))
        if backup:
            cur.execute("CREATE TABLE IF NOT EXISTS gas_storage_countries_backup_20261110 AS "
                        "SELECT * FROM gas_storage_country_snapshots")
            cur.execute("CREATE TABLE IF NOT EXISTS gas_storage_eu_backup_20261110 AS "
                        "SELECT * FROM gas_storage_snapshots")
        for obs in plan["observations"]:
            area=obs["area"];data=obs["data"]
            row=_existing(cur,area,data["date"],locked=True)
            if area=="EU" and row is None:
                deferred.append(data["date"])
                logger.info("AGSI new EU gas day %s deferred to normal capture/scoring writer",data["date"])
                continue
            old=values(row,area);new=_new_values(data, old);changed=changes(old,new)
            if not changed:
                continue
            if not _write_observation(cur,area,data,row):
                rejected.append({"area": area, "gas_day": data["date"]})
                continue
            revisions.append(_record_revision(cur, area, data, old))
        if revisions:
            cur.execute("DELETE FROM gas_storage_widget_daily_cache")
        identity = _audit_refresh(cur, plan, {"observations": len(plan["observations"]),
                                             "revisions": len(revisions), "rejected": rejected,
                                             "deferred_eu_days": deferred})
    logger.info("AGSI_REFETCH %s", json.dumps(identity, default=str, sort_keys=True))
    # Log committed changes only. No customer notifications.
    for revision in revisions:
        logger.info("AGSI_REVISION %s",json.dumps(revision,default=str,sort_keys=True))
    return {"success":len(plan["observations"])-len(deferred)-len(rejected),"failed":len(plan["errors"]),"skipped":len(deferred)+len(rejected),
            "deferred_eu_days":deferred,
            "stale_rejections":rejected,
            "data_date":plan["end"],"countries":list(dict.fromkeys(
                o["area"] for o in plan["observations"] if o["area"]!="EU")),
            "revision_count":len(revisions),"revisions":revisions,"errors":plan["errors"]}


def refresh_storage_revisions(countries=None):
    return apply_revision_plan(prepare_revision_plan(countries))


def write_eu_scoring_snapshot(conn, metrics):
    """Sole EU insert owner. Existing gas days retain all dates and risk fields."""
    from psycopg2.extras import RealDictCursor
    data = metrics["raw_data"]
    _validate(data)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT pg_advisory_xact_lock(%s,%s)", (82633, 0))
        row = _existing(cur, "EU", data["date"], locked=True)
        old = values(row, "EU")
        if row:
            if _stale(data, row):
                logger.warning("AGSI_STALE_REJECT area=EU gas_day=%s", data["date"])
                return False
            if not changes(old, _new_values(data, old)):
                return True
            if not _write_observation(cur, "EU", data, row):
                return False
        else:
            # This table's existing publication-date key is gas day + 1 (verified
            # against the last 30 rows). Keep it, never shift historical keys.
            # All provenance, deduplication and scoring use provider gasDayStart.
            cur.execute("""
                INSERT INTO gas_storage_snapshots
                (date,eu_storage_percent,seasonal_norm,deviation_from_norm,refill_speed_7d,
                 withdrawal_rate_7d,winter_deviation_risk,days_to_target,risk_score,risk_band,
                 interpretation,raw_data)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                ON CONFLICT(date) DO NOTHING
            """, (str(date.fromisoformat(data["date"]) + timedelta(days=1)),
                  data["full_percent"], metrics["seasonal_norm"],
                  metrics["deviation_from_norm"], metrics["refill_speed_7d"],
                  metrics["withdrawal_rate_7d"], metrics["winter_deviation_risk"],
                  metrics["days_to_target"], metrics["risk_score"], metrics["risk_band"],
                  metrics["interpretation"], json.dumps(data)))
            if cur.rowcount == 0:
                raise RuntimeError("EU publication date occupied by a different provider day; refusing date shift")
        revision = _record_revision(cur, "EU", data, old)
        cur.execute("DELETE FROM gas_storage_widget_daily_cache")
    # Caller owns transaction commit/rollback.
    return revision


def capture_storage(target_date):
    """Daily/website owner: seven-day EU+country refresh, then score NEW EU days."""
    from src.db.db import get_connection
    from src.scripts.backfill_snapshots import compute_gas_metrics
    plan = prepare_revision_plan(end_day=target_date)
    result = apply_revision_plan(plan)
    rows = {o["data"]["date"]: o["data"] for o in plan["observations"] if o["area"] == "EU"}
    inserted = []
    for day in result["deferred_eu_days"]:
        data = rows[day]
        metrics = compute_gas_metrics(data, date.fromisoformat(day).month)
        with get_connection() as conn:
            revision = write_eu_scoring_snapshot(conn, metrics)
            conn.commit()
        if revision:
            inserted.append(day)
            logger.info("AGSI_REVISION %s", json.dumps(revision, default=str, sort_keys=True))
    return {"status": "success" if not result["errors"] else "partial",
            "date": result["data_date"], "country_capture": result, "new_eu_gas_days": inserted}
