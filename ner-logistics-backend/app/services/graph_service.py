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
CACHE_TTL_SECONDS = 600   # 10 minutes
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


def get_graph_diagnostics() -> dict:
    """Return diagnostic information about the routing graph cache."""
    return _DIAGNOSTICS.copy()


def invalidate_graph_cache():
    """Manually invalidate the graph cache, forcing rebuild on next access."""
    global _GRAPH_CACHE, _CACHE_TIMESTAMP, _ROAD_COORDS_CACHE
    _GRAPH_CACHE = None
    _CACHE_TIMESTAMP = 0.0
    _ROAD_COORDS_CACHE = None
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

def _extract_topology_from_db(db: Session) -> Tuple[nx.DiGraph, Dict[int, List[Tuple[float, float]]]]:
    """Build a routable DiGraph using vertex-sharing topology.
    
    Algorithm:
    1. Fetch all road coordinates as vertex arrays (ST_DumpPoints)
    2. Build a coordinate → {road_ids} index using rounded coordinates
    3. Identify shared vertices (those appearing in 2+ roads) = intersections
    4. For each road, find its "key vertices" (endpoints + shared vertices)
    5. Create directed edges between consecutive key vertices
    6. Store full coordinate sub-arrays on edges for geometry reconstruction
    
    Returns:
        (graph, road_coords_map)
        - graph: NetworkX DiGraph
        - road_coords_map: {road_id: [(lat, lon), ...]} for geometry reconstruction
    """
    t0 = time.time()
    
    # ── Step 1: Fetch all road vertices from PostGIS ────────────────────
    logger.info("Fetching road vertices from PostGIS...")
    
    engine = db.get_bind()
    raw_conn = engine.raw_connection()
    try:
        with raw_conn.cursor(name='fetch_roads_stream') as cursor:
            cursor.itersize = 2000
            
            cursor.execute("""
                SELECT r.id as road_id,
                       r.road_type,
                       r.osm_tags,
                       ST_NPoints(r.geometry) as n_vertices,
                       ST_AsText(r.geometry) as wkt
                FROM roads r
                WHERE r.geometry IS NOT NULL
                  AND r.status = 'open'
                  AND r.is_legacy = false
            """)
            
            t1 = time.time()
            logger.info(f"Query executed in {t1 - t0:.2f}s, starting stream processing...")
            
            # ── Step 2: Parse vertices and build coordinate index ───────────────
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
                wkt = row[4]
                
                coords_str = wkt.replace("LINESTRING(", "").replace("LINESTRING (", "").rstrip(")")
                parts = coords_str.split(",")
                
                coords = []
                for p in parts:
                    lon_str, lat_str = p.strip().split(" ")
                    coords.append((float(lat_str), float(lon_str)))
                
                road_vertices[road_id] = coords
                road_meta[road_id] = {
                    "road_type": road_type,
                    "oneway": tags.get("oneway", "no") if tags else "no",
                    "n_vertices": row[4],
                }
                
                for lat, lon in coords:
                    r_lat = _round_coord(lat)
                    r_lon = _round_coord(lon)
                    coord_to_roads[(r_lat, r_lon)].add(road_id)
                    
            logger.info(f"Streamed and parsed {row_count} roads in {time.time() - t1:.2f}s")
    except Exception as e:
        logger.error(f"Error streaming topology: {e}")
        raw_conn.rollback()
        raise e
    finally:
        raw_conn.rollback()  # Safely cancel the named cursor before closing
        raw_conn.close()
    
    index_time = time.time() - t1
    logger.info(f"Indexed {len(road_vertices)} roads, {len(coord_to_roads)} unique coords in {index_time:.2f}s")
    
    # ── Step 3: Identify shared vertices (intersections) ────────────────
    t2 = time.time()
    
    shared_coords: Set[Tuple[float, float]] = set()
    for coord, road_ids in coord_to_roads.items():
        if len(road_ids) > 1:
            shared_coords.add(coord)
    
    shared_time = time.time() - t2
    logger.info(f"Found {len(shared_coords)} shared vertices (intersections) in {shared_time:.3f}s")
    
    # ── Step 4 & 5: Build graph with key-vertex edges ───────────────────
    t3 = time.time()
    
    G = nx.DiGraph()
    total_edges_added = 0
    
    for road_id, vertices in road_vertices.items():
        meta = road_meta[road_id]
        oneway = meta["oneway"]
        road_type = meta["road_type"]
        total_length_m = _approximate_segment_length(vertices)
        
        # Identify key vertex indices: first, last, and any shared intermediate vertices
        key_indices = [0]  # always include start
        
        for i in range(1, len(vertices) - 1):
            rounded = _round_point(vertices[i][0], vertices[i][1])
            if rounded in shared_coords:
                key_indices.append(i)
        
        key_indices.append(len(vertices) - 1)  # always include end
        
        # Remove duplicates and sort
        key_indices = sorted(set(key_indices))
        
        # Create edges between consecutive key vertices
        for seg_idx in range(len(key_indices) - 1):
            i_start = key_indices[seg_idx]
            i_end = key_indices[seg_idx + 1]
            
            start_pt = _round_point(vertices[i_start][0], vertices[i_start][1])
            end_pt = _round_point(vertices[i_end][0], vertices[i_end][1])
            
            if start_pt == end_pt:
                continue  # skip degenerate segments
            
            # Calculate segment length proportionally from total road length
            # (proportional to vertex count in segment vs total road)
            if len(vertices) > 1:
                # Use vertex-based length approximation
                segment_coords = vertices[i_start:i_end + 1]
                seg_length_m = _approximate_segment_length(segment_coords)
            else:
                seg_length_m = total_length_m
            
            seg_length_km = max(seg_length_m / 1000.0, MIN_EDGE_DISTANCE_KM)
            
            # Store the full coordinate sub-array for geometry reconstruction
            segment_coord_list = [(v[1], v[0]) for v in vertices[i_start:i_end + 1]]  # (lon, lat) for GeoJSON
            
            edge_data = {
                "road_id": road_id,
                "road_type": road_type,
                "distance_km": seg_length_km,
                "coordinates": segment_coord_list,  # GeoJSON order: [lon, lat]
                "oneway": oneway,
                "is_reversed": False,
            }
            
            # Add directed edges based on oneway tag
            if oneway == "yes":
                G.add_edge(start_pt, end_pt, **edge_data)
                total_edges_added += 1
            elif oneway == "-1":
                # Reverse direction
                reverse_coords = list(reversed(segment_coord_list))
                edge_data_rev = {**edge_data, "coordinates": reverse_coords, "is_reversed": True}
                G.add_edge(end_pt, start_pt, **edge_data_rev)
                total_edges_added += 1
            else:
                # Bidirectional
                G.add_edge(start_pt, end_pt, **edge_data)
                reverse_coords = list(reversed(segment_coord_list))
                edge_data_rev = {**edge_data, "coordinates": reverse_coords, "is_reversed": True}
                G.add_edge(end_pt, start_pt, **edge_data_rev)
                total_edges_added += 2
    
    build_time = time.time() - t3
    
    total_time = time.time() - t0
    logger.info(
        f"Built vertex-sharing graph: {G.number_of_nodes()} nodes, "
        f"{G.number_of_edges()} edges from {len(road_vertices)} roads "
        f"({len(shared_coords)} shared vertices) in {total_time:.2f}s"
    )
    
    return G, road_vertices


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


