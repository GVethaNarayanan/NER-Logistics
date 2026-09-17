import pytest
from geoalchemy2.elements import WKTElement
import json

def test_highway_filter():
    """Verify that only the requested highway types are accepted."""
    from scripts.ingest_osm_roads import INCLUDED_HIGHWAYS
    
    assert "motorway" in INCLUDED_HIGHWAYS
    assert "residential" in INCLUDED_HIGHWAYS
    assert "service" not in INCLUDED_HIGHWAYS
    assert "footway" not in INCLUDED_HIGHWAYS

def test_extract_osm_tags():
    """Verify that OSM tags are properly extracted into a dictionary."""
    from scripts.ingest_osm_roads import extract_osm_tags
    
    # Mock row from osmnx GeoDataFrame
    row = {
        "highway": "primary",
        "surface": "asphalt",
        "lanes": "2",
        "maxspeed": "80",
        "name": "NH 10",
        "ref": "10",
        "bridge": "yes",
        "ignored_tag": "should not be here"
    }
    
    tags = extract_osm_tags(row)
    assert tags["highway"] == "primary"
    assert tags["surface"] == "asphalt"
    assert tags["lanes"] == "2"
    assert tags["maxspeed"] == "80"
    assert tags["bridge"] == "yes"
    assert "ignored_tag" not in tags

def test_legacy_flag_support(db_session):
    """Verify that the database schema supports the is_legacy and source flags."""
    from app.models import Road
    
    # Add a mock legacy road
    legacy_road = Road(
        name="Legacy Demo Road",
        road_type="trunk",
        is_legacy=True,
        source="osm"
    )
    db_session.add(legacy_road)
    db_session.commit()
    
    # Add a new mock OSM road
    osm_road = Road(
        name="Real OSM Road",
        road_type="primary",
        osm_id=123456789,
        osm_tags={"highway": "primary"},
        is_legacy=False,
        source="osm"
    )
    db_session.add(osm_road)
    db_session.commit()
    
    # Query back
    legacy = db_session.query(Road).filter(Road.is_legacy == True).first()
    assert legacy.name == "Legacy Demo Road"
    assert legacy.osm_id is None
    
    new_road = db_session.query(Road).filter(Road.osm_id == 123456789).first()
    assert new_road.name == "Real OSM Road"
    assert new_road.is_legacy is False
    assert new_road.osm_tags["highway"] == "primary"
