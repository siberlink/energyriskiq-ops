import logging
import os
import sys
import json
import time
from typing import Optional, Dict, Any, Tuple
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from openai import OpenAI
from src.db.db import get_cursor, execute_query
from src.db.migrations import run_migrations

logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

AI_MAX_EVENTS_PER_RUN = int(os.environ.get('AI_MAX_EVENTS_PER_RUN', '20'))
AI_MAX_CHARS = int(os.environ.get('AI_MAX_CHARS', '6000'))
AI_TEMPERATURE = float(os.environ.get('AI_TEMPERATURE', '0.2'))
AI_SLEEP_BETWEEN_CALLS = float(os.environ.get('AI_SLEEP_BETWEEN_CALLS', '0.5'))
AI_MAX_RETRIES = 2

OPENAI_MODEL = os.environ.get('OPENAI_MODEL', 'gpt-4.1-mini')

SYSTEM_PROMPT = """You are an energy and geopolitical risk analyst. Analyze news events and provide structured intelligence output.

You must respond with ONLY valid JSON (no markdown fences, no explanations). Follow this exact schema:

{
  "summary": "2-3 sentence neutral summary in English. No hype, no speculation.",
  "key_facts": ["fact1", "fact2", "fact3"],
  "entities": {
    "countries": ["list of countries mentioned"],
    "companies": ["list of companies mentioned"],
    "commodities": ["oil", "gas", "lng", "power", "freight", "fx"],
    "routes": ["Suez", "Black Sea", "Bosphorus", "Panama", "Red Sea", "North Sea"]
  },
  "impact": {
    "oil": {"direction": "up|down|mixed|unclear", "confidence": 0.0-1.0, "rationale": "brief explanation"},
    "gas": {"direction": "up|down|mixed|unclear", "confidence": 0.0-1.0, "rationale": "brief explanation"},
    "fx": {"direction": "risk_off|risk_on|mixed|unclear", "confidence": 0.0-1.0, "rationale": "brief explanation"},
    "freight": {"direction": "up|down|mixed|unclear", "confidence": 0.0-1.0, "rationale": "brief explanation"}
  },
  "time_horizon_days": 7,
  "risk_flags": []
}

Rules:
- Only include commodities/routes actually mentioned or directly relevant
- Use "unclear" with low confidence (0.1-0.3) when uncertain
- risk_flags can include: sanctions, supply_disruption, military_escalation, port_disruption, pipeline_outage, strike, regulatory_change
- Be neutral, factual, and cautious
- Do not give investment advice
- If the text is insufficient for analysis, still provide a valid JSON with "unclear" values"""

def get_openai_client() -> OpenAI:
    base_url = os.environ.get('AI_INTEGRATIONS_OPENAI_BASE_URL')
    api_key = os.environ.get('AI_INTEGRATIONS_OPENAI_API_KEY')
    
    if not base_url or not api_key:
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("No OpenAI API key found. Set AI_INTEGRATIONS_OPENAI_API_KEY or OPENAI_API_KEY")
        return OpenAI(api_key=api_key)
    
    return OpenAI(base_url=base_url, api_key=api_key)

def fetch_unprocessed_events(limit: int) -> list:
    query = """
    SELECT id, title, raw_text, ai_attempts
    FROM events
    WHERE processed = FALSE AND ai_attempts < 3
    ORDER BY inserted_at ASC
    LIMIT %s
    """
    return execute_query(query, (limit,))

def increment_attempts(event_id: int):
    with get_cursor() as cursor:
        cursor.execute(
            "UPDATE events SET ai_attempts = ai_attempts + 1 WHERE id = %s",
            (event_id,)
        )

def save_ai_result(event_id: int, summary: str, impact_json: dict, model: str):
    with get_cursor() as cursor:
        cursor.execute(
            """UPDATE events 
               SET processed = TRUE, 
                   ai_summary = %s, 
                   ai_impact_json = %s,
                   ai_model = %s,
                   ai_processed_at = NOW(),
                   ai_error = NULL
               WHERE id = %s""",
            (summary, json.dumps(impact_json), model, event_id)
        )

def save_ai_error(event_id: int, error_message: str):
    with get_cursor() as cursor:
        cursor.execute(
            """UPDATE events 
               SET ai_error = %s
               WHERE id = %s""",
            (error_message[:500], event_id)
        )

