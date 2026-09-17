import geopandas as gpd
import osmnx as ox
import logging
import warnings

warnings.filterwarnings('ignore')
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_legacy_roads():
    # Load boundaries
    logger.info("Loading boundaries from ind_adm2.geojson...")
    boundaries = gpd.read_file('ind_adm2.geojson')
    
    # Filter Kamrup Metropolitan
    kamrup = boundaries[boundaries['shapeName'].str.lower() == 'kamrup metropolitan']
    if kamrup.empty:
        logger.error("Kamrup Metropolitan not found in geojson.")
        return
    
    kamrup_geom = kamrup.geometry.iloc[0]
    
    # Fetch ~80 legacy roads from OSM (similar to legacy fixture)
    logger.info("Fetching legacy road network for Guwahati (bbox)...")
    # A small bbox in central Guwahati
    north, south, east, west = 26.2, 26.1, 91.8, 91.7
    graph = ox.graph_from_bbox(bbox=(north, south, east, west), network_type='drive', simplify=True, truncate_by_edge=True)
    
    _, edges = ox.graph_to_gdfs(graph)
    edges = edges.head(80) # Limit to 80 roads
    
    logger.info(f"Loaded {len(edges)} legacy roads.")
    
    mapped_count = 0
    outside_count = 0
    cross_count = 0
    
    for idx, road in edges.iterrows():
        road_geom = road.geometry
        
        # Check intersection
        if kamrup_geom.contains(road_geom):
            mapped_count += 1
        elif kamrup_geom.intersects(road_geom):
            # It crosses the boundary (or partially outside)
            cross_count += 1
        else:
            outside_count += 1
            
    print("\n" + "="*50)
    print("80 LEGACY ROADS SPATIAL TEST")
    print("="*50)
    print(f"Total Roads Tested: {len(edges)}")
    print(f"Mapped correctly to Kamrup Metropolitan: {mapped_count}")
    print(f"Roads crossing a district boundary: {cross_count}")
    print(f"Roads falling outside every district: {outside_count}")
    print("="*50)

if __name__ == "__main__":
    test_legacy_roads()
