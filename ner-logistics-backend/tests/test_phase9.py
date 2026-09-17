import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from app import models

def _create_road(db, name, slat, slon, elat, elon, status="open"):
    r = models.Road(name=name, start_lat=slat, start_lon=slon, end_lat=elat, end_lon=elon, status=status)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r

def _create_incident(db, road_id, status):
    i = models.Incident(
        incident_type="landslide",
        latitude=0.0,
        longitude=0.0,
        road_id=road_id,
        status=status,
        synced="synced",
        reported_at=datetime.now(timezone.utc).replace(tzinfo=None)
    )
    db.add(i)
    db.commit()
    return i

def _create_bridge(db, road_id, condition):
    b = models.Bridge(
        name="Test Bridge",
        road_id=road_id,
        latitude=0.0,
        longitude=0.0,
        condition=condition
    )
    db.add(b)
    db.commit()
    return b

def _create_weather(db, lat, lon, rainfall_mm, hours_ago=0, data_source="verified"):
    w = models.WeatherSnapshot(
        latitude=lat,
        longitude=lon,
        rainfall_mm=rainfall_mm,
        temperature_c=25.0,
        data_source=data_source,
        recorded_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours_ago)
    )
    db.add(w)
    db.commit()
    return w

def test_shortest_vs_safest_divergence(client, db_session):
    r_direct = _create_road(db_session, "Direct", 0.0, 0.0, 2.0, 0.0)
    r_detour1 = _create_road(db_session, "Detour1", 0.0, 0.0, 1.0, 1.0)
    r_detour2 = _create_road(db_session, "Detour2", 1.0, 1.0, 2.0, 0.0)
    _create_incident(db_session, r_direct.id, "verified")
    _create_bridge(db_session, r_direct.id, "poor")

    resp_shortest = client.post("/routing/route", json={
        "origin_lat": 0.0, "origin_lon": 0.0,
        "destination_lat": 2.0, "destination_lon": 0.0,
        "preference": "shortest"
    })
    data_short = resp_shortest.json()
    assert data_short["properties"]["route_preference"] == "shortest"
    assert r_direct.id in data_short["properties"]["road_ids"]

    resp_safest = client.post("/routing/route", json={
        "origin_lat": 0.0, "origin_lon": 0.0,
        "destination_lat": 2.0, "destination_lon": 0.0,
        "preference": "safest"
    })
    data_safe = resp_safest.json()
    assert data_safe["properties"]["route_preference"] == "safest"
    assert r_detour1.id in data_safe["properties"]["road_ids"]
    assert data_safe["properties"]["total_distance_km"] > data_short["properties"]["total_distance_km"]
    assert data_safe["properties"]["average_risk_score"] < data_short["properties"]["average_risk_score"]

def test_equal_risk_routes(client, db_session):
    _create_road(db_session, "Path1", 0.0, 0.0, 1.0, 0.0)
    _create_road(db_session, "Path2", 0.0, 0.0, 0.0, 1.0) 
    resp_short = client.post("/routing/route", json={
        "origin_lat": 0.0, "origin_lon": 0.0,
        "destination_lat": 1.0, "destination_lon": 0.0,
        "preference": "shortest"
    }).json()
    resp_safe = client.post("/routing/route", json={
        "origin_lat": 0.0, "origin_lon": 0.0,
        "destination_lat": 1.0, "destination_lon": 0.0,
        "preference": "safest"
    }).json()
    assert resp_short["properties"]["road_ids"] == resp_safe["properties"]["road_ids"]

def test_incident_lifecycle(db_session):
    r1 = _create_road(db_session, "R1", 0.0, 0.0, 1.0, 0.0) 
    r2 = _create_road(db_session, "R2", 0.0, 0.0, 1.0, 1.0) 
    r3 = _create_road(db_session, "R3", 0.0, 0.0, 1.0, -1.0) 
    _create_incident(db_session, r1.id, "reported")
    _create_incident(db_session, r2.id, "verified")
    _create_incident(db_session, r3.id, "resolved")
    
    from app.services.graph_service import build_road_graph
    g = build_road_graph(db_session)
    r1_edge = g[(0.0, 0.0)][(1.0, 0.0)]
    r2_edge = g[(0.0, 0.0)][(1.0, 1.0)]
    r3_edge = g[(0.0, 0.0)][(1.0, -1.0)]
    assert r1_edge["risk_score"] > 0
    assert r2_edge["risk_score"] > 0
    assert r3_edge["risk_score"] == 3.0

