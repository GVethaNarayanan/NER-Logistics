"""
Phase 7.1 — Comprehensive Vehicle/GPS Tracking Tests

Covers ALL 23 required scenarios identified in the Phase 7 audit,
plus the simulator enable/disable config fix.
"""
import pytest
from unittest.mock import patch
from tests.conftest import get_auth_header
from app import models
from app.services.simulation_job import run_vehicle_simulation, SIMULATION_INTERVAL_SECONDS
from app.services.vehicle_service import haversine_distance_km


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _create_road(db, name, start_lat, start_lon, end_lat, end_lon, district="Test"):
    """Insert a Road directly via ORM for deterministic test setup."""
    road = models.Road(
        name=name, road_type="highway",
        start_lat=start_lat, start_lon=start_lon,
        end_lat=end_lat, end_lon=end_lon,
        district=district,
    )
    db.add(road)
    db.commit()
    db.refresh(road)
    return road


def _create_route_with_roads(db, name, roads_coords):
    """
    Create a Route and attach roads in order.
    roads_coords: list of (start_lat, start_lon, end_lat, end_lon)
    Returns (route, [roads])
    """
    route = models.Route(name=name)
    db.add(route)
    db.commit()
    db.refresh(route)

    roads = []
    for i, (slat, slon, elat, elon) in enumerate(roads_coords):
        road = _create_road(db, f"{name}_road_{i}", slat, slon, elat, elon)
        rr = models.RouteRoad(route_id=route.id, road_id=road.id, sequence=i + 1)
        db.add(rr)
        roads.append(road)
    db.commit()
    return route, roads


def _create_vehicle(db, number, lat, lon, speed_kmh, status="in_transit",
                    route_id=None, seq=0, progress=0.0):
    """Insert a Vehicle directly via ORM."""
    veh = models.Vehicle(
        vehicle_number=number,
        current_lat=lat, current_lon=lon,
        speed_kmh=speed_kmh, status=status,
        current_route_id=route_id,
        current_route_sequence=seq,
        current_route_progress_km=progress,
    )
    db.add(veh)
    db.commit()
    db.refresh(veh)
    return veh


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Route creation
# ═══════════════════════════════════════════════════════════════════════════════

class TestRouteCreation:
    def test_create_route_success(self, client, db_session, admin_user):
        auth = get_auth_header(client, "testadmin", "adminpass123")
        res = client.post("/routes/", json={"name": "Route Alpha"}, headers=auth)
        assert res.status_code == 201
        data = res.json()
        assert data["name"] == "Route Alpha"
        assert "id" in data
        assert "created_at" in data


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Ordered RouteRoad assignment
# ═══════════════════════════════════════════════════════════════════════════════

class TestRouteRoadAssignment:
    def test_add_roads_in_order(self, client, db_session, admin_user):
        auth = get_auth_header(client, "testadmin", "adminpass123")
        route = models.Route(name="Ordered")
        db_session.add(route)
        db_session.commit()
        db_session.refresh(route)

        road1 = _create_road(db_session, "R1", 26.0, 91.0, 26.01, 91.01)
        road2 = _create_road(db_session, "R2", 26.01, 91.01, 26.02, 91.02)

        res1 = client.post(f"/routes/{route.id}/roads",
                           json={"road_id": road1.id, "sequence": 1}, headers=auth)
        assert res1.status_code == 201
        assert res1.json()["sequence"] == 1

        res2 = client.post(f"/routes/{route.id}/roads",
                           json={"road_id": road2.id, "sequence": 2}, headers=auth)
        assert res2.status_code == 201
        assert res2.json()["sequence"] == 2


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Duplicate / non-increasing sequence rejection
# ═══════════════════════════════════════════════════════════════════════════════

