"""Owner-authorized private-only replay; dry-run by default, no provider calls."""
import argparse
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path

from src.db.db import get_cursor
from src.geri import version12
from src.geri.live_v12 import finalize_close
from src.geri.model_selection import published_model, live_model
from src.geri.repo import get_alerts_for_date
from src.geri.shadow_smoothing import calculate
from src.geri.v12_history import final_health, final_history, exclude_correction
from scripts.geri_lab.variants import get_variant


def public_fingerprint():
    with get_cursor(commit=False) as c:
        c.execute("""SELECT count(*) AS rows,
            md5(string_agg(t::text,'' ORDER BY index_id,date)) AS fingerprint
            FROM intel_indices_daily t""")
        return dict(c.fetchone())


def run(start, end, reason, apply=False):
    if not reason.strip() or end < start:
        raise ValueError("A reason and ordered date range are required")
    if published_model() != "v1.1" or live_model() != "legacy":
        raise ValueError("This maintenance run requires unchanged public legacy selectors")
    before = public_fingerprint()
    source = hashlib.sha256(b"".join(Path(p).read_bytes() for p in (
        "src/geri/version12.py", "src/geri/v12_history.py",
        "src/geri/v12_math.py", "src/geri/shadow_smoothing.py",
        "src/geri/live_v12.py"))).hexdigest()
    private_overrides = {}
    shadow_overrides = {}
    results = []
    day = start
    while day <= end:
        with get_cursor(commit=False) as c:
            health = final_health(c, day)
            c.execute("SELECT * FROM intel_indices_daily_v12 WHERE date=%s AND index_id=%s",
                      (day, version12.INDEX_ID))
            old_private = dict(c.fetchone() or {})
            c.execute("""SELECT * FROM geri_shadow_daily WHERE index_date=%s
                AND variant='wk_carry15'""", (day,))
            old_shadow = dict(c.fetchone() or {})
            c.execute("""SELECT * FROM geri_shadow_daily WHERE variant='wk_carry15'
                AND index_date>=%s AND index_date<%s ORDER BY index_date""",
                (day-timedelta(days=90), day))
            shadow_history = [dict(r) for r in c.fetchall()]
            shadow_history = [shadow_overrides.get(r["index_date"], r) for r in shadow_history]
            shadow_history = final_history(c, shadow_history)
        if not old_private or not old_shadow or not shadow_history:
            raise ValueError(f"Missing private observation or seed for {day}")
        rows, history = version12.history_for(day)
        rows = [private_overrides.get(r["date"], r) for r in rows]
        history = [{"index_date": r["date"],
                    "components": r["smoothing_state"]["normalized_raw"],
                    "inputs": {"original_raw": r["smoothing_state"]["original_raw"],
                               "data_quality": r["smoothing_state"]["data_quality"]}}
                   for r in rows]
        with get_cursor(commit=False) as c:
            history = final_history(c, history)
        ids = set(old_private["smoothing_state"]["alert_ids"])
        alerts = [a for a in get_alerts_for_date(day) if a.id in ids]
        if {a.id for a in alerts} != ids:
            raise ValueError(f"Missing frozen private alert for {day}")
        private = version12.calculate_day(day, alerts, health["data_quality"], rows, history,
            raw_override=old_private["smoothing_state"]["original_raw"])
        value, components, state, diagnostics = calculate(get_variant("wk_carry15"), day,
            health["data_quality"], old_shadow["inputs"]["original_raw"], shadow_history,
            shadow_history[-1]["inputs"]["smoothing_state"])
        inputs = {**old_shadow["inputs"], **diagnostics,
            "data_quality": health["data_quality"], "smoothing_state": state,
            "baseline_dates": [str(r["index_date"]) for r in shadow_history
                               if r["inputs"]["data_quality"] == "OK"],
            "late_repair": True, "point_in_time": False, "prospective_eligible": False,
            "repair_reason": reason, "repair_source_sha256": source}
        shadow = {**old_shadow, "value": value, "components": components, "inputs": inputs}
        if private["value"] != value or private["smoothing_state"]["transform_state"] != state:
            raise ValueError(f"Independent private/shadow replay disagrees for {day}")
        details = {"date": str(day), "private_old": old_private["value"],
            "private_new": private["value"], "shadow_old": old_shadow["value"],
            "shadow_new": value, "normalization_rows": diagnostics["normalization_rows"],
            "same_state": True, "excluded_from_prospective": True}
        if apply:
            version12.store(private, backfilled=True, reason=reason, apply_revision=True)
            with get_cursor() as c:
                c.execute("""INSERT INTO geri_v12_revisions
                    (index_date,old_payload,new_payload,reason,applied)
                    VALUES(%s,%s::jsonb,%s::jsonb,%s,true)""",
                    (day, json.dumps({"table": "geri_shadow_daily", **old_shadow}, default=str),
                     json.dumps({"table": "geri_shadow_daily", **shadow}, default=str),
                     reason+"; wk_carry15 shadow history correction"))
                c.execute("""UPDATE geri_shadow_daily SET value=%s,components=%s::jsonb,
                    inputs=%s::jsonb,computed_at=now()
                    WHERE index_date=%s AND variant='wk_carry15'""",
                    (value, json.dumps(components), json.dumps(inputs), day))
                exclude_correction(c, day, {"reason": reason, **details})
            finalize_close(private)
            version12.parity_monitor(day)
        private_overrides[day] = private
        shadow_overrides[day] = shadow
        results.append(details)
        day += timedelta(days=1)
    after = public_fingerprint()
    if before != after:
        raise RuntimeError("Published v1.1 fingerprint changed; investigate concurrent writer")
    return {"applied": apply, "source_sha256": source, "public_before": before,
            "public_after": after, "public_unchanged": True, "rows": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-date", type=date.fromisoformat, required=True)
    parser.add_argument("--through", type=date.fromisoformat, required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.from_date, args.through, args.reason, args.apply), indent=2))
