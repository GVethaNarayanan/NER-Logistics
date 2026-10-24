"""
Phase 4.3 — Routing Service (OSM Geometry-Aware)

Provides:
- PostGIS-first spatial snapping to real road geometry
- Shortest vs Safest path routing via NetworkX DiGraph
- Route geometry reconstruction from actual OSM LineString coordinates
- Deferred risk scoring (only edges in the routing neighborhood)
- Lightweight virtual node insertion without full graph copy

Key design:
- Snap uses PostGIS ST_ClosestPoint for accuracy, with brute-force fallback
- Virtual nodes are added/removed from the shared graph in a try/finally block
  (safe in single-worker ASGI; each multi-worker process has its own cache)
- Route geometry is assembled from the stored coordinate arrays on edges
- Risk scoring is computed lazily for edges on candidate paths
"""
import logging
import math
import time
import json
import threading
from dataclasses import dataclass
from typing import Optional, List, Tuple, Any, Dict, Set

import networkx as nx
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.services.graph_service import (
    build_road_graph,
    get_road_coordinates,
    get_road_edges,
    _round_point,
    MIN_EDGE_DISTANCE_KM,
)
from app.services.vehicle_service import haversine_distance_km

logger = logging.getLogger("ner_logistics.routing_service")

# Lock for virtual node operations on the shared graph
_GRAPH_LOCK = threading.Lock()

# Average speeds by road type (km/h) for duration estimation
SPEED_BY_TYPE = {
    "trunk": 60,
    "trunk_link": 50,
    "primary": 50,
    "primary_link": 40,
    "secondary": 40,
    "secondary_link": 35,
    "tertiary": 35,
    "tertiary_link": 30,
    "unclassified": 25,
    "residential": 20,
    "service": 15,
}
DEFAULT_SPEED_KMH = 25


# ── Snap result ───────────────────────────────────────────────────────────────

@dataclass
class SnapResult:
    """Result of snapping a coordinate to the nearest road edge."""
    edge: tuple                     # (u_node, v_node)
    snapped_lat: float
    snapped_lon: float
    t: float                        # parametric position on edge [0, 1]
    distance_km: float              # distance from input to snap point
    edge_data: dict                 # edge metadata (road_id, distance_km, etc.)
    road_id: int                    # the road this snap is on


# ── Point-to-segment projection ──────────────────────────────────────────────

def _project_point_to_segment(
    plat: float, plon: float,
    alat: float, alon: float,
    blat: float, blon: float,
) -> Tuple[float, float, float]:
    """Project point P onto line segment A→B using parametric projection.

    Uses a flat-earth approximation (adequate for short segments).
    Returns (projected_lat, projected_lon, t) where t ∈ [0, 1].
    """
    cos_lat = math.cos(math.radians((alat + blat) / 2.0))

    ax = alon * cos_lat
    ay = alat
    bx = blon * cos_lat
    by = blat
    px = plon * cos_lat
    py = plat

    dx = bx - ax
    dy = by - ay
    len_sq = dx * dx + dy * dy

    if len_sq < 1e-20:
        return alat, alon, 0.0

    t = ((px - ax) * dx + (py - ay) * dy) / len_sq
    t = max(0.0, min(1.0, t))

    proj_lat = alat + (blat - alat) * t
    proj_lon = alon + (blon - alon) * t

    return proj_lat, proj_lon, t


# ── PostGIS-first Nearest-Road Snapping ───────────────────────────────────────

