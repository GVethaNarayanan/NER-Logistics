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
                
                # Search for edges belonging to this road_id
                best_edge = None
                best_t = 0.5
                
                for u, v, data in graph.edges(data=True):
                    if data.get("road_id") == road_id:
                        # Project snap point onto this edge segment
                        u_lat, u_lon = u
                        v_lat, v_lon = v
                        proj_lat, proj_lon, t = _project_point_to_segment(
                            snap_lat, snap_lon, u_lat, u_lon, v_lat, v_lon
                        )
                        proj_dist = haversine_distance_km(snap_lat, snap_lon, proj_lat, proj_lon)
                        
                        if best_edge is None or proj_dist < haversine_distance_km(
                            snap_lat, snap_lon, 
                            best_edge[2].get("_proj_lat", 0), 
                            best_edge[2].get("_proj_lon", 0)
                        ):
                            data["_proj_lat"] = proj_lat
                            data["_proj_lon"] = proj_lon
                            best_edge = (u, v, data)
                            best_t = t
                
                if best_edge is not None:
                    u, v, data = best_edge
                    # Clean up temporary projection data
                    data.pop("_proj_lat", None)
                    data.pop("_proj_lon", None)
                    
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
    
    Correction 3: Performs ONE batch weather lookup for all road_ids,
    then computes risk for each road using the batch results.
    Avoids per-road DB query waterfalls.
    
    Returns dict mapping road_id -> (risk_score, risk_level).
    """
    from app.services.weather_match import (
        batch_match_weather_for_roads,
        _make_missing_result,
    )
    
    if not road_ids:
        return {}
    
    # One batch weather lookup for all route edges
    weather_batch = batch_match_weather_for_roads(db, road_ids=list(road_ids))
    
    results: Dict[int, Tuple[float, str]] = {}
    for rid in road_ids:
        wmatch = weather_batch.get(rid, _make_missing_result())
        results[rid] = _compute_edge_risk(db, rid, weather_result=wmatch)
    
    return results


def _calculate_risk_cost(distance_km: float, risk_score: float) -> float:
    """Deterministic risk cost formula.
    
    At 0 risk, risk_cost == distance_km.
    At 100 risk, risk_cost == distance_km * 10 (10x penalty).
    """
    penalty_multiplier = 1.0 + (risk_score / 100.0) * 9.0
    return distance_km * penalty_multiplier


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
    
    graph = build_road_graph(db)
    
    if graph.number_of_edges() == 0:
        raise RoutingError(
            code="ROUTING_DATA_UNAVAILABLE",
            message="No routable road data is available. Load road data before routing.",
        )
    
    # Snap origin and destination
    origin_snap = snap_to_nearest_edge(graph, origin_lat, origin_lon, db=db)
    if origin_snap is None:
        raise RoutingError(
            code="SNAP_FAILED",
            message="Could not snap origin coordinates to any road segment within the maximum search distance.",
        )
    
    dest_snap = snap_to_nearest_edge(graph, dest_lat, dest_lon, db=db)
    if dest_snap is None:
        raise RoutingError(
            code="SNAP_FAILED",
            message="Could not snap destination coordinates to any road segment within the maximum search distance.",
        )
    
    # Add virtual nodes and route (with cleanup)
    with _GRAPH_LOCK:
        try:
            _add_virtual_node(graph, _ORIGIN_NODE, origin_snap)
            _add_virtual_node(graph, _DEST_NODE, dest_snap)
            
            # Choose weight attribute
            if preference == "safest":
                # For safest routing, we need risk-weighted edges
                # Apply deferred risk scoring to edges in the routing neighborhood
                _apply_risk_scores_to_neighborhood(db, graph, origin_snap, dest_snap)
                weight_attr = "risk_cost"
            else:
                weight_attr = "distance_km"
            
            try:
                path = nx.shortest_path(
                    graph, _ORIGIN_NODE, _DEST_NODE, weight=weight_attr,
                )
            except nx.NetworkXNoPath:
                raise RoutingError(
                    code="NO_ROUTE",
                    message="No routable path exists between the specified origin and destination.",
                )
            
            # Extract route data before cleanup
            route_data = _extract_route_data(graph, path, origin_snap, dest_snap, preference)
            
        finally:
            _remove_virtual_nodes(graph)
            # Clean up any risk_cost attributes added during safest routing
            # (they persist on graph edges but will be recomputed next time)
    
    t_total = time.time() - t_start
    route_data["properties"]["computation_time_ms"] = round(t_total * 1000, 1)
    
    return route_data


def _apply_risk_scores_to_neighborhood(
    db: Session,
    graph: nx.DiGraph,
    origin_snap: SnapResult,
    dest_snap: SnapResult,
):
    """Apply deferred risk scores to edges near the origin and destination.
    
    Instead of scoring all 226k roads, we score edges within a reasonable
    neighborhood of the route. We first find the shortest-distance path,
    then score all edges on that path plus adjacent edges.
    """
    # First, find the shortest-distance path to identify relevant edges
    try:
        distance_path = nx.shortest_path(
            graph, _ORIGIN_NODE, _DEST_NODE, weight="distance_km"
        )
    except nx.NetworkXNoPath:
        return  # Let the main routing handle the no-path case
    
    # Collect road_ids from the path and their neighbors
    road_ids_to_score: Set[int] = set()
    nodes_in_path: Set = set(distance_path)
    
    for i in range(len(distance_path) - 1):
        edge_data = graph.get_edge_data(distance_path[i], distance_path[i + 1])
        if edge_data:
            rid = edge_data.get("road_id")
            if rid:
                road_ids_to_score.add(rid)
        
        # Include edges from neighbors of path nodes (1-hop neighborhood)
        for neighbor in graph.neighbors(distance_path[i]):
            edge_data = graph.get_edge_data(distance_path[i], neighbor)
            if edge_data:
                rid = edge_data.get("road_id")
                if rid:
                    road_ids_to_score.add(rid)
    
    # Batch-compute risk scores for all relevant roads (Correction 3)
    # One batch weather lookup instead of per-road DB query waterfall
    risk_cache = _compute_batch_edge_risks(db, road_ids_to_score)
    
    for u, v, data in graph.edges(data=True):
        rid = data.get("road_id")
        if rid and rid in risk_cache:
            risk_score, risk_level = risk_cache[rid]
            data["risk_score"] = risk_score
            data["risk_level"] = risk_level
            data["risk_cost"] = _calculate_risk_cost(data.get("distance_km", 0.001), risk_score)
        elif "risk_cost" not in data:
            # Default risk cost for unscored edges
            data["risk_cost"] = data.get("distance_km", 0.001)


def _extract_route_data(
    graph: nx.DiGraph,
    path: List,
    origin_snap: SnapResult,
    dest_snap: SnapResult,
    preference: str,
) -> Dict[str, Any]:
    """Extract route GeoJSON data from a computed path.
    
    Reconstructs actual route geometry from the stored coordinate arrays
    on each edge, producing a real LineString that follows the road.
    """
    coordinates: List[List[float]] = []
    route_segments: List[Dict[str, Any]] = []
    total_distance = 0.0
    total_risk_score = 0.0
    max_risk_score = 0.0
    total_duration_minutes = 0.0
    edge_count = 0
    
    for i in range(len(path) - 1):
        edge_data = graph.get_edge_data(path[i], path[i + 1])
        if not edge_data:
            continue
        
        edge_count += 1
        seg_dist = edge_data.get("distance_km", 0)
        total_distance += seg_dist
        
        r_score = edge_data.get("risk_score", 0.0)
        total_risk_score += r_score
        max_risk_score = max(max_risk_score, r_score)
        
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
        
        # Reconstruct geometry from stored coordinates
        edge_coords = edge_data.get("coordinates", [])
        if edge_coords:
            for coord in edge_coords:
                # coord is [lon, lat] (GeoJSON order)
                if not coordinates or coordinates[-1] != list(coord):
                    coordinates.append(list(coord))
        else:
            # Virtual edge — use node coordinates
            if isinstance(path[i], tuple) and len(path[i]) == 2:
                coord = [path[i][1], path[i][0]]  # [lon, lat]
            else:
                node_data = graph.nodes[path[i]]
                coord = [node_data.get("lon", 0), node_data.get("lat", 0)]
            
            if not coordinates or coordinates[-1] != coord:
                coordinates.append(coord)
    
    # Add final point
    last = path[-1]
    if isinstance(last, tuple) and len(last) == 2:
        final_coord = [last[1], last[0]]
    else:
        node_data = graph.nodes[last]
        final_coord = [node_data.get("lon", 0), node_data.get("lat", 0)]
    
    if not coordinates or coordinates[-1] != final_coord:
        coordinates.append(final_coord)
    
    # Risk summary
    num_edges = max(1, edge_count)
    average_risk_score = round(total_risk_score / num_edges, 1)
    
    if average_risk_score < 35:
        risk_level = "LOW"
    elif average_risk_score < 65:
        risk_level = "MEDIUM"
    else:
        risk_level = "HIGH"
    
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
            "total_distance_km": round(total_distance, 4),
            "estimated_duration_minutes": round(total_duration_minutes, 1),
            "average_risk_score": average_risk_score,
            "max_risk_score": max_risk_score,
            "risk_level": risk_level,
            "num_roads": len(route_segments),
            "route_segments": route_segments,
            "num_coordinates": len(coordinates),
            "geometry_source": "osm_linestring",
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