class TestSequenceRejection:
    def test_duplicate_sequence_rejected(self, client, db_session, admin_user):
        auth = get_auth_header(client, "testadmin", "adminpass123")
        route = models.Route(name="DupSeq")
        db_session.add(route)
        db_session.commit()
        db_session.refresh(route)

        road1 = _create_road(db_session, "DS1", 26.0, 91.0, 26.01, 91.01)
        road2 = _create_road(db_session, "DS2", 26.01, 91.01, 26.02, 91.02)

        client.post(f"/routes/{route.id}/roads",
                    json={"road_id": road1.id, "sequence": 1}, headers=auth)

        # Same sequence → rejected
        res = client.post(f"/routes/{route.id}/roads",
                          json={"road_id": road2.id, "sequence": 1}, headers=auth)
        assert res.status_code == 400
        assert "Sequence must be strictly increasing" in res.json()["error"]["message"]

    def test_decreasing_sequence_rejected(self, client, db_session, admin_user):
        auth = get_auth_header(client, "testadmin", "adminpass123")
        route = models.Route(name="DecSeq")
        db_session.add(route)
        db_session.commit()
        db_session.refresh(route)

        road1 = _create_road(db_session, "DC1", 26.0, 91.0, 26.01, 91.01)
        road2 = _create_road(db_session, "DC2", 26.01, 91.01, 26.02, 91.02)

        client.post(f"/routes/{route.id}/roads",
                    json={"road_id": road1.id, "sequence": 5}, headers=auth)

        res = client.post(f"/routes/{route.id}/roads",
                          json={"road_id": road2.id, "sequence": 3}, headers=auth)
        assert res.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Invalid / missing road ID rejection
# ═══════════════════════════════════════════════════════════════════════════════

class TestInvalidRoadRejection:
    def test_nonexistent_road_id(self, client, db_session, admin_user):
        auth = get_auth_header(client, "testadmin", "adminpass123")
        route = models.Route(name="BadRoad")
        db_session.add(route)
        db_session.commit()
        db_session.refresh(route)

        res = client.post(f"/routes/{route.id}/roads",
                          json={"road_id": 99999, "sequence": 1}, headers=auth)
        assert res.status_code == 404
        assert "Road not found" in res.json()["error"]["message"]

    def test_nonexistent_route_id(self, client, db_session, admin_user):
        auth = get_auth_header(client, "testadmin", "adminpass123")
        road = _create_road(db_session, "Orphan", 26.0, 91.0, 26.01, 91.01)

        res = client.post("/routes/99999/roads",
                          json={"road_id": road.id, "sequence": 1}, headers=auth)
        assert res.status_code == 404
        assert "Route not found" in res.json()["error"]["message"]


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Vehicle route assignment
# ═══════════════════════════════════════════════════════════════════════════════

class TestVehicleRouteAssignment:
    def test_assign_route_success(self, client, db_session, admin_user):
        auth = get_auth_header(client, "testadmin", "adminpass123")
        route, roads = _create_route_with_roads(db_session, "AR", [
            (26.0, 91.0, 26.01, 91.01),
        ])
        veh = _create_vehicle(db_session, "VRA-01", 26.0, 91.0, 60)

        res = client.patch(f"/vehicles/{veh.id}/route?route_id={route.id}", headers=auth)
        assert res.status_code == 200
        data = res.json()
        assert data["current_route_id"] == route.id
        assert data["current_route_sequence"] == 0
        assert data["current_route_progress_km"] == 0.0

    def test_assign_nonexistent_route(self, client, db_session, admin_user):
        auth = get_auth_header(client, "testadmin", "adminpass123")
        veh = _create_vehicle(db_session, "VRA-02", 26.0, 91.0, 60)
        res = client.patch(f"/vehicles/{veh.id}/route?route_id=99999", headers=auth)
        assert res.status_code == 404

    def test_assign_route_nonexistent_vehicle(self, client, db_session, admin_user):
        auth = get_auth_header(client, "testadmin", "adminpass123")
        route, _ = _create_route_with_roads(db_session, "ARN", [
            (26.0, 91.0, 26.01, 91.01),
        ])
        res = client.patch(f"/vehicles/99999/route?route_id={route.id}", headers=auth)
        assert res.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Empty route handling
# ═══════════════════════════════════════════════════════════════════════════════

