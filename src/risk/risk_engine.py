import logging
import os
import sys
import json
import math
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.db.db import get_cursor, execute_query, execute_one
from src.db.migrations import run_migrations

logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

CATEGORY_WEIGHTS = {
    'geopolitical': 1.2,
    'energy': 1.5,
    'supply_chain': 1.0
}

RECENCY_DECAY_HALF_LIFE = 14
ASSETS = ['oil', 'gas', 'fx', 'freight']
WINDOWS = [7, 30]
FOCUS_REGIONS = ['Europe', 'Middle East', 'Asia', 'North America', 'Black Sea', 'North Africa', 'global']

def compute_recency_decay(days_since_event: float) -> float:
    return math.exp(-days_since_event / RECENCY_DECAY_HALF_LIFE)

def extract_avg_confidence(ai_impact_json: Optional[dict]) -> float:
    if not ai_impact_json:
        return 0.5
    
    impact = ai_impact_json.get('impact', {})
    if not impact:
        return 0.5
    
    confidences = []
    for asset in ASSETS:
        if asset in impact and isinstance(impact[asset], dict):
            conf = impact[asset].get('confidence', 0.5)
            if isinstance(conf, (int, float)):
                confidences.append(float(conf))
    
    if not confidences:
        return 0.5
    
    return sum(confidences) / len(confidences)

def compute_weighted_score(base_severity: int, ai_confidence: float, category: str, days_since_event: float) -> float:
    category_weight = CATEGORY_WEIGHTS.get(category, 1.0)
    recency_decay = compute_recency_decay(days_since_event)
    
    return base_severity * ai_confidence * category_weight * recency_decay

def fetch_unscored_events() -> List[dict]:
    query = """
    SELECT e.id, e.region, e.category, e.severity_score, e.ai_impact_json, e.inserted_at
    FROM events e
    WHERE e.processed = TRUE
      AND e.ai_impact_json IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM risk_events r WHERE r.event_id = e.id)
    ORDER BY e.inserted_at ASC
    """
    return execute_query(query)

def insert_risk_event(event_id: int, region: str, category: str, base_severity: int, ai_confidence: float, weighted_score: float):
    with get_cursor() as cursor:
        cursor.execute(
            """INSERT INTO risk_events (event_id, region, category, base_severity, ai_confidence, weighted_score)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (event_id) DO NOTHING""",
            (event_id, region, category, base_severity, ai_confidence, weighted_score)
        )

def get_rolling_max(region: str, days: int = 90) -> float:
    query = """
    SELECT COALESCE(MAX(total_score), 1.0) as max_score
    FROM (
        SELECT SUM(weighted_score) as total_score
        FROM risk_events
        WHERE region = %s
          AND created_at >= NOW() - make_interval(days => %s)
        GROUP BY DATE(created_at)
    ) daily_totals
    """
    result = execute_one(query, (region, days))
    return max(result['max_score'] if result['max_score'] else 1.0, 1.0)

def compute_window_score(region: str, window_days: int) -> float:
    query = """
    SELECT COALESCE(SUM(weighted_score), 0) as total
    FROM risk_events
    WHERE region = %s
      AND created_at >= NOW() - make_interval(days => %s)
    """
    result = execute_one(query, (region, window_days))
    return result['total'] if result['total'] else 0.0

def compute_trend(region: str) -> str:
    current_7d = compute_window_score(region, 7)
    
    query = """
    SELECT COALESCE(SUM(weighted_score), 0) as total
    FROM risk_events
    WHERE region = %s
      AND created_at >= NOW() - make_interval(days => 14)
      AND created_at < NOW() - make_interval(days => 7)
    """
    result = execute_one(query, (region,))
    previous_7d = result['total'] if result['total'] else 0.0
    
    if previous_7d == 0:
        return 'stable'
    
    change_pct = (current_7d - previous_7d) / previous_7d * 100
    
    if change_pct >= 10:
        return 'rising'
    elif change_pct <= -10:
        return 'falling'
    else:
        return 'stable'

def save_risk_index(region: str, window_days: int, risk_score: float, trend: str):
    with get_cursor() as cursor:
        cursor.execute(
            """INSERT INTO risk_indices (region, window_days, risk_score, trend)
               VALUES (%s, %s, %s, %s)""",
            (region, window_days, risk_score, trend)
        )

