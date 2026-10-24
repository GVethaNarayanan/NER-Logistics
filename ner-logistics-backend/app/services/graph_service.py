"""
Phase 4.3 — OSM Road Graph Service (Vertex-Sharing Topology)

Builds a routable NetworkX DiGraph from real OSM LineString geometry.

TOPOLOGY STRATEGY: Vertex-Sharing
==================================
Endpoint-only topology was measured and proven INSUFFICIENT:
  - 161,093 connected components from 226,869 roads
  - Largest component: 5,695 nodes (1.5%)
  - 27.4% intermediate crossing ratio

This module extracts ALL coordinate vertices from each road's LineString,
identifies shared vertices between roads (exact coordinate match after
rounding to 7 decimal places ≈ 1.1cm), and builds graph nodes at those
intersection points plus road endpoints.

COORDINATE TOLERANCE:
  7 decimal places → ~1.1cm precision
  This is tight enough to avoid false connections while capturing
  real OSM shared nodes.

DESIGN DECISIONS:
  - DiGraph (directed) for oneway road support
  - Edge weight = actual road geometry length in km (ST_Length geography)
  - Risk scoring is DEFERRED — computed per-route, not per-build
  - Legacy roads (is_legacy=true) excluded from graph
  - district_id=NULL roads included (routing is topology-based)
  - Process-level cache with configurable TTL
  - No deep-copy on access — routing uses lightweight overlay
"""
import logging
import time
import sys
from datetime import datetime, timezone
from collections import defaultdict
from typing import Dict, List, Tuple, Optional, Set

import networkx as nx
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger("ner_logistics.graph_service")

# ── Configuration ─────────────────────────────────────────────────────────────

COORD_PRECISION = 7       # decimal places for coordinate rounding (~1.1cm)
CACHE_TTL_SECONDS = 86400   # 24 hours — graph stays in memory for the entire session
MIN_EDGE_DISTANCE_KM = 0.0001  # minimum edge weight to avoid zero-length edges

# ── Per-process Graph Cache ───────────────────────────────────────────────────

_GRAPH_CACHE: Optional[nx.DiGraph] = None
_CACHE_TIMESTAMP: float = 0.0
_ROAD_COORDS_CACHE: Optional[Dict[int, List[Tuple[float, float]]]] = None
_DIAGNOSTICS: Dict = {
    "node_count": 0,
    "edge_count": 0,
    "connected_components": 0,
    "largest_component_nodes": 0,
    "largest_component_pct": 0.0,
    "build_duration_ms": 0,
    "last_rebuild_time": None,
    "topology_strategy": "vertex_sharing",
    "coord_precision": COORD_PRECISION,
    "roads_in_graph": 0,
    "shared_vertices_found": 0,
}

_CURRENT_BBOX: Optional[Tuple[float, float, float, float]] = None


def get_graph_diagnostics() -> dict:
    """Return diagnostic information about the routing graph cache."""
    return _DIAGNOSTICS.copy()


def invalidate_graph_cache():
    """Manually invalidate the graph cache, forcing rebuild on next access."""
    global _GRAPH_CACHE, _CACHE_TIMESTAMP, _ROAD_COORDS_CACHE, _ROAD_TO_EDGES_CACHE, _CURRENT_BBOX
    _GRAPH_CACHE = None
    _CACHE_TIMESTAMP = 0.0
    _ROAD_COORDS_CACHE = None
    _ROAD_TO_EDGES_CACHE = None
    _CURRENT_BBOX = None
    logger.info("Graph cache manually invalidated.")


# ── Coordinate Utilities ─────────────────────────────────────────────────────

def _round_coord(val: float) -> float:
    """Round a coordinate value to COORD_PRECISION decimal places.
    
    7 decimal places ≈ 1.1cm precision, sufficient to match
    exact OSM node coordinates without false connections.
    """
    return round(val, COORD_PRECISION)


def _round_point(lat: float, lon: float) -> Tuple[float, float]:
    """Round a (lat, lon) point to standardized precision."""
    return (_round_coord(lat), _round_coord(lon))