class TestEmptyRoute:
    def test_vehicle_on_empty_route_does_not_move(self, db_session):
        """A vehicle assigned to a route with 0 roads should not move."""
        route = models.Route(name="EmptyRoute")
        db_session.add(route)
        db_session.commit()
        db_session.refresh(route)

        veh = _create_vehicle(db_session, "EMPTY-01", 10.0, 10.0, 60,
                              route_id=route.id, seq=0, progress=0.0)
        original_lat, original_lon = veh.current_lat, veh.current_lon

        run_vehicle_simulation(db_session)
        db_session.refresh(veh)

        assert veh.current_lat == original_lat
        assert veh.current_lon == original_lon
        history = db_session.query(models.VehicleLocationHistory)\
            .filter_by(vehicle_id=veh.id).all()
        assert len(history) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Disconnected-road rejection
# ═══════════════════════════════════════════════════════════════════════════════

class TestDisconnectedRoadRejection:
    def test_roads_too_far_apart(self, client, db_session, admin_user):
        auth = get_auth_header(client, "testadmin", "adminpass123")
        route = models.Route(name="Disconnected")
        db_session.add(route)
        db_session.commit()
        db_session.refresh(route)

        road1 = _create_road(db_session, "Far1", 26.0, 91.0, 26.01, 91.01)
        road2 = _create_road(db_session, "Far2", 30.0, 95.0, 30.01, 95.01)  # >5km away

        client.post(f"/routes/{route.id}/roads",
                    json={"road_id": road1.id, "sequence": 1}, headers=auth)

        res = client.post(f"/routes/{route.id}/roads",
                          json={"road_id": road2.id, "sequence": 2}, headers=auth)
        assert res.status_code == 400
        assert "Disconnected route" in res.json()["error"]["message"]

    def test_connected_roads_accepted(self, client, db_session, admin_user):
        """Roads within 5km tolerance are accepted."""
        auth = get_auth_header(client, "testadmin", "adminpass123")
        route = models.Route(name="Connected")
        db_session.add(route)
        db_session.commit()
        db_session.refresh(route)

        road1 = _create_road(db_session, "Close1", 26.0, 91.0, 26.01, 91.01)
        road2 = _create_road(db_session, "Close2", 26.01, 91.01, 26.02, 91.02)

        client.post(f"/routes/{route.id}/roads",
                    json={"road_id": road1.id, "sequence": 1}, headers=auth)

        res = client.post(f"/routes/{route.id}/roads",
                          json={"road_id": road2.id, "sequence": 2}, headers=auth)
        assert res.status_code == 201


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Active in_transit vehicle movement
# ═══════════════════════════════════════════════════════════════════════════════

class TestActiveVehicleMovement:
    def test_in_transit_vehicle_moves(self, db_session):
        """An in_transit vehicle with route and speed >0 should move after a sim tick."""
        route, roads = _create_route_with_roads(db_session, "Move", [
            (26.0, 91.0, 26.1, 91.1),  # ~15.7km road
        ])
        veh = _create_vehicle(db_session, "MOV-01", 26.0, 91.0, 60,
                              route_id=route.id, seq=0, progress=0.0)

        run_vehicle_simulation(db_session)
        db_session.refresh(veh)

        # Vehicle must have moved from origin
        assert not (veh.current_lat == 26.0 and veh.current_lon == 91.0)


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Different speeds produce different movement distances
# ═══════════════════════════════════════════════════════════════════════════════

class TestSpeedEffect:
    def test_faster_vehicle_moves_farther(self, db_session):
        """Two vehicles on identical routes, the faster one should advance more."""
        # Create two identical routes
        route_slow, roads_slow = _create_route_with_roads(db_session, "Slow", [
            (26.0, 91.0, 26.2, 91.2),  # ~31km road
        ])
        route_fast, roads_fast = _create_route_with_roads(db_session, "Fast", [
            (26.0, 91.0, 26.2, 91.2),
        ])

        veh_slow = _create_vehicle(db_session, "SLOW-01", 26.0, 91.0, 30,
                                   route_id=route_slow.id, seq=0, progress=0.0)
        veh_fast = _create_vehicle(db_session, "FAST-01", 26.0, 91.0, 120,
                                   route_id=route_fast.id, seq=0, progress=0.0)

        run_vehicle_simulation(db_session)
        db_session.refresh(veh_slow)
        db_session.refresh(veh_fast)

        assert veh_fast.current_route_progress_km > veh_slow.current_route_progress_km

        # Verify the formula: distance = speed * (10/3600)
        expected_slow = 30 * (SIMULATION_INTERVAL_SECONDS / 3600.0)
        expected_fast = 120 * (SIMULATION_INTERVAL_SECONDS / 3600.0)
        assert abs(veh_slow.current_route_progress_km - expected_slow) < 0.001
        assert abs(veh_fast.current_route_progress_km - expected_fast) < 0.001


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Progressive movement actually changes location
# ═══════════════════════════════════════════════════════════════════════════════

