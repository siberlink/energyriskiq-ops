"""One opt-in reader selection; legacy writers always use an explicit context."""
from contextlib import contextmanager
from contextvars import ContextVar
import os
import re

_override=ContextVar("geri_reader_version",default=None)
_live_override=ContextVar("geri_live_reader_version",default=None)


def published_model():
    value=_override.get() or os.getenv("GERI_PUBLISHED_MODEL","v1.1")
    if value not in ("v1.1","v1.2"):
        raise ValueError("GERI_PUBLISHED_MODEL must be v1.1 or v1.2")
    return value


def live_model():
    value=_live_override.get() or os.getenv("GERI_LIVE_MODEL","legacy")
    if value not in ("legacy","v1.2"):
        raise ValueError("GERI_LIVE_MODEL must be legacy or v1.2")
    return value


@contextmanager
def reader_model(version,live=None):
    if version not in ("v1.1","v1.2"):
        raise ValueError("Unknown GERI methodology")
    token=_override.set(version)
    live_token=_live_override.set(live) if live else None
    try:
        yield
    finally:
        _override.reset(token)
        if live_token is not None:_live_override.reset(live_token)


def cache_namespace(key):
    from src.geri.admin_preview import preview_cache_key
    key = key if published_model()=="v1.1" else key+":geri_v1.2"
    return preview_cache_key(key)


# Projection deliberately matches the legacy schema, not the private metadata.
_columns=("id,index_id,date,value,band,trend_1d,trend_7d,components,"
          "model_version,computed_at,interpretation")
_relation=("(SELECT "+_columns+" FROM public.intel_indices_daily "
           "WHERE index_id<>'global:geo_energy_risk' UNION ALL SELECT "+_columns+
           " FROM public.intel_indices_daily_v12 "
           "WHERE index_id='global:geo_energy_risk' "
           "AND smoothing_state->>'data_quality'<>'UNAVAILABLE')")


def _replace_relation(query,name,relation):
    chunks=re.split(r"('(?:''|[^'])*'|--[^\n]*|/\*.*?\*/)",query,flags=re.S)
    pattern=r'\b(FROM|JOIN)(\s+)(?:"?public"?\.)?"?'+name+r'"?(?=\s|[),;]|$)'
    for i in range(0,len(chunks),2):
        chunks[i]=re.sub(pattern,lambda m:m[1]+m[2]+relation+
            ("" if re.match(r'\s+(?:AS\s+)?(?!WHERE\b|ORDER\b|GROUP\b|LIMIT\b|JOIN\b|LEFT\b|RIGHT\b|INNER\b|FULL\b|UNION\b|OFFSET\b|FOR\b|HAVING\b|CROSS\b|ON\b|USING\b|WINDOW\b|FETCH\b)(?:\w|"[^"]+")',
                           chunks[i][m.end():],re.I) else " AS "+name),
            chunks[i],flags=re.I)
    return "".join(chunks)


_live_relation="""(SELECT id,value,value::numeric AS value_raw,band,
    value-(metadata->>'previous_daily_value')::numeric AS trend_vs_yesterday,components,
    COALESCE(metadata->>'interpretation','') AS interpretation,
    COALESCE((metadata->>'alerts_received')::integer,0) AS alert_count,
    NULL::integer AS last_alert_id,COALESCE(components->'top_drivers','[]'::jsonb) AS top_drivers,
    COALESCE(components->'top_regions','[]'::jsonb) AS top_regions,metadata,
    computed_at AT TIME ZONE 'UTC' AS computed_at FROM geri_live_v12_shadow)"""
_live_history_relation="""(SELECT n.id,(n.computed_at AT TIME ZONE 'UTC')::date AS snapshot_date,
    n.value,n.value::numeric AS value_raw,n.band,
    lag(n.value) OVER(ORDER BY n.computed_at) AS prev_value,
    n.value-lag(n.value) OVER(ORDER BY n.computed_at) AS value_change,
    COALESCE((n.metadata->>'alerts_received')::integer,0) AS alert_count,
    NULL::integer AS new_alert_count,NULL::integer AS last_alert_id,
    '[]'::jsonb AS trigger_events,'[]'::jsonb AS trigger_event_ids,
    COALESCE(n.components->'top_drivers','[]'::jsonb) AS top_drivers,
    p.brent_price,p.brent_change_pct,p.wti_price,p.wti_change_pct,
    p.natgas_price,p.natgas_change_pct,n.metadata,n.computed_at AT TIME ZONE 'UTC' AS computed_at
    FROM geri_live_v12_shadow n LEFT JOIN LATERAL
    (SELECT h.brent_price,h.brent_change_pct,h.wti_price,h.wti_change_pct,
        h.natgas_price,h.natgas_change_pct FROM public.geri_live_history h
        WHERE h.computed_at BETWEEN (n.computed_at AT TIME ZONE 'UTC')-interval '10 seconds'
            AND (n.computed_at AT TIME ZONE 'UTC')+interval '10 seconds'
        ORDER BY abs(extract(epoch FROM h.computed_at-(n.computed_at AT TIME ZONE 'UTC')))
        LIMIT 1) p ON true)"""


def read_sql(query):
    """Rewrite relations, not literals/writes. Off is a byte-identical no-op.

    All application readers use ModelCursor, including direct SQL readers.
    psycopg2 readonly lab/shadow connections are deliberately not intercepted.
    """
    if not isinstance(query,str):
        return query
    head=re.sub(r"^(?:\s|--[^\n]*(?:\n|$)|/\*.*?\*/)*","",query,flags=re.S)
    if not re.match(r"(SELECT|WITH)\b",head,re.I):
        return query
    code=" ".join(re.split(r"('(?:''|[^'])*'|--[^\n]*|/\*.*?\*/)",query,flags=re.S)[::2])
    if re.search(r"\b(INSERT|UPDATE|DELETE|MERGE)\b",code,re.I):
        return query
    if published_model()=="v1.2":
        query=_replace_relation(query,"intel_indices_daily",_relation)
    if live_model()=="v1.2":
        # History first, so the relation's explicit legacy price lookup is not
        # mistaken for a user-facing history reader in the same pass.
        query=_replace_relation(query,"geri_live",_live_relation)
        query=_replace_relation(query,"geri_live_history",_live_history_relation)
    return query
