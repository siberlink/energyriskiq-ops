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
    parser.add_argument('--mode', choices=['api', 'ingest'], default='api',
                        help='Run mode: api (start server) or ingest (run ingestion)')
    
    args = parser.parse_args()
    
    if args.mode == 'api':
        import uvicorn
        from src.api.app import app
        logger.info("Starting API server on port 5000...")
        uvicorn.run(app, host="0.0.0.0", port=5000)
    
    elif args.mode == 'ingest':
        from src.ingest.ingest_runner import run_ingestion
        run_ingestion()

if __name__ == "__main__":
    main()
