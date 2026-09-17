import sys
import logging
import osmnx as ox
from sqlalchemy.orm import Session
from shapely.geometry import shape

# Add project root to sys.path
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import State, District
from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ner_logistics.fetch_registry")

NER_STATES = [
    "Arunachal Pradesh, India",
    "Assam, India",
    "Manipur, India",
    "Meghalaya, India",
    "Mizoram, India",
    "Nagaland, India",
    "Sikkim, India",
    "Tripura, India"
]

def fetch_registry():
    db: Session = SessionLocal()
    try:
        for state_query in NER_STATES:
            state_name = state_query.split(",")[0].strip()
            logger.info(f"Fetching state boundary for {state_name}...")
            try:
                # Use nominatim via osmnx
                gdf_state = ox.geocode_to_gdf(state_query)
                state_geom = gdf_state.iloc[0].geometry
                
                state_record = db.query(State).filter(State.name == state_name).first()
                if not state_record:
                    state_record = State(name=state_name, boundary=state_geom.wkt)
                    db.add(state_record)
                    db.commit()
                    db.refresh(state_record)
                else:
                    state_record.boundary = state_geom.wkt
                    db.commit()
                
                # Fetch districts within this state
                # In India, districts are admin_level=5
                logger.info(f"Fetching districts for {state_name}...")
                
                query = {"state": state_name, "country": "India"}
                try:
                    gdf_districts = ox.features_from_place(state_query, tags={'admin_level': '5', 'boundary': 'administrative'})
                    for idx, row in gdf_districts.iterrows():
                        district_name = row.get('name', 'Unknown')
                        if district_name == 'Unknown' or not isinstance(district_name, str):
                            continue
                            
                        # Some names include " District" suffix, some don't. Let's normalize slightly or keep as is.
                        # It's better to keep the canonical OSM name.
                        dist_geom = row.geometry
                        centroid = dist_geom.centroid
                        
                        dist_record = db.query(District).filter(
                            District.name == district_name, 
                            District.state_id == state_record.id
                        ).first()
                        
                        if not dist_record:
                            dist_record = District(
                                name=district_name,
                                state_id=state_record.id,
                                boundary=dist_geom.wkt,
                                centroid_lat=centroid.y,
                                centroid_lon=centroid.x
                            )
                            db.add(dist_record)
                        else:
                            dist_record.boundary = dist_geom.wkt
                            dist_record.centroid_lat = centroid.y
                            dist_record.centroid_lon = centroid.x
                            
                    db.commit()
                    logger.info(f"Saved {len(gdf_districts)} districts for {state_name}.")
                except Exception as e:
                    logger.error(f"Failed to fetch districts for {state_name}: {e}")
            except Exception as e:
                logger.error(f"Failed to fetch state {state_name}: {e}")
                
    finally:
        db.close()

if __name__ == "__main__":
    fetch_registry()