class TestProgressiveMovement:
    def test_location_changes_each_tick(self, db_session):
        route, _ = _create_route_with_roads(db_session, "Prog", [
            (26.0, 91.0, 26.5, 91.5),  # long road
        ])
        veh = _create_vehicle(db_session, "PROG-01", 26.0, 91.0, 60,
                              route_id=route.id, seq=0, progress=0.0)

        run_vehicle_simulation(db_session)
        db_session.refresh(veh)
        lat_after_1 = veh.current_lat
        lon_after_1 = veh.current_lon
        progress_1 = veh.current_route_progress_km

        run_vehicle_simulation(db_session)
        db_session.refresh(veh)
        lat_after_2 = veh.current_lat
        lon_after_2 = veh.current_lon
        progress_2 = veh.current_route_progress_km

        # Second tick moves farther
        assert progress_2 > progress_1
        assert (lat_after_2, lon_after_2) != (lat_after_1, lon_after_1)


# ═══════════════════════════════════════════════════════════════════════════════
# 11. Sequence 1 → sequence 2 progression
# ═══════════════════════════════════════════════════════════════════════════════

class TestSequenceProgression:
    def test_crosses_road_boundary(self, db_session):
        """Use a very short first road so one tick at high speed crosses it."""
        # First road: ~0.001km (effectively a point near 0.01 deg difference)
        # At 360 km/h, one tick = 1km, which will easily exceed the short road
        route, roads = _create_route_with_roads(db_session, "SeqProg", [
            (26.0, 91.0, 26.00001, 91.00001),   # ~1.5m road
            (26.00001, 91.00001, 26.1, 91.1),    # ~15.7km road
        ])
        veh = _create_vehicle(db_session, "SEQ-01", 26.0, 91.0, 360,
                              route_id=route.id, seq=0, progress=0.0)

        run_vehicle_simulation(db_session)
        db_session.refresh(veh)

        # Must have advanced past sequence 0 (the tiny road)
        assert veh.current_route_sequence >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# 12. Final route completion: in_transit → delivered
# ═══════════════════════════════════════════════════════════════════════════════

class TestRouteCompletion:
    def test_vehicle_becomes_delivered(self, db_session):
        """A vehicle that finishes its last road should be set to 'delivered'."""
        # Very short single-road route, high speed → finishes in one tick
        route, roads = _create_route_with_roads(db_session, "Finish", [
            (26.0, 91.0, 26.00001, 91.00001),  # ~1.5m road
        ])
        veh = _create_vehicle(db_session, "FIN-01", 26.0, 91.0, 360,
                              route_id=route.id, seq=0, progress=0.0)

        run_vehicle_simulation(db_session)
        db_session.refresh(veh)

        assert veh.status == "delivered"
        # Snapped to end of road
        assert abs(veh.current_lat - 26.00001) < 0.0001
        assert abs(veh.current_lon - 91.00001) < 0.0001


# ═══════════════════════════════════════════════════════════════════════════════
# 13. Delivered vehicle does not move on later ticks
# ═══════════════════════════════════════════════════════════════════════════════

