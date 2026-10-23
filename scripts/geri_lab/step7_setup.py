"""Explicit owner-approved installation, frozen calibration and history seeding."""
import argparse
import csv
from datetime import date, datetime
import json
from pathlib import Path

from src.db.db import get_cursor
from src.risk.shadow_schema import install
from src.geri.shadow_daily import code_sha, VARIANTS
from .step7_calibration import build

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/"reports/geri_lab/step7"
SEEDS = {"integrity_v1":"integrity_v1","rel41":"rel41_only",
         "pillars_v2_continuous":"pillars_continuous",
         "pillars_v2_continuous_rel41":"pillars_continuous_rel41"}


def seed():
    from psycopg2.extras import execute_values
    counts = {}
    with get_cursor() as c:
        c.execute("SELECT start_date FROM risk_pipeline_v2_control WHERE singleton")
        start = c.fetchone()["start_date"]
        for name, old in SEEDS.items():
            rows = list(csv.DictReader((ROOT/f"reports/geri_lab/step5/variants/{old}/series.csv").open()))
            records = []
            for r in rows:
                if date.fromisoformat(r["date"]) >= start:
                    continue
                components = {k:float(r[k]) for k in r if k.startswith(("raw_","norm_"))}
                # Match production's stored concentration precision boundary.
                components["raw_C"] = round(components["raw_C"],2)
                records.append(
                    (r["date"],name,int(r["geri"]),json.dumps(components),
                     json.dumps({"seed":True,"data_quality":r["data_quality"],
                                 "source_variant":old,"source":"frozen Step5 own replay",
                                 "hindsight_counterfactual":True}),code_sha()))
            execute_values(c,"""INSERT INTO geri_shadow_daily
                    (index_date,variant,value,components,inputs,code_sha)
                    VALUES %s ON CONFLICT DO NOTHING""",records,page_size=1000)
            counts[name] = len(records)
        # Reference seeds copy the actual published value, never a lab "prod".
        c.execute("""INSERT INTO geri_shadow_daily(index_date,variant,value,components,inputs,code_sha)
            SELECT date,'prod',value,'{}'::jsonb,
                jsonb_build_object('seed',true,'data_quality',COALESCE(h.data_quality,'MISSING')),
                %s FROM intel_indices_daily i LEFT JOIN geri_daily_health h ON h.index_date=i.date
            WHERE i.index_id='global:geo_energy_risk' AND i.date<%s
            ON CONFLICT DO NOTHING""",(code_sha(),start))
        counts["prod"] = c.rowcount
    return counts


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--activate",action="store_true")
    p.add_argument("--percentile",type=float,default=.90)
    args=p.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    calibration=build(ROOT,args.percentile)
    (OUT/"reference_floors.json").write_text(json.dumps(calibration,indent=2))
    if not args.activate:
        print(json.dumps({"calibration_only":True,"eligible_days":calibration["eligible_days"]}))
        return
    install()
    with get_cursor() as c:
        # Never reset the shadow start date or change calibration on a resumed run.
        c.execute("""INSERT INTO risk_pipeline_v2_control
            (singleton,mode,start_date,runner,calibration,code_sha)
            VALUES(true,'shadow',%s,'github:ingestion_pipeline',%s::jsonb,%s)
            ON CONFLICT(singleton) DO NOTHING""",
                  (datetime.utcnow().date(),json.dumps(calibration),code_sha()))
        c.execute("SELECT calibration,mode FROM risk_pipeline_v2_control WHERE singleton")
        saved=c.fetchone()
        if saved["mode"]!="shadow" or saved["calibration"]["source_sha256"]!=calibration["source_sha256"]:
            raise RuntimeError("Existing activation differs; explicit review required")
    seeds=seed()
    from src.ai.shadow_enrichment import mark_stale
    stale=mark_stale()
    (OUT/"activation.json").write_text(json.dumps(
        {"seed_rows":seeds,"new_skipped_stale":stale,"activated_at":datetime.utcnow().isoformat(),
         "code_sha":code_sha(),"mode":"shadow","budget_usd":5},indent=2))
    print(json.dumps({"seed_rows":seeds,"skipped_stale":stale}))


if __name__=="__main__":
    main()
