import json
from fastapi import APIRouter, Query, HTTPException, Path
from typing import Optional
from src.db.db import execute_query, execute_one

router = APIRouter()

@router.get("/health")
def health_check():
    return {"status": "ok"}

@router.get("/events")
def get_events(
    category: Optional[str] = Query(None, description="Filter by category"),
    region: Optional[str] = Query(None, description="Filter by region"),
    min_severity: Optional[int] = Query(None, ge=1, le=5, description="Minimum severity score"),
    processed: Optional[bool] = Query(None, description="Filter by AI processed status"),
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
    
    if processed is not None:
        conditions.append("processed = %s")
        params.append(processed)
    
    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)
    
    params.append(limit)
    
    query = f"""
    SELECT id, title, source_name, source_url, category, region, 
           severity_score, event_time, inserted_at, processed, ai_summary, ai_processed_at
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
            "inserted_at": row['inserted_at'].isoformat() if row['inserted_at'] else None,
            "processed": row['processed'],
            "ai_summary": row['ai_summary'],
            "ai_processed_at": row['ai_processed_at'].isoformat() if row['ai_processed_at'] else None
        })
    
    return {"count": len(events), "events": events}

@router.get("/events/latest")
def get_latest_events():
    query = """
    SELECT id, title, source_name, source_url, category, region, 
           severity_score, event_time, inserted_at, processed, ai_summary, ai_processed_at
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
            "inserted_at": row['inserted_at'].isoformat() if row['inserted_at'] else None,
            "processed": row['processed'],
            "ai_summary": row['ai_summary'],
            "ai_processed_at": row['ai_processed_at'].isoformat() if row['ai_processed_at'] else None
        })
    
    return {"count": len(events), "events": events}

@router.get("/events/{event_id}")
def get_event_detail(event_id: int = Path(..., description="Event ID")):
    query = """
    SELECT id, title, source_name, source_url, category, region, 
           severity_score, event_time, raw_text, inserted_at, 
           classification_reason, processed, ai_summary, ai_impact_json,
           ai_model, ai_processed_at, ai_error, ai_attempts
    FROM events
    WHERE id = %s
    """
    
    result = execute_one(query, (event_id,))
    
    if not result:
        raise HTTPException(status_code=404, detail="Event not found")
    
    ai_impact = None
    if result['ai_impact_json']:
        if isinstance(result['ai_impact_json'], str):
            ai_impact = json.loads(result['ai_impact_json'])
        else:
            ai_impact = result['ai_impact_json']
    
    return {
        "id": result['id'],
        "title": result['title'],
        "source_name": result['source_name'],
        "source_url": result['source_url'],
        "category": result['category'],
        "region": result['region'],
        "severity_score": result['severity_score'],
        "event_time": result['event_time'].isoformat() if result['event_time'] else None,
        "raw_text": result['raw_text'],
        "inserted_at": result['inserted_at'].isoformat() if result['inserted_at'] else None,
        "classification_reason": result['classification_reason'],
        "processed": result['processed'],
        "ai_summary": result['ai_summary'],
        "ai_impact": ai_impact,
        "ai_model": result['ai_model'],
        "ai_processed_at": result['ai_processed_at'].isoformat() if result['ai_processed_at'] else None,
        "ai_error": result['ai_error'],
        "ai_attempts": result['ai_attempts']
    }

@router.get("/ingestion-runs")
def get_ingestion_runs(limit: int = Query(10, ge=1, le=50)):
    query = """
    SELECT id, started_at, finished_at, status, notes,
           total_items, inserted_items, skipped_duplicates, failed_items
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
            "notes": row['notes'],
            "total_items": row.get('total_items', 0),
            "inserted_items": row.get('inserted_items', 0),
            "skipped_duplicates": row.get('skipped_duplicates', 0),
            "failed_items": row.get('failed_items', 0)
        })
    
    return {"count": len(runs), "runs": runs}

@router.get("/ai/stats")
def get_ai_stats():
    query = """
    SELECT 
        COUNT(*) as total_events,
        COUNT(*) FILTER (WHERE processed = TRUE) as processed_events,
        COUNT(*) FILTER (WHERE processed = FALSE) as unprocessed_events,
        COUNT(*) FILTER (WHERE ai_error IS NOT NULL) as events_with_errors,
        AVG(ai_attempts) FILTER (WHERE processed = TRUE) as avg_attempts_success
    FROM events
    """
    
    result = execute_one(query)
    
    return {
        "total_events": result['total_events'],
        "processed_events": result['processed_events'],
        "unprocessed_events": result['unprocessed_events'],
        "events_with_errors": result['events_with_errors'],
        "avg_attempts_success": float(result['avg_attempts_success']) if result['avg_attempts_success'] else None
    }
