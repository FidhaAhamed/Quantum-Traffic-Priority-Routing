"""
qubo_builder.py
---------------
*** LEGACY / REFERENCE ONLY ***
This file is superseded by priority_aware_mtf.py and is no longer imported
by app.py or any active module. It is kept for reference purposes only.

Builds a Priority-Aware QUBO model for traffic optimization.
Emergency vehicles are given higher weights so their routes
are preferred during optimization.

Author: Your Team
"""

import dimod
from collections import defaultdict


# --------------------------------------------------
# 1. CREATE QUBO VARIABLES
# --------------------------------------------------

def create_qubo_variables(vehicles):
    """
    Create binary decision variables for each vehicle-route pair.

    Variable format:
        x_(vehicle_id)_(route_index)

    Returns:
        variable_map (dict)
    """
    variable_map = {}
    for v in vehicles:
        vid = v["vehicle_id"]
        for r_idx in range(len(v["candidate_routes"])):
            var_name = f"x_{vid}_{r_idx}"
            variable_map[(vid, r_idx)] = var_name
    return variable_map


# --------------------------------------------------
# 2. BUILD PRIORITY-AWARE QUBO
# --------------------------------------------------

def build_qubo(vehicles, variable_map, congestion_weight=1.0):
    """
    Construct the QUBO dictionary.

    Objective:
    - Each vehicle selects exactly one route
    - Minimize congestion overlap
    - Prioritize emergency vehicles

    Returns:
        Q (dict)
    """
    Q = defaultdict(float)

    # --------------------------------------------------
    # Constraint 1: Each vehicle selects exactly ONE route
    # --------------------------------------------------
    for v in vehicles:
        vid = v["vehicle_id"]
        route_indices = range(len(v["candidate_routes"]))

        for i in route_indices:
            var_i = variable_map[(vid, i)]
            Q[(var_i, var_i)] += -2  # linear term

            for j in route_indices:
                if i != j:
                    var_j = variable_map[(vid, j)]
                    Q[(var_i, var_j)] += 2  # quadratic penalty

    # --------------------------------------------------
    # Constraint 2: Congestion minimization (route overlap)
    # --------------------------------------------------
    edge_usage = defaultdict(list)

    for v in vehicles:
        vid = v["vehicle_id"]
        priority = v["priority_weight"]

        for r_idx, route in enumerate(v["candidate_routes"]):
            edges = [(route[i], route[i + 1]) for i in range(len(route) - 1)]
            for edge in edges:
                edge_usage[edge].append((vid, r_idx, priority))

    for edge, users in edge_usage.items():
        if len(users) > 1:
            for i in range(len(users)):
                for j in range(i + 1, len(users)):
                    vid1, r1, p1 = users[i]
                    vid2, r2, p2 = users[j]

                    var1 = variable_map[(vid1, r1)]
                    var2 = variable_map[(vid2, r2)]

                    penalty = congestion_weight * (1 / p1 + 1 / p2)
                    Q[(var1, var2)] += penalty

    return Q


# --------------------------------------------------
# 3. BUILD BINARY QUADRATIC MODEL (BQM)
# --------------------------------------------------

def build_bqm(Q):
    """
    Convert QUBO dictionary into BinaryQuadraticModel.

    Returns:
        bqm (BinaryQuadraticModel)
    """
    bqm = dimod.BinaryQuadraticModel.from_qubo(Q)
    return bqm


# --------------------------------------------------
# 4. FULL PIPELINE FUNCTION
# --------------------------------------------------

def build_priority_aware_qubo(vehicles):
    """
    Complete QUBO pipeline.

    Returns:
        bqm, variable_map
    """
    variable_map = create_qubo_variables(vehicles)
    Q = build_qubo(vehicles, variable_map)
    bqm = build_bqm(Q)

    return bqm, variable_map
