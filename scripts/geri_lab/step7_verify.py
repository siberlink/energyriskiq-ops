"""Capture isolation fingerprints and verify statement-level legacy write guards."""
import argparse
import json
from pathlib import Path

from .data import readonly_snapshot
from .step7_setup import OUT


def capture():
    value={}
    with readonly_snapshot() as c:
        for table in ("risk_events","risk_indices","asset_risk"):
            c.execute(f"""SELECT count(*) AS rows,max(id) AS max_id,
                md5(COALESCE(string_agg(row_to_json(t)::text,'' ORDER BY id),'')) AS content_md5
                FROM {table} t""")
            value[table]=dict(c.fetchone())
        c.execute("""SELECT count(*) AS rows,md5(COALESCE(string_agg(
            row_to_json(t)::text,'' ORDER BY index_id,date,id),'')) AS content_md5
            FROM intel_indices_daily t""")
        value["published_daily"]=dict(c.fetchone())
        c.execute("""SELECT count(*) AS rows,md5(COALESCE(string_agg(
            row_to_json(t)::text,'' ORDER BY id),'')) AS content_md5
            FROM events t WHERE NOT processed AND ai_attempts>=3""")
        value["exhausted_events"]=dict(c.fetchone())
        c.execute("""SELECT alert_type,count(*) AS rows,max(id) AS max_id FROM alert_events
            WHERE alert_type IN ('REGIONAL_RISK_SPIKE','ASSET_RISK_SPIKE')
            GROUP BY alert_type ORDER BY alert_type""")
        value["risk_alerts"]=[dict(r) for r in c.fetchall()]
    return value


def guard_proof():
    from src.db.db import get_connection
    result={}
    with get_connection() as conn:
        with conn.cursor() as c:
            for table in ("risk_events","risk_indices","asset_risk"):
                c.execute("SAVEPOINT guard_probe")
                try:
                    # BEFORE STATEMENT executes even when no rows match.
                    c.execute(f"UPDATE {table} SET id=id WHERE false")
                    result[table]="FAILED: write statement was admitted"
                except Exception as exc:
                    result[table]="blocked" if "Legacy risk writes blocked" in str(exc) else type(exc).__name__
                finally:
                    c.execute("ROLLBACK TO SAVEPOINT guard_probe")
        conn.rollback()
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument("phase",choices=["before","after"])
    args=p.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    value=capture()
    (OUT/f"fingerprints_{args.phase}.json").write_text(json.dumps(value,default=str,indent=2))
    if args.phase=="after":
        before=json.loads((OUT/"fingerprints_before.json").read_text())
        result={key:value[key]==before[key] for key in value}
        result["write_guards"]=guard_proof()
        with readonly_snapshot() as c:
            for table in ("risk_events_v2","risk_indices_v2","asset_risk_v2"):
                c.execute(f"SELECT count(*) AS rows,max(id) AS max_id FROM {table}")
                result[table]=dict(c.fetchone())
        (OUT/"isolation_proof.json").write_text(json.dumps(result,default=str,indent=2))
        if not all(result[k] for k in ("risk_events","risk_indices","asset_risk","published_daily","exhausted_events")):
            raise RuntimeError("Isolation fingerprints differ; stop activation")
        if set(result["write_guards"].values())!={"blocked"}:
            raise RuntimeError("A legacy writer is not protected")
        print(json.dumps(result,default=str))
    else:
        print(json.dumps(value,default=str))


if __name__=="__main__":
    main()