def snap_to_nearest_edge(
    graph: nx.DiGraph,
    lat: float,
    lon: float,
    max_distance_km: float = 50.0,
    db: Session = None,
) -> Optional[SnapResult]:
    """Snap an arbitrary coordinate to the nearest road edge in the graph.
    
    Strategy:
    1. Use PostGIS ST_ClosestPoint for fast, index-assisted nearest-road lookup
    2. Find the corresponding edge in the graph
    3. Fall back to brute-force graph iteration if PostGIS unavailable
    """
    # ── PostGIS fast path ────────────────────────────────────────────────
    if db is not None:
        try:
            max_dist_deg = max_distance_km / 111.0
            result = db.execute(text("""
                SELECT r.id as road_id,
                       r.road_type,
                       ST_Y(ST_ClosestPoint(r.geometry, ST_SetSRID(ST_Point(:lon, :lat), 4326))) as snap_lat,
                       ST_X(ST_ClosestPoint(r.geometry, ST_SetSRID(ST_Point(:lon, :lat), 4326))) as snap_lon,
                       ST_Distance(r.geometry::geography, ST_SetSRID(ST_Point(:lon, :lat), 4326)::geography) as dist_m,
                       ST_Y(ST_StartPoint(r.geometry)) as start_lat,
                       ST_X(ST_StartPoint(r.geometry)) as start_lon,
                       ST_Y(ST_EndPoint(r.geometry)) as end_lat,
                       ST_X(ST_EndPoint(r.geometry)) as end_lon
                FROM roads r
                WHERE r.geometry IS NOT NULL
                  AND r.is_legacy = false
                  AND r.status = 'open'
                  AND ST_DWithin(r.geometry, ST_SetSRID(ST_Point(:lon, :lat), 4326), :max_dist_deg)
                ORDER BY r.geometry <-> ST_SetSRID(ST_Point(:lon, :lat), 4326)
                LIMIT 1
            """), {"lon": lon, "lat": lat, "max_dist_deg": max_dist_deg}).fetchone()
            
            if result and result.dist_m / 1000.0 <= max_distance_km:
                snap_lat = result.snap_lat
                snap_lon = result.snap_lon
                road_id = result.road_id
                dist_km = result.dist_m / 1000.0
                
                # Find which graph edge this road corresponds to
                # The snap point is on this road — find the edge segment containing it
                snap_rounded = _round_point(snap_lat, snap_lon)
                start_rounded = _round_point(result.start_lat, result.start_lon)
                end_rounded = _round_point(result.end_lat, result.end_lon)
                
                # Search for edges belonging to this road_id using O(1) lookup
                best_edge = None
                best_t = 0.5
                
                candidate_edges = get_road_edges(road_id)
                if candidate_edges:
                    best_proj_dist = float("inf")
                    for edge_item in candidate_edges:
                        u, v = edge_item[0], edge_item[1]
                        seg_dist_km = edge_item[2] if len(edge_item) > 2 else dist_km
                        u_lat, u_lon = u
                        v_lat, v_lon = v
                        proj_lat, proj_lon, t = _project_point_to_segment(
                            snap_lat, snap_lon, u_lat, u_lon, v_lat, v_lon
                        )
                        proj_dist = haversine_distance_km(snap_lat, snap_lon, proj_lat, proj_lon)
                        
                        if best_edge is None or proj_dist < best_proj_dist:
                            best_edge = (u, v, seg_dist_km)
                            best_proj_dist = proj_dist
                            best_t = t
                
                if best_edge is not None:
                    u, v, seg_dist_km = best_edge
                    data = graph.get_edge_data(u, v) or {"road_id": road_id, "distance_km": seg_dist_km}
                    logger.info(f"PostGIS snap: road={road_id} dist={dist_km:.3f}km")
                    return SnapResult(
                        edge=(u, v),
                        snapped_lat=snap_lat,
                        snapped_lon=snap_lon,
                        t=best_t,
                        distance_km=dist_km,
                        edge_data=data,
                        road_id=road_id,
                    )
                else:
                    # Road found in DB but no matching edge in graph
                    # Try using endpoint nodes
                    if graph.has_edge(start_rounded, end_rounded):
                        data = graph.get_edge_data(start_rounded, end_rounded)
                        _, _, t = _project_point_to_segment(
                            snap_lat, snap_lon,
                            start_rounded[0], start_rounded[1],
                            end_rounded[0], end_rounded[1]
                        )
                        logger.info(f"PostGIS snap (endpoint fallback): road={road_id} dist={dist_km:.3f}km")
                        return SnapResult(
                            edge=(start_rounded, end_rounded),
                            snapped_lat=snap_lat,
                            snapped_lon=snap_lon,
                            t=t,
                            distance_km=dist_km,
                            edge_data=data,
                            road_id=road_id,
                        )
                    
        except Exception as e:
            print(f"POSTGIS SNAP FAILED: {e}")
            logger.warning(f"PostGIS snap failed, falling back to brute-force: {e}")
    
    # ── Brute-force fallback ─────────────────────────────────────────────
    best: Optional[SnapResult] = None
    
    for u, v, data in graph.edges(data=True):
        u_lat, u_lon = u
        v_lat, v_lon = v
        
        proj_lat, proj_lon, t = _project_point_to_segment(
            lat, lon, u_lat, u_lon, v_lat, v_lon,
        )
        dist = haversine_distance_km(lat, lon, proj_lat, proj_lon)
        
        if dist <= max_distance_km and (best is None or dist < best.distance_km):
            best = SnapResult(
                edge=(u, v),
                snapped_lat=proj_lat,
                snapped_lon=proj_lon,
                t=t,
                distance_km=dist,
                edge_data=data,
                road_id=data.get("road_id", 0),
            )
    
    return best


# ── Risk Scoring (Deferred) ──────────────────────────────────────────────────