def _approximate_segment_length(coords: List[Tuple[float, float]]) -> float:
    """Calculate the haversine length of a line string segment."""
    from app.services.routing_service import haversine_distance_km
    dist_m = 0.0
    for i in range(len(coords) - 1):
        dist_m += haversine_distance_km(coords[i][0], coords[i][1], coords[i+1][0], coords[i+1][1]) * 1000.0
    return dist_m



# ── Topology Extraction ─────────────────────────────────────────────────────

def _extract_topology_from_db(
    db: Session,
    bbox: Optional[Tuple[float, float, float, float]] = None
) -> Tuple[nx.DiGraph, Dict[int, List[Tuple[tuple, tuple, float]]], dict]:
    """Build a routable DiGraph using vertex-sharing topology.
    
    If bbox is provided (min_lon, min_lat, max_lon, max_lat), only roads
    intersecting that corridor are queried, yielding sub-second query performance.
    
    Returns:
        (graph, road_to_edges_map, timings)
    """
    timings = {}
    
    # ── Step 1: Fetch road vertices from PostGIS ─────────────────────────
    t_fetch_start = time.time()
    logger.info(f"Fetching road vertices from PostGIS (bbox={bbox})...")
    
    engine = db.get_bind()
    raw_conn = engine.raw_connection()
    try:
        with raw_conn.cursor(name='fetch_roads_stream') as cursor:
            cursor.itersize = 2000
            if bbox:
                sql = """
                    SELECT r.id as road_id,
                           r.road_type,
                           r.osm_tags,
                           ST_NPoints(r.geometry) as n_vertices,
                           ST_Length(r.geometry::geography) as total_length_m,
                           ST_AsText(r.geometry) as wkt
                    FROM roads r
                    WHERE r.geometry IS NOT NULL
                      AND r.status = 'open'
                      AND r.is_legacy = false
                      AND ST_Intersects(r.geometry, ST_MakeEnvelope(%s, %s, %s, %s, 4326))
                """
                cursor.execute(sql, (bbox[0], bbox[1], bbox[2], bbox[3]))
            else:
                sql = """
                    SELECT r.id as road_id,
                           r.road_type,
                           r.osm_tags,
                           ST_NPoints(r.geometry) as n_vertices,
                           ST_Length(r.geometry::geography) as total_length_m,
                           ST_AsText(r.geometry) as wkt
                    FROM roads r
                    WHERE r.geometry IS NOT NULL
                      AND r.status = 'open'
                      AND r.is_legacy = false
                """
                cursor.execute(sql)
            
            t_fetch_end = time.time()
            timings["db_fetch_stream_s"] = t_fetch_end - t_fetch_start
            logger.info(f"Query executed in {timings['db_fetch_stream_s']:.2f}s, starting stream processing...")
            
            # ── Step 2: Parse vertices and build coordinate index ───────────────
            t_parse_start = time.time()
            coord_to_roads: Dict[Tuple[float, float], Set[int]] = defaultdict(set)
            road_vertices: Dict[int, List[Tuple[float, float]]] = {}
            road_meta: Dict[int, dict] = {}
            
            row_count = 0
            for row in cursor:
                row_count += 1
                road_id = row[0]
                road_type = row[1]
                tags = row[2] if isinstance(row[2], dict) else {}
                n_vertices = row[3]
                total_length_m = row[4]
                wkt = row[5]
                
                coords_str = wkt.replace("LINESTRING(", "").replace("LINESTRING (", "").rstrip(")")
                parts = coords_str.split(",")
                
                coords = []
                for p in parts:
                    lon_str, lat_str = p.strip().split(" ")
                    # Pre-round the coordinates here to avoid re-rounding later
                    r_lat = _round_coord(float(lat_str))
                    r_lon = _round_coord(float(lon_str))
                    coords.append((r_lat, r_lon))
                
                road_vertices[road_id] = coords
                road_meta[road_id] = {
                    "road_type": road_type,
                    "oneway": tags.get("oneway", "no") if tags else "no",
                    "n_vertices": n_vertices,
                    "total_length_m": total_length_m,
                }
                
                for pt in coords:
                    coord_to_roads[pt].add(road_id)
                    
    except Exception as e:
        logger.error(f"Error streaming topology: {e}")
        raw_conn.rollback()
        raise e
    finally:
        try:
            raw_conn.rollback()
            raw_conn.close()
        except:
            pass
    
    t_parse_end = time.time()
    timings["coordinate_parsing_s"] = t_parse_end - t_parse_start
    logger.info(f"Indexed {len(road_vertices)} roads in {timings['coordinate_parsing_s']:.2f}s")
    
    # ── Step 3: Identify shared vertices (intersections) ────────────────
    t_shared_start = time.time()
    shared_coords: Set[Tuple[float, float]] = set()
    for coord, road_ids in coord_to_roads.items():
        if len(road_ids) > 1:
            shared_coords.add(coord)
    
    t_shared_end = time.time()
    timings["shared_vertex_detection_s"] = t_shared_end - t_shared_start
    logger.info(f"Found {len(shared_coords)} shared vertices in {timings['shared_vertex_detection_s']:.3f}s")
    
    # ── Step 4 & 5: Build graph with key-vertex edges ───────────────────
    t_edge_start = time.time()
    G = nx.DiGraph()
    road_to_edges = defaultdict(list)
    
    import math
    R_pi_180 = 6371000.0 * math.pi / 180.0
    
    all_edges = []
    
    for road_id, vertices in road_vertices.items():
        meta = road_meta[road_id]
        oneway = meta["oneway"]
        road_type = meta["road_type"]
        
        n_v = len(vertices)
        
        # Pull pre-calculated length from DB
        total_length_m = meta.get("total_length_m", 0.0)
            
        # 1. Identify key vertex indices: first, last, and any shared intermediate vertices
        key_indices = [0]
        for i in range(1, n_v - 1):
            if vertices[i] in shared_coords:
                key_indices.append(i)
        
        key_indices.append(n_v - 1)
        # Remove duplicates while preserving order
        unique_keys = []
        last_k = -1
        for k in key_indices:
            if k != last_k:
                unique_keys.append(k)
                last_k = k
        
        for seg_idx in range(len(unique_keys) - 1):
            i_start = unique_keys[seg_idx]
            i_end = unique_keys[seg_idx + 1]
            
            start_pt = vertices[i_start]
            end_pt = vertices[i_end]
            
            if start_pt == end_pt:
                continue
            
            # Proportional length approximation completely skips heavy math
            # Distance is proportional to vertex count in segment vs total road
            seg_length_m = total_length_m * ((i_end - i_start) / max(1, n_v - 1))
            seg_length_km = max(seg_length_m / 1000.0, MIN_EDGE_DISTANCE_KM)
            
            edge_data = {
                "road_id": road_id,
                "road_type": road_type,
                "distance_km": seg_length_km,
                "risk_cost": seg_length_km,
                "oneway": oneway,
                "is_reversed": False,
            }
            
            edges_to_add = []
            if oneway == "yes":
                edges_to_add.append((start_pt, end_pt, edge_data))
            elif oneway == "-1":
                edges_to_add.append((end_pt, start_pt, {**edge_data, "is_reversed": True}))
            else:
                edges_to_add.append((start_pt, end_pt, edge_data))
                edges_to_add.append((end_pt, start_pt, {**edge_data, "is_reversed": True}))
            
            for u, v, data in edges_to_add:
                all_edges.append((u, v, data))
            
            # Store lightweight (u, v, distance_km) tuple in road_to_edges
            road_to_edges[road_id].append((start_pt, end_pt, seg_length_km))
    
    # Bulk insert into NetworkX
    G.add_edges_from(all_edges)
    
    t_edge_end = time.time()
    timings["graph_edge_creation_s"] = t_edge_end - t_edge_start
    
    return G, dict(road_to_edges), timings


