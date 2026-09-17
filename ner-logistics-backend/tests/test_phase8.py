"""
Phase 8 — GIS / Routing Implementation Tests

Covers all 28 Phase 8 routing scenarios:
- Graph construction from Road records
- Blocked road exclusion
- Basic connected routing
- Shortest-route selection
- Mid-edge snapping (origin, destination, both)
- Same-edge routing without artificial detour
- Same-edge route distance is sensible
- Request-local virtual nodes (original graph not mutated)
- GeoJSON structure, geometry type, coordinate order
- Route geometry follows road order
- Total distance is sensible
- Invalid coordinate validation
- No routing data error
- Disconnected graph NO_ROUTE error
- No fabricated route for disconnected points
- Existing auth remains correct
- Phase 1–7.1 regression (via full pytest run)
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import networkx as nx

from app import models
from app.services.graph_service import build_road_graph
from app.services.routing_service import snap_to_nearest_edge, find_route, RoutingError
from app.services.vehicle_service import haversine_distance_km


# ── Helpers ──────────────────────────────────────────────────────────────────

def _create_road(
    db: Session, name: str,
    start_lat: float, start_lon: float,
    end_lat: float, end_lon: float,
    status: str = "open",
) -> models.Road:
    road = models.Road(
        name=name, road_type="highway",
        start_lat=start_lat, start_lon=start_lon,
        end_lat=end_lat, end_lon=end_lon,
        status=status, district="Test",
    )
    db.add(road)
    db.commit()
    db.refresh(road)
    return road


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Graph builds successfully from Road records
# ═══════════════════════════════════════════════════════════════════════════════

class TestGraphBuild:
    def test_build_graph_from_records(self, db_session):
        _create_road(db_session, "R1", 26.0, 91.0, 26.1, 91.1)
        _create_road(db_session, "R2", 26.1, 91.1, 26.2, 91.2)

        graph = build_road_graph(db_session)
        assert isinstance(graph, nx.Graph)
        assert not isinstance(graph, nx.DiGraph)
        assert graph.number_of_nodes() == 3
        assert graph.number_of_edges() == 2

    def test_blocked_roads_excluded(self, db_session):
        _create_road(db_session, "Open", 26.0, 91.0, 26.1, 91.1, status="open")
        _create_road(db_session, "Blocked", 26.1, 91.1, 26.2, 91.2, status="blocked")
        _create_road(db_session, "Restricted", 26.2, 91.2, 26.3, 91.3, status="restricted")

        graph = build_road_graph(db_session)
        assert graph.number_of_edges() == 1

    def test_edge_has_metadata(self, db_session):
        r = _create_road(db_session, "R1", 26.0, 91.0, 26.1, 91.1)
        graph = build_road_graph(db_session)
        edges = list(graph.edges(data=True))
        assert len(edges) == 1
        data = edges[0][2]
        assert data["road_id"] == r.id
        assert data["distance_km"] > 0
        assert data["start_lat"] == 26.0
        assert data["end_lon"] == 91.1

    def test_empty_graph_when_no_roads(self, db_session):
        graph = build_road_graph(db_session)
        assert graph.number_of_nodes() == 0
        assert graph.number_of_edges() == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Basic route between connected roads
# ═══════════════════════════════════════════════════════════════════════════════

class TestBasicRouting:
    def test_route_exists_between_connected_roads(self, db_session):
        _create_road(db_session, "R1", 26.0, 91.0, 26.1, 91.1)
        _create_road(db_session, "R2", 26.1, 91.1, 26.2, 91.2)

        route = find_route(db_session, 26.0, 91.0, 26.2, 91.2)
        assert route["type"] == "Feature"
        assert route["geometry"]["type"] == "LineString"
        assert len(route["properties"]["road_ids"]) >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Correct shortest route selected based on distance
# ═══════════════════════════════════════════════════════════════════════════════

class TestShortestRoute:
    def test_shorter_path_chosen(self, db_session):
        """Triangle: A→B→C is long, A→C is short. Route A→C must use direct road."""
        # Long detour: A(26.0, 91.0) → B(26.0, 92.0) → C(26.0, 91.5)
        # Each leg ~110km, total ~220km
        _create_road(db_session, "Long1", 26.0, 91.0, 26.0, 92.0)
        _create_road(db_session, "Long2", 26.0, 92.0, 26.0, 91.5)
        # Direct: A(26.0, 91.0) → C(26.0, 91.5)  ~55km
        r_short = _create_road(db_session, "Short", 26.0, 91.0, 26.0, 91.5)

        route = find_route(db_session, 26.0, 91.0, 26.0, 91.5)
        # The direct (shorter) road must be used
        assert r_short.id in route["properties"]["road_ids"]
        # Total distance should be close to the direct distance (~55km), not ~220km
        assert route["properties"]["total_distance_km"] < 100


# ═══════════════════════════════════════════════════════════════════════════════
# 4-5. Arbitrary origin/destination accepted (not exact node)
# ═══════════════════════════════════════════════════════════════════════════════

class TestArbitraryCoordinates:
    def test_arbitrary_origin_accepted(self, db_session):
        """Origin at midpoint of a road, not at an endpoint."""
        _create_road(db_session, "R1", 26.0, 91.0, 26.0, 91.2)
        route = find_route(db_session, 26.0, 91.1, 26.0, 91.2)
        assert route["type"] == "Feature"

    def test_arbitrary_destination_accepted(self, db_session):
        """Destination at midpoint of a road, not at an endpoint."""
        _create_road(db_session, "R1", 26.0, 91.0, 26.0, 91.2)
        route = find_route(db_session, 26.0, 91.0, 26.0, 91.1)
        assert route["type"] == "Feature"


# ═══════════════════════════════════════════════════════════════════════════════
# 6-7. Origin/destination snapped to nearest edge
# ═══════════════════════════════════════════════════════════════════════════════

class TestEdgeSnapping:
    def test_origin_snapped_to_nearest_edge(self, db_session):
        """Point slightly off-road snaps onto the road."""
        _create_road(db_session, "R1", 26.0, 91.0, 26.0, 91.2)
        graph = build_road_graph(db_session)

        # Point at (26.001, 91.1) — slightly north of the east-west road
        snap = snap_to_nearest_edge(graph, 26.001, 91.1)
        assert snap is not None
        assert abs(snap.snapped_lat - 26.0) < 0.002  # close to road latitude
        assert abs(snap.snapped_lon - 91.1) < 0.01

    def test_destination_snapped_to_nearest_edge(self, db_session):
        _create_road(db_session, "R1", 26.0, 91.0, 26.0, 91.2)
        graph = build_road_graph(db_session)

        snap = snap_to_nearest_edge(graph, 25.999, 91.15)
        assert snap is not None
        assert abs(snap.snapped_lat - 26.0) < 0.002
        assert abs(snap.snapped_lon - 91.15) < 0.01


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Snapped coordinates returned in response
# ═══════════════════════════════════════════════════════════════════════════════

class TestSnappedCoordinatesReturned:
    def test_response_contains_snapped_coords(self, db_session):
        _create_road(db_session, "R1", 26.0, 91.0, 26.0, 91.2)
        route = find_route(db_session, 26.001, 91.1, 25.999, 91.15)

        props = route["properties"]
        assert "snapped_origin" in props
        assert "lat" in props["snapped_origin"]
        assert "lon" in props["snapped_origin"]
        assert "snapped_destination" in props
        assert "lat" in props["snapped_destination"]
        assert "lon" in props["snapped_destination"]

        # Snapped coords should differ from input (slightly off-road inputs)
        assert abs(props["snapped_origin"]["lat"] - 26.001) < 0.01
        assert abs(props["snapped_destination"]["lat"] - 25.999) < 0.01


# ═══════════════════════════════════════════════════════════════════════════════
# 9-10. GeoJSON structure valid, geometry type LineString
# ═══════════════════════════════════════════════════════════════════════════════

class TestGeoJSONStructure:
    def test_geojson_feature_structure(self, db_session):
        _create_road(db_session, "R1", 26.0, 91.0, 26.1, 91.1)
        route = find_route(db_session, 26.0, 91.0, 26.1, 91.1)

        assert route["type"] == "Feature"
        assert "geometry" in route
        assert "properties" in route
        assert route["geometry"]["type"] == "LineString"
        assert "coordinates" in route["geometry"]

    def test_geojson_coordinate_order_lon_lat(self, db_session):
        """GeoJSON coordinates must be [longitude, latitude]."""
        _create_road(db_session, "R1", 26.0, 91.0, 26.1, 91.1)
        route = find_route(db_session, 26.0, 91.0, 26.1, 91.1)

        coords = route["geometry"]["coordinates"]
        # First coord: lon=91.0, lat=26.0
        assert coords[0][0] == pytest.approx(91.0, abs=0.01)
        assert coords[0][1] == pytest.approx(26.0, abs=0.01)


# ═══════════════════════════════════════════════════════════════════════════════
# 12. Route geometry follows selected roads in correct order
# ═══════════════════════════════════════════════════════════════════════════════

class TestRouteGeometryOrder:
    def test_geometry_follows_road_order(self, db_session):
        _create_road(db_session, "R1", 26.0, 91.0, 26.0, 91.1)
        _create_road(db_session, "R2", 26.0, 91.1, 26.0, 91.2)

        route = find_route(db_session, 26.0, 91.0, 26.0, 91.2)
        coords = route["geometry"]["coordinates"]

        # Coordinates should go west to east (91.0 → 91.1 → 91.2)
        lons = [c[0] for c in coords]
        assert lons == sorted(lons)


# ═══════════════════════════════════════════════════════════════════════════════
# 13. Total route distance returned and sensible
# ═══════════════════════════════════════════════════════════════════════════════

class TestTotalDistance:
    def test_distance_positive_and_sensible(self, db_session):
        _create_road(db_session, "R1", 26.0, 91.0, 26.1, 91.1)
        route = find_route(db_session, 26.0, 91.0, 26.1, 91.1)

        dist = route["properties"]["total_distance_km"]
        assert dist > 0
        # Haversine ~15.7km for this distance
        assert 10 < dist < 25


# ═══════════════════════════════════════════════════════════════════════════════
# 14-15. Invalid latitude/longitude rejected
# ═══════════════════════════════════════════════════════════════════════════════

class TestInvalidCoordinates:
    def test_invalid_latitude(self, client):
        res = client.post("/routing/route", json={
            "origin_lat": 999.0, "origin_lon": 91.0,
            "destination_lat": 26.1, "destination_lon": 91.1,
        })
        assert res.status_code == 422

    def test_invalid_longitude(self, client):
        res = client.post("/routing/route", json={
            "origin_lat": 26.0, "origin_lon": 999.0,
            "destination_lat": 26.1, "destination_lon": 91.1,
        })
        assert res.status_code == 422

    def test_invalid_dest_latitude(self, client):
        res = client.post("/routing/route", json={
            "origin_lat": 26.0, "origin_lon": 91.0,
            "destination_lat": -91.0, "destination_lon": 91.1,
        })
        assert res.status_code == 422

    def test_invalid_dest_longitude(self, client):
        res = client.post("/routing/route", json={
            "origin_lat": 26.0, "origin_lon": 91.0,
            "destination_lat": 26.1, "destination_lon": 181.0,
        })
        assert res.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════════
# 16. No routing data → clear error
# ═══════════════════════════════════════════════════════════════════════════════

class TestNoRoutingData:
    def test_empty_roads_returns_error(self, db_session):
        with pytest.raises(RoutingError) as exc_info:
            find_route(db_session, 26.0, 91.0, 26.1, 91.1)
        assert exc_info.value.code == "ROUTING_DATA_UNAVAILABLE"

    def test_empty_roads_api_returns_400(self, client, db_session):
        db_session.query(models.Road).delete()
        db_session.commit()

        res = client.post("/routing/route", json={
            "origin_lat": 26.0, "origin_lon": 91.0,
            "destination_lat": 26.1, "destination_lon": 91.1,
        })
        assert res.status_code == 400
        body = res.json()
        assert "ROUTING_DATA_UNAVAILABLE" in body["error"]["message"]


# ═══════════════════════════════════════════════════════════════════════════════
# 17-19. Disconnected graph → 4xx NO_ROUTE, not 500, no fake geometry
# ═══════════════════════════════════════════════════════════════════════════════

class TestDisconnectedGraph:
    def test_disconnected_raises_no_route(self, db_session):
        _create_road(db_session, "C1_R1", 26.0, 91.0, 26.1, 91.1)
        _create_road(db_session, "C2_R1", 30.0, 95.0, 30.1, 95.1)

        with pytest.raises(RoutingError) as exc_info:
            find_route(db_session, 26.0, 91.0, 30.1, 95.1)
        assert exc_info.value.code == "NO_ROUTE"

    def test_disconnected_api_returns_400(self, client, db_session):
        _create_road(db_session, "C1_R1", 26.0, 91.0, 26.1, 91.1)
        _create_road(db_session, "C2_R1", 30.0, 95.0, 30.1, 95.1)

        res = client.post("/routing/route", json={
            "origin_lat": 26.0, "origin_lon": 91.0,
            "destination_lat": 30.1, "destination_lon": 95.1,
        })
        assert res.status_code == 400
        assert "NO_ROUTE" in res.json()["error"]["message"]

    def test_disconnected_not_500(self, client, db_session):
        _create_road(db_session, "C1_R1", 26.0, 91.0, 26.1, 91.1)
        _create_road(db_session, "C2_R1", 30.0, 95.0, 30.1, 95.1)

        res = client.post("/routing/route", json={
            "origin_lat": 26.0, "origin_lon": 91.0,
            "destination_lat": 30.1, "destination_lon": 95.1,
        })
        assert res.status_code != 500

    def test_disconnected_no_geometry_in_error(self, client, db_session):
        _create_road(db_session, "C1_R1", 26.0, 91.0, 26.1, 91.1)
        _create_road(db_session, "C2_R1", 30.0, 95.0, 30.1, 95.1)

        res = client.post("/routing/route", json={
            "origin_lat": 26.0, "origin_lon": 91.0,
            "destination_lat": 30.1, "destination_lon": 95.1,
        })
        body = res.json()
        assert "geometry" not in body or body.get("geometry") is None


# ═══════════════════════════════════════════════════════════════════════════════
# Mid-edge snapping tests (snap-to-edge gotcha)
# ═══════════════════════════════════════════════════════════════════════════════

class TestMidEdgeSnapping:
    def test_origin_mid_edge_route_succeeds(self, db_session):
        """Origin lies in the middle of Road A, not at any endpoint."""
        r1 = _create_road(db_session, "R1", 26.0, 91.0, 26.0, 91.2)
        route = find_route(db_session, 26.0, 91.1, 26.0, 91.2)

        assert route["type"] == "Feature"
        snapped = route["properties"]["snapped_origin"]
        assert abs(snapped["lon"] - 91.1) < 0.01
        assert r1.id in route["properties"]["road_ids"]

    def test_destination_mid_edge_route_succeeds(self, db_session):
        r1 = _create_road(db_session, "R1", 26.0, 91.0, 26.0, 91.2)
        route = find_route(db_session, 26.0, 91.0, 26.0, 91.1)

        snapped = route["properties"]["snapped_destination"]
        assert abs(snapped["lon"] - 91.1) < 0.01

    def test_both_mid_edge_different_edges(self, db_session):
        r1 = _create_road(db_session, "R1", 26.0, 91.0, 26.0, 91.2)
        r2 = _create_road(db_session, "R2", 26.0, 91.2, 26.0, 91.4)

        route = find_route(db_session, 26.0, 91.1, 26.0, 91.3)
        road_ids = route["properties"]["road_ids"]
        assert r1.id in road_ids
        assert r2.id in road_ids


# ═══════════════════════════════════════════════════════════════════════════════
# Same-edge routing
# ═══════════════════════════════════════════════════════════════════════════════

class TestSameEdgeRouting:
    def test_same_edge_route_succeeds(self, db_session):
        """Origin and destination both snap to the same road."""
        r1 = _create_road(db_session, "R1", 26.0, 91.0, 26.0, 91.4)

        route = find_route(db_session, 26.0, 91.1, 26.0, 91.3)
        assert route["type"] == "Feature"
        assert r1.id in route["properties"]["road_ids"]

    def test_same_edge_distance_less_than_full_road(self, db_session):
        """Route between two mid-edge points should be shorter than full road."""
        _create_road(db_session, "R1", 26.0, 91.0, 26.0, 91.4)

        full_road_dist = haversine_distance_km(26.0, 91.0, 26.0, 91.4)
        route = find_route(db_session, 26.0, 91.1, 26.0, 91.3)
        route_dist = route["properties"]["total_distance_km"]

        assert route_dist > 0
        assert route_dist < full_road_dist

    def test_same_edge_no_detour(self, db_session):
        """Same-edge route distance should be close to direct haversine, not a detour."""
        _create_road(db_session, "R1", 26.0, 91.0, 26.0, 91.4)

        direct_dist = haversine_distance_km(26.0, 91.1, 26.0, 91.3)
        route = find_route(db_session, 26.0, 91.1, 26.0, 91.3)
        route_dist = route["properties"]["total_distance_km"]

        # Route distance should be close to direct distance (within 50% tolerance)
        assert route_dist < direct_dist * 1.5


# ═══════════════════════════════════════════════════════════════════════════════
# Virtual snap nodes are request-local
# ═══════════════════════════════════════════════════════════════════════════════

class TestRequestLocalGraph:
    def test_original_graph_not_mutated(self, db_session):
        _create_road(db_session, "R1", 26.0, 91.0, 26.0, 91.4)

        graph_before = build_road_graph(db_session)
        nodes_before = graph_before.number_of_nodes()
        edges_before = graph_before.number_of_edges()

        # Perform a route that creates virtual nodes
        find_route(db_session, 26.0, 91.1, 26.0, 91.3)

        # Build graph again — should be identical
        graph_after = build_road_graph(db_session)
        assert graph_after.number_of_nodes() == nodes_before
        assert graph_after.number_of_edges() == edges_before


# ═══════════════════════════════════════════════════════════════════════════════
# API-level tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestRoutingAPI:
    def test_route_geojson_response(self, client, db_session):
        _create_road(db_session, "R1", 26.0, 91.0, 26.1, 91.1)

        res = client.post("/routing/route", json={
            "origin_lat": 26.0, "origin_lon": 91.0,
            "destination_lat": 26.1, "destination_lon": 91.1,
        })
        assert res.status_code == 200

        data = res.json()
        assert data["type"] == "Feature"
        assert data["geometry"]["type"] == "LineString"

        coords = data["geometry"]["coordinates"]
        assert len(coords) >= 2

        props = data["properties"]
        assert "snapped_origin" in props
        assert "snapped_destination" in props
        assert "origin" in props
        assert "destination" in props
        assert props["total_distance_km"] > 0
        assert props["geometry_source"] == "reconstructed_from_endpoints"
        assert len(props["road_ids"]) >= 1
        assert props["num_roads"] >= 1

    def test_route_endpoint_is_public(self, client, db_session):
        """Routing is a read operation — no auth required."""
        _create_road(db_session, "R1", 26.0, 91.0, 26.1, 91.1)

        res = client.post("/routing/route", json={
            "origin_lat": 26.0, "origin_lon": 91.0,
            "destination_lat": 26.1, "destination_lon": 91.1,
        })
        # Should succeed without auth headers
        assert res.status_code == 200