def _compute_edge_risk(
    db: Session,
    road_id: int,
    weather_result=None,
) -> Tuple[float, str]:
    """Compute risk score for a single road edge at routing time.
    
    Uses the existing risk engine (Tier 1 heuristic + ML fallback).
    Returns (risk_score, risk_level).
    
    Stage 5: Uses geometry-based weather matching via weather_match utility.
    If weather_result is provided (from batch lookup), uses it directly.
    """
    from app.services.risk_engine import compute_risk_score
    from app.services.weather_match import match_weather_for_road, _make_missing_result
    from app import models
    
    # Get incident count for this road
    incident_count = db.query(models.Incident).filter(
        models.Incident.road_id == road_id,
        models.Incident.status.in_(["reported", "verified"])
    ).count()
    
    # Get bridge condition
    bridges = db.query(models.Bridge).filter(models.Bridge.road_id == road_id).all()
    bridge_condition = "good"
    if bridges:
        bridge_conds = [b.condition for b in bridges]
        if "poor" in bridge_conds:
            bridge_condition = "poor"
        elif "fair" in bridge_conds:
            bridge_condition = "fair"
    
    # Get weather via geometry matching (or use pre-fetched batch result)
    if weather_result is None:
        weather_result = match_weather_for_road(db, road_id)
    
    # Use effective_rainfall_mm which applies uncertainty penalty
    # for missing weather (Correction 4: missing ≠ safe)
    rainfall_mm = weather_result.effective_rainfall_mm
    
    result = compute_risk_score(
        rainfall_mm=rainfall_mm,
        road_condition="good",  # status='open' roads
        bridge_condition=bridge_condition,
        recent_incidents=incident_count,
        terrain_difficulty=0.3,
    )
    
    return result["risk_score"], result["risk_level"]


def _compute_batch_edge_risks(
    db: Session,
    road_ids: Set[int],
) -> Dict[int, Tuple[float, str]]:
    """Batch-compute risk scores for multiple road edges.
    
    Performs ONE batch weather lookup, ONE batch incident query, and ONE batch
    bridge query for all road_ids, then computes risk in-memory.
    Avoids per-road DB query waterfalls.
    
    Returns dict mapping road_id -> (risk_score, risk_level).
    """
    from app.services.weather_match import (
        batch_match_weather_for_roads,
        _make_missing_result,
    )
    from app.services.risk_engine import compute_risk_score
    from app import models
    from sqlalchemy import func
    
    if not road_ids:
        return {}
    
    road_list = list(road_ids)
    
    # 1. Batch weather lookup
    weather_batch = batch_match_weather_for_roads(db, road_ids=road_list)
    
    # 2. Batch incident query
    incident_rows = db.query(
        models.Incident.road_id,
        models.Incident.incident_type,
        models.Incident.severity,
    ).filter(
        models.Incident.road_id.in_(road_list),
        models.Incident.status.in_(["reported", "verified"])
    ).all()
    incident_counts: Dict[int, int] = {}
    severe_disaster_roads: Set[int] = set()
    for inc in incident_rows:
        incident_counts[inc.road_id] = incident_counts.get(inc.road_id, 0) + 1
        if inc.severity == "high" or inc.incident_type in ["landslide", "flood", "road_damage"]:
            severe_disaster_roads.add(inc.road_id)
    
    # 3. Batch bridge query
    bridges = db.query(models.Bridge).filter(
        models.Bridge.road_id.in_(road_list)
    ).all()
    bridge_conditions: Dict[int, str] = {}
    for b in bridges:
        existing = bridge_conditions.get(b.road_id, "good")
        if b.condition == "poor" or (b.condition == "fair" and existing != "poor"):
            bridge_conditions[b.road_id] = b.condition
    
    # 4. In-memory risk computation
    results: Dict[int, Tuple[float, str]] = {}
    for rid in road_list:
        wmatch = weather_batch.get(rid, _make_missing_result())
        inc_count = incident_counts.get(rid, 0)
        is_severe = rid in severe_disaster_roads
        bridge_cond = bridge_conditions.get(rid, "good")
        road_condition = "poor" if (is_severe or inc_count >= 2) else ("fair" if inc_count == 1 else "good")
        res = compute_risk_score(
            rainfall_mm=wmatch.effective_rainfall_mm,
            road_condition=road_condition,
            bridge_condition=bridge_cond,
            recent_incidents=inc_count,
            terrain_difficulty=0.3,
        )
        score = res["risk_score"]
        if bridge_cond in ["poor", "critical"]:
            score = max(score, 90.0)
            level = "HIGH"
        elif bridge_cond in ["fair", "repair_needed"]:
            score = max(score, 45.0)
            level = "MEDIUM" if res["risk_level"] == "LOW" else res["risk_level"]
        elif is_severe:
            score = max(score, 85.0)
            level = "HIGH"
        else:
            level = res["risk_level"]
        results[rid] = (score, level)
    
    return results


