"""Step 5 paired weekly bootstrap, restricted to genuine prospective dates."""
import argparse
from datetime import date
import json
from pathlib import Path

from .data import readonly_snapshot
from .scorecard import scorecard
from .bootstrap import compare_scorecards
from .variants import get_variant


def main():
    from .step7_setup import OUT
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path,default=OUT/"prospective_comparison.json")
    args=p.parse_args()
    with readonly_snapshot() as c:
        c.execute("SELECT start_date FROM risk_pipeline_v2_control WHERE singleton")
        start=c.fetchone()["start_date"]
        c.execute("""SELECT index_date,variant,value,components,inputs FROM geri_shadow_daily
            WHERE index_date>%s AND COALESCE((inputs->>'seed')::boolean,false)=false
            ORDER BY index_date,variant""",(start,))
        rows=[dict(r) for r in c.fetchall()]
    result={"shadow_start_date":str(start),"partial_activation_day_excluded":True,
            "observations_by_variant":{},"comparisons":{},
            "note":"Paired weekly bootstrap is unassessable until prospective forward returns mature."}
    by_variant={}
    for r in rows:
        if r["inputs"].get("data_quality")!="OK":
            continue
        row={"date":str(r["index_date"]),"geri":r["value"],"data_quality":"OK",
             **{f"raw_{p}":0. for p in "HRAC"}, **r["components"],
             "n_alerts":len(r["inputs"].get("alert_ids",[])),
             "n_by_type":{},"fallback_used":r["inputs"].get("normalization_rows",0)<14,
             "active_pillar_ceiling":100}
        by_variant.setdefault(r["variant"],[]).append(row)
    for name in ("prod","integrity_v1","rel41","pillars_v2_continuous","pillars_v2_continuous_rel41"):
        result["observations_by_variant"][name]=len(by_variant.get(name,[]))
    if by_variant.get("integrity_v1"):
        from .step7_markets import markets
        from .step4_report import split_market
        from . import step4_report
        from datetime import timedelta
        data=markets(start)
        # Retain Step 5 bootstrap math, but H1/H2 must split this prospective
        # interval, not the historical January–October research interval.
        dates=sorted(r["index_date"] for r in rows)
        first,last=dates[0],dates[-1]
        middle=first+(last-first)//2
        original_splits=step4_report.SPLITS
        step4_report.SPLITS={"full":(first,last),"H1":(first,middle),
                             "H2":(middle+timedelta(days=1),last)}
        ref=scorecard(by_variant.get("integrity_v1",[]),data,get_variant("integrity_v1"))
        ref["market_splits_step4"]=split_market(by_variant.get("integrity_v1",[]),data)
        for name,series in by_variant.items():
            if name in ("prod","integrity_v1"):
                continue
            score=scorecard(series,data,get_variant("integrity_v1"))
            score["variant"]=name
            score["market_splits_step4"]=split_market(series,data)
            result["comparisons"][name]=compare_scorecards(ref,score)[0]
        step4_report.SPLITS=original_splits
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,default=str,indent=2))
    print(json.dumps(result,default=str,indent=2))


if __name__=="__main__":
    main()
