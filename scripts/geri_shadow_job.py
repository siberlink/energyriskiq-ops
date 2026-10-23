"""Single-runner CLI: private daily GERI, supervised catch-up and checkpoints."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
from contextlib import contextmanager

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


@contextmanager
def single_runner(wait_seconds=1800):
    """Wait for an already-running legacy ingestion; never steal its lock."""
    from src.db.db import advisory_lock
    deadline=time.monotonic()+wait_seconds
    while True:
        with advisory_lock(7001) as acquired:
            if acquired:
                yield
                return
        if time.monotonic()>=deadline:
            raise RuntimeError("Single production runner still active after 30-minute wait")
        print("Waiting for the existing ingestion runner; no paid calls started",flush=True)
        time.sleep(30)


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
        from src.ai.shadow_enrichment import run,catchup_remaining
        from src.risk.shadow_risk import run as risk
        with single_runner():
            inserted,skipped,errors=run_ingestion()
            good,bad=run()
            # Same one approved catch-up can resume after midnight's budget reset.
            # Keep the hourly job bounded so ingestion remains hourly.
            stop=time.monotonic()+900
            while catchup_remaining() and time.monotonic()<stop:
                more,errors=run(batch_size=100)
                good+=more;bad+=errors
                if more+errors==0:
                    break
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
        from src.ai.shadow_enrichment import run,catchup_remaining
        from src.risk.shadow_risk import run as risk
        # Share the same overlap lock as scheduled ingestion. A process cannot
        # start a second independent enrichment stream while this holds the lock.
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
                catchup_remaining()
            return {"successes":successes,"failures":failures}
        with single_runner():
            result=catchup()
    print(json.dumps(result,default=str,indent=2))


if __name__=="__main__":
    main()
