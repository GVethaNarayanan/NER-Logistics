import sys
import logging
import argparse
import os
import time
import json
import urllib.request
from datetime import datetime
from pathlib import Path

import osmium
import shapely.wkb
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, LineString, MultiLineString, MultiPolygon
from geoalchemy2.shape import to_shape
from sqlalchemy.orm import Session
import sqlalchemy.exc
import osmnx as ox
import argparse
import os
import time
import json
import urllib.request
from datetime import datetime
from pathlib import Path

import osmium
import shapely.wkb
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, LineString, MultiLineString
from geoalchemy2.shape import to_shape
from sqlalchemy.orm import Session
import osmnx as ox

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import State, District, Road

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("ner_logistics.stage3.osm_roads")

INCLUDED_HIGHWAYS = {
    "motorway", "motorway_link",
    "trunk", "trunk_link",
    "primary", "primary_link",
    "secondary", "secondary_link",
    "tertiary", "tertiary_link",
    "unclassified",
    "residential"
}

TAG_KEYS = [
    "highway", "surface", "smoothness", "tracktype", "access",
    "bridge", "tunnel", "lanes", "maxspeed", "oneway", "name", "ref"
]

CACHE_DIR = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) / ".osm_cache"
PBF_URL = "https://download.geofabrik.de/asia/india/north-eastern-zone-latest.osm.pbf"
PBF_FILE = CACHE_DIR / "north-eastern-zone-latest.osm.pbf"
STATE_CACHE = CACHE_DIR / "ner_states_generic.gpkg"

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

class RoadHandler(osmium.SimpleHandler):
    def __init__(self):
        super(RoadHandler, self).__init__()
        self.roads = []
        self.wkbfab = osmium.geom.WKBFactory()

    def way(self, w):
        if 'highway' in w.tags and w.tags['highway'] in INCLUDED_HIGHWAYS:
            try:
                wkb = self.wkbfab.create_linestring(w)
                geom = shapely.wkb.loads(wkb, hex=True)
                
                tags = {key: w.tags[key] for key in TAG_KEYS if key in w.tags}
                
                self.roads.append({
                    'osmid': w.id,
                    'highway': w.tags['highway'],
                    'geometry': geom,
                    **tags
                })
            except Exception:
                pass

def ensure_pbf_downloaded():
    CACHE_DIR.mkdir(exist_ok=True)
    if not PBF_FILE.exists():
        logger.info(f"Downloading Geofabrik PBF extract from {PBF_URL}...")
        urllib.request.urlretrieve(PBF_URL, PBF_FILE)
        logger.info("Download complete.")

def get_generic_state_boundaries():
    if STATE_CACHE.exists():
        logger.info("Loading generic state boundaries from cache...")
        return gpd.read_file(STATE_CACHE)
    
    logger.info("Fetching generic state boundaries from OSMnx...")
    gdfs = []
    for state in NER_STATES:
        try:
            gdf = ox.geocode_to_gdf(state)
            # Store just the state name, e.g. 'Assam'
            gdf['state_name'] = state.split(',')[0]
            gdfs.append(gdf[['state_name', 'geometry']])
            time.sleep(1) # Be polite to Nominatim
        except Exception as e:
            logger.error(f"Failed to fetch geometry for {state}: {e}")
            
    states_gdf = pd.concat(gdfs, ignore_index=True)
    states_gdf.to_file(STATE_CACHE, driver="GPKG")
    
    # Store provenance
    meta = {
        "source": "osmnx Nominatim geocoding",
        "retrieval_date": datetime.utcnow().isoformat() + "Z",
        "purpose": "NER inclusion and state reporting ONLY. Not for authentic boundaries."
    }
    with open(STATE_CACHE.with_suffix('.json'), 'w') as f:
        json.dump(meta, f, indent=2)
        
    return states_gdf

