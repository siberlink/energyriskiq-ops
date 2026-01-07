from fastapi import APIRouter, Query, HTTPException, Path
from typing import Optional
from src.db.db import execute_query, execute_one

router = APIRouter(prefix="/risk", tags=["risk"])

@router.get("/regions")
def get_risk_regions():
    query = """
    SELECT DISTINCT ON (region, window_days) 
        region, window_days, risk_score, trend, calculated_at
    FROM risk_indices
    ORDER BY region, window_days, calculated_at DESC
    """
    results = execute_query(query)
    
    regions = {}
    for row in results:
        region = row['region']
        window = row['window_days']
        
        if region not in regions:
            regions[region] = {}
        
        regions[region][f"{window}d"] = {
            "risk_score": row['risk_score'],
            "trend": row['trend'],
            "calculated_at": row['calculated_at'].isoformat() if row['calculated_at'] else None
        }
    
    return {"regions": regions}

@router.get("/regions/{region}")
def get_region_history(
    region: str = Path(..., description="Region name (e.g., Europe)"),
    limit: int = Query(30, ge=1, le=100, description="Number of historical entries")
):
    query = """
    SELECT region, window_days, risk_score, trend, calculated_at
    FROM risk_indices
    WHERE LOWER(region) = LOWER(%s)
    ORDER BY calculated_at DESC
    LIMIT %s
    """
    results = execute_query(query, (region, limit))
    
    if not results:
        raise HTTPException(status_code=404, detail=f"No data found for region: {region}")
    
    history = []
    for row in results:
        history.append({
            "window_days": row['window_days'],
            "risk_score": row['risk_score'],
            "trend": row['trend'],
            "calculated_at": row['calculated_at'].isoformat() if row['calculated_at'] else None
        })
    
    return {"region": region, "count": len(history), "history": history}

@router.get("/assets")
def get_asset_risks():
    query = """
    SELECT DISTINCT ON (asset, region, window_days)
        asset, region, window_days, risk_score, direction, calculated_at
    FROM asset_risk
    ORDER BY asset, region, window_days, calculated_at DESC
    """
    results = execute_query(query)
    
    assets = {}
    for row in results:
        asset = row['asset']
        region = row['region']
        window = row['window_days']
        
        if asset not in assets:
            assets[asset] = {}
        
        if region not in assets[asset]:
            assets[asset][region] = {}
        
        assets[asset][region][f"{window}d"] = {
            "risk_score": row['risk_score'],
            "direction": row['direction'],
            "calculated_at": row['calculated_at'].isoformat() if row['calculated_at'] else None
        }
    
    return {"assets": assets}

@router.get("/summary")
def get_risk_summary(region: str = Query("Europe", description="Focus region")):
    idx_query = """
    SELECT window_days, risk_score, trend
    FROM risk_indices
    WHERE LOWER(region) = LOWER(%s)
    ORDER BY calculated_at DESC
    LIMIT 2
    """
    idx_results = execute_query(idx_query, (region,))
    
    risk_7d = None
    trend_7d = None
    risk_30d = None
    trend_30d = None
    
    for row in idx_results:
        if row['window_days'] == 7 and risk_7d is None:
            risk_7d = row['risk_score']
            trend_7d = row['trend']
        elif row['window_days'] == 30 and risk_30d is None:
            risk_30d = row['risk_score']
            trend_30d = row['trend']
    
    asset_query = """
    SELECT DISTINCT ON (asset)
        asset, risk_score, direction
    FROM asset_risk
    WHERE LOWER(region) = LOWER(%s) AND window_days = 7
    ORDER BY asset, calculated_at DESC
    """
    asset_results = execute_query(asset_query, (region,))
    
    assets = {}
    for row in asset_results:
        assets[row['asset']] = {
            "risk": row['risk_score'],
            "direction": row['direction']
        }
    
    return {
        "region": region,
        "risk_7d": risk_7d,
        "trend_7d": trend_7d,
        "risk_30d": risk_30d,
        "trend_30d": trend_30d,
        "assets": assets
    }

@router.get("/events")
def get_risk_events(
    region: Optional[str] = Query(None, description="Filter by region"),
    category: Optional[str] = Query(None, description="Filter by category"),
    limit: int = Query(50, ge=1, le=200, description="Number of results")
):
    conditions = []
    params = []
    
    if region:
        conditions.append("r.region = %s")
        params.append(region)
    
    if category:
        conditions.append("r.category = %s")
        params.append(category)
    
    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)
    
    params.append(limit)
    
    query = f"""
    SELECT r.id, r.event_id, r.region, r.category, r.base_severity, 
           r.ai_confidence, r.weighted_score, r.created_at,
           e.title
    FROM risk_events r
    JOIN events e ON e.id = r.event_id
    {where_clause}
    ORDER BY r.weighted_score DESC
    LIMIT %s
    """
    
    results = execute_query(query, tuple(params))
    
    events = []
    for row in results:
        events.append({
            "id": row['id'],
            "event_id": row['event_id'],
            "title": row['title'],
            "region": row['region'],
            "category": row['category'],
            "base_severity": row['base_severity'],
            "ai_confidence": row['ai_confidence'],
            "weighted_score": round(row['weighted_score'], 3),
            "created_at": row['created_at'].isoformat() if row['created_at'] else None
        })
    
    return {"count": len(events), "events": events}