def test_weather_staleness(db_session):
    r1 = _create_road(db_session, "Fresh", 10.0, 10.0, 11.0, 10.0)
    r2 = _create_road(db_session, "Stale", 20.0, 20.0, 21.0, 20.0)
    _create_weather(db_session, 10.0, 10.0, 100.0, hours_ago=1)
    _create_weather(db_session, 20.0, 20.0, 100.0, hours_ago=7)
    
    from app.services.graph_service import build_road_graph
    g = build_road_graph(db_session)
    fresh_edge = g[(10.0, 10.0)][(11.0, 10.0)]
    stale_edge = g[(20.0, 20.0)][(21.0, 20.0)]
    assert fresh_edge["risk_score"] > stale_edge["risk_score"]
    assert stale_edge["risk_score"] == 3.0

def test_multiple_hazards(db_session):
    r1 = _create_road(db_session, "Hazards", 0.0, 0.0, 1.0, 0.0)
    _create_incident(db_session, r1.id, "verified")
    _create_bridge(db_session, r1.id, "poor")
    _create_weather(db_session, 0.0, 0.0, 150.0)
    r2 = _create_road(db_session, "OneHazard", 0.0, 0.0, 0.0, 1.0)
    _create_incident(db_session, r2.id, "verified")
    
    from app.services.graph_service import build_road_graph
    g = build_road_graph(db_session)
    edge1 = g[(0.0, 0.0)][(1.0, 0.0)]
    edge2 = g[(0.0, 0.0)][(0.0, 1.0)]
    assert edge1["risk_score"] > edge2["risk_score"]

def test_same_edge_routing_and_virtual_splitting(client, db_session):
    r1 = _create_road(db_session, "R1", 0.0, 0.0, 0.0, 10.0)
    _create_incident(db_session, r1.id, "verified")
    
    from app.services.graph_service import build_road_graph
    g = build_road_graph(db_session)
    original_risk = g[(0.0, 0.0)][(0.0, 10.0)]["risk_score"]
    
    resp = client.post("/routing/route", json={
        "origin_lat": 0.0, "origin_lon": 2.0,
        "destination_lat": 0.0, "destination_lon": 8.0,
        "preference": "safest"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["properties"]["average_risk_score"] == original_risk

def test_blocked_roads_disconnected(client, db_session):
    r1 = _create_road(db_session, "Open", 0.0, 0.0, 1.0, 0.0)
    r2 = _create_road(db_session, "Blocked", 1.0, 0.0, 2.0, 0.0, status="blocked")
    resp = client.post("/routing/route", json={
        "origin_lat": 0.0, "origin_lon": 0.0,
        "destination_lat": 2.0, "destination_lon": 0.0,
        "preference": "safest"
    })
    assert resp.status_code == 400

def test_invalid_preference(client, db_session):
    resp = client.post("/routing/route", json={
        "origin_lat": 0.0, "origin_lon": 0.0,
        "destination_lat": 1.0, "destination_lon": 0.0,
        "preference": "invalid_pref"
    })
    assert resp.status_code == 422 

def test_default_preference_is_shortest(client, db_session):
    r1 = _create_road(db_session, "R1", 0.0, 0.0, 1.0, 0.0)
    resp1 = client.post("/routing/route", json={
        "origin_lat": 0.0, "origin_lon": 0.0,
        "destination_lat": 1.0, "destination_lon": 0.0
    })
    resp2 = client.post("/routing/route", json={
        "origin_lat": 0.0, "origin_lon": 0.0,
        "destination_lat": 1.0, "destination_lon": 0.0,
        "preference": "shortest"
    })
    assert resp1.json()["properties"]["route_preference"] == "shortest"
    assert resp1.json() == resp2.json()

def test_no_n_plus_one_queries(db_session):
    for i in range(5):
        _create_road(db_session, f"R{i}", float(i), 0.0, float(i+1), 0.0)
        
    from app.services.graph_service import build_road_graph
    original_query = db_session.query
    query_count = 0
    def mock_query(*args, **kwargs):
        nonlocal query_count
        query_count += 1
        return original_query(*args, **kwargs)
        
    with patch.object(db_session, "query", side_effect=mock_query):
        build_road_graph(db_session)
    assert query_count == 4