# ── Public API ────────────────────────────────────────────────────────────────

def build_road_graph(db: Session, force_rebuild: bool = False) -> nx.DiGraph:
    """Build or return cached routable DiGraph from OSM road data.
    
    Uses vertex-sharing topology: roads are connected wherever they share
    a coordinate vertex (after rounding to 7 decimal places).
    
    The graph is cached per-process with a configurable TTL.
    Risk scoring is NOT applied during build — use deferred scoring at routing time.
    
    Args:
        db: SQLAlchemy session for database access
        force_rebuild: If True, ignore cache and rebuild
        
    Returns:
        NetworkX DiGraph suitable for routing
    """
    global _GRAPH_CACHE, _CACHE_TIMESTAMP, _ROAD_COORDS_CACHE, _DIAGNOSTICS
    
    current_time = time.time()
    if not force_rebuild and _GRAPH_CACHE is not None:
        if (current_time - _CACHE_TIMESTAMP) < CACHE_TTL_SECONDS:
            return _GRAPH_CACHE
    
    logger.info("Building road graph (vertex-sharing topology)...")
    start_time = time.time()
    
    graph, road_coords = _extract_topology_from_db(db)
    
    # Compute connected components
    n_components = nx.number_weakly_connected_components(graph) if graph.number_of_nodes() > 0 else 0
    
    largest_cc_size = 0
    if graph.number_of_nodes() > 0:
        largest_cc = max(nx.weakly_connected_components(graph), key=len)
        largest_cc_size = len(largest_cc)
    
    build_duration_ms = int((time.time() - start_time) * 1000)
    
    # Update cache
    _GRAPH_CACHE = graph
    _CACHE_TIMESTAMP = time.time()
    _ROAD_COORDS_CACHE = road_coords
    
    # Update diagnostics
    n_nodes = graph.number_of_nodes()
    _DIAGNOSTICS.update({
        "node_count": n_nodes,
        "edge_count": graph.number_of_edges(),
        "connected_components": n_components,
        "largest_component_nodes": largest_cc_size,
        "largest_component_pct": round(largest_cc_size / n_nodes * 100, 1) if n_nodes > 0 else 0,
        "build_duration_ms": build_duration_ms,
        "last_rebuild_time": datetime.now(timezone.utc).isoformat(),
        "roads_in_graph": len(road_coords),
        "shared_vertices_found": sum(1 for n in graph.nodes() if graph.degree(n) > 2),
    })
    
    logger.info(
        f"Graph ready: {n_nodes} nodes, {graph.number_of_edges()} edges, "
        f"{n_components} components (largest: {largest_cc_size}, {_DIAGNOSTICS['largest_component_pct']}%%) "
        f"in {build_duration_ms}ms"
    )
    
    return graph


def get_road_coordinates(road_id: int) -> Optional[List[Tuple[float, float]]]:
    """Get the full coordinate list for a road from the cached road data.
    
    Returns list of (lat, lon) tuples, or None if not found.
    """
    if _ROAD_COORDS_CACHE is None:
        return None
    return _ROAD_COORDS_CACHE.get(road_id)