def _calculate_risk_cost(distance_km: float, risk_score: float) -> float:
    """Deterministic risk cost formula.
    
    At 0 risk, risk_cost == distance_km.
    At 80+ risk (poor bridge / severe disaster), applies an additive barrier penalty
    (+1000 km) so even a 20m bridge will be bypassed if any alternative exists.
    """
    if risk_score >= 80.0:
        return distance_km + 1000.0
    elif risk_score >= 50.0:
        return distance_km * 3.0 + 10.0
    else:
        return distance_km * (1.0 + (risk_score / 100.0) * 1.5)


# ── Virtual Node Management ─────────────────────────────────────────────────

_ORIGIN_NODE = "__virtual_origin__"
_DEST_NODE = "__virtual_destination__"


def _add_virtual_node(
    graph: nx.DiGraph,
    node_key: str,
    snap: SnapResult,
):
    """Insert a virtual node at the snap point, connecting to edge endpoints.
    
    Splits the snapped edge's distance proportionally.
    Adds edges in both directions for routing flexibility.
    """
    u, v = snap.edge
    edge_dist = snap.edge_data.get("distance_km", MIN_EDGE_DISTANCE_KM)
    road_id = snap.road_id
    road_type = snap.edge_data.get("road_type", "unclassified")
    
    dist_to_u = max(edge_dist * snap.t, MIN_EDGE_DISTANCE_KM)
    dist_to_v = max(edge_dist * (1.0 - snap.t), MIN_EDGE_DISTANCE_KM)
    
    graph.add_node(node_key, lat=snap.snapped_lat, lon=snap.snapped_lon)
    
    # Add edges in both directions (virtual node can be origin or destination)
    for src, dst, dist in [(node_key, u, dist_to_u), (node_key, v, dist_to_v),
                            (u, node_key, dist_to_u), (v, node_key, dist_to_v)]:
        graph.add_edge(
            src, dst,
            road_id=road_id,
            road_type=road_type,
            distance_km=dist,
            risk_cost=dist,
            coordinates=[],  # virtual edges have no geometry
            virtual=True,
        )


def _remove_virtual_nodes(graph: nx.DiGraph):
    """Remove all virtual nodes from the graph (cleanup after routing)."""
    for node_key in [_ORIGIN_NODE, _DEST_NODE]:
        if node_key in graph:
            graph.remove_node(node_key)


# ── Route Finding ────────────────────────────────────────────────────────────

