import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app import models
from scripts.ingest_district_boundaries import ingest_boundaries

def run_mock_dry_run():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    
    # Load 133 districts
    with open('ner_districts_133.json', 'r') as f:
        data = json.load(f)
        
    for state_name, info in data.items():
        state = models.State(name=state_name.title())
        db.add(state)
        db.flush()
        for d in info['districts']:
            dist = models.District(name=d, state_id=state.id)
            db.add(dist)
    
    db.commit()
    
    source_info = {
        "source": "geoBoundaries Open (Mock DB Run)",
        "dataset_version": "current",
        "publication_date": "Unknown",
        "retrieval_date": "2026-09-13",
        "license": "Creative Commons Attribution 4.0",
        "geographic_vintage": "2020-2023"
    }
    
    print("Running dry run...")
    ingest_boundaries('ind_adm2.geojson', source_info, dry_run=True, db_session=db)
    
if __name__ == "__main__":
    run_mock_dry_run()