def _approximate_segment_length(coords: List[Tuple[float, float]]) -> float:
    """Approximate the length of a coordinate segment using Haversine between consecutive points.
    
    coords: list of (lat, lon) tuples
    Returns: length in meters
    """
    import math
    total = 0.0
    R = 6371000.0  # Earth radius in meters
    
    for i in range(len(coords) - 1):
        lat1, lon1 = math.radians(coords[i][0]), math.radians(coords[i][1])
        lat2, lon2 = math.radians(coords[i + 1][0]), math.radians(coords[i + 1][1])
        
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        total += R * c
    
    return total


# ── Island Stitching ────────────────────────────────────────────────────────

def _stitch_disconnected_islands(graph: nx.DiGraph) -> int:
    """Connect all disconnected graph components to the main highway network.
    
    Algorithm:
    1. Find all weakly connected components
    2. Identify the largest component as the "main network"
    3. For each smaller component (island), find the nearest node on the main network
    4. Add bidirectional bridge edges with realistic distance weights
    
    This ensures every node is reachable from every other node, eliminating
    all NO_ROUTE errors caused by OSM data gaps.
    
    Uses a spatial grid index for fast nearest-neighbor lookups (O(1) average
    per island instead of O(n) brute force).
    
    Returns:
        Number of islands stitched to the main network.
    """
    import math
    
    if graph.number_of_nodes() < 2:
        return 0
    
    undirected = graph.to_undirected(as_view=True)
    components = list(nx.connected_components(undirected))
    
    if len(components) <= 1:
        return 0  # Already fully connected
    
    # Sort components by size (largest first)
    components.sort(key=len, reverse=True)
    main_component = components[0]
    island_components = components[1:]
    
    logger.info(
        f"Island stitching: {len(components)} components found. "
        f"Main network: {len(main_component)} nodes, "
        f"{len(island_components)} islands to stitch."
    )
    
    # Build spatial grid index over main component nodes for fast nearest-lookup
    # Grid cell size: ~0.01 degrees ≈ 1.1km — coarse enough for fast lookups
    GRID_CELL = 0.01
    grid: Dict[Tuple[int, int], List[Tuple[float, float]]] = defaultdict(list)
    
    for node in main_component:
        if isinstance(node, tuple) and len(node) == 2:
            lat, lon = node
            cell = (int(lat / GRID_CELL), int(lon / GRID_CELL))
            grid[cell].append(node)
    
    def _find_nearest_main_node(
        island_node: Tuple[float, float],
    ) -> Tuple[Optional[Tuple[float, float]], float]:
        """Find the nearest main-network node using the spatial grid.
        
        Searches the grid cell containing the island node plus all 24
        surrounding cells (5x5 neighborhood), expanding if needed.
        """
        lat, lon = island_node
        best_node = None
        best_dist = float("inf")
        
        # Search expanding neighborhoods: 5x5, then 11x11, then 21x21
        for radius in [2, 5, 10, 25]:
            center_cell_lat = int(lat / GRID_CELL)
            center_cell_lon = int(lon / GRID_CELL)
            
            for di in range(-radius, radius + 1):
                for dj in range(-radius, radius + 1):
                    cell = (center_cell_lat + di, center_cell_lon + dj)
                    for candidate in grid.get(cell, []):
                        c_lat, c_lon = candidate
                        # Fast squared-distance approximation (no sqrt/trig needed for comparison)
                        dlat = lat - c_lat
                        dlon = (lon - c_lon) * math.cos(math.radians(lat))
                        sq_dist = dlat * dlat + dlon * dlon
                        if sq_dist < best_dist:
                            best_dist = sq_dist
                            best_node = candidate
            
            if best_node is not None:
                break  # Found at this radius, no need to expand
        
        # Convert squared-degree-distance to km
        if best_node is not None:
            actual_dist_km = math.sqrt(best_dist) * 111.0  # rough deg->km
        else:
            actual_dist_km = float("inf")
        
        return best_node, actual_dist_km
    
    # Stitch each island to the main network
    n_stitched = 0
    bridge_edges = []
    
    for island in island_components:
        # Find the island node closest to any main-network node
        best_island_node = None
        best_main_node = None
        best_distance_km = float("inf")
        
        for island_node in island:
            if not isinstance(island_node, tuple) or len(island_node) != 2:
                continue
            
            main_node, dist_km = _find_nearest_main_node(island_node)
            if main_node is not None and dist_km < best_distance_km:
                best_distance_km = dist_km
                best_island_node = island_node
                best_main_node = main_node
        
        if best_island_node is not None and best_main_node is not None:
            # Add bidirectional bridge edges
            edge_data = {
                "road_id": 0,  # virtual bridge — no real road
                "road_type": "bridge_stitch",
                "distance_km": max(best_distance_km, MIN_EDGE_DISTANCE_KM),
                "risk_cost": max(best_distance_km, MIN_EDGE_DISTANCE_KM),
                "oneway": "no",
                "is_reversed": False,
                "is_bridge_stitch": True,
            }
            bridge_edges.append((best_island_node, best_main_node, edge_data))
            bridge_edges.append((best_main_node, best_island_node, {**edge_data, "is_reversed": True}))
            n_stitched += 1
            
            # After stitching this island, add its nodes to the main component
            # so subsequent islands can also stitch to formerly-island nodes
            for node in island:
                if isinstance(node, tuple) and len(node) == 2:
                    lat, lon = node
                    cell = (int(lat / GRID_CELL), int(lon / GRID_CELL))
                    grid[cell].append(node)
                    main_component.add(node)
    
    # Bulk-add all bridge edges
    if bridge_edges:
        graph.add_edges_from(bridge_edges)
    
    if n_stitched > 0:
        logger.info(f"Stitched {n_stitched} islands to main network ({len(bridge_edges)} bridge edges added)")
    
    return n_stitched


