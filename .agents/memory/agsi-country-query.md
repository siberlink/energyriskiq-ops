---
name: AGSI+ per-country storage gotcha
description: AGSI+ gas storage API silently returns EU aggregate unless country is passed as a query param, not a path segment.
---

# AGSI+ per-country storage gotcha

The GIE AGSI+ API (`https://agsi.gie.eu/api`) returns per-country gas storage
ONLY when the country is passed as a **query parameter** (`?country=DE`). The
path-style form (`/api/de`) returns HTTP 200 with the **EU aggregate** instead —
no error, just wrong data (e.g. workingGasVolume ≈ 1131 TWh for all of Europe vs
≈ 248 TWh for Germany alone).

**Why:** A helper that builds `f"{base}/{endpoint}"` from a country code will hit
the path form and silently get EU numbers for every country, so all "per-country"
rows come out identical to the EU figure.

**How to apply:** When fetching any single country/operator/facility from AGSI+,
always send it as a query param (`country=`, and later `company=`/`facility=`),
never as a path segment. If per-country rows look identical to the EU aggregate,
this is the cause.
