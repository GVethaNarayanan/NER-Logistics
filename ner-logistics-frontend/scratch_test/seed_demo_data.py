import os
import sys
import csv
import json
import argparse
import random
import re
import networkx as nx
import requests

# Default configuration from environment or defaults
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
SEED_ADMIN_USERNAME = os.getenv("SEED_ADMIN_USERNAME", "admin")
SEED_ADMIN_PASSWORD = os.getenv("SEED_ADMIN_PASSWORD", "admin_dev_password")

def get_auth_token():
    url = f"{API_BASE_URL}/auth/login"
    payload = {
        "username": SEED_ADMIN_USERNAME,
        "password": SEED_ADMIN_PASSWORD
    }
    # FastAPI OAuth2PasswordRequestForm expects form data, not json
    res = requests.post(url, data=payload)
    if res.status_code != 200:
        print(f"Error logging in: {res.text}")
        sys.exit(1)
    return res.json().get("access_token")

def parse_wkt_linestring(wkt):
    # Extracts coordinates from "LINESTRING (lon lat, lon lat, ...)"
    inner = wkt.replace("LINESTRING", "").strip(" ()")
    points = inner.split(",")
    first_pt = points[0].strip().split()
    last_pt = points[-1].strip().split()
    return {
        "start_lon": float(first_pt[0]),
        "start_lat": float(first_pt[1]),
        "end_lon": float(last_pt[0]),
        "end_lat": float(last_pt[1])
    }

def fetch_roads_data():
    csv_path = os.path.join(os.path.dirname(__file__), "..", "..", "ner-logistics-backend", "data", "roads_guwahati.csv")
    if not os.path.exists(csv_path):
        print(f"File not found: {csv_path}. Run fetch_osm_roads.py first.")
        sys.exit(1)
    
    edges = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Only consider roads with geometry
            if row.get("geometry") and "LINESTRING" in row["geometry"]:
                edges.append(row)
    return edges

def select_connected_subgraph(edges, target_size=80):
    print("Building full in-memory undirected graph to validate connectivity...")
    G = nx.Graph()
    for e in edges:
        G.add_edge(e["u"], e["v"], **e)
    
    # Find the largest connected component to guarantee multiple paths
    components = list(nx.connected_components(G))
    largest_cc = max(components, key=len)
    
    sub_G = G.subgraph(largest_cc)
    
    # Take a BFS traversal to get a tight, localized subgraph of ~target_size edges
    start_node = list(sub_G.nodes())[0]
    
    selected_edges = []
    visited_nodes = set([start_node])
    queue = [start_node]
    
    while queue and len(selected_edges) < target_size:
        curr = queue.pop(0)
        for neighbor in sub_G.neighbors(curr):
            if len(selected_edges) >= target_size:
                break
            
            edge_data = sub_G.get_edge_data(curr, neighbor)
            # Add edge
            selected_edges.append(edge_data)
            
            if neighbor not in visited_nodes:
                visited_nodes.add(neighbor)
                queue.append(neighbor)
                
    # Verify the extracted graph is connected
    TestG = nx.Graph()
    for e in selected_edges:
        TestG.add_edge(e["u"], e["v"])
    
    if not nx.is_connected(TestG):
        print("WARNING: Selected subgraph is not fully connected!")
        sys.exit(1)
        
    print(f"Selected {len(selected_edges)} highly connected road segments.")
    return selected_edges

def dry_run(roads, bridges, vehicles):
    print("\n--- DRY RUN REPORT ---")
    print(f"Roads to insert: {len(roads)}")
    print(f"Bridges to insert: {len(bridges)}")
    print(f"Vehicles to insert: {len(vehicles)}")
    print("\nSample Road Payload:")
    if roads:
        print(json.dumps(roads[0], indent=2))
    print("\nSample Bridge Payload:")
    if bridges:
        print(json.dumps(bridges[0], indent=2))
    print("\nSample Vehicle Payload:")
    if vehicles:
        print(json.dumps(vehicles[0], indent=2))
    print("----------------------\n")

def seed_data(roads_payload, bridges_payload, vehicles_payload, token, force=False):
    print("\n--- SEEDING DATA ---")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    # Check if roads exist
    res = requests.get(f"{API_BASE_URL}/roads/")
    existing_roads = res.json().get("items", [])
    if len(existing_roads) > 0 and not force:
        print(f"Found {len(existing_roads)} existing roads. Skipping road insertion to avoid duplicates.")
        inserted_road_ids = [r["id"] for r in existing_roads]
    else:
        inserted_road_ids = []
        for r in roads_payload:
            # POST /roads/ currently doesn't require auth in backend (known limitation), but we pass it anyway.
            resp = requests.post(f"{API_BASE_URL}/roads/", json=r)
            if resp.status_code == 200 or resp.status_code == 201:
                inserted_road_ids.append(resp.json()["id"])
            else:
                print(f"Failed to insert road: {resp.text}")
        print(f"Inserted {len(inserted_road_ids)} roads.")

    # Bridges
    res = requests.get(f"{API_BASE_URL}/bridges/")
    existing_bridges = res.json().get("items", [])
    if len(existing_bridges) > 0 and not force:
        print(f"Found {len(existing_bridges)} existing bridges. Skipping.")
    else:
        b_count = 0
        for i, b in enumerate(bridges_payload):
            # Assign valid road_id if available
            if inserted_road_ids:
                b["road_id"] = inserted_road_ids[i % len(inserted_road_ids)]
            resp = requests.post(f"{API_BASE_URL}/bridges/", json=b, headers=headers)
            if resp.status_code == 201 or resp.status_code == 200:
                b_count += 1
            else:
                print(f"Failed to insert bridge: {resp.text}")
        print(f"Inserted {b_count} bridges.")

    # Vehicles
    res = requests.get(f"{API_BASE_URL}/vehicles/", headers=headers)
    existing_vehicles = res.json().get("items", [])
    if len(existing_vehicles) > 0 and not force:
        print(f"Found {len(existing_vehicles)} existing vehicles. Skipping.")
    else:
        v_count = 0
        for v in vehicles_payload:
            resp = requests.post(f"{API_BASE_URL}/vehicles/", json=v, headers=headers)
            if resp.status_code == 200 or resp.status_code == 201:
                v_count += 1
            else:
                print(f"Failed to insert vehicle: {resp.text}")
        print(f"Inserted {v_count} vehicles.")

