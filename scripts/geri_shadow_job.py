"""Single-runner CLI: private daily GERI, supervised catch-up and checkpoints."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    p=argparse.ArgumentParser()
    p.add_argument("job",choices=["daily","monitor","catchup","risk","ingestion"])
    p.add_argument("--max-events",type=int,default=5000)
    args=p.parse_args()
    from src.risk.pipeline_v2_core import mode
    if mode()!="shadow":
        raise RuntimeError("Explicit shadow mode required")
    from src.risk.shadow_monitor import capture
    if args.job=="monitor":
        result=capture()
    elif args.job=="daily":
        from src.geri.shadow_daily import run
        result=run()
    elif args.job=="ingestion":
        from src.ingest.ingest_runner import run_ingestion
        from src.ai.shadow_enrichment import run
        from src.risk.shadow_risk import run as risk
        from src.db.db import advisory_lock
        with advisory_lock(7001) as acquired:
            if not acquired:
                raise RuntimeError("Single production runner is already active")
            inserted,skipped,errors=run_ingestion()
            good,bad=run()
            scored=risk()
            result={"inserted":inserted,"ingestion_errors":errors,
                    "enriched":good,"enrichment_errors":bad,"shadow_scored":scored}
            capture()
            if errors or bad:
                print(json.dumps(result))
                raise RuntimeError("Pipeline contains failed work; see counts")
    elif args.job=="risk":
        from src.risk.shadow_risk import run
        result={"scored":run()}
    else:
        from src.ai.shadow_enrichment import run
        from src.risk.shadow_risk import run as risk
        # Share the same overlap lock as scheduled ingestion. A process cannot
        # start a second independent enrichment stream while this holds the lock.
        from src.db.db import advisory_lock
        def catchup():
            successes=failures=0
            while successes+failures<args.max_events:
                good,bad=run(batch_size=min(100,args.max_events-successes-failures))
                successes+=good;failures+=bad
                risk()
                capture()
                print(json.dumps({"successes":successes,"failures":failures}),flush=True)
                if good+bad==0:
                    break
            return {"successes":successes,"failures":failures}
        with advisory_lock(7001) as acquired:
            if not acquired:
                raise RuntimeError("Single production runner is already active")
            result=catchup()
    print(json.dumps(result,default=str,indent=2))


if __name__=="__main__":
    main()
