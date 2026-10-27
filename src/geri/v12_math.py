"""Frozen release mathematics; independent of mutable lab variant definitions."""
from datetime import timedelta
from statistics import mean
from src.geri.types import GERIComponents,HistoricalBaseline
from src.geri.normalize import normalize_components,calculate_geri_value

RAW_FIELDS=("high_impact_score","regional_spike_score","asset_risk_score","region_concentration_score_raw")
NORMAL_FIELDS=("norm_high_impact","norm_regional_spike","norm_asset_risk","norm_region_concentration")
PILLARS=("H","R","A","C")


def vector(day,quality,original,history,previous):
    previous=previous or {}
    eligible=[r for r in history if r["inputs"]["data_quality"]=="OK"
              and day-timedelta(days=56)<=r["index_date"]<day]
    same=[r["inputs"]["original_raw"][0] for r in eligible
          if r["index_date"].weekday()==day.weekday()]
    all_h=[r["inputs"]["original_raw"][0] for r in eligible]
    factor=mean(same)/mean(all_h) if len(same)>=4 and mean(all_h)>0 and mean(same)>0 else 1.
    adjusted=list(original);adjusted[0]/=factor
    prior=previous.get("ewma");k=.5**(1/1.5)
    if quality!="OK":adjusted=list(prior) if prior is not None else [0.]*4
    elif prior is not None:adjusted=[k*a+(1-k)*b for a,b in zip(prior,adjusted)]
    state={"ewma":adjusted if quality=="OK" or prior is not None else None,
           "original_raw":list(original),"weekday_factor":factor,"display_previous":None}
    components=GERIComponents()
    for f,x in zip(RAW_FIELDS,adjusted):setattr(components,f,x)
    healthy=[r for r in history if r["inputs"]["data_quality"]=="OK"
             and day-timedelta(days=90)<=r["index_date"]<day]
    baseline=HistoricalBaseline(days_count=len(healthy))
    for p,prefix in zip(PILLARS,("high_impact","regional_spike","asset_risk","region_concentration")):
        values=[r["components"]["raw_"+p] for r in healthy]
        if values:
            setattr(baseline,prefix+"_min",min(values))
            setattr(baseline,prefix+"_max",max(values))
    normalize_components(components,baseline)
    value=calculate_geri_value(components)
    state["display_previous"]=float(value)
    output={f"raw_{p}":x for p,x in zip(PILLARS,adjusted)}
    output["raw_C"]=round(output["raw_C"],2)
    output.update({f"norm_{p}":getattr(components,f) for p,f in zip(PILLARS,NORMAL_FIELDS)})
    return value,output,state,{"normalization_rows":len(healthy),"pre_display_value":value,
                              "fallback_used":components.insufficient_history}
