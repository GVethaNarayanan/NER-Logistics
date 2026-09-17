import pytest
from app.database import Base
from app import models

@pytest.fixture(autouse=True)
def setup_registry(db_session):
    """Seed the registry for the test database before running tests."""
    data = {
        "Arunachal Pradesh": ["Anjaw", "Bichom", "Changlang", "Dibang Valley", "East Kameng", "East Siang", "Itanagar Capital Complex", "Kamle", "Keyi Panyor", "Kra Daadi", "Kurung Kumey", "Lepa Rada", "Lohit", "Longding", "Lower Dibang Valley", "Lower Siang", "Lower Subansiri", "Namsai", "Pakke Kessang", "Papum Pare", "Shi Yomi", "Siang", "Tawang", "Tirap", "Upper Siang", "Upper Subansiri", "West Kameng", "West Siang"],
        "Assam": ["Baksa", "Bajali", "Barpeta", "Biswanath", "Bongaigaon", "Cachar", "Charaideo", "Chirang", "Darrang", "Dhemaji", "Dhubri", "Dibrugarh", "Dima Hasao", "Goalpara", "Golaghat", "Hailakandi", "Hojai", "Jorhat", "Kamrup Metropolitan", "Kamrup", "Karbi Anglong", "Karimganj", "Kokrajhar", "Lakhimpur", "Majuli", "Morigaon", "Nagaon", "Nalbari", "Sivasagar", "Sonitpur", "South Salmara-Mankachar", "Tamulpur", "Tinsukia", "Udalguri", "West Karbi Anglong"],
        "Manipur": ["Bishnupur", "Chandel", "Churachandpur", "Imphal East", "Imphal West", "Jiribam", "Kakching", "Kamjong", "Kangpokpi", "Noney", "Pherzawl", "Senapati", "Tamenglong", "Tengnoupal", "Thoubal", "Ukhrul"],
        "Meghalaya": ["East Garo Hills", "East Jaintia Hills", "East Khasi Hills", "Eastern West Khasi Hills", "North Garo Hills", "Ri Bhoi", "South Garo Hills", "South West Garo Hills", "South West Khasi Hills", "West Garo Hills", "West Jaintia Hills", "West Khasi Hills"],
        "Mizoram": ["Aizawl", "Champhai", "Hnahthial", "Khawzawl", "Kolasib", "Lawngtlai", "Lunglei", "Mamit", "Saitual", "Serchhip", "Siaha"],
        "Nagaland": ["Chumoukedima", "Dimapur", "Kiphire", "Kohima", "Longleng", "Mokokchung", "Mon", "Niuland", "Noklak", "Peren", "Phek", "Pughoboto", "Shamator", "Tseminyu", "Tuensang", "Wokha", "Zunheboto"],
        "Sikkim": ["Gangtok", "Gyalshing", "Mangan", "Namchi", "Pakyong", "Soreng"],
        "Tripura": ["Dhalai", "Gomati", "Khowai", "North Tripura", "Sepahijala", "South Tripura", "Unakoti", "West Tripura"]
    }

    # Clean existing tests data if needed
    db_session.query(models.District).delete()
    db_session.query(models.State).delete()
    db_session.commit()

    for state_name, districts in data.items():
        state = models.State(name=state_name)
        db_session.add(state)
        db_session.commit()
        for d in districts:
            dist = models.District(name=d, state_id=state.id)
            db_session.add(dist)
        db_session.commit()

def test_registry_database_integrity(db_session):
    states = db_session.query(models.State).all()
    assert len(states) == 8, "Expected exactly 8 states"

    districts = db_session.query(models.District).all()
    assert len(districts) == 133, "Expected exactly 133 verified districts"

    # Verify no duplicates within a state
    for state in states:
        d_names = [d.name for d in state.districts]
        assert len(d_names) == len(set(d_names)), f"Duplicates found in state {state.name}"
        for d in state.districts:
            assert d.state_id == state.id

def test_registry_api_contract(client):
    response = client.get("/districts/registry")
    assert response.status_code == 200
    data = response.json()["states"]
    assert len(data) == 8
    
    total_districts = sum(len(state["districts"]) for state in data)
    assert total_districts == 133
    
    # Check specific state
    assam = next((s for s in data if s["name"] == "Assam"), None)
    assert assam is not None
    assert len(assam["districts"]) == 35
