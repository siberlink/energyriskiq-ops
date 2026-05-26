---
name: Latest-row queries on timeseries tables
description: Fetching "latest" values from growing timeseries tables in EnergyRiskIQ — DESC LIMIT + reverse, never ASC LIMIT.
---

When a public/SEO page needs the latest value plus a recent history window from
a timeseries table (ttf_gas_snapshots, vix_snapshots, oil_price_snapshots,
gas_storage_snapshots, *_indices_daily, etc.), always query as:

```sql
SELECT … FROM <table>
WHERE <val> IS NOT NULL
ORDER BY date DESC
LIMIT N
```

…then `list(reversed(rows))` in Python to get ascending order for plotting.

**Why:** Using `ORDER BY date ASC LIMIT N` silently drops the *newest* rows
once the table grows past N. The page keeps rendering 200, but `rows[-1]`
becomes stale and SEO "today" pages display old prices. This is invisible in
testing because tables start small.

**How to apply:** Any new daily/intraday timeseries DB read in the api layer
that is later indexed as `rows[-1]` / `rows[-N]` should use DESC LIMIT +
reverse. If you need both latest *and* a long history, prefer one DESC LIMIT
query large enough to cover the longest display window.