def get_final_roads(db: Session):
    logger.info("Starting Stage 3 Dry Run using Geofabrik PBF...")
    ensure_pbf_downloaded()
    
    logger.info("Parsing OSM PBF file... (this may take a few minutes)")
    handler = RoadHandler()
    start_time = time.time()
    handler.apply_file(str(PBF_FILE), locations=True)
    logger.info(f"Parsed {len(handler.roads)} road geometries in {time.time() - start_time:.2f}s")
    
    if not handler.roads:
        logger.error("No roads parsed from PBF!")
        return
        
    roads_gdf = gpd.GeoDataFrame(handler.roads, geometry='geometry', crs="EPSG:4326")
    valid_mask = roads_gdf.geometry.is_valid & roads_gdf.geometry.type.isin(["LineString", "MultiLineString"])
    invalid_count = len(roads_gdf) - valid_mask.sum()
    roads_gdf = roads_gdf[valid_mask].copy()

    # 1. State Coverage (Existence in NER)
    generic_states_gdf = get_generic_state_boundaries()
    
    logger.info("Performing spatial join with generic NER states to filter outliers...")
    # Map roads to states. Since roads can cross states, we'll keep the first one they intersect for reporting.
    # We do a 'left' join first or 'inner' to filter out those completely outside.
    roads_in_states = gpd.sjoin(roads_gdf, generic_states_gdf, how="inner", predicate="intersects")
    
    # Deduplicate roads that might cross multiple generic state boundaries (assign to first)
    roads_in_states = roads_in_states.drop_duplicates(subset=['osmid'], keep='first')
    
    accepted_ner_roads = roads_in_states.copy()
    accepted_ner_roads = accepted_ner_roads.drop(columns=['index_right'], errors='ignore')
    num_outside_ner = len(roads_gdf) - len(accepted_ner_roads)
    
    # Prepare unassigned metrics
    # Create dictionary mapping osmid -> state_name
    osmid_to_state = dict(zip(accepted_ner_roads['osmid'], accepted_ner_roads['state_name']))
    
    # 2. District Assignment
    try:
        # Try database first
        districts = db.query(District).filter(District.boundary != None).all()
        district_features = [{'district_id': d.id, 'geometry': to_shape(d.boundary)} for d in districts]
        districts_gdf = gpd.GeoDataFrame(district_features, geometry='geometry', crs="EPSG:4326")
    except sqlalchemy.exc.OperationalError:
        logger.warning("Database connection failed. Falling back to reading authentic boundaries from ind_adm2.geojson for the dry-run!")
        # Re-implement the district parsing logic from Stage 2 ingest script to mock the 109 districts
        def normalize_name(name):
            if not name: return ""
            return name.lower().replace(" district", "").replace("-", " ").strip()
        
        CANONICAL_DISTRICTS = [
            "Anjaw", "Bichom", "Changlang", "Dibang Valley", "East Kameng", "East Siang", "Itanagar Capital Complex", "Kamle", "Keyi Panyor", "Kra Daadi", "Kurung Kumey", "Lepa Rada", "Lohit", "Longding", "Lower Dibang Valley", "Lower Siang", "Lower Subansiri", "Namsai", "Pakke Kessang", "Papum Pare", "Shi Yomi", "Siang", "Tawang", "Tirap", "Upper Siang", "Upper Subansiri", "West Kameng", "West Siang",
            "Baksa", "Bajali", "Barpeta", "Biswanath", "Bongaigaon", "Cachar", "Charaideo", "Chirang", "Darrang", "Dhemaji", "Dhubri", "Dibrugarh", "Dima Hasao", "Goalpara", "Golaghat", "Hailakandi", "Hojai", "Jorhat", "Kamrup Metropolitan", "Kamrup", "Karbi Anglong", "Karimganj", "Kokrajhar", "Lakhimpur", "Majuli", "Morigaon", "Nagaon", "Nalbari", "Sivasagar", "Sonitpur", "South Salmara-Mankachar", "Tamulpur", "Tinsukia", "Udalguri", "West Karbi Anglong",
            "Bishnupur", "Chandel", "Churachandpur", "Imphal East", "Imphal West", "Jiribam", "Kakching", "Kamjong", "Kangpokpi", "Noney", "Pherzawl", "Senapati", "Tamenglong", "Tengnoupal", "Thoubal", "Ukhrul",
            "East Garo Hills", "East Jaintia Hills", "East Khasi Hills", "Eastern West Khasi Hills", "North Garo Hills", "Ri Bhoi", "South Garo Hills", "South West Garo Hills", "South West Khasi Hills", "West Garo Hills", "West Jaintia Hills", "West Khasi Hills",
            "Aizawl", "Champhai", "Hnahthial", "Khawzawl", "Kolasib", "Lawngtlai", "Lunglei", "Mamit", "Saitual", "Serchhip", "Siaha",
            "Chumoukedima", "Dimapur", "Kiphire", "Kohima", "Longleng", "Mokokchung", "Mon", "Niuland", "Noklak", "Peren", "Phek", "Pughoboto", "Shamator", "Tseminyu", "Tuensang", "Wokha", "Zunheboto",
            "Gangtok", "Gyalshing", "Mangan", "Namchi", "Pakyong", "Soreng",
            "Dhalai", "Gomati", "Khowai", "North Tripura", "Sepahijala", "South Tripura", "Unakoti", "West Tripura"
        ]
        canonical_norms = {normalize_name(d): d for d in CANONICAL_DISTRICTS}
        
        gdf = gpd.read_file(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ind_adm2.geojson"))
        matched_features = []
        for idx, row in gdf.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty or not geom.is_valid: continue
            adm2 = row.get("shapeName") or row.get("NAME_2") or row.get("dt_name") or row.get("district")
            if not adm2: continue
            d_norm = normalize_name(adm2)
            if d_norm == "kamrup metro": d_norm = "kamrup metropolitan"
            if d_norm == "bongaigaon district": d_norm = "bongaigaon"
            if d_norm == "papumpare": d_norm = "papum pare"
            if d_norm == "karbi anglong west": d_norm = "west karbi anglong"
            if d_norm == "shiyomi": d_norm = "shi yomi"
            
            if d_norm in canonical_norms:
                d_name = canonical_norms[d_norm]
                if geom.geom_type == 'Polygon': geom = MultiPolygon([geom])
                # Mock ID mapping
                district_id = abs(hash(d_name)) % (10 ** 8)
                matched_features.append({'district_id': district_id, 'district_name': d_name, 'geometry': geom})
                
        districts_gdf = gpd.GeoDataFrame(matched_features, geometry='geometry', crs="EPSG:4326")
    
    logger.info(f"Loaded {len(districts_gdf)} authentic district boundaries for spatial assignment.")
    
    logger.info("Performing spatial assignment against districts...")
    # Use left join so we don't drop any NER road, even if district is unresolved
    district_joined = gpd.sjoin(accepted_ner_roads, districts_gdf, how="left", predicate="intersects")
    
    # 3. Handle Assignments and Ties
    final_roads = []
    
    # Metrics
    assigned_count = 0
    unassigned_count = 0
    border_resolved = 0
    border_tied = 0
    
    unresolved_by_state = {state.split(',')[0]: 0 for state in NER_STATES}
    
    # Group by osmid to process border-crossing roads
    for osmid, group in district_joined.groupby('osmid'):
        row = group.iloc[0]
        
        # Check if district_id is NaN (unresolved)
        if pd.isna(row['district_id']):
            unassigned_count += 1
            unresolved_by_state[osmid_to_state[osmid]] += 1
            row['final_district_id'] = None
            final_roads.append(row)
            continue
            
        if len(group) == 1:
            # Single district intersection
            assigned_count += 1
            row['final_district_id'] = row['district_id']
            final_roads.append(row)
        else:
            # Multiple authentic districts
            road_geom = row.geometry
            max_len = -1
            best_d_id = None
            tied = False
            
            for _, g_row in group.iterrows():
                d_id = g_row['district_id']
                d_geom = districts_gdf[districts_gdf['district_id'] == d_id].iloc[0].geometry
                intersection = road_geom.intersection(d_geom)
                ilength = intersection.length
                
                # Check for indistinguishable tie (float tolerance)
                if abs(ilength - max_len) < 1e-9:
                    tied = True
                elif ilength > max_len:
                    max_len = ilength
                    best_d_id = d_id
                    tied = False
                    
            if tied:
                # Retain road but district_id = None
                border_tied += 1
                unassigned_count += 1
                unresolved_by_state[osmid_to_state[osmid]] += 1
                row['final_district_id'] = None
            else:
                border_resolved += 1
                assigned_count += 1
                row['final_district_id'] = best_d_id
                
            final_roads.append(row)
            
    final_gdf = pd.DataFrame(final_roads)
    
    # Report metrics
    state_coverage = accepted_ner_roads['state_name'].value_counts().to_dict()
    
    return final_gdf, {
        "total_source_features": len(roads_gdf) + invalid_count,
        "accepted_ner_roads": len(accepted_ner_roads),
        "dropped_outside_ner": num_outside_ner,
        "invalid_geometry": invalid_count,
        "assigned_count": assigned_count,
        "unassigned_count": unassigned_count,
        "border_resolved": border_resolved,
        "border_tied": border_tied,
        "unresolved_by_state": unresolved_by_state,
        "state_coverage": state_coverage
    }

def run_dry_run(db: Session):
    logger.info("Starting dry-run...")
    final_gdf, metrics = get_final_roads(db)
    
    print("\\n" + "="*70)
    print("NER ROAD NETWORK — REVISED STAGE 3 VALIDATION REPORT (DRY RUN)")
    print("="*70)
    print(f"Source: Geofabrik north-eastern-zone-latest.osm.pbf")
    print(f"Retrieval Date: {datetime.utcnow().isoformat()}")
    print("-" * 70)
    print(f"Total source features parsed: {metrics['total_source_features']}")
    print(f"Accepted NER roads (inside 8 states): {metrics['accepted_ner_roads']}")
    print(f"Roads genuinely outside NER (dropped): {metrics['dropped_outside_ner']}")
    print(f"Invalid geometry (dropped): {metrics['invalid_geometry']}")
    print("-" * 70)
    print(f"Roads assigned to authentic districts: {metrics['assigned_count']}")
    print(f"Roads retained with district_id=NULL (unresolved): {metrics['unassigned_count']}")
    print("-" * 70)
    print(f"Border-crossing roads resolved (max length): {metrics['border_resolved']}")
    print(f"Ambiguous/tied border roads (retained as NULL): {metrics['border_tied']}")
    print("-" * 70)
    print("Unresolved roads breakdown by State (district_id=NULL):")
    for st in sorted(metrics['unresolved_by_state'].keys()):
        count = metrics['unresolved_by_state'][st]
        print(f"  - {st}: {count}")
    print("-" * 70)
    print("Coverage for all 8 NER states (Total Accepted Roads):")
    for st in [s.split(',')[0] for s in NER_STATES]:
        count = metrics['state_coverage'].get(st, 0)
        print(f"  - {st}: {count} roads")
    print("="*70)

def run_import(db: Session):
    logger.info("Starting PRODUCTION IMPORT...")
    final_gdf, metrics = get_final_roads(db)
    
    logger.info("Cleaning up old non-legacy roads...")
    try:
        deleted = db.query(Road).filter(Road.is_legacy == False).delete()
        db.commit()
        logger.info(f"Deleted {deleted} old non-legacy roads.")
    except Exception as e:
        logger.error(f"Failed to delete old roads: {e}")
        db.rollback()
        return

    logger.info("Preparing roads for bulk insert...")
    from shapely.wkt import dumps
    
    chunk_size = 5000
    total_roads = len(final_gdf)
    logger.info(f"Inserting {total_roads} roads in chunks of {chunk_size}...")
    
    records = []
    for idx, row in final_gdf.iterrows():
        tags = {k: v for k, v in row.to_dict().items() if k in TAG_KEYS and pd.notna(v)}
        geom_wkt = dumps(row.geometry)
        
        name = tags.get("name")
        if not name and tags.get("ref"):
            name = tags.get("ref")
            
        record = {
            "osm_id": int(row["osmid"]),
            "osm_tags": tags,
            "source": "osm",
            "is_legacy": False,
            "name": name,
            "road_type": row["highway"],
            "geometry": f"SRID=4326;{geom_wkt}",
            "district_id": int(row["final_district_id"]) if pd.notna(row["final_district_id"]) else None,
            "status": "open"
        }
        records.append(record)
        
    inserted_count = 0
    try:
        for i in range(0, len(records), chunk_size):
            chunk = records[i:i+chunk_size]
            db.execute(Road.__table__.insert(), chunk)
            db.commit()
            inserted_count += len(chunk)
            logger.info(f"Inserted {inserted_count} / {total_roads} roads...")
        logger.info("Production import completed successfully!")
    except Exception as e:
        logger.error(f"Bulk insert failed at chunk {i}: {e}")
        db.rollback()
        return

    print("\\n" + "="*70)
    print("NER ROAD NETWORK — STAGE 3 PRODUCTION IMPORT REPORT")
    print("="*70)
    print(f"Source: Geofabrik north-eastern-zone-latest.osm.pbf")
    print(f"Retrieval Date: {datetime.utcnow().isoformat()}")
    print("-" * 70)
    print(f"Old non-legacy roads deleted: {deleted}")
    print(f"Total source features parsed: {metrics['total_source_features']}")
    print(f"Total valid NER roads (inside 8 states): {metrics['accepted_ner_roads']}")
    print(f"Roads successfully inserted: {inserted_count}")
    print("="*70)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Acquire and validate NER road network from OSM.")
    parser.add_argument("--dry-run", action="store_true", help="Acquire, cache, and print validation report without importing to DB.")
    args = parser.parse_args()
    
    db = SessionLocal()
    try:
        if args.dry_run:
            run_dry_run(db)
        else:
            run_import(db)
    finally:
        db.close()
