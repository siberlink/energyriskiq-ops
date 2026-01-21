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
    parser.add_argument('--mode', choices=['api', 'ingest', 'ai', 'risk', 'alerts', 'digest', 'geri', 'migrate_plans'], default='api',
                        help='Run mode: api (start server), ingest (run ingestion), ai (run AI processing), risk (run risk scoring), alerts (run alerts engine), digest (run daily digest), geri (compute daily GERI index), migrate_plans (migrate user plans)')
    
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
        alerts_v2 = os.environ.get('ALERTS_V2_ENABLED', 'true').lower() == 'true'
        if alerts_v2:
            from src.alerts.alerts_engine_v2 import run_alerts_engine_v2
            from src.db.migrations import run_migrations
            run_migrations()
            run_alerts_engine_v2()
        else:
            from src.alerts.alerts_engine import run_alerts_engine, run_alerts_loop, ALERTS_LOOP
            if ALERTS_LOOP:
                run_alerts_loop()
            else:
                run_alerts_engine()
    
    elif args.mode == 'digest':
        from src.alerts.digest_worker import run_digest_worker
        run_digest_worker()
    
    elif args.mode == 'geri':
        from src.geri.service import compute_yesterday
        from src.geri import ENABLE_GERI
        from datetime import date, timedelta
        if not ENABLE_GERI:
            logger.warning("GERI module is disabled (ENABLE_GERI=false)")
        else:
            yesterday = date.today() - timedelta(days=1)
            logger.info(f"Computing GERI index for yesterday: {yesterday}")
            result = compute_yesterday()
            if result:
                logger.info(f"GERI computed: value={result.value}, band={result.band.value}")
            else:
                logger.info("GERI computation skipped (already exists or no data)")
    
    elif args.mode == 'migrate_plans':
        from src.db.migrations import ensure_user_plans_table
        from src.plans.plan_helpers import migrate_user_plans
        logger.info("Running user_plans migration...")
        ensure_user_plans_table()
        migrate_user_plans()
        logger.info("Migration complete.")

if __name__ == "__main__":
    main()
