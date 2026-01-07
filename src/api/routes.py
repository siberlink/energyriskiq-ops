from fastapi import APIRouter, Query, HTTPException
from typing import Optional, List
from src.db.db import execute_query

router = APIRouter()

@router.get("/health")
def health_check():
    return {"status": "ok"}

@router.get("/events")
def get_events(
    category: Optional[str] = Query(None, description="Filter by category"),
    region: Optional[str] = Query(None, description="Filter by region"),
    min_severity: Optional[int] = Query(None, ge=1, le=5, description="Minimum severity score"),
    limit: int = Query(50, ge=1, le=200, description="Number of results to return")
):
    conditions = []
    params = []
    
    if category:
        if category not in ['geopolitical', 'energy', 'supply_chain']:
            raise HTTPException(status_code=400, detail="Invalid category")
        conditions.append("category = %s")
        params.append(category)
    
    if region:
        conditions.append("region = %s")
        params.append(region)
    
    if min_severity:
        conditions.append("severity_score >= %s")
        params.append(min_severity)
    
    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)
    
    params.append(limit)
    
    query = f"""
    SELECT id, title, source_name, source_url, category, region, 
           severity_score, event_time, inserted_at
    FROM events
    {where_clause}
    ORDER BY inserted_at DESC
    LIMIT %s
    """
    
    results = execute_query(query, tuple(params))
    
    events = []
    for row in results:
        events.append({
            "id": row['id'],
            "title": row['title'],
            "source_name": row['source_name'],
            "source_url": row['source_url'],
            "category": row['category'],
            "region": row['region'],
            "severity_score": row['severity_score'],
            "event_time": row['event_time'].isoformat() if row['event_time'] else None,
            "inserted_at": row['inserted_at'].isoformat() if row['inserted_at'] else None
        })
    
    return {"count": len(events), "events": events}

@router.get("/events/latest")
def get_latest_events():
    query = """
    SELECT id, title, source_name, source_url, category, region, 
           severity_score, event_time, inserted_at
    FROM events
    ORDER BY inserted_at DESC
    LIMIT 20
    """
    
    results = execute_query(query)
    
    events = []
    for row in results:
        events.append({
            "id": row['id'],
            "title": row['title'],
            "source_name": row['source_name'],
            "source_url": row['source_url'],
            "category": row['category'],
            "region": row['region'],
            "severity_score": row['severity_score'],
            "event_time": row['event_time'].isoformat() if row['event_time'] else None,
            "inserted_at": row['inserted_at'].isoformat() if row['inserted_at'] else None
        })
    
    return {"count": len(events), "events": events}

@router.get("/ingestion-runs")
def get_ingestion_runs(limit: int = Query(10, ge=1, le=50)):
    query = """
    SELECT id, started_at, finished_at, status, notes
    FROM ingestion_runs
    ORDER BY started_at DESC
    LIMIT %s
    """
    
    results = execute_query(query, (limit,))
    
    runs = []
    for row in results:
        runs.append({
            "id": row['id'],
            "started_at": row['started_at'].isoformat() if row['started_at'] else None,
            "finished_at": row['finished_at'].isoformat() if row['finished_at'] else None,
            "status": row['status'],
            "notes": row['notes']
        })
    
    return {"count": len(runs), "runs": runs}