class TestDeliveredNoMovement:
    def test_delivered_vehicle_stays_put(self, db_session):
        route, _ = _create_route_with_roads(db_session, "Done", [
            (26.0, 91.0, 26.00001, 91.00001),
        ])
        veh = _create_vehicle(db_session, "DONE-01", 26.0, 91.0, 360,
                              route_id=route.id, seq=0, progress=0.0)

        # First tick → delivered
        run_vehicle_simulation(db_session)
        db_session.refresh(veh)
        assert veh.status == "delivered"
        history_count_1 = db_session.query(models.VehicleLocationHistory)\
            .filter_by(vehicle_id=veh.id).count()

        lat_delivered = veh.current_lat
        lon_delivered = veh.current_lon

        # Second tick → should not add more history
        run_vehicle_simulation(db_session)
        db_session.refresh(veh)
        history_count_2 = db_session.query(models.VehicleLocationHistory)\
            .filter_by(vehicle_id=veh.id).count()

        assert veh.status == "delivered"
        assert veh.current_lat == lat_delivered
        assert veh.current_lon == lon_delivered
        assert history_count_2 == history_count_1


# ═══════════════════════════════════════════════════════════════════════════════
# 14. Idle/inactive vehicle does not move
# ═══════════════════════════════════════════════════════════════════════════════

class TestIdleVehicleNoMovement:
    def test_idle_vehicle_not_simulated(self, db_session):
        route, _ = _create_route_with_roads(db_session, "Idle", [
            (26.0, 91.0, 26.1, 91.1),
        ])
        veh = _create_vehicle(db_session, "IDLE-01", 26.0, 91.0, 60,
                              status="idle", route_id=route.id, seq=0, progress=0.0)

        run_vehicle_simulation(db_session)
        db_session.refresh(veh)

        assert veh.current_lat == 26.0
        assert veh.current_lon == 91.0
        history = db_session.query(models.VehicleLocationHistory)\
            .filter_by(vehicle_id=veh.id).all()
        assert len(history) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 15. in_transit vehicle without assigned route does not move
# ═══════════════════════════════════════════════════════════════════════════════

class TestNoRouteNoMovement:
    def test_in_transit_without_route(self, db_session):
        veh = _create_vehicle(db_session, "NORTE-01", 26.0, 91.0, 60,
                              route_id=None)

        run_vehicle_simulation(db_session)
        db_session.refresh(veh)

        assert veh.current_lat == 26.0
        assert veh.current_lon == 91.0
        history = db_session.query(models.VehicleLocationHistory)\
            .filter_by(vehicle_id=veh.id).all()
        assert len(history) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 16. current_route_sequence persists after simulation
# ═══════════════════════════════════════════════════════════════════════════════

class TestPersistentSequence:
    def test_sequence_persisted(self, db_session):
        route, _ = _create_route_with_roads(db_session, "PSeq", [
            (26.0, 91.0, 26.1, 91.1),
        ])
        veh = _create_vehicle(db_session, "PSEQ-01", 26.0, 91.0, 60,
                              route_id=route.id, seq=0, progress=0.0)

        run_vehicle_simulation(db_session)
        db_session.refresh(veh)

        # Since the road is ~15.7km and speed is 60km/h, one 10s tick moves
        # 60*(10/3600) = 0.1667km.  That's well within the road, so seq stays 0.
        assert veh.current_route_sequence == 0

        # Re-query from DB to prove persistence
        veh_reloaded = db_session.query(models.Vehicle).filter_by(id=veh.id).first()
        assert veh_reloaded.current_route_sequence == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 17. current_route_progress_km persists after simulation
# ═══════════════════════════════════════════════════════════════════════════════

class TestPersistentProgress:
    def test_progress_km_persisted(self, db_session):
        route, _ = _create_route_with_roads(db_session, "PProg", [
            (26.0, 91.0, 26.5, 91.5),  # long road
        ])
        veh = _create_vehicle(db_session, "PPROG-01", 26.0, 91.0, 60,
                              route_id=route.id, seq=0, progress=0.0)

        run_vehicle_simulation(db_session)
        db_session.refresh(veh)

        expected = 60 * (SIMULATION_INTERVAL_SECONDS / 3600.0)
        assert abs(veh.current_route_progress_km - expected) < 0.001

        veh_reloaded = db_session.query(models.Vehicle).filter_by(id=veh.id).first()
        assert abs(veh_reloaded.current_route_progress_km - expected) < 0.001


# ═══════════════════════════════════════════════════════════════════════════════
# 18. Vehicle current_lat/lon equals latest history record
# ═══════════════════════════════════════════════════════════════════════════════

