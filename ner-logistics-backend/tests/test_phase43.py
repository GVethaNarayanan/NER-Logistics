"""
Phase 4.3 — Routing Service (OSM Geometry-Aware) Tests

Tests the new vertex-sharing topology, PostGIS snapping, and graph-based routing.
Uses mocking to bypass SQLite's lack of PostGIS support in unit tests.
"""
import pytest
from unittest.mock import MagicMock, patch
import networkx as nx

from app.services.graph_service import (
    build_road_graph,
    get_road_coordinates,
    invalidate_graph_cache,
    _extract_topology_from_db,
)
from app.services.routing_service import (
    find_route,
    snap_to_nearest_edge,
    RoutingError,
    _ORIGIN_NODE,
    _DEST_NODE,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear graph cache before each test."""
    invalidate_graph_cache()
    yield


# ── Mocks ──────────────────────────────────────────────────────────────

class MockRow:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def mock_db_execute_topology(rows):
    """Mock db.execute to return specific road rows for topology extraction."""
    mock_db = MagicMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = rows
    mock_db.execute.return_value = mock_result
    return mock_db


# ── Tests: Graph Construction ──────────────────────────────────────────

class TestGraphConstruction:
    def test_build_graph_from_linestring(self):
        rows = [
            MockRow(road_id=1, road_type="residential", osm_tags={"oneway": "no"}, 
                    length_m=100.0, n_vertices=2, wkt="LINESTRING(91.0 26.0, 91.1 26.1)")
        ]
        db = mock_db_execute_topology(rows)
        graph, _ = _extract_topology_from_db(db)
        
        assert graph.number_of_nodes() == 2
        # Bidirectional by default = 2 edges
        assert graph.number_of_edges() == 2
        
        # Check coordinates stored on edge
        edge_data = graph.get_edge_data((26.0, 91.0), (26.1, 91.1))
        assert edge_data["road_id"] == 1
        assert edge_data["coordinates"] == [(91.0, 26.0), (91.1, 26.1)]

    def test_multi_vertex_road_preserved(self):
        rows = [
            MockRow(road_id=1, road_type="residential", osm_tags={"oneway": "no"}, 
                    length_m=100.0, n_vertices=4, wkt="LINESTRING(91.0 26.0, 91.05 26.05, 91.08 26.08, 91.1 26.1)")
        ]
        db = mock_db_execute_topology(rows)
        graph, _ = _extract_topology_from_db(db)
        
        # Should only have 2 nodes (endpoints) because there are no intersections
        assert graph.number_of_nodes() == 2
        assert graph.number_of_edges() == 2
        
        # But edge should contain all 4 vertices for geometry reconstruction
        edge_data = graph.get_edge_data((26.0, 91.0), (26.1, 91.1))
        assert len(edge_data["coordinates"]) == 4

    def test_shared_intersection_connected(self):
        rows = [
            MockRow(road_id=1, road_type="residential", osm_tags={"oneway": "no"}, 
                    length_m=100.0, n_vertices=2, wkt="LINESTRING(91.0 26.0, 91.1 26.1)"),
            MockRow(road_id=2, road_type="residential", osm_tags={"oneway": "no"}, 
                    length_m=100.0, n_vertices=2, wkt="LINESTRING(91.1 26.1, 91.2 26.2)")
        ]
        db = mock_db_execute_topology(rows)
        graph, _ = _extract_topology_from_db(db)
        
        assert graph.number_of_nodes() == 3
        assert graph.number_of_edges() == 4  # 2 bidirectional roads
        assert nx.number_weakly_connected_components(graph) == 1

    def test_oneway_direction_forward(self):
        rows = [
            MockRow(road_id=1, road_type="residential", osm_tags={"oneway": "yes"}, 
                    length_m=100.0, n_vertices=2, wkt="LINESTRING(91.0 26.0, 91.1 26.1)")
        ]
        db = mock_db_execute_topology(rows)
        graph, _ = _extract_topology_from_db(db)
        
        assert graph.number_of_nodes() == 2
        assert graph.number_of_edges() == 1
        assert graph.has_edge((26.0, 91.0), (26.1, 91.1))
        assert not graph.has_edge((26.1, 91.1), (26.0, 91.0))


# ── Tests: Routing (Mocked Snap & Graph) ───────────────────────────────

class TestRouting:
    @patch("app.services.routing_service.build_road_graph")
    @patch("app.services.routing_service.snap_to_nearest_edge")
    def test_shortest_route_works(self, mock_snap, mock_build):
        # Create a mock graph
        graph = nx.DiGraph()
        graph.add_edge((26.0, 91.0), (26.0, 91.1), road_id=1, distance_km=1.0, coordinates=[(91.0, 26.0), (91.1, 26.0)])
        graph.add_edge((26.0, 91.1), (26.0, 91.2), road_id=2, distance_km=1.0, coordinates=[(91.1, 26.0), (91.2, 26.0)])
        mock_build.return_value = graph
        
        from app.services.routing_service import SnapResult
        
        mock_snap.side_effect = [
            SnapResult(edge=((26.0, 91.0), (26.0, 91.1)), snapped_lat=26.0, snapped_lon=91.0, 
                       t=0.0, distance_km=0.0, edge_data={"distance_km": 1.0, "road_id": 1}, road_id=1),
            SnapResult(edge=((26.0, 91.1), (26.0, 91.2)), snapped_lat=26.0, snapped_lon=91.2, 
                       t=1.0, distance_km=0.0, edge_data={"distance_km": 1.0, "road_id": 2}, road_id=2)
        ]
        
        route = find_route(MagicMock(), 26.0, 91.0, 26.0, 91.2, preference="shortest")
        
        assert route["type"] == "Feature"
        assert route["geometry"]["type"] == "LineString"
        assert len(route["geometry"]["coordinates"]) >= 3
        
        # Verify virtual nodes were cleaned up
        assert _ORIGIN_NODE not in graph
        assert _DEST_NODE not in graph

    @patch("app.services.routing_service.build_road_graph")
    @patch("app.services.routing_service.snap_to_nearest_edge")
    def test_no_path_returns_error(self, mock_snap, mock_build):
        graph = nx.DiGraph()
        graph.add_node((26.0, 91.0))
        graph.add_node((27.0, 92.0))
        # Add a dummy edge so graph.number_of_edges() > 0 and we don't get ROUTING_DATA_UNAVAILABLE
        graph.add_edge((0.0, 0.0), (0.1, 0.1), distance_km=1.0)
        mock_build.return_value = graph
        
        from app.services.routing_service import SnapResult
        mock_snap.side_effect = [
            SnapResult(edge=((26.0, 91.0), (26.0, 91.0)), snapped_lat=26.0, snapped_lon=91.0, 
                       t=0.0, distance_km=0.0, edge_data={"distance_km": 1.0}, road_id=1),
            SnapResult(edge=((27.0, 92.0), (27.0, 92.0)), snapped_lat=27.0, snapped_lon=92.0, 
                       t=0.0, distance_km=0.0, edge_data={"distance_km": 1.0}, road_id=2)
        ]
        
        with pytest.raises(RoutingError) as exc:
            find_route(MagicMock(), 26.0, 91.0, 27.0, 92.0, preference="shortest")
        
        assert exc.value.code == "NO_ROUTE"
