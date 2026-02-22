"""
traffic_simulator.py
--------------------
Simulates traffic demand and vehicle types
for Priority-Aware Quantum Traffic Optimization.

Author: Your Team
"""

import random


# --------------------------------------------------
# 1. CREATE VEHICLES (REGULAR + EMERGENCY)
# --------------------------------------------------

def generate_vehicles(od_pairs, emergency_ratio=0.2):
    """
    Generate vehicle objects from origin-destination pairs.

    Args:
        od_pairs (list): List of (origin, destination)
        emergency_ratio (float): Fraction of emergency vehicles

    Returns:
        vehicles (list of dicts)
    """
    vehicles = []
    num_emergency = max(1, int(len(od_pairs) * emergency_ratio))
    emergency_indices = set(random.sample(range(len(od_pairs)), num_emergency))

    for idx, (origin, destination) in enumerate(od_pairs):
        vehicle = {
            "vehicle_id": idx,
            "origin": origin,
            "destination": destination,
            "type": "emergency" if idx in emergency_indices else "regular",
            "priority_weight": 10 if idx in emergency_indices else 1
        }
        vehicles.append(vehicle)

    return vehicles


# --------------------------------------------------
# 2. ASSIGN CANDIDATE ROUTES TO VEHICLES
# --------------------------------------------------

def assign_routes_to_vehicles(vehicles, routes_dict):
    """
    Attach candidate routes to each vehicle.

    Args:
        vehicles (list of dicts)
        routes_dict (dict): {(origin, destination): routes}

    Returns:
        vehicles (list of dicts)
    """
    for vehicle in vehicles:
        od_key = (vehicle["origin"], vehicle["destination"])
        vehicle["candidate_routes"] = routes_dict.get(od_key, [])

    return vehicles


# --------------------------------------------------
# 3. TAG CONGESTED EDGES
# --------------------------------------------------

def identify_congested_edges(G, congestion_threshold=7):
    """
    Identify heavily congested road segments.

    Args:
        G (networkx.Graph)
        congestion_threshold (int)

    Returns:
        List of congested edges
    """
    congested_edges = []

    for u, v, data in G.edges(data=True):
        if data.get("congestion", 0) >= congestion_threshold:
            congested_edges.append((u, v))

    return congested_edges


# --------------------------------------------------
# 4. BUILD TRAFFIC SCENARIO (PIPELINE)
# --------------------------------------------------

def build_traffic_scenario(network_data, emergency_ratio=0.2):
    """
    Complete traffic simulation pipeline.

    Args:
        network_data (dict): Output from network_builder
        emergency_ratio (float)

    Returns:
        scenario (dict)
    """
    G = network_data["graph"]
    od_pairs = network_data["od_pairs"]
    routes = network_data["routes"]

    vehicles = generate_vehicles(od_pairs, emergency_ratio)
    vehicles = assign_routes_to_vehicles(vehicles, routes)
    congested_edges = identify_congested_edges(G)

    scenario = {
        "graph": G,
        "vehicles": vehicles,
        "congested_edges": congested_edges
    }

    return scenario
