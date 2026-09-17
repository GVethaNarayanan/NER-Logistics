import pytest
import os
import json
import tempfile
from app import models
from scripts.ingest_district_boundaries import ingest_boundaries

@pytest.fixture
def mock_geojson():
    # Create a small mock geojson for testing
    data = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "shapeGroup": "IND",
                    "shapeName": "Kamrup Metropolitan"
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[91.0, 26.0], [92.0, 26.0], [92.0, 27.0], [91.0, 27.0], [91.0, 26.0]]]
                }
            },
            {
                "type": "Feature",
                "properties": {
                    "shapeGroup": "IND",
                    "shapeName": "Unknown District"
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[91.0, 26.0], [92.0, 26.0], [92.0, 27.0], [91.0, 27.0], [91.0, 26.0]]]
                }
            },
            {
                "type": "Feature",
                "properties": {
                    "shapeGroup": "IND",
                    "shapeName": "Ambiguous Name"
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[91.0, 26.0], [92.0, 26.0], [92.0, 27.0], [91.0, 27.0], [91.0, 26.0]]]
                }
            },
            {
                "type": "Feature",
                "properties": {
                    "shapeGroup": "IND",
                    "shapeName": "Imphal West"
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[93.0, 24.0], [94.0, 24.0], [94.0, 25.0], [93.0, 25.0], [93.0, 24.0]]]
                }
            }
        ]
    }
    with tempfile.NamedTemporaryFile(mode='w', suffix='.geojson', delete=False) as f:
        json.dump(data, f)
        temp_path = f.name
    yield temp_path
    os.remove(temp_path)

def test_ingest_boundaries_logic(db_session, mock_geojson, capsys):
    """Verify reconciliation logic: unique matches succeed, ambiguous names are rejected,
    unknown source districts are skipped, missing canonical districts are reported."""
    # Setup test DB with canonical states and districts
    assam = models.State(name="Assam")
    manipur = models.State(name="Manipur")
    db_session.add_all([assam, manipur])
    db_session.commit()
    
    kamrup = models.District(name="Kamrup Metropolitan", state_id=assam.id)
    imphal = models.District(name="Imphal West", state_id=manipur.id)
    ambig1 = models.District(name="Ambiguous Name", state_id=assam.id)
    ambig2 = models.District(name="Ambiguous Name", state_id=manipur.id)
    missing = models.District(name="Missing District", state_id=assam.id)
    
    db_session.add_all([kamrup, imphal, ambig1, ambig2, missing])
    db_session.commit()
    
    # Run dry-run — this rolls back all DB changes but prints the reconciliation report
    source_info = {"source": "Test"}
    ingest_boundaries(mock_geojson, source_info, dry_run=True, db_session=db_session)
    
    # Capture the printed reconciliation report
    captured = capsys.readouterr()
    report = captured.out
    
    # Verify reconciliation report counts
    assert "Total Canonical Districts: 5" in report, "Should report 5 canonical districts"
    assert "Authentic Boundaries Imported: 2" in report, "Should match exactly 2 unique districts (Kamrup Metropolitan + Imphal West)"
    assert "Missing Canonical Boundaries: 3" in report, "Should report 3 missing (2 Ambiguous Name + 1 Missing District)"
    assert "Unmatched Source Features: 1" in report, "Should report 1 unmatched (Unknown District)"
    assert "Ambiguous Source District Names: 1" in report, "Should report 1 ambiguous (Ambiguous Name appears in 2 states)"
    
    # Verify specific missing districts are listed
    assert "Assam - Ambiguous Name" in report
    assert "Manipur - Ambiguous Name" in report
    assert "Assam - Missing District" in report
