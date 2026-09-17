"""
Phase 4.3 — Graph Topology Measurement Script

Connects to the live PostGIS database and measures:
1. Total roads / geometry statistics
2. Endpoint-based topology: node count, edge count, shared intersections
3. Intermediate-vertex intersection detection (roads crossing at non-endpoints)
4. Coordinate precision analysis
5. Oneway tag distribution
6. Graph build time, memory estimate
7. Connected components
8. Sample route performance (cold/warm)

Run: python scripts/measure_graph.py
Requires: PostgreSQL/PostGIS running via Docker Compose
"""
import sys, os, time, math, json
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import text
from app.database import SessionLocal

COORD_PRECISION = 7  # decimal places (~1cm)

def round_coord(val):
    return round(val, COORD_PRECISION)

def main():
    db = SessionLocal()
    print("=" * 70)
    print("PHASE 4.3 — TOPOLOGY MEASUREMENT")
    print("=" * 70)

    # ── 1. Basic statistics ──────────────────────────────────────────────
    total = db.execute(text("SELECT count(*) FROM roads")).scalar()
    osm = db.execute(text("SELECT count(*) FROM roads WHERE source='osm'")).scalar()
    legacy = db.execute(text("SELECT count(*) FROM roads WHERE is_legacy=true")).scalar()
    with_geom = db.execute(text("SELECT count(*) FROM roads WHERE geometry IS NOT NULL")).scalar()
    null_district = db.execute(text("SELECT count(*) FROM roads WHERE district_id IS NULL AND geometry IS NOT NULL")).scalar()
    open_roads = db.execute(text("SELECT count(*) FROM roads WHERE status='open' AND geometry IS NOT NULL AND is_legacy=false")).scalar()

    print(f"\n[1] BASIC STATISTICS")
    print(f"  Total roads:            {total}")
    print(f"  OSM roads:              {osm}")
    print(f"  Legacy roads:           {legacy}")
    print(f"  Roads with geometry:    {with_geom}")
    print(f"  NULL district (w/geom): {null_district}")
    print(f"  Open OSM (routable):    {open_roads}")

    # ── 2. Vertex statistics ─────────────────────────────────────────────
    verts = db.execute(text("""
        SELECT 
            SUM(ST_NPoints(geometry)) as total_vertices,
            AVG(ST_NPoints(geometry)) as avg_vertices,
            MIN(ST_NPoints(geometry)) as min_vertices,
            MAX(ST_NPoints(geometry)) as max_vertices
        FROM roads WHERE geometry IS NOT NULL AND is_legacy=false
    """)).fetchone()
    
    print(f"\n[2] VERTEX STATISTICS (OSM roads)")
    print(f"  Total vertices:         {verts.total_vertices}")
    print(f"  Avg vertices/road:      {verts.avg_vertices:.1f}")
    print(f"  Min vertices/road:      {verts.min_vertices}")
    print(f"  Max vertices/road:      {verts.max_vertices}")

    # ── 3. Road type distribution ────────────────────────────────────────
    types = db.execute(text("""
        SELECT road_type, count(*) as cnt
        FROM roads WHERE is_legacy=false AND geometry IS NOT NULL
        GROUP BY road_type ORDER BY cnt DESC LIMIT 15
    """)).fetchall()
    
    print(f"\n[3] ROAD TYPE DISTRIBUTION")
    for row in types:
        print(f"  {row.road_type or 'NULL':25s} {row.cnt}")

    # ── 4. Oneway tag distribution ───────────────────────────────────────
    oneway = db.execute(text("""
        SELECT osm_tags->>'oneway' as val, count(*) as cnt
        FROM roads
        WHERE osm_tags IS NOT NULL AND (osm_tags::jsonb) ? 'oneway' AND is_legacy=false
        GROUP BY val ORDER BY cnt DESC
    """)).fetchall()
    
    print(f"\n[4] ONEWAY TAG DISTRIBUTION")
    if oneway:
        for row in oneway:
            print(f"  oneway={row.val:10s} {row.cnt}")
    else:
        print("  No oneway tags found")
    
    # Count roads without oneway tag
    no_oneway = db.execute(text("""
        SELECT count(*) FROM roads 
        WHERE is_legacy=false AND geometry IS NOT NULL 
        AND (osm_tags IS NULL OR NOT ((osm_tags::jsonb) ? 'oneway'))
    """)).scalar()
    print(f"  No oneway tag:          {no_oneway}")

    # ── 5. Endpoint-based topology ───────────────────────────────────────
    print(f"\n[5] ENDPOINT-BASED TOPOLOGY ANALYSIS")
    print(f"    (Using coordinate precision: {COORD_PRECISION} decimal places)")
    
    t0 = time.time()
    # Fetch all road endpoints
    rows = db.execute(text("""
        SELECT id, 
               ST_Y(ST_StartPoint(geometry)) as start_lat,
               ST_X(ST_StartPoint(geometry)) as start_lon,
               ST_Y(ST_EndPoint(geometry)) as end_lat,
               ST_X(ST_EndPoint(geometry)) as end_lon
        FROM roads 
        WHERE geometry IS NOT NULL AND is_legacy=false AND status='open'
    """)).fetchall()
    
    node_degree = defaultdict(int)
    node_roads = defaultdict(set)
    edges = []
    
    for row in rows:
        start = (round_coord(row.start_lat), round_coord(row.start_lon))
        end = (round_coord(row.end_lat), round_coord(row.end_lon))
        node_degree[start] += 1
        node_degree[end] += 1
        node_roads[start].add(row.id)
        node_roads[end].add(row.id)
        edges.append((start, end, row.id))
    
    endpoint_time = time.time() - t0
    
    total_nodes = len(node_degree)
    total_edges = len(edges)
    
    # Shared nodes (intersection degree > 1)
    shared_nodes = sum(1 for d in node_degree.values() if d > 1)
    isolated_nodes = sum(1 for d in node_degree.values() if d == 1)
    max_degree = max(node_degree.values()) if node_degree else 0
    
    # Count high-degree intersections
    degree_3_plus = sum(1 for d in node_degree.values() if d >= 3)
    degree_4_plus = sum(1 for d in node_degree.values() if d >= 4)
    degree_10_plus = sum(1 for d in node_degree.values() if d >= 10)
    
    print(f"  Endpoint extraction:    {endpoint_time:.2f}s")
    print(f"  Total unique nodes:     {total_nodes}")
    print(f"  Total edges (roads):    {total_edges}")
    print(f"  Shared nodes (deg>1):   {shared_nodes}")
    print(f"  Isolated endpoints:     {isolated_nodes}")
    print(f"  Intersections (deg>=3): {degree_3_plus}")
    print(f"  Complex (deg>=4):       {degree_4_plus}")
    print(f"  Very high (deg>=10):    {degree_10_plus}")
    print(f"  Max degree:             {max_degree}")

    # ── 6. Intermediate intersection detection ───────────────────────────
    print(f"\n[6] INTERMEDIATE INTERSECTION DETECTION")
    print(f"    Checking if roads cross at non-endpoint locations...")
    
    t0 = time.time()
    # Use PostGIS to find roads whose geometries intersect but
    # whose endpoints don't match (i.e., true intermediate crossings)
    # Sample a subset for performance (check first 5000 roads)
    intermediate_crossings = db.execute(text("""
        WITH sample_roads AS (
            SELECT id, geometry 
            FROM roads 
            WHERE geometry IS NOT NULL AND is_legacy=false AND status='open'
            LIMIT 5000
        )
        SELECT count(*) as crossing_count FROM (
            SELECT DISTINCT LEAST(a.id, b.id) as id1, GREATEST(a.id, b.id) as id2
            FROM sample_roads a
            JOIN sample_roads b ON a.id < b.id
            WHERE ST_Intersects(a.geometry, b.geometry)
            AND NOT ST_Equals(ST_StartPoint(a.geometry), ST_StartPoint(b.geometry))
            AND NOT ST_Equals(ST_StartPoint(a.geometry), ST_EndPoint(b.geometry))
            AND NOT ST_Equals(ST_EndPoint(a.geometry), ST_StartPoint(b.geometry))
            AND NOT ST_Equals(ST_EndPoint(a.geometry), ST_EndPoint(b.geometry))
            LIMIT 500
        ) sub
    """)).scalar()
    intermediate_time = time.time() - t0
    
    print(f"  Sample size: 5000 roads")
    print(f"  Intermediate crossings found: {intermediate_crossings}")
    print(f"  Detection time: {intermediate_time:.2f}s")
    
    # Also check how many endpoint intersections exist
    endpoint_intersections = db.execute(text("""
        WITH endpoints AS (
            SELECT id,
                   ST_StartPoint(geometry) as spt,
                   ST_EndPoint(geometry) as ept
            FROM roads 
            WHERE geometry IS NOT NULL AND is_legacy=false AND status='open'
            LIMIT 5000
        )
        SELECT count(*) FROM (
            SELECT DISTINCT LEAST(a.id, b.id), GREATEST(a.id, b.id)
            FROM endpoints a
            JOIN endpoints b ON a.id < b.id
            WHERE ST_DWithin(a.spt, b.spt, 0.00001)
               OR ST_DWithin(a.spt, b.ept, 0.00001)
               OR ST_DWithin(a.ept, b.spt, 0.00001)
               OR ST_DWithin(a.ept, b.ept, 0.00001)
            LIMIT 5000
        ) sub
    """)).scalar()
    print(f"  Endpoint-shared pairs (same 5000): {endpoint_intersections}")
    
    # Ratio analysis
    if endpoint_intersections > 0 and intermediate_crossings is not None:
        ratio = intermediate_crossings / max(endpoint_intersections, 1) * 100
        print(f"  Intermediate/Endpoint ratio: {ratio:.1f}%")
    
    # ── 7. Build a NetworkX graph and measure ────────────────────────────
    print(f"\n[7] GRAPH BUILD MEASUREMENT")
    import networkx as nx
    
    t0 = time.time()
    
    # Fetch full road data for graph build
    road_data = db.execute(text("""
        SELECT id, road_type,
               ST_Y(ST_StartPoint(geometry)) as start_lat,
               ST_X(ST_StartPoint(geometry)) as start_lon,
               ST_Y(ST_EndPoint(geometry)) as end_lat,
               ST_X(ST_EndPoint(geometry)) as end_lon,
               ST_Length(geometry::geography) as length_m,
               osm_tags
        FROM roads 
        WHERE geometry IS NOT NULL AND is_legacy=false AND status='open'
    """)).fetchall()
    
    fetch_time = time.time() - t0
    print(f"  DB fetch time:          {fetch_time:.2f}s ({len(road_data)} roads)")
    
    t0 = time.time()
    G = nx.DiGraph()
    
    for row in road_data:
        start = (round_coord(row.start_lat), round_coord(row.start_lon))
        end = (round_coord(row.end_lat), round_coord(row.end_lon))
        dist_km = row.length_m / 1000.0
        
        # Parse oneway
        tags = row.osm_tags or {}
        oneway = tags.get("oneway", "no") if isinstance(tags, dict) else "no"
        
        if oneway == "yes":
            G.add_edge(start, end, road_id=row.id, distance_km=dist_km, road_type=row.road_type)
        elif oneway == "-1":
            G.add_edge(end, start, road_id=row.id, distance_km=dist_km, road_type=row.road_type)
        else:
            G.add_edge(start, end, road_id=row.id, distance_km=dist_km, road_type=row.road_type)
            G.add_edge(end, start, road_id=row.id, distance_km=dist_km, road_type=row.road_type)
    
    build_time = time.time() - t0
    
    n_nodes = G.number_of_nodes()
    n_edges = G.number_of_edges()
    
    # Connected components (weakly, since DiGraph)
    t0 = time.time()
    n_components = nx.number_weakly_connected_components(G)
    components_time = time.time() - t0
    
    # Largest component
    largest_cc = max(nx.weakly_connected_components(G), key=len)
    largest_cc_size = len(largest_cc)
    
    print(f"  Graph build time:       {build_time:.3f}s")
    print(f"  Components calc time:   {components_time:.3f}s")
    print(f"  Total graph nodes:      {n_nodes}")
    print(f"  Total graph edges:      {n_edges}")
    print(f"  Weakly connected comp.: {n_components}")
    print(f"  Largest component:      {largest_cc_size} nodes ({largest_cc_size/n_nodes*100:.1f}%)")
    
    # Memory estimate
    import sys as _sys
    graph_size = _sys.getsizeof(G)
    # Better estimate: count actual data
    node_data_size = sum(_sys.getsizeof(n) for n in G.nodes()) 
    edge_data_est = n_edges * 200  # rough estimate per edge (dict + values)
    total_est_mb = (graph_size + node_data_size + edge_data_est) / (1024 * 1024)
    print(f"  Memory estimate:        {total_est_mb:.1f} MB (rough)")

    # ── 8. Sample route performance ──────────────────────────────────────
    print(f"\n[8] SAMPLE ROUTE PERFORMANCE")
    
    # Pick two nodes in the largest component for testing
    cc_nodes = list(largest_cc)
    if len(cc_nodes) >= 2:
        test_src = cc_nodes[0]
        test_dst = cc_nodes[min(len(cc_nodes) - 1, 1000)]  # pick a distant node
        
        # Cold route (first dijkstra)
        t0 = time.time()
        try:
            path = nx.shortest_path(G, test_src, test_dst, weight="distance_km")
            cold_time = time.time() - t0
            path_len = sum(G[path[i]][path[i+1]]["distance_km"] for i in range(len(path)-1))
            print(f"  Cold route time:        {cold_time*1000:.1f}ms")
            print(f"  Path length:            {len(path)} nodes, {path_len:.2f} km")
        except nx.NetworkXNoPath:
            cold_time = time.time() - t0
            print(f"  Cold route time:        {cold_time*1000:.1f}ms (NO PATH)")
        
        # Warm route (second dijkstra, same graph)
        t0 = time.time()
        try:
            path2 = nx.shortest_path(G, test_src, test_dst, weight="distance_km")
            warm_time = time.time() - t0
            print(f"  Warm route time:        {warm_time*1000:.1f}ms")
        except nx.NetworkXNoPath:
            warm_time = time.time() - t0
            print(f"  Warm route time:        {warm_time*1000:.1f}ms (NO PATH)")
        
        # Try a few more routes for average
        import random
        random.seed(42)
        route_times = []
        route_lengths = []
        no_path_count = 0
        for _ in range(10):
            src = random.choice(cc_nodes)
            dst = random.choice(cc_nodes)
            if src == dst:
                continue
            t0 = time.time()
            try:
                p = nx.shortest_path(G, src, dst, weight="distance_km")
                rt = time.time() - t0
                route_times.append(rt)
                pl = sum(G[p[i]][p[i+1]]["distance_km"] for i in range(len(p)-1))
                route_lengths.append(pl)
            except nx.NetworkXNoPath:
                no_path_count += 1
                route_times.append(time.time() - t0)
        
        if route_times:
            avg_rt = sum(route_times) / len(route_times)
            print(f"  Avg route time (10):    {avg_rt*1000:.1f}ms")
            print(f"  No-path count:          {no_path_count}/10")
            if route_lengths:
                print(f"  Avg route distance:     {sum(route_lengths)/len(route_lengths):.2f} km")
    else:
        print("  Not enough nodes for routing test")

    # ── 9. State-level analysis ──────────────────────────────────────────
    print(f"\n[9] STATE-LEVEL ROAD DISTRIBUTION")
    states = db.execute(text("""
        SELECT s.name, count(r.id) as road_count
        FROM roads r
        JOIN districts d ON r.district_id = d.id
        JOIN states s ON d.state_id = s.id
        WHERE r.is_legacy=false AND r.geometry IS NOT NULL
        GROUP BY s.name
        ORDER BY road_count DESC
    """)).fetchall()
    for s in states:
        print(f"  {s.name:25s} {s.road_count}")
    
    unassigned = db.execute(text("""
        SELECT count(*) FROM roads 
        WHERE district_id IS NULL AND is_legacy=false AND geometry IS NOT NULL
    """)).scalar()
    print(f"  {'(unassigned)':25s} {unassigned}")

    # ── 10. Snap performance (PostGIS) ───────────────────────────────────
    print(f"\n[10] POSTGIS SNAP PERFORMANCE")
    
    # Test point: center of Assam (Guwahati area)
    test_points = [
        (26.14, 91.74, "Guwahati, Assam"),
        (24.82, 93.95, "Imphal, Manipur"),
        (25.57, 91.88, "Shillong, Meghalaya"),
        (27.33, 88.61, "Gangtok, Sikkim"),
        (27.10, 93.62, "Itanagar, Arunachal Pradesh"),
    ]
    
    for lat, lon, label in test_points:
        t0 = time.time()
        result = db.execute(text("""
            SELECT r.id, r.name, r.road_type,
                   ST_Distance(r.geometry::geography, ST_SetSRID(ST_Point(:lon, :lat), 4326)::geography) as dist_m,
                   ST_AsText(ST_ClosestPoint(r.geometry, ST_SetSRID(ST_Point(:lon, :lat), 4326))) as snap_point
            FROM roads r
            WHERE r.geometry IS NOT NULL AND r.is_legacy=false
            ORDER BY r.geometry <-> ST_SetSRID(ST_Point(:lon, :lat), 4326)
            LIMIT 1
        """), {"lat": lat, "lon": lon}).fetchone()
        snap_time = time.time() - t0
        
        if result:
            print(f"  {label}: road={result.id} ({result.road_type}) dist={result.dist_m:.1f}m time={snap_time*1000:.1f}ms")
        else:
            print(f"  {label}: NO RESULT time={snap_time*1000:.1f}ms")

    # ── Summary ──────────────────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print(f"SUMMARY & RECOMMENDATION")
    print(f"{'=' * 70}")
    print(f"  Routable roads:         {open_roads}")
    print(f"  Graph nodes:            {n_nodes}")
    print(f"  Graph edges:            {n_edges}")
    print(f"  Connected components:   {n_components}")
    print(f"  Largest component:      {largest_cc_size} ({largest_cc_size/n_nodes*100:.1f}%)")
    print(f"  Graph build time:       {build_time:.3f}s")
    print(f"  Memory estimate:        {total_est_mb:.1f} MB")
    
    if build_time < 60 and total_est_mb < 1000:
        print(f"\n  ✅ RECOMMENDATION: SINGLE GLOBAL GRAPH is viable")
        print(f"     Build time under 60s, memory under 1GB")
    else:
        print(f"\n  ⚠️  RECOMMENDATION: Consider PARTITIONED GRAPHS")
        print(f"     Build time or memory exceeds threshold")
    
    if intermediate_crossings and intermediate_crossings > 50:
        print(f"\n  ⚠️  TOPOLOGY: {intermediate_crossings} intermediate crossings detected")
        print(f"     Must handle road-crossing intersections, not just endpoints")
    else:
        print(f"\n  ✅ TOPOLOGY: Endpoint-based topology appears sufficient")
        print(f"     {intermediate_crossings or 0} intermediate crossings in 5000-road sample")

    db.close()
    print(f"\nDone.")

if __name__ == "__main__":
    main()