def get_asset_directions(region: str, window_days: int) -> Dict[str, Dict]:
    query = """
    SELECT e.ai_impact_json, r.weighted_score
    FROM risk_events r
    JOIN events e ON e.id = r.event_id
    WHERE r.region = %s
      AND r.created_at >= NOW() - make_interval(days => %s)
      AND e.ai_impact_json IS NOT NULL
    """
    rows = execute_query(query, (region, window_days))
    
    asset_votes = {asset: {'up': 0, 'down': 0, 'mixed': 0, 'unclear': 0, 'total_weight': 0} for asset in ASSETS}
    
    for row in rows:
        ai_json = row['ai_impact_json']
        if isinstance(ai_json, str):
            ai_json = json.loads(ai_json)
        
        impact = ai_json.get('impact', {})
        weight = row['weighted_score']
        
        for asset in ASSETS:
            if asset in impact and isinstance(impact[asset], dict):
                direction = impact[asset].get('direction', 'unclear')
                confidence = impact[asset].get('confidence', 0.5)
                
                vote_weight = weight * confidence
                
                if asset == 'fx':
                    if direction in ['risk_off', 'down']:
                        asset_votes[asset]['down'] += vote_weight
                    elif direction in ['risk_on', 'up']:
                        asset_votes[asset]['up'] += vote_weight
                    elif direction == 'mixed':
                        asset_votes[asset]['mixed'] += vote_weight
                    else:
                        asset_votes[asset]['unclear'] += vote_weight
                else:
                    if direction in asset_votes[asset]:
                        asset_votes[asset][direction] += vote_weight
                    else:
                        asset_votes[asset]['unclear'] += vote_weight
                
                asset_votes[asset]['total_weight'] += vote_weight
    
    results = {}
    for asset in ASSETS:
        votes = asset_votes[asset]
        total = votes['total_weight']
        
        if total == 0:
            results[asset] = {'direction': 'unclear', 'score_contribution': 0}
            continue
        
        up = votes['up']
        down = votes['down']
        mixed = votes['mixed']
        unclear = votes['unclear']
        
        max_vote = max(up, down, mixed, unclear)
        
        if max_vote == unclear or (up > 0 and down > 0 and abs(up - down) < 0.2 * max(up, down)):
            direction = 'mixed'
        elif up > down:
            if asset == 'fx':
                direction = 'risk_on'
            else:
                direction = 'up'
        elif down > up:
            if asset == 'fx':
                direction = 'risk_off'
            else:
                direction = 'down'
        else:
            direction = 'unclear'
        
        results[asset] = {'direction': direction, 'score_contribution': total}
    
    return results

def get_asset_rolling_max(region: str, asset: str, days: int = 90) -> float:
    query = """
    SELECT COALESCE(MAX(daily_score), 1.0) as max_score
    FROM (
        SELECT SUM(r.weighted_score * COALESCE((e.ai_impact_json->'impact'->%s->>'confidence')::float, 0.5)) as daily_score
        FROM risk_events r
        JOIN events e ON e.id = r.event_id
        WHERE r.region = %s
          AND r.created_at >= NOW() - make_interval(days => %s)
          AND e.ai_impact_json->'impact'->%s IS NOT NULL
        GROUP BY DATE(r.created_at)
    ) daily_totals
    """
    result = execute_one(query, (asset, region, days, asset))
    return max(result['max_score'] if result['max_score'] else 1.0, 1.0)

def compute_asset_risk_score(region: str, asset: str, window_days: int) -> float:
    query = """
    SELECT COALESCE(SUM(r.weighted_score * 
        COALESCE((e.ai_impact_json->'impact'->%s->>'confidence')::float, 0.5)
    ), 0) as weighted_total
    FROM risk_events r
    JOIN events e ON e.id = r.event_id
    WHERE r.region = %s
      AND r.created_at >= NOW() - make_interval(days => %s)
      AND e.ai_impact_json->'impact'->%s IS NOT NULL
    """
    result = execute_one(query, (asset, region, window_days, asset))
    return result['weighted_total'] if result['weighted_total'] else 0.0

def save_asset_risk(asset: str, region: str, window_days: int, risk_score: float, direction: str):
    with get_cursor() as cursor:
        cursor.execute(
            """INSERT INTO asset_risk (asset, region, window_days, risk_score, direction)
               VALUES (%s, %s, %s, %s, %s)""",
            (asset, region, window_days, risk_score, direction)
        )

def run_risk_engine():
    logger.info("=" * 60)
    logger.info("Starting EnergyRiskIQ Risk Scoring Engine")
    logger.info("=" * 60)
    
    run_migrations()
    
    events = fetch_unscored_events()
    logger.info(f"Found {len(events)} unscored events")
    
    now = datetime.now()
    scored_count = 0
    
    for event in events:
        event_id = event['id']
        region = event['region']
        category = event['category']
        base_severity = event['severity_score']
        
        ai_json = event['ai_impact_json']
        if isinstance(ai_json, str):
            ai_json = json.loads(ai_json)
        
        ai_confidence = extract_avg_confidence(ai_json)
        
        inserted_at = event['inserted_at']
        days_since = (now - inserted_at).total_seconds() / 86400
        
        weighted_score = compute_weighted_score(base_severity, ai_confidence, category, days_since)
        
        insert_risk_event(event_id, region, category, base_severity, ai_confidence, weighted_score)
        scored_count += 1
    
    logger.info(f"Scored {scored_count} events")
    
    logger.info("Computing regional risk indices...")
    
    for region in FOCUS_REGIONS:
        rolling_max = get_rolling_max(region)
        trend = compute_trend(region)
        
        for window in WINDOWS:
            raw_score = compute_window_score(region, window)
            normalized_score = min((raw_score / rolling_max) * 100, 100)
            
            save_risk_index(region, window, round(normalized_score, 2), trend)
            
            if region == 'Europe':
                logger.info(f"  Europe {window}d: {normalized_score:.1f} ({trend})")
    
    logger.info("Computing asset-level risk...")
    
    for region in ['Europe']:
        asset_directions = {}
        
        for window in WINDOWS:
            directions = get_asset_directions(region, window)
            
            for asset in ASSETS:
                asset_max = get_asset_rolling_max(region, asset)
                raw_score = compute_asset_risk_score(region, asset, window)
                normalized = min((raw_score / asset_max) * 100, 100) if asset_max > 0 else 0
                direction = directions[asset]['direction']
                
                save_asset_risk(asset, region, window, round(normalized, 2), direction)
                
                if window == 7:
                    asset_directions[asset] = {'risk': round(normalized, 2), 'direction': direction}
        
        logger.info(f"  {region} assets (7d): {asset_directions}")
    
    logger.info("=" * 60)
    logger.info("Risk Engine Complete")
    logger.info("=" * 60)
    
    return scored_count

if __name__ == "__main__":
    run_risk_engine()