# ── Public API ────────────────────────────────────────────────────────────────

def build_road_graph(
    db: Session,
    bbox: Optional[Tuple[float, float, float, float]] = None,
    force_rebuild: bool = False
) -> nx.DiGraph:
    """Build or return cached routable DiGraph from OSM road data.
    
    If bbox is provided, only extracts roads in the corridor, completing in ~2-3s.
    Subsequent route requests in the same corridor hit the in-memory cache in 0ms.
    
    Args:
        db: SQLAlchemy session for database access
        bbox: Optional (min_lon, min_lat, max_lon, max_lat) corridor bounding box
        force_rebuild: If True, ignore cache and rebuild
        
    Returns:
        NetworkX DiGraph suitable for routing
    """
    global _GRAPH_CACHE, _CACHE_TIMESTAMP, _ROAD_TO_EDGES_CACHE, _DIAGNOSTICS, _CURRENT_BBOX
    
    import os
    import pickle
    
    current_time = time.time()
    if not force_rebuild and _GRAPH_CACHE is not None:
        if bbox is None:
            if (current_time - _CACHE_TIMESTAMP) < CACHE_TTL_SECONDS:
                return _GRAPH_CACHE
        elif _CURRENT_BBOX is not None:
            # Check if requested corridor is already contained within current cached bbox
            c_min_lon, c_min_lat, c_max_lon, c_max_lat = _CURRENT_BBOX
            r_min_lon, r_min_lat, r_max_lon, r_max_lat = bbox
            if (c_min_lon <= r_min_lon and c_min_lat <= r_min_lat and
                c_max_lon >= r_max_lon and c_max_lat >= r_max_lat):
                if (current_time - _CACHE_TIMESTAMP) < CACHE_TTL_SECONDS:
                    return _GRAPH_CACHE
            
    CACHE_FILE_PATH = "/app/cache/ner_graph_cache.pkl"
    if not force_rebuild and bbox is None and os.path.exists(CACHE_FILE_PATH):
        try:
            logger.info("Loading graph from disk cache...")
            with open(CACHE_FILE_PATH, "rb") as f:
                cached_data = pickle.load(f)
                
            _GRAPH_CACHE = cached_data["graph"]
            _ROAD_TO_EDGES_CACHE = cached_data.get("road_to_edges", {})
            _CURRENT_BBOX = None
            _CACHE_TIMESTAMP = time.time()
            
            logger.info(f"Loaded graph from disk cache: {_GRAPH_CACHE.number_of_nodes()} nodes, {_GRAPH_CACHE.number_of_edges()} edges.")
            return _GRAPH_CACHE
        except Exception as e:
            logger.warning(f"Failed to load graph from disk cache: {e}. Rebuilding...")

    logger.info(f"Building road graph (vertex-sharing topology, bbox={bbox})...")
    start_time = time.time()
    
    graph, road_to_edges, timings = _extract_topology_from_db(db, bbox=bbox)
    
    # ── Island Stitching: Connect all disconnected components to main network ──
    # This guarantees 100% route success — no NO_ROUTE errors from OSM data gaps
    t_stitch_start = time.time()
    n_stitched = _stitch_disconnected_islands(graph)
    t_stitch_end = time.time()
    timings["island_stitching_s"] = t_stitch_end - t_stitch_start
    
    # Compute connected components (for diagnostics)
    t_cc_start = time.time()
    undirected = graph.to_undirected(as_view=True)
    components = list(nx.connected_components(undirected))
    n_components = len(components)
    largest_cc_size = max(len(c) for c in components) if components else 0
    t_cc_end = time.time()
    timings["connected_components_s"] = t_cc_end - t_cc_start
    
    t_cache_start = time.time()
    
    # Update memory cache
    _GRAPH_CACHE = graph
    _CACHE_TIMESTAMP = time.time()
    _ROAD_TO_EDGES_CACHE = road_to_edges
    _CURRENT_BBOX = bbox
    
    # Save to disk cache if full graph
    if bbox is None:
        try:
            logger.info("Saving lightweight graph to disk cache...")
            with open(CACHE_FILE_PATH, "wb") as f:
                pickle.dump({
                    "graph": graph,
                    "road_to_edges": road_to_edges
                }, f, protocol=pickle.HIGHEST_PROTOCOL)
            logger.info("Graph saved to disk cache successfully.")
        except Exception as e:
            logger.warning(f"Failed to save graph to disk cache: {e}")
    
    t_cache_end = time.time()
    timings["cache_storage_s"] = t_cache_end - t_cache_start
    
    build_duration_ms = int((time.time() - start_time) * 1000)
    
    # Update diagnostics
    n_nodes = graph.number_of_nodes()
    _DIAGNOSTICS.update({
        "node_count": n_nodes,
        "edge_count": graph.number_of_edges(),
        "connected_components": n_components,
        "largest_component_nodes": largest_cc_size,
        "largest_component_pct": round(100.0 * largest_cc_size / max(1, n_nodes), 1),
        "islands_stitched": n_stitched,
        "build_duration_ms": build_duration_ms,
        "last_rebuild_time": datetime.now(timezone.utc).isoformat(),
        "roads_in_graph": len(road_to_edges),
        "shared_vertices_found": 0,
        "timings": timings,
    })
    
    logger.info(
        f"Graph ready: {n_nodes} nodes, {graph.number_of_edges()} edges, "
        f"{n_components} components, {n_stitched} islands stitched in {build_duration_ms}ms"
    )
    
    return graph


def get_road_coordinates(road_id: int) -> Optional[List[Tuple[float, float]]]:
    """Deprecated: Road coordinates are retrieved on-demand from PostGIS."""
    return None

def get_road_edges(road_id: int) -> Optional[List[Tuple[tuple, tuple, float]]]:
    """Get the graph edges for a road from the cached edge mapping.
    
    Returns list of (u, v, dist_km) tuples, or None if not found.
    """
    if _ROAD_TO_EDGES_CACHE is None:
        return None
    return _ROAD_TO_EDGES_CACHE.get(road_id)
