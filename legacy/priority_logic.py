"""
priority_logic.py
-----------------
*** LEGACY / REFERENCE ONLY ***
This file is superseded by priority_aware_mtf.py and is no longer imported
by app.py or any active module. It is kept for reference purposes only.

Implements priority-aware logic for traffic optimization.
This module handles emergency vehicle prioritization and
green corridor identification.

Author: Your Team
"""

# --------------------------------------------------
# 1. SEPARATE EMERGENCY AND REGULAR VEHICLES
# --------------------------------------------------

def separate_vehicles(vehicles):
    """
    Separate vehicles based on type.

    Args:
        vehicles (list of dicts)

    Returns:
        emergency_vehicles, regular_vehicles
    """
    emergency_vehicles = []
    regular_vehicles = []

    for v in vehicles:
        if v["type"] == "emergency":
            emergency_vehicles.append(v)
        else:
            regular_vehicles.append(v)

    return emergency_vehicles, regular_vehicles


# --------------------------------------------------
# 2. PRIORITY SCORE FOR A ROUTE
# --------------------------------------------------

def compute_route_priority(route_edges, congested_edges, vehicle_priority):
    """
    Compute priority score for a given route.

    Args:
        route_edges (list of edges)
        congested_edges (list of edges)
        vehicle_priority (int)

    Returns:
        priority_score (float)
    """
    congestion_penalty = 0

    for edge in route_edges:
        if edge in congested_edges or (edge[1], edge[0]) in congested_edges:
            congestion_penalty += 1

    # Emergency vehicles get amplified priority
    priority_score = vehicle_priority / (1 + congestion_penalty)

    return priority_score


# --------------------------------------------------
# 3. RANK ROUTES BASED ON PRIORITY
# --------------------------------------------------

def rank_vehicle_routes(vehicle, congested_edges):
    """
    Rank candidate routes for a vehicle.

    Args:
        vehicle (dict)
        congested_edges (list)

    Returns:
        sorted_routes (list)
    """
    ranked_routes = []

    for route in vehicle["candidate_routes"]:
        route_edges = [(route[i], route[i + 1]) for i in range(len(route) - 1)]
        score = compute_route_priority(
            route_edges,
            congested_edges,
            vehicle["priority_weight"]
        )
        ranked_routes.append((route, score))

    # Sort routes by descending priority score
    ranked_routes.sort(key=lambda x: x[1], reverse=True)

    return ranked_routes


# --------------------------------------------------
# 4. SELECT PREFERRED ROUTE FOR EACH VEHICLE
# --------------------------------------------------

def select_preferred_routes(vehicles, congested_edges):
    """
    Select best route for each vehicle based on priority.

    Args:
        vehicles (list of dicts)
        congested_edges (list)

    Returns:
        selected_routes (dict)
    """
    selected_routes = {}

    for vehicle in vehicles:
        ranked = rank_vehicle_routes(vehicle, congested_edges)

        if ranked:
            selected_routes[vehicle["vehicle_id"]] = ranked[0][0]
        else:
            selected_routes[vehicle["vehicle_id"]] = None

    return selected_routes


# --------------------------------------------------
# 5. IDENTIFY EMERGENCY CORRIDOR
# --------------------------------------------------

def identify_emergency_corridor(emergency_vehicles, congested_edges):
    """
    Identify road segments that form emergency corridors.

    Args:
        emergency_vehicles (list)
        congested_edges (list)

    Returns:
        corridor_edges (set)
    """
    corridor_edges = set()

    for v in emergency_vehicles:
        for route in v.get("candidate_routes", []):
            for i in range(len(route) - 1):
                edge = (route[i], route[i + 1])
                if edge not in congested_edges and (edge[1], edge[0]) not in congested_edges:
                    corridor_edges.add(edge)

    return corridor_edges
