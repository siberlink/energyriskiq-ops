"""Stored-observation briefing used when generated commentary is unavailable."""


def fallback_digest(geri, eeri=None, egsi=None, observation_date=None):
    def latest(value):
        return value[0] if isinstance(value, list) and value else (value or {})

    geri, eeri, egsi = map(latest, (geri, eeri, egsi))
    day = geri.get("date") or observation_date or "unavailable"
    lines = [f"## Stored index snapshot — {day}"]
    for name, row in (("GERI", geri), ("EERI", eeri), ("EGSI-M", egsi)):
        if row.get("value") is not None:
            lines.append(f"- {name}: {row['value']} ({row.get('band') or 'band unavailable'}); "
                         f"observation date: {row.get('date') or observation_date or 'unavailable'}.")
    lines.extend([
        "",
        "Generated commentary is unavailable. This deterministic briefing reports stored "
        "observations only; it does not infer forecasts, probabilities or active index components.",
        "Watch for the next stored observation before drawing conclusions about a change in conditions.",
        "",
        "Informational only. Not financial advice.",
    ])
    return "\n".join(lines)