def verify_seeding(token):
    print("\n--- VERIFYING ROUTING & RISK ---")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    # Get roads to pick valid coordinates
    roads = requests.get(f"{API_BASE_URL}/roads/").json().get("items", [])
    if not roads:
        print("No roads available to test routing.")
        return

    # Pick two distinct points
    origin = roads[0]
    dest = roads[-1]
    
    # Test Shortest
    payload_shortest = {
        "origin_lat": origin["start_lat"],
        "origin_lon": origin["start_lon"],
        "destination_lat": dest["end_lat"],
        "destination_lon": dest["end_lon"],
        "preference": "shortest"
    }
    res = requests.post(f"{API_BASE_URL}/routing/route", json=payload_shortest, headers=headers)
    if res.status_code == 200:
        data = res.json()
        print(f"[OK] Routing (Shortest) SUCCESS. Distance: {data['properties'].get('total_distance_km')} km.")
        print(f"     GeoJSON returned: {data.get('type') == 'Feature' and data.get('geometry', {}).get('type') == 'LineString'}")
    else:
        print(f"[FAIL] Routing (Shortest): {res.text}")

    # Test Safest
    payload_safest = payload_shortest.copy()
    payload_safest["preference"] = "safest"
    res = requests.post(f"{API_BASE_URL}/routing/route", json=payload_safest, headers=headers)
    if res.status_code == 200:
        data = res.json()
        print(f"[OK] Routing (Safest) SUCCESS. Distance: {data['properties'].get('total_distance_km')} km.")
    else:
        print(f"[FAIL] Routing (Safest): {res.text}")

    # Test Risk
    payload_risk = {
        "latitude": origin["start_lat"],
        "longitude": origin["start_lon"],
        "weather_condition": "heavy_rain"
    }
    res = requests.post(f"{API_BASE_URL}/risk/predict", json=payload_risk, headers=headers)
    if res.status_code == 200:
        data = res.json()
        print(f"[OK] Risk Prediction SUCCESS. Score: {data.get('risk_score')}, Level: {data.get('risk_level')}")
        print(f"     Source: {data.get('prediction_source')}")
    else:
        print(f"[FAIL] Risk Prediction: {res.text}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print payloads without modifying data")
    parser.add_argument("--force", action="store_true", help="Force insert even if data exists")
    args = parser.parse_args()

    token = get_auth_token()
    all_edges = fetch_roads_data()
    selected_edges = select_connected_subgraph(all_edges, target_size=80)
    
    # Prepare Road Payloads
    roads_payload = []
    for e in selected_edges:
        coords = parse_wkt_linestring(e["geometry"])
        name = e.get("name")
        if not name or name.strip() == "":
            name = f"OSM Road {e.get('osmid', '')}"
        road = {
            "name": name,
            "road_type": e.get("highway", "unknown"),
            "start_lat": coords["start_lat"],
            "start_lon": coords["start_lon"],
            "end_lat": coords["end_lat"],
            "end_lon": coords["end_lon"],
            "status": "open",
            "district": "Guwahati"
        }
        roads_payload.append(road)

    # Prepare Bridge Payloads (we will attach to road IDs during insertion)
    # Using some coords from the selected roads
    b1_coords = parse_wkt_linestring(selected_edges[0]["geometry"])
    b2_coords = parse_wkt_linestring(selected_edges[-1]["geometry"])
    b3_coords = parse_wkt_linestring(selected_edges[len(selected_edges)//2]["geometry"])
    
    bridges_payload = [
        {"name": "Demo Bridge 1", "latitude": b1_coords["start_lat"], "longitude": b1_coords["start_lon"], "condition": "good"},
        {"name": "Demo Bridge 2", "latitude": b2_coords["start_lat"], "longitude": b2_coords["start_lon"], "condition": "repair_needed"},
        {"name": "Demo Bridge 3", "latitude": b3_coords["start_lat"], "longitude": b3_coords["start_lon"], "condition": "critical"}
    ]

    # Prepare Vehicle Payloads
    vehicles_payload = [
        {"vehicle_number": "VH-1001", "type": "truck", "capacity": 5000, "status": "active", "current_lat": b1_coords["start_lat"], "current_lon": b1_coords["start_lon"]},
        {"vehicle_number": "VH-1002", "type": "van", "capacity": 2000, "status": "active", "current_lat": b2_coords["start_lat"], "current_lon": b2_coords["start_lon"]},
        {"vehicle_number": "VH-1003", "type": "truck", "capacity": 10000, "status": "maintenance", "current_lat": b3_coords["start_lat"], "current_lon": b3_coords["start_lon"]}
    ]

    if args.dry_run:
        dry_run(roads_payload, bridges_payload, vehicles_payload)
    else:
        seed_data(roads_payload, bridges_payload, vehicles_payload, token, force=args.force)
        verify_seeding(token)
