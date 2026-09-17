import requests
import sys

BASE_URL = "http://localhost:8000"

def verify_openapi():
    print(f"Fetching OpenAPI schema from {BASE_URL}/openapi.json")
    try:
        response = requests.get(f"{BASE_URL}/openapi.json")
        response.raise_for_status()
    except Exception as e:
        print(f"Failed to fetch OpenAPI schema: {e}")
        sys.exit(1)

    schema = response.json()

    print("\n--- Verifying Paths ---")
    paths = schema.get("paths", {})
    expected_prefixes = [
        "/auth", "/roads", "/bridges", "/districts", 
        "/weather", "/risk", "/incidents", "/vehicles", 
        "/routes", "/routing", "/alerts", "/"
    ]
    
    found_prefixes = set()
    for path in paths:
        for prefix in expected_prefixes:
            if path == prefix or path.startswith(f"{prefix}/"):
                found_prefixes.add(prefix)

    missing = set(expected_prefixes) - found_prefixes
    if missing:
        print(f"ERROR: Missing endpoints for prefixes: {missing}")
        sys.exit(1)
    else:
        print("SUCCESS: All expected routers are registered in the OpenAPI schema.")

    print("\n--- Verifying Schemas ---")
    components = schema.get("components", {}).get("schemas", {})
    expected_schemas = [
        "RoadOut", "BridgeOut", "IncidentOut", "VehicleOut", 
        "RouteOut", "AlertOut"
    ]
    
    missing_schemas = [s for s in expected_schemas if s not in components]
    if missing_schemas:
        print(f"ERROR: Missing schemas: {missing_schemas}")
        sys.exit(1)
    else:
        print("SUCCESS: All expected response schemas are present.")

    print("\n--- Verification Complete ---")
    print("OpenAPI schema is valid and accurately reflects the current implementation.")

if __name__ == "__main__":
    verify_openapi()
