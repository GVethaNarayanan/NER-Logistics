import json
import geopandas as gpd
import argparse
import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def normalize_name(name):
    if not name:
        return ""
    return name.lower().replace(" district", "").replace("-", " ").strip()

def reconcile(geojson_path, canonical_json_path):
    logger.info(f"Loading GeoJSON from {geojson_path}")
    gdf = gpd.read_file(geojson_path)
    logger.info(f"GeoJSON loaded. {len(gdf)} features found.")

    with open(canonical_json_path, 'r') as f:
        canonical_data = json.load(f)

    # Flatten canonical districts
    canonical = {}
    for state, info in canonical_data.items():
        canonical[normalize_name(state)] = {normalize_name(d): d for d in info['districts']}

    matched = []
    unmatched_canonical = []
    unmatched_source_ner = []
    invalid_geometries = []
    
    # Track matches
    matched_set = set()

    for idx, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        
        # Flatten canonical for global district name lookup to handle missing ADM1
        # Mapping: {d_norm: state_name}
        global_canonical = {}
        for s_norm, dists in canonical.items():
            for d_norm, d_name in dists.items():
                # For simplicity in this script, assume district names are unique across NER
                # If there are duplicates, we would need spatial joins, but we'll flag them if they happen.
                global_canonical[d_norm] = s_norm
                
        adm1 = row.get("shapeGroup") or row.get("NAME_1") or row.get("st_nm") or row.get("state")
        adm2 = row.get("shapeName") or row.get("NAME_2") or row.get("dt_name") or row.get("district")
        
        if not adm2:
            continue
        
        s_norm = normalize_name(adm1)
        d_norm = normalize_name(adm2)
        
        # known aliases
        if d_norm == "kamrup metro": d_norm = "kamrup metropolitan"
        if d_norm == "bongaigaon district": d_norm = "bongaigaon"
        if d_norm == "papumpare": d_norm = "papum pare"
        if d_norm == "karbi anglong west": d_norm = "west karbi anglong"
        if d_norm == "shiyomi": d_norm = "shi yomi"
        
        # If state name is provided in the file and matches
        if s_norm in canonical:
            matched_state = s_norm
        else:
            # Fallback to global lookup if state is missing (e.g. geoBoundaries uses "IND")
            matched_state = global_canonical.get(d_norm)

        if matched_state:
            if d_norm in canonical[matched_state]:
                matched.append(f"{matched_state.title()} - {canonical[matched_state][d_norm]}")
                matched_set.add((matched_state, d_norm))
                if not geom.is_valid:
                    invalid_geometries.append(f"{matched_state} - {adm2}")
            else:
                unmatched_source_ner.append(f"Unknown - {adm2}")
        else:
            # Unmatched feature across all of India, we don't care if it's outside NER
            pass

    # Find missing
    for state, districts in canonical.items():
        for d_norm, d_name in districts.items():
            if (state, d_norm) not in matched_set:
                unmatched_canonical.append(f"{state.title()} - {d_name}")

    total_canonical = sum(len(districts) for districts in canonical.values())

    print("\n" + "="*50)
    print("RECONCILIATION REPORT")
    print("="*50)
    print(f"Total Canonical Districts: {total_canonical}")
    print(f"Authentic Boundaries Matched: {len(matched)}")
    print(f"Missing Boundaries: {len(unmatched_canonical)}")
    print(f"Unmatched Source Features (in NER states): {len(unmatched_source_ner)}")
    print(f"Invalid Geometries Repaired/Rejected: {len(invalid_geometries)}")
    print("-"*50)
    print("Missing Canonical Boundaries (Top 20):")
    for missing in unmatched_canonical[:20]:
        print(f"  - {missing}")
    if len(unmatched_canonical) > 20:
        print(f"  ... and {len(unmatched_canonical) - 20} more.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--geojson", required=True)
    parser.add_argument("--canonical", required=True)
    args = parser.parse_args()
    reconcile(args.geojson, args.canonical)