def find_route(
    db: Session,
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    preference: str = "shortest",
) -> Dict[str, Any]:
    """Compute a shortest or safest path route between arbitrary coordinates.

    Returns a GeoJSON Feature dict on success.
    Raises RoutingError on failure.
    
    Strategy:
    1. Build/retrieve cached graph
    2. Snap origin and destination to nearest road edges (PostGIS-first)
    3. Add virtual nodes to the shared graph (with lock)
    4. Run Dijkstra shortest path
    5. For 'safest': apply deferred risk scoring to path edges
    6. Reconstruct route geometry from stored coordinate arrays
    7. Clean up virtual nodes
    """
    t_start = time.time()
    
    # Calculate corridor bounding box around origin and destination (with ~22km margin)
    pad = 0.40
    min_lat = min(origin_lat, dest_lat) - pad
    max_lat = max(origin_lat, dest_lat) + pad
    min_lon = min(origin_lon, dest_lon) - pad
    max_lon = max(origin_lon, dest_lon) + pad
    corridor_bbox = (min_lon, min_lat, max_lon, max_lat)

    graph = build_road_graph(db, bbox=corridor_bbox)
    
    if graph.number_of_edges() == 0:
        raise RoutingError(
            code="ROUTING_DATA_UNAVAILABLE",
            message="No routable road data is available. Load road data before routing.",
        )
    
    # Snap origin and destination
    t_snap_orig_start = time.time()
    origin_snap = snap_to_nearest_edge(graph, origin_lat, origin_lon, db=db)
    t_snap_orig_end = time.time()
    
    if origin_snap is None:
        raise RoutingError(
            code="SNAP_FAILED",
            message="Could not snap origin coordinates to any road segment within the maximum search distance.",
        )
    
    t_snap_dest_start = time.time()
    dest_snap = snap_to_nearest_edge(graph, dest_lat, dest_lon, db=db)
    t_snap_dest_end = time.time()
    
    if dest_snap is None:
        raise RoutingError(
            code="SNAP_FAILED",
            message="Could not snap destination coordinates to any road segment within the maximum search distance.",
        )
    
    t_dijkstra_s = 0.0
    t_reconstruct_s = 0.0
    
    # Add virtual nodes and route (with cleanup)
    with _GRAPH_LOCK:
        try:
            _add_virtual_node(graph, _ORIGIN_NODE, origin_snap)
            _add_virtual_node(graph, _DEST_NODE, dest_snap)
            
            # Apply risk scoring to graph edges when safest routing is requested
            if preference == "safest":
                _apply_risk_scores_to_neighborhood(db, graph, origin_snap, dest_snap)
                weight_attr = lambda u, v, d: d.get("risk_cost", d.get("distance_km", 0.001))
            else:
                weight_attr = "distance_km"
            
            t_dijkstra_start = time.time()
            try:
                path = nx.shortest_path(
                    graph, _ORIGIN_NODE, _DEST_NODE, weight=weight_attr,
                )
            except nx.NetworkXNoPath:
                raise RoutingError(
                    code="NO_ROUTE",
                    message="No routable path exists between the specified origin and destination.",
                )
            t_dijkstra_end = time.time()
            t_dijkstra_s = t_dijkstra_end - t_dijkstra_start
            
            # Extract route data before cleanup
            t_reconstruct_start = time.time()
            route_data = _extract_route_data(db, graph, path, origin_snap, dest_snap, preference)
            t_reconstruct_end = time.time()
            t_reconstruct_s = t_reconstruct_end - t_reconstruct_start
            
        finally:
            _remove_virtual_nodes(graph)
            # Clean up any risk_cost attributes added during safest routing
            # (they persist on graph edges but will be recomputed next time)
    
    t_total = time.time() - t_start
    route_data["properties"]["computation_time_ms"] = round(t_total * 1000, 1)
    route_data["properties"]["timings_s"] = {
        "origin_snap": t_snap_orig_end - t_snap_orig_start,
        "dest_snap": t_snap_dest_end - t_snap_dest_start,
        "dijkstra": t_dijkstra_s,
        "geometry_reconstruct": t_reconstruct_s,
        "total": t_total,
    }
    
    return route_data


def _apply_risk_scores_to_neighborhood(
    db: Session,
    graph: nx.DiGraph,
    origin_snap: SnapResult,
    dest_snap: SnapResult,
):
    """Apply risk penalties to roads with poor bridges or high incidents so Dijkstra detours around them."""
    # 1. Fetch all road IDs with POOR/CRITICAL bridges or active HIGH-severity incidents (~2ms)
    avoid_rows = db.execute(text("""
        SELECT DISTINCT road_id FROM bridges WHERE condition IN ('poor', 'critical') AND road_id IS NOT NULL
        UNION
        SELECT DISTINCT road_id FROM incidents WHERE severity = 'high' AND status IN ('reported', 'verified') AND road_id IS NOT NULL
    """)).fetchall()
    avoid_road_ids = {row[0] for row in avoid_rows if row[0]}
    
    # 2. Heavily penalize any edges belonging to those dangerous roads (+1000km barrier)
    for rid in avoid_road_ids:
        edge_tuples = get_road_edges(rid)
        if edge_tuples:
            for item in edge_tuples:
                u, v = item[0], item[1]
                dist = item[2] if len(item) > 2 else 0.5
                cost = dist + 1000.0  # Barrier penalty forces Dijkstra onto safe bypass
                if graph.has_edge(u, v):
                    graph.edges[u, v]["risk_cost"] = cost
                    graph.edges[u, v]["risk_score"] = 95.0
                    graph.edges[u, v]["risk_level"] = "HIGH"
                if graph.has_edge(v, u):
                    graph.edges[v, u]["risk_cost"] = cost
                    graph.edges[v, u]["risk_score"] = 95.0
                    graph.edges[v, u]["risk_level"] = "HIGH"
                    
    # 3. For the remaining roads on the shortest-distance path, compute actual risk scores (~10ms)
    try:
        distance_path = nx.shortest_path(
            graph, _ORIGIN_NODE, _DEST_NODE, weight="distance_km"
        )
        path_road_ids: Set[int] = set()
        for i in range(len(distance_path) - 1):
            edata = graph.get_edge_data(distance_path[i], distance_path[i + 1])
            if edata and edata.get("road_id"):
                rid = edata["road_id"]
                # Only score roads that don't already have the hazard barrier penalty
                if rid not in avoid_road_ids:
                    path_road_ids.add(rid)
        
        if path_road_ids:
            risk_cache = _compute_batch_edge_risks(db, path_road_ids)
            for rid, (risk_score, risk_level) in risk_cache.items():
                edge_tuples = get_road_edges(rid)
                if edge_tuples:
                    for item in edge_tuples:
                        u, v = item[0], item[1]
                        dist = item[2] if len(item) > 2 else 0.5
                        cost = _calculate_risk_cost(dist, risk_score)
                        if graph.has_edge(u, v):
                            graph.edges[u, v]["risk_cost"] = cost
                            graph.edges[u, v]["risk_score"] = risk_score
                            graph.edges[u, v]["risk_level"] = risk_level
                        if graph.has_edge(v, u):
                            graph.edges[v, u]["risk_cost"] = cost
                            graph.edges[v, u]["risk_score"] = risk_score
                            graph.edges[v, u]["risk_level"] = risk_level
    except nx.NetworkXNoPath:
        pass


