import os
import sys
import logging
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("ner_logistics.stage4.backfill")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/ner_logistics")

def run_backfill():
    logger.info("Starting backfill of endpoint coordinates from geometry...")
    
    engine = create_engine(DATABASE_URL)
    with engine.begin() as conn:
        # Check current state
        result = conn.execute(text("SELECT COUNT(*) FROM roads WHERE start_lat IS NULL")).scalar()
        logger.info(f"Roads missing endpoints before backfill: {result}")
        
        legacy_count = conn.execute(text("SELECT COUNT(*) FROM roads WHERE is_legacy = true")).scalar()
        logger.info(f"Total legacy roads: {legacy_count}")

        # Execute backfill
        # We use ST_Y for latitude and ST_X for longitude (since PostGIS is lon/lat)
        # ST_StartPoint and ST_EndPoint extract the first and last vertex of a LineString
        backfill_sql = text("""
            UPDATE roads
            SET start_lat = ST_Y(ST_StartPoint(geometry)),
                start_lon = ST_X(ST_StartPoint(geometry)),
                end_lat   = ST_Y(ST_EndPoint(geometry)),
                end_lon   = ST_X(ST_EndPoint(geometry))
            WHERE geometry IS NOT NULL
              AND start_lat IS NULL
        """)
        
        result = conn.execute(backfill_sql)
        updated_count = result.rowcount
        logger.info(f"Successfully backfilled endpoints for {updated_count} roads.")
        
        # Verify
        remaining = conn.execute(text("SELECT COUNT(*) FROM roads WHERE geometry IS NOT NULL AND start_lat IS NULL")).scalar()
        logger.info(f"Roads with geometry but missing endpoints after backfill: {remaining}")
        
        if remaining > 0:
            logger.warning(f"There are still {remaining} roads missing endpoints.")
            
        legacy_after = conn.execute(text("SELECT COUNT(*) FROM roads WHERE is_legacy = true")).scalar()
        if legacy_count != legacy_after:
            logger.error("Legacy road count changed during backfill! This should not happen.")
            
        logger.info("Backfill complete.")

if __name__ == "__main__":
    run_backfill()
