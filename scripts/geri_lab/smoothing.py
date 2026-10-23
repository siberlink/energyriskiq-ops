"""Causal carry-over/weekday/display transforms shared by lab and private shadow."""
from datetime import timedelta
from statistics import mean


def raw_transform(raw,day,quality,variant,history,previous=None):
    """History is preceding (date, original raw vector, quality), never today's."""
    previous=previous or {}
    factor=1.
    adjusted=list(raw)
    if variant.weekday_adjust:
        eligible=[(d,r) for d,r,q in history
                  if q=="OK" and day-timedelta(days=56)<=d<day]
        same=[r[0] for d,r in eligible if d.weekday()==day.weekday()]
        all_h=[r[0] for d,r in eligible]
        if len(same)>=4 and mean(all_h)>0 and mean(same)>0:
            factor=mean(same)/mean(all_h)
        adjusted[0]/=factor
    prior=previous.get("ewma")
    if variant.carryover_half_life_days is not None:
        k=.5**(1/variant.carryover_half_life_days)
        if quality!="OK":
            adjusted=list(prior) if prior is not None else [0.]*4
        elif prior is not None:
            adjusted=[k*a+(1-k)*b for a,b in zip(prior,adjusted)]
        # First healthy observation initializes x_t, not an invented zero.
    state={"ewma":adjusted if (quality=="OK" or prior is not None) else None,
           "original_raw":list(raw),"weekday_factor":factor,
           "display_previous":previous.get("display_previous")}
    return tuple(adjusted),state


def display_transform(value,variant,state):
    prior=state.get("display_previous")
    if variant.display_smoothing is not None and prior is not None:
        k=.5**(1/variant.display_smoothing[1])
        shown=max(value,k*prior+(1-k)*value)
    else:
        shown=float(value)
    state["display_previous"]=shown
    return int(round(shown))