class TestLocationConsistency:
    def test_vehicle_location_matches_history(self, db_session):
        route, _ = _create_route_with_roads(db_session, "Cons", [
            (26.0, 91.0, 26.5, 91.5),
        ])
        veh = _create_vehicle(db_session, "CONS-01", 26.0, 91.0, 60,
                              route_id=route.id, seq=0, progress=0.0)

        run_vehicle_simulation(db_session)
        db_session.refresh(veh)

        latest = db_session.query(models.VehicleLocationHistory)\
            .filter_by(vehicle_id=veh.id)\
            .order_by(models.VehicleLocationHistory.timestamp.desc())\
            .first()

        assert latest is not None
        assert veh.current_lat == latest.latitude
        assert veh.current_lon == latest.longitude

    def test_consistency_after_multiple_ticks(self, db_session):
        route, _ = _create_route_with_roads(db_session, "MultiCons", [
            (26.0, 91.0, 26.5, 91.5),
        ])
        veh = _create_vehicle(db_session, "MCONS-01", 26.0, 91.0, 60,
                              route_id=route.id, seq=0, progress=0.0)

        for _ in range(3):
            run_vehicle_simulation(db_session)

        db_session.expire_all()
        db_session.refresh(veh)
        latest = db_session.query(models.VehicleLocationHistory)\
            .filter_by(vehicle_id=veh.id)\
            .order_by(models.VehicleLocationHistory.id.desc())\
            .first()

        assert veh.current_lat == latest.latitude
        assert veh.current_lon == latest.longitude


# ═══════════════════════════════════════════════════════════════════════════════
# 19. EVERY simulated history record has data_source="simulated"
# ═══════════════════════════════════════════════════════════════════════════════

class TestDataSourceSimulated:
    def test_all_history_records_simulated(self, db_session):
        route, _ = _create_route_with_roads(db_session, "DSrc", [
            (26.0, 91.0, 26.5, 91.5),
        ])
        veh = _create_vehicle(db_session, "DSRC-01", 26.0, 91.0, 60,
                              route_id=route.id, seq=0, progress=0.0)

        for _ in range(5):
            run_vehicle_simulation(db_session)

        records = db_session.query(models.VehicleLocationHistory)\
            .filter_by(vehicle_id=veh.id).all()

        assert len(records) == 5
        for rec in records:
            assert rec.data_source == "simulated"


# ═══════════════════════════════════════════════════════════════════════════════
# 20. History endpoint returns chronological records
# ═══════════════════════════════════════════════════════════════════════════════

class TestHistoryChronological:
    def test_history_ordered_by_timestamp(self, client, db_session, admin_user):
        route, _ = _create_route_with_roads(db_session, "Chron", [
            (26.0, 91.0, 26.5, 91.5),
        ])
        veh = _create_vehicle(db_session, "CHRON-01", 26.0, 91.0, 60,
                              route_id=route.id, seq=0, progress=0.0)

        for _ in range(3):
            run_vehicle_simulation(db_session)

        res = client.get(f"/vehicles/{veh.id}/history")
        assert res.status_code == 200
        items = res.json()["items"]
        assert len(items) == 3
        # Verify chronological ordering
        timestamps = [item["timestamp"] for item in items]
        assert timestamps == sorted(timestamps)


# ═══════════════════════════════════════════════════════════════════════════════
# 21. History endpoint 404 for nonexistent vehicle
# ═══════════════════════════════════════════════════════════════════════════════

