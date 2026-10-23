"""Additional private smoothing arms; no provider calls, public writes or risk reads."""
from datetime import date,datetime,timedelta
import json

from src.db.db import get_cursor
from src.geri.compute import compute_components
from scripts.geri_lab.data import readonly_snapshot
from scripts.geri_lab.replay import as_alert,RAW_FIELDS,NORMAL_FIELDS,PILLARS
from scripts.geri_lab.smoothing import raw_transform,display_transform
from scripts.geri_lab.variants import get_variant


def base_name(variant):
    if variant.pillar_mode=="continuous":
        return "pillars_v2_continuous_rel41"
    return "rel41" if variant.label_model=="gpt41" else "integrity_v1"


def calculate(variant,day,quality,original,history,previous):
    """Identical causal transform and normalization boundary to the lab replay."""
    from src.geri.shadow_daily import normalize
    components=compute_components([])
    preceding=[(r["index_date"],tuple(r["inputs"]["original_raw"]),r["inputs"]["data_quality"])
               for r in history]
    adjusted,state=raw_transform(original,day,quality,variant,preceding,previous)
    for field,value in zip(RAW_FIELDS,adjusted):
        setattr(components,field,value)
    baseline=[tuple(float(r["components"]["raw_"+p]) for p in PILLARS)
              for r in history if r["inputs"]["data_quality"]=="OK"
              and day-timedelta(days=variant.baseline_window_days)<=r["index_date"]<day]
    before=normalize(components,baseline)
    value=display_transform(before,variant,state)
    output={f"raw_{p}":x for p,x in zip(PILLARS,adjusted)}
    output["raw_C"]=round(output["raw_C"],2)
    output.update({f"norm_{p}":getattr(components,f) for p,f in zip(PILLARS,NORMAL_FIELDS)})
    return value,output,state,{"normalization_rows":len(baseline),
            "pre_display_value":before,"fallback_used":components.insufficient_history}


def insert_new(records):
    """Write only the new named variants, never update existing observations."""
    from psycopg2.extras import execute_values
    from src.geri.shadow_daily import VARIANTS
    if any(r[1] in VARIANTS for r in records):
        raise ValueError("Refusing to write an existing Step 7 variant")
    if not records:
        return 0
    with get_cursor() as c:
        execute_values(c,"""INSERT INTO geri_shadow_daily
            (index_date,variant,value,components,inputs,code_sha) VALUES %s
            ON CONFLICT(index_date,variant) DO NOTHING""",
                       records,template="(%s,%s,%s,%s::jsonb,%s::jsonb,%s)",page_size=500)
    return len(records)


def run(day=None):
    # Settings, guards and existing variants are deliberately not touched here.
    from src.geri.shadow_daily import code_sha
    with readonly_snapshot() as c:
        c.execute("SELECT start_date,mode FROM risk_pipeline_v2_control WHERE singleton")
        control=c.fetchone()
        if not control or control["mode"]!="shadow":
            raise RuntimeError("New variants require the existing shadow activation")
        c.execute("""SELECT DISTINCT variant FROM geri_shadow_daily
            WHERE inputs->>'step8'='true' ORDER BY variant""")
        names=[r["variant"] for r in c.fetchall()]
        c.execute("""SELECT * FROM geri_shadow_daily
            WHERE index_date>=%s AND index_date<%s AND inputs->>'seed'='false'
            AND variant IN ('integrity_v1','rel41','pillars_v2_continuous_rel41')
            AND (%s::date IS NULL OR index_date=%s::date)
            ORDER BY index_date,variant""",
                  (control["start_date"],datetime.utcnow().date(),day,day))
        bases={(r["index_date"],r["variant"]):dict(r) for r in c.fetchall()}
    results=[];pending=[]
    for when in sorted({d for d,_ in bases}):
        originals={}
        for name in names:
            variant=get_variant(name)
            base=bases.get((when,base_name(variant)))
            if base is None:
                pending.append({"date":str(when),"variant":name,"reason":"base_not_ready"})
                continue
            with readonly_snapshot() as c:
                c.execute("SELECT 1 AS present FROM geri_shadow_daily WHERE index_date=%s AND variant=%s",
                          (when,name))
                if c.fetchone():
                    continue
                c.execute("""SELECT * FROM geri_shadow_daily WHERE variant=%s
                    AND index_date>=%s AND index_date<%s ORDER BY index_date""",
                          (name,when-timedelta(days=max(variant.baseline_window_days,56)),when))
                history=[dict(r) for r in c.fetchall()]
                if not history or history[-1]["index_date"]!=when-timedelta(days=1):
                    raise ValueError(f"Missing preceding smoothing state: {name} {when}")
                key=base_name(variant)
                if key not in originals:
                    # Reconstruct full-precision C from exactly the frozen base's selected
                    # alerts. No new relevance classification or later V2 snapshot.
                    c.execute("""SELECT id,alert_type,severity,confidence AS risk_score,
                        scope_region AS region,created_at,headline,body,raw_input
                        FROM alert_events WHERE id=ANY(%s) ORDER BY created_at,id""",
                              (base["inputs"]["alert_ids"],))
                    alerts=[dict(r) for r in c.fetchall()]
                    if len(alerts)!=len(base["inputs"]["alert_ids"]):
                        raise ValueError("Missing immutable base alert")
                    components=compute_components([as_alert(r) for r in alerts])
                    raw=[getattr(components,f) for f in RAW_FIELDS]
                    if variant.pillar_mode=="continuous":
                        raw[1]=base["components"]["raw_R"]
                        raw[2]=base["components"]["raw_A"]
                    originals[key]=raw
            original=originals[base_name(variant)]
            quality=base["inputs"]["data_quality"]
            value,output,state,diagnostics=calculate(
                variant,when,quality,original,history,history[-1]["inputs"]["smoothing_state"])
            inputs={**base["inputs"],**diagnostics,"step8":True,"seed":False,
                    "base_variant":base_name(variant),"original_raw":original,
                    "smoothing_state":state,
                    "point_in_time":bool(base["inputs"].get("point_in_time"))
                        and datetime.utcnow().date()==when+timedelta(days=1),
                    "signal_available_at":datetime.utcnow().isoformat(),
                    "no_additional_llm_calls":True}
            insert_new([(when,name,value,json.dumps(output),json.dumps(inputs),code_sha())])
            results.append({"date":str(when),"variant":name,"value":value})
    return {"rows":results,"pending":pending}
