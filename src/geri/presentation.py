"""Read-time availability labels; never changes stored digest or index rows."""
from copy import deepcopy
from datetime import date


def overlay_digest_health(model):
    result = deepcopy(model)
    geri = result.get("geri") or {}
    if not geri.get("date"):
        return result
    from src.geri.repo import get_index_for_date
    current = get_index_for_date(date.fromisoformat(str(geri["date"])[:10]))
    if current:
        geri["data_quality"] = current["data_quality"]
        if current["data_quality"] == "UNAVAILABLE":
            geri.update(value=None, band="UNAVAILABLE", trend_1d=None, trend_7d=None)
        result["geri"] = geri
    return result
