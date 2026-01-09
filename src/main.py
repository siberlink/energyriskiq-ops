import os
import sys
import argparse
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description='EnergyRiskIQ Pipeline')
    parser.add_argument('--mode', choices=['api', 'ingest', 'ai', 'risk', 'alerts', 'digest', 'migrate_plans'], default='api',
                        help='Run mode: api (start server), ingest (run ingestion), ai (run AI processing), risk (run risk scoring), alerts (run alerts engine), digest (run daily digest), migrate_plans (migrate user plans)')
    
    args = parser.parse_args()
    
    if args.mode == 'api':
        import uvicorn
        from src.api.app import app
        port = int(os.environ.get('PORT', 5000))
        logger.info(f"Starting API server on port {port}...")
        uvicorn.run(app, host="0.0.0.0", port=port)
    
    elif args.mode == 'ingest':
        from src.ingest.ingest_runner import run_ingestion
        run_ingestion()
    
    elif args.mode == 'ai':
        from src.ai.ai_worker import run_ai_worker
        run_ai_worker()
    
    elif args.mode == 'risk':
        from src.risk.risk_engine import run_risk_engine
        run_risk_engine()
    
    elif args.mode == 'alerts':
        from src.alerts.alerts_engine import run_alerts_engine, run_alerts_loop, ALERTS_LOOP
        if ALERTS_LOOP:
            run_alerts_loop()
        else:
            run_alerts_engine()
    
    elif args.mode == 'digest':
        from src.alerts.digest_worker import run_digest_worker
        run_digest_worker()
    
    elif args.mode == 'migrate_plans':
        from src.db.migrations import ensure_user_plans_table
        from src.plans.plan_helpers import migrate_user_plans
        logger.info("Running user_plans migration...")
        ensure_user_plans_table()
        migrate_user_plans()
        logger.info("Migration complete.")

if __name__ == "__main__":
    main()