def build_input_text(title: str, raw_text: Optional[str]) -> str:
    text = title
    if raw_text:
        text += "\n\n" + raw_text
    return text[:AI_MAX_CHARS]

def parse_ai_response(response_text: str) -> Tuple[bool, Dict[str, Any], str]:
    try:
        cleaned = response_text.strip()
        if cleaned.startswith('```'):
            lines = cleaned.split('\n')
            if lines[0].startswith('```'):
                lines = lines[1:]
            if lines and lines[-1].strip() == '```':
                lines = lines[:-1]
            cleaned = '\n'.join(lines)
        
        result = json.loads(cleaned)
        
        if 'summary' not in result:
            return False, {}, "Missing 'summary' field in response"
        if 'impact' not in result:
            return False, {}, "Missing 'impact' field in response"
        
        return True, result, ""
    
    except json.JSONDecodeError as e:
        return False, {}, f"Invalid JSON: {str(e)}"
    except Exception as e:
        return False, {}, f"Parse error: {str(e)}"

def call_ai_with_retries(client: OpenAI, input_text: str, model: str) -> Tuple[bool, str, str]:
    for attempt in range(AI_MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Analyze this news event:\n\n{input_text}"}
                ],
                temperature=AI_TEMPERATURE,
                max_tokens=2000
            )
            
            response_text = response.choices[0].message.content
            return True, response_text, ""
        
        except Exception as e:
            error_msg = str(e)
            logger.warning(f"AI call attempt {attempt + 1} failed: {error_msg}")
            
            if attempt < AI_MAX_RETRIES:
                sleep_time = (2 ** attempt) * 1.0
                time.sleep(sleep_time)
            else:
                return False, "", error_msg
    
    return False, "", "Max retries exceeded"

def process_event(client: OpenAI, event: dict, model: str) -> Tuple[bool, str]:
    event_id = event['id']
    title = event['title']
    raw_text = event.get('raw_text')
    
    increment_attempts(event_id)
    
    input_text = build_input_text(title, raw_text)
    
    success, response_text, error = call_ai_with_retries(client, input_text, model)
    
    if not success:
        save_ai_error(event_id, error)
        return False, f"API error: {error}"
    
    parse_success, result, parse_error = parse_ai_response(response_text)
    
    if not parse_success:
        save_ai_error(event_id, parse_error)
        return False, f"Parse error: {parse_error}"
    
    summary = result.get('summary', '')
    save_ai_result(event_id, summary, result, model)
    
    return True, summary[:100]

def run_ai_worker():
    logger.info("=" * 60)
    logger.info("Starting EnergyRiskIQ AI Processing Worker")
    logger.info(f"Model: {OPENAI_MODEL}, Max events: {AI_MAX_EVENTS_PER_RUN}")
    logger.info("=" * 60)
    
    run_migrations()
    
    try:
        client = get_openai_client()
    except ValueError as e:
        logger.error(f"Failed to initialize AI client: {e}")
        return 0, 0
    
    events = fetch_unprocessed_events(AI_MAX_EVENTS_PER_RUN)
    
    if not events:
        logger.info("No unprocessed events found.")
        return 0, 0
    
    logger.info(f"Found {len(events)} unprocessed events")
    
    success_count = 0
    failure_count = 0
    total_time = 0
    
    for i, event in enumerate(events):
        start_time = time.time()
        
        logger.info(f"Processing event {i + 1}/{len(events)}: {event['title'][:50]}...")
        
        success, message = process_event(client, event, OPENAI_MODEL)
        
        elapsed = time.time() - start_time
        total_time += elapsed
        
        if success:
            success_count += 1
            logger.info(f"  Success ({elapsed:.1f}s): {message}...")
        else:
            failure_count += 1
            logger.error(f"  Failed ({elapsed:.1f}s): {message}")
        
        if i < len(events) - 1:
            time.sleep(AI_SLEEP_BETWEEN_CALLS)
    
    avg_time = total_time / len(events) if events else 0
    
    logger.info("=" * 60)
    logger.info(f"AI Processing Complete:")
    logger.info(f"  Processed: {success_count} success, {failure_count} failed")
    logger.info(f"  Average time per event: {avg_time:.1f}s")
    logger.info("=" * 60)
    
    return success_count, failure_count

if __name__ == "__main__":
    run_ai_worker()
