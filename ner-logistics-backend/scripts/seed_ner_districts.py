import json
import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add the root directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import Base
from app import models

DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/ner_logistics")
engine = create_engine(DB_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def seed_districts():
    """
    Registry Version: 1.0-133-districts
    Source: Authoritative government portals (LGD-aligned)
    Retrieved At: 2026-09-13
    """
    data = {
        "Arunachal Pradesh": [
            "Anjaw", "Bichom", "Changlang", "Dibang Valley", "East Kameng", "East Siang", 
            "Itanagar Capital Complex", "Kamle", "Keyi Panyor", "Kra Daadi", "Kurung Kumey", 
            "Lepa Rada", "Lohit", "Longding", "Lower Dibang Valley", "Lower Siang", 
            "Lower Subansiri", "Namsai", "Pakke Kessang", "Papum Pare", "Shi Yomi", 
            "Siang", "Tawang", "Tirap", "Upper Siang", "Upper Subansiri", "West Kameng", "West Siang"
        ],
        "Assam": [
            "Baksa", "Bajali", "Barpeta", "Biswanath", "Bongaigaon", "Cachar", "Charaideo", 
            "Chirang", "Darrang", "Dhemaji", "Dhubri", "Dibrugarh", "Dima Hasao", 
            "Goalpara", "Golaghat", "Hailakandi", "Hojai", "Jorhat", "Kamrup Metropolitan", 
            "Kamrup", "Karbi Anglong", "Karimganj", "Kokrajhar", "Lakhimpur", "Majuli", 
            "Morigaon", "Nagaon", "Nalbari", "Sivasagar", "Sonitpur", "South Salmara-Mankachar", 
            "Tamulpur", "Tinsukia", "Udalguri", "West Karbi Anglong"
        ],
        "Manipur": [
            "Bishnupur", "Chandel", "Churachandpur", "Imphal East", "Imphal West", 
            "Jiribam", "Kakching", "Kamjong", "Kangpokpi", "Noney", "Pherzawl", 
            "Senapati", "Tamenglong", "Tengnoupal", "Thoubal", "Ukhrul"
        ],
        "Meghalaya": [
            "East Garo Hills", "East Jaintia Hills", "East Khasi Hills", "Eastern West Khasi Hills",
            "North Garo Hills", "Ri Bhoi", "South Garo Hills", "South West Garo Hills", 
            "South West Khasi Hills", "West Garo Hills", "West Jaintia Hills", "West Khasi Hills"
        ],
        "Mizoram": [
            "Aizawl", "Champhai", "Hnahthial", "Khawzawl", "Kolasib", 
            "Lawngtlai", "Lunglei", "Mamit", "Saitual", "Serchhip", "Siaha"
        ],
        "Nagaland": [
            "Chumoukedima", "Dimapur", "Kiphire", "Kohima", "Longleng", 
            "Mokokchung", "Mon", "Niuland", "Noklak", "Peren", "Phek", 
            "Pughoboto", "Shamator", "Tseminyu", "Tuensang", "Wokha", "Zunheboto"
        ],
        "Sikkim": [
            "Gangtok", "Gyalshing", "Mangan", "Namchi", "Pakyong", "Soreng"
        ],
        "Tripura": [
            "Dhalai", "Gomati", "Khowai", "North Tripura", 
            "Sepahijala", "South Tripura", "Unakoti", "West Tripura"
        ]
    }

    db = SessionLocal()
    try:
        total_states = 0
        total_districts = 0
        for state_name, districts in data.items():
            state = db.query(models.State).filter(models.State.name == state_name).first()
            if not state:
                state = models.State(name=state_name)
                db.add(state)
                db.commit()
                db.refresh(state)
            total_states += 1
            
            for district_name in districts:
                district = db.query(models.District).filter(
                    models.District.name == district_name,
                    models.District.state_id == state.id
                ).first()
                if not district:
                    district = models.District(name=district_name, state_id=state.id)
                    db.add(district)
                    db.commit()
                total_districts += 1
                
        print(f"Successfully seeded {total_states} states and {total_districts} districts.")
    finally:
        db.close()

if __name__ == "__main__":
    seed_districts()
