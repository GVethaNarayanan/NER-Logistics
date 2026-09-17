import sys
import logging
import warnings

warnings.warn("DEPRECATED: Use seed_ner_districts.py for authoritative NER district registry.", DeprecationWarning)
from sqlalchemy.orm import Session
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.database import SessionLocal
from app.models import State, District

logging.basicConfig(level=logging.INFO)

def seed_registry():
    db = SessionLocal()
    try:
        # Seed Assam
        assam = db.query(State).filter_by(name="Assam").first()
        if not assam:
            assam = State(name="Assam")
            db.add(assam)
            db.commit()
            db.refresh(assam)
            
        # Seed Kamrup Metropolitan
        kamrup = db.query(District).filter_by(name="Kamrup Metropolitan").first()
        if not kamrup:
            kamrup = District(
                name="Kamrup Metropolitan", 
                state_id=assam.id,
                centroid_lat=26.1445,
                centroid_lon=91.7362
            )
            db.add(kamrup)
            db.commit()
            
        logging.info("Registry seeded successfully.")
    finally:
        db.close()

if __name__ == "__main__":
    seed_registry()
