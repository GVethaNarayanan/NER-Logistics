import os
import sys
import argparse
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import geopandas as gpd
from geoalchemy2.shape import from_shape
from geoalchemy2.elements import WKTElement

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import Base
from app import models

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/ner_logistics")
engine = create_engine(DB_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def normalize_name(name):
    if not name:
        return ""
    # Lowercase and remove common suffixes/punctuation
    name = name.lower().replace(" district", "").replace("-", " ").strip()
    return name

def ingest_boundaries(geojson_path: str, source_info: dict, dry_run: bool = False, db_session=None):
    """
    Ingests district boundaries from a GeoJSON file.
    Only maps to districts that already exist in the database (from Stage 1 registry).
    Uses strict geometric validation.
    """
    if not os.path.exists(geojson_path):
        logger.error(f"GeoJSON file not found: {geojson_path}")
        return

    logger.info(f"Loading GeoJSON from {geojson_path}...")
    gdf = gpd.read_file(geojson_path)
    logger.info(f"Loaded {len(gdf)} features from {geojson_path}.")

    # Ensure CRS is EPSG:4326 (WGS84)
    if gdf.crs and gdf.crs.to_string() != "EPSG:4326":
        logger.info(f"Reprojecting from {gdf.crs.to_string()} to EPSG:4326...")
        gdf = gdf.to_crs("EPSG:4326")

    db = db_session or SessionLocal()
    try:
        # Load all canonical states and districts from DB
        states = {s.name: s for s in db.query(models.State).all()}
        districts_db = db.query(models.District).all()
        canonical_districts = {d.id: d for d in districts_db}
        
        # Mapping: {district_name_norm: [district_id_1, district_id_2, ...]}
        global_canonical = {}
        for d in districts_db:
            d_norm = normalize_name(d.name)
            if d_norm not in global_canonical:
                global_canonical[d_norm] = []
            global_canonical[d_norm].append(d.id)

        matched_count = 0
        matched_district_ids = set()
        missing_geometries = []
        unmatched_features = []
        ambiguous_features = []
        invalid_geometries = []

        logger.info("Beginning reconciliation...")
        for idx, row in gdf.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty:
                continue
            if not geom.is_valid:
                geom = geom.buffer(0) # Attempt to fix invalid geometries
                if not geom.is_valid:
                    invalid_geometries.append(idx)
                    continue

            # Extract ONLY district name because shapeGroup is just 'IND' in this dataset
            adm2 = row.get("shapeName") or row.get("NAME_2") or row.get("dt_name") or row.get("district")

            if not adm2:
                continue
            
            d_norm = normalize_name(adm2)
            
            # Known aliases
            if d_norm == "kamrup metro": d_norm = "kamrup metropolitan"
            if d_norm == "bongaigaon district": d_norm = "bongaigaon"
            if d_norm == "papumpare": d_norm = "papum pare"
            if d_norm == "karbi anglong west": d_norm = "west karbi anglong"
            if d_norm == "shiyomi": d_norm = "shi yomi"

            if d_norm in global_canonical:
                matched_ids = global_canonical[d_norm]
                if len(matched_ids) == 1:
                    d_id = matched_ids[0]
                    district_obj = canonical_districts[d_id]
                    
                    if geom.geom_type == 'Polygon':
                        from shapely.geometry import MultiPolygon
                        geom = MultiPolygon([geom])
                    elif geom.geom_type != 'MultiPolygon':
                        invalid_geometries.append(f"{adm2}: type {geom.geom_type}")
                        continue
                        
                    district_obj.boundary = from_shape(geom, srid=4326)
                    matched_district_ids.add(d_id)
                    matched_count += 1
                else:
                    ambiguous_features.append(adm2)
            else:
                unmatched_features.append(adm2)

        missing_geometries = []
        for d in districts_db:
            if d.id not in matched_district_ids:
                s_name = next(s_name for s_name, s in states.items() if s.id == d.state_id)
                missing_geometries.append(f"{s_name} - {d.name}")

        if not dry_run:
            db.commit()
            logger.info("Transaction committed successfully.")
        else:
            db.rollback()
            logger.info("Dry run complete. Transaction rolled back.")

        print("\n" + "="*50)
        print("RECONCILIATION REPORT")
        print("="*50)
        print(f"Source: {source_info.get('source')}")
        print(f"Dataset/Version: {source_info.get('dataset_version')}")
        print(f"Publication Date: {source_info.get('publication_date')}")
        print(f"Retrieval Date: {source_info.get('retrieval_date')}")
        print(f"License: {source_info.get('license')}")
        print(f"Geographic Vintage: {source_info.get('geographic_vintage')}")
        print("-"*50)
        print(f"Total Canonical Districts: {len(canonical_districts)}")
        print(f"Authentic Boundaries Imported: {matched_count}")
        print(f"Missing Canonical Boundaries: {len(missing_geometries)}")
        print(f"Unmatched Source Features: {len(unmatched_features)}")
        print(f"Ambiguous Source District Names: {len(ambiguous_features)}")
        print(f"Invalid Geometries Repaired/Rejected: {len(invalid_geometries)}")
        print("-"*50)
        print("Missing Canonical Boundaries:")
        for missing in missing_geometries[:20]:
            print(f"  - {missing}")
        if len(missing_geometries) > 20:
            print(f"  ... and {len(missing_geometries) - 20} more.")

    except Exception as e:
        db.rollback()
        logger.error(f"Transaction failed, rolling back: {e}")
        raise
    finally:
        if db_session is None:
            db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--geojson", required=True, help="Path to authentic GeoJSON file")
    parser.add_argument("--dry-run", action="store_true", help="Do not commit transaction")
    parser.add_argument("--source", default="geoBoundaries Open", help="Source name")
    parser.add_argument("--version", default="current", help="Dataset version")
    parser.add_argument("--date", default="2026-09-13", help="Retrieval date")
    parser.add_argument("--license", default="Creative Commons Attribution 4.0 (CC-BY 4.0)", help="License")
    parser.add_argument("--vintage", default="2020-2023", help="Geographic Vintage")
    args = parser.parse_args()

    source_info = {
        "source": args.source,
        "dataset_version": args.version,
        "publication_date": "Unknown",
        "retrieval_date": args.date,
        "license": args.license,
        "geographic_vintage": args.vintage
    }
    
    ingest_boundaries(args.geojson, source_info, dry_run=args.dry_run)