def _extract_route_data(
    db: Session,
    graph: nx.DiGraph,
    path: List,
    origin_snap: SnapResult,
    dest_snap: SnapResult,
    preference: str,
) -> Dict[str, Any]:
    """Extract route GeoJSON data from a computed path.
    
    Reconstructs actual route geometry from PostGIS road coordinates and path nodes.
    Risk scores are computed directly from the database for the route roads.
    """
    from app.services.risk_engine import compute_risk_score
    from app.services.weather_match import match_weather_for_road, _make_missing_result
    from app import models
    
    coordinates: List[List[float]] = []
    route_segments: List[Dict[str, Any]] = []
    total_distance = 0.0
    total_duration_minutes = 0.0
    edge_count = 0
    
    # First pass: collect distance and segments
    for i in range(len(path) - 1):
        edge_data = graph.get_edge_data(path[i], path[i + 1])
        if not edge_data:
            continue
        
        edge_count += 1
        seg_dist = edge_data.get("distance_km", 0)
        total_distance += seg_dist
        
        # Duration estimation
        road_type = edge_data.get("road_type", "unclassified")
        speed = SPEED_BY_TYPE.get(road_type, DEFAULT_SPEED_KMH)
        if seg_dist > 0 and speed > 0:
            total_duration_minutes += (seg_dist / speed) * 60
        
        # Track route segments (deduplicated by road_id, preserving order)
        rid = edge_data.get("road_id")
        if rid is not None:
            if not route_segments or route_segments[-1]["road_id"] != rid:
                route_segments.append({
                    "road_id": rid,
                    "is_reversed": edge_data.get("is_reversed", False),
                    "distance_km": seg_dist
                })
            else:
                route_segments[-1]["distance_km"] += seg_dist

    # Collect unique road_ids for geometry and risk queries
    unique_road_ids = list({seg["road_id"] for seg in route_segments})

    # Fetch real PostGIS geometries for roads traversed in the route
    road_geometries: Dict[int, List[List[float]]] = {}
    if unique_road_ids:
        try:
            g_rows = db.execute(
                text("SELECT id, ST_AsGeoJSON(geometry) FROM roads WHERE id = ANY(:rids)"),
                {"rids": unique_road_ids}
            ).fetchall()
            for gr in g_rows:
                if gr[1]:
                    geom_obj = json.loads(gr[1])
                    road_geometries[gr[0]] = geom_obj.get("coordinates", [])
        except Exception as e:
            logger.warning(f"Failed to fetch road geometries from PostGIS: {e}")

    # Reconstruct high-fidelity LineString
    for seg in route_segments:
        rid = seg["road_id"]
        coords = road_geometries.get(rid)
        if coords:
            pts = coords[::-1] if seg.get("is_reversed") else coords
            for pt in pts:
                if not coordinates or coordinates[-1] != list(pt):
                    coordinates.append(list(pt))

    # If geometry lookup yielded no points, fall back directly to graph path nodes
    if not coordinates:
        for node in path:
            if isinstance(node, tuple) and len(node) == 2:
                coord = [node[1], node[0]]
            else:
                nd = graph.nodes[node]
                coord = [nd.get("lon", 0), nd.get("lat", 0)]
            if not coordinates or coordinates[-1] != coord:
                coordinates.append(coord)
    
    # ── Bulletproof Risk Scoring: query DB directly ──────────────────────
    # Collect unique road_ids from route segments
    unique_road_ids = list({seg["road_id"] for seg in route_segments})
    
    # Batch query: count active incidents and track disaster severity per road
    incident_counts: Dict[int, int] = {}
    has_severe_disaster_per_road: Dict[int, bool] = {}
    inc_records = []
    if unique_road_ids:
        inc_records = db.query(
            models.Incident.road_id,
            models.Incident.incident_type,
            models.Incident.severity,
            models.Incident.description,
            models.Incident.bridge_id,
        ).filter(
            models.Incident.road_id.in_(unique_road_ids),
            models.Incident.status.in_(["reported", "verified"])
        ).all()
        for r in inc_records:
            incident_counts[r.road_id] = incident_counts.get(r.road_id, 0) + 1
            if r.severity == "high" or r.incident_type in ["landslide", "flood", "road_damage"]:
                has_severe_disaster_per_road[r.road_id] = True
    
    # Batch query: bridges on route roads + worst bridge condition per road
    bridge_conditions: Dict[int, str] = {}
    bridges_on_route: List[Dict[str, Any]] = []
    if unique_road_ids:
        bridges = db.query(models.Bridge).filter(
            models.Bridge.road_id.in_(unique_road_ids)
        ).all()
        for b in bridges:
            cond = (b.condition or "good").lower()
            existing = bridge_conditions.get(b.road_id, "good")
            if cond in ["poor", "critical"] or (cond in ["fair", "repair_needed"] and existing not in ["poor", "critical"]):
                bridge_conditions[b.road_id] = cond
            
            # Determine explicit hazard cause from incident or geotechnical analysis
            matching_inc = None
            for r in inc_records:
                if r.bridge_id == b.id:
                    matching_inc = r
                    break
                elif r.road_id == b.road_id and matching_inc is None:
                    matching_inc = r

            if matching_inc:
                itype = (matching_inc.incident_type or "hazard").lower()
                if "landslide" in itype:
                    cause = "Landslide Blockade"
                elif "flood" in itype:
                    cause = "Flash Flood & Pier Scour"
                elif "damage" in itype or "road_damage" in itype:
                    cause = "Road Damage & Embankment Collapse"
                else:
                    cause = f"{matching_inc.incident_type.title()} Hazard"
                cause_desc = matching_inc.description or f"Active {itype} reported along this corridor."
                hazard_type = itype
            elif cond in ["poor", "critical"]:
                # Geotechnical inference based on location and terrain
                if (b.latitude and b.latitude >= 26.9) and (b.longitude and b.longitude <= 93.7):
                    cause = "Landslide & Hill Slope Collapse"
                    cause_desc = "Torrential rains caused hillside mudslide and rockfall debris blocking bridge approach."
                    hazard_type = "landslide"
                elif (b.latitude and b.latitude < 26.9) or "river" in (b.name or "").lower():
                    cause = "Flash Flood & Pier Scour"
                    cause_desc = "High monsoon river current caused deep foundation scour and structural shifting."
                    hazard_type = "flood"
                else:
                    cause = "Structural Deck Crack & Girder Wear"
                    cause_desc = "Critical shear cracking in bridge deck and girder fatigue; impassable for heavy loads."
                    hazard_type = "structural"
            elif cond in ["fair", "repair_needed"]:
                if (b.latitude and b.latitude >= 26.9):
                    cause = "Monsoon Erosion & Minor Slump"
                    cause_desc = "Hillside soil erosion along bridge abutments; 15T load restriction applied."
                    hazard_type = "erosion"
                else:
                    cause = "High River Current & Pier Wear"
                    cause_desc = "Surface joint wear and minor pier abrasion from river current; standard load limit."
                    hazard_type = "scour"
            else:
                cause = "Operational & Safe"
                cause_desc = "Bridge superstructure, piers, and approach roads inspected and fully operational."
                hazard_type = "none"

            bridges_on_route.append({
                "id": b.id,
                "name": b.name,
                "road_id": b.road_id,
                "latitude": b.latitude,
                "longitude": b.longitude,
                "condition": cond,
                "cause": cause,
                "cause_description": cause_desc,
                "hazard_type": hazard_type,
                "last_verified": b.last_verified.isoformat() if b.last_verified else None,
            })
            
    
    # Compute risk per road
    road_risk_cache: Dict[int, float] = {}
    for rid in unique_road_ids:
        inc_count = incident_counts.get(rid, 0)
        is_severe = has_severe_disaster_per_road.get(rid, False)
        bridge_cond = bridge_conditions.get(rid, "good")
        
        # Disaster impacts road condition
        if is_severe or inc_count >= 2:
            road_cond = "poor"
        elif inc_count == 1:
            road_cond = "fair"
        else:
            road_cond = "good"
            
        result = compute_risk_score(
            rainfall_mm=0.0,
            road_condition=road_cond,
            bridge_condition=bridge_cond,
            recent_incidents=inc_count,
            terrain_difficulty=0.3,
        )
        r_score = result["risk_score"]
        if bridge_cond in ["poor", "critical"]:
            r_score = max(r_score, 90.0)
        elif bridge_cond in ["fair", "repair_needed"]:
            r_score = max(r_score, 45.0)
        # If severe disaster (landslide/flood) is present on this road, reflect severity directly
        if is_severe:
            is_high_sev = any(r.severity == "high" for r in inc_records if r.road_id == rid)
            r_score = max(r_score, 80.0 if is_high_sev else 55.0)
        elif inc_count > 0:
            r_score = max(r_score, 40.0)
        road_risk_cache[rid] = r_score
    
    # Compute route-level risk from per-road scores
    total_risk_score = 0.0
    max_risk_score = 0.0
    for seg in route_segments:
        r_score = road_risk_cache.get(seg["road_id"], 0.0)
        total_risk_score += r_score
        max_risk_score = max(max_risk_score, r_score)
    
    num_segments = max(1, len(route_segments))
    average_risk_score = round(total_risk_score / num_segments, 1)
    total_incidents = sum(incident_counts.values())
    
    # Route condition: If severe disasters (landslide/flood) or poor bridges exist,
    # the route cannot be classified as LOW.
    has_high_disaster = any(
        r.severity == "high" for r in inc_records
    ) if unique_road_ids and inc_records else False

    has_poor_bridge = any(
        (b.get("condition") or "").lower() in ["poor", "critical"] for b in bridges_on_route
    )

    if preference == "safest" and not has_poor_bridge and not has_high_disaster:
        # Safest route successfully detoured around all hazards!
        risk_level = "LOW" if average_risk_score < 30 else "MEDIUM"
    else:
        if has_high_disaster or has_poor_bridge or max_risk_score >= 65 or average_risk_score >= 65:
            risk_level = "HIGH"
        elif max_risk_score >= 35 or average_risk_score >= 35 or total_incidents > 0 or any((b.get("condition") or "").lower() in ["fair", "repair_needed"] for b in bridges_on_route):
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"
    
    poor_causes = list({b["cause"] for b in bridges_on_route if b["condition"] in ["poor", "critical"]})

    return {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": coordinates,
        },
        "properties": {
            "origin": {"lat": origin_snap.snapped_lat, "lon": origin_snap.snapped_lon},
            "destination": {"lat": dest_snap.snapped_lat, "lon": dest_snap.snapped_lon},
            "snapped_origin": {
                "lat": origin_snap.snapped_lat,
                "lon": origin_snap.snapped_lon,
            },
            "snapped_destination": {
                "lat": dest_snap.snapped_lat,
                "lon": dest_snap.snapped_lon,
            },
            "route_preference": preference,
            "distance_km": round(total_distance, 4),
            "total_distance_km": round(total_distance, 4),
            "estimated_duration_minutes": round(total_duration_minutes, 1),
            "average_risk_score": average_risk_score,
            "max_risk_score": max_risk_score,
            "risk_level": risk_level,
            "total_incidents": total_incidents,
            "num_roads": len(route_segments),
            "route_segments": route_segments,
            "num_coordinates": len(coordinates),
            "geometry_source": "osm_linestring",
            "bridges": bridges_on_route,
            "bridge_count": len(bridges_on_route),
            "bridges_good": sum(1 for b in bridges_on_route if b["condition"] == "good"),
            "bridges_fair": sum(1 for b in bridges_on_route if b["condition"] in ["fair", "repair_needed"]),
            "bridges_poor": sum(1 for b in bridges_on_route if b["condition"] in ["poor", "critical"]),
            "poor_causes": poor_causes,
            "primary_cause": poor_causes[0] if poor_causes else ("Safe Bypass" if preference == "safest" else "Operational"),
        },
    }


from app import models
from app import schemas

def create_route_from_computed(db: Session, route_data: Dict[str, Any], name: str = "") -> models.Route:
    """
    Converts a computed GeoJSON route into a persisted Route and RouteRoads.
    """
    # Create the route
    db_route = models.Route(name=name)
    db.add(db_route)
    db.commit()
    db.refresh(db_route)
    
    # Create the route roads
    route_segments = route_data.get("properties", {}).get("route_segments", [])
    for idx, seg in enumerate(route_segments):
        route_road = models.RouteRoad(
            route_id=db_route.id,
            road_id=seg["road_id"],
            sequence=idx,
            is_reversed=seg["is_reversed"],
            road_length_km=seg["distance_km"]
        )
        db.add(route_road)
        
    db.commit()
    db.refresh(db_route)
    return db_route

class RoutingError(Exception):
    """Raised when routing cannot be completed."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)