class TestHistory404:
    def test_nonexistent_vehicle_history(self, client, db_session):
        res = client.get("/vehicles/99999/history")
        assert res.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# 22. Authentication/authorization on protected endpoints
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuthOnRouteEndpoints:
    def test_create_route_requires_auth(self, client, db_session):
        res = client.post("/routes/", json={"name": "NoAuth"})
        assert res.status_code in (401, 403)

    def test_create_route_requires_admin(self, client, db_session, field_user):
        auth = get_auth_header(client, "testfield", "fieldpass123")
        res = client.post("/routes/", json={"name": "FieldAttempt"}, headers=auth)
        assert res.status_code == 403

    def test_add_road_to_route_requires_auth(self, client, db_session):
        res = client.post("/routes/1/roads", json={"road_id": 1, "sequence": 1})
        assert res.status_code in (401, 403)

    def test_assign_route_requires_auth(self, client, db_session):
        res = client.patch("/vehicles/1/route?route_id=1")
        assert res.status_code in (401, 403)

    def test_assign_route_requires_admin(self, client, db_session, field_user):
        auth = get_auth_header(client, "testfield", "fieldpass123")
        res = client.patch("/vehicles/1/route?route_id=1", headers=auth)
        assert res.status_code == 403

    def test_vehicle_history_is_public(self, client, db_session):
        """History endpoint should be accessible without auth (just 404 for missing)."""
        res = client.get("/vehicles/99999/history")
        # 404, not 401/403
        assert res.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# 23. Simulator scheduler startup/shutdown lifecycle
# ═══════════════════════════════════════════════════════════════════════════════

class TestSchedulerLifecycle:
    def test_simulation_job_registered_when_enabled(self):
        """When vehicle_simulation_enabled=True, the sim job should be registered."""
        from app.services.weather_job import scheduler, start_scheduler, shutdown_scheduler

        with patch("app.services.weather_job.settings") as mock_settings:
            mock_settings.vehicle_simulation_enabled = True
            # Make sure scheduler is fresh
            if scheduler.running:
                scheduler.shutdown()

            start_scheduler()
            try:
                job = scheduler.get_job("vehicle_simulation_job")
                assert job is not None
            finally:
                shutdown_scheduler()

    def test_simulation_job_not_registered_when_disabled(self):
        """When vehicle_simulation_enabled=False, the sim job must NOT be registered."""
        from app.services.weather_job import scheduler, start_scheduler, shutdown_scheduler

        with patch("app.services.weather_job.settings") as mock_settings:
            mock_settings.vehicle_simulation_enabled = False
            if scheduler.running:
                scheduler.shutdown()

            start_scheduler()
            try:
                job = scheduler.get_job("vehicle_simulation_job")
                assert job is None
            finally:
                shutdown_scheduler()

    def test_shutdown_stops_scheduler(self):
        """After shutdown, scheduler should not be running."""
        from app.services.weather_job import scheduler, start_scheduler, shutdown_scheduler

        with patch("app.services.weather_job.settings") as mock_settings:
            mock_settings.vehicle_simulation_enabled = True
            if scheduler.running:
                scheduler.shutdown()

            start_scheduler()
            assert scheduler.running is True
            shutdown_scheduler()
            assert scheduler.running is False


# ═══════════════════════════════════════════════════════════════════════════════
# 24. Config fix: enable/disable vehicle simulation
# ═══════════════════════════════════════════════════════════════════════════════

class TestSimulationConfig:
    def test_config_default_is_enabled(self):
        """The default value for vehicle_simulation_enabled should be True."""
        from app.config import Settings
        s = Settings()
        assert s.vehicle_simulation_enabled is True

    def test_config_can_be_disabled(self):
        """Setting the env var should disable simulation."""
        from app.config import Settings
        s = Settings(vehicle_simulation_enabled=False)
        assert s.vehicle_simulation_enabled is False


# ═══════════════════════════════════════════════════════════════════════════════
# 25. Edge case: zero-speed vehicle does not move
# ═══════════════════════════════════════════════════════════════════════════════

class TestZeroSpeedNoMovement:
    def test_zero_speed_vehicle_excluded(self, db_session):
        route, _ = _create_route_with_roads(db_session, "ZeroSpd", [
            (26.0, 91.0, 26.1, 91.1),
        ])
        veh = _create_vehicle(db_session, "ZERO-01", 26.0, 91.0, 0,
                              route_id=route.id, seq=0, progress=0.0)

        run_vehicle_simulation(db_session)
        db_session.refresh(veh)

        assert veh.current_lat == 26.0
        assert veh.current_lon == 91.0
        history = db_session.query(models.VehicleLocationHistory)\
            .filter_by(vehicle_id=veh.id).all()
        assert len(history) == 0
