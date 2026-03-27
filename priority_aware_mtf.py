"""
priority_aware_mtf.py
---------------------
Implements the Priority-Aware Mini-scale Traffic Flow (MTF) algorithm.

This module integrates a weighted prioritization layer into the standard
QUBO formulation and uses iterative decomposition to solve sub-problems
on a quantum-inspired solver (Neal SA / Tabu) or D-Wave QPU.

Author: Fidha Ahamed
"""

import random
import dimod
import numpy as np
from collections import defaultdict
from copy import deepcopy


# ==================================================
# 1. COST HAMILTONIAN BUILDER (Priority-Aware)
# ==================================================

def build_cost_hamiltonian(vehicles, variable_map, graph,
                           alpha=1.0, beta=2.0, gamma=5.0,
                           emergency_boost=10.0):
    """
    Build the full Priority-Aware Cost Hamiltonian as a QUBO dict.

    H_cost = alpha * H_route_cost
           + beta  * H_congestion
           + gamma * H_one_route_constraint

    Where H_route_cost incorporates priority weights so that
    emergency vehicles strongly prefer shorter/faster routes,
    and regular vehicles are penalised for sharing edges with ESVs
    (creating the "green corridor" effect).
    """
    Q = defaultdict(float)

    # ----- H_one_route: each vehicle picks exactly one route -----
    for v in vehicles:
        vid = v["vehicle_id"]
        n_routes = len(v.get("candidate_routes", []))
        if n_routes == 0:
            continue

        for i in range(n_routes):
            var_i = variable_map[(vid, i)]
            Q[(var_i, var_i)] += -gamma

            for j in range(n_routes):
                if i != j:
                    var_j = variable_map[(vid, j)]
                    Q[(var_i, var_j)] += gamma

    # ----- H_route_cost: prefer shorter routes, amplified for ESVs -----
    # Pre-compute max cost across all candidate routes for proper normalisation
    all_raw_costs = []
    for v in vehicles:
        for route in v.get("candidate_routes", []):
            all_raw_costs.append(_compute_route_cost(route, graph))
    max_cost = max(all_raw_costs) if all_raw_costs else 1.0

    for v in vehicles:
        vid = v["vehicle_id"]
        priority = v.get("priority_weight", 1)
        is_emergency = v.get("type") == "emergency"

        for r_idx, route in enumerate(v.get("candidate_routes", [])):
            var = variable_map[(vid, r_idx)]
            route_cost = _compute_route_cost(route, graph, max_cost=max_cost)

            weight = alpha * priority if is_emergency else alpha
            Q[(var, var)] += weight * route_cost

    # ----- H_congestion: penalise edge overlaps (green corridor) -----
    edge_usage = defaultdict(list)

    for v in vehicles:
        vid = v["vehicle_id"]
        priority = v.get("priority_weight", 1)
        is_emergency = v.get("type") == "emergency"

        for r_idx, route in enumerate(v.get("candidate_routes", [])):
            edges = [(route[i], route[i + 1]) for i in range(len(route) - 1)]
            for edge in edges:
                norm_edge = tuple(sorted(edge))
                edge_usage[norm_edge].append((vid, r_idx, priority, is_emergency))

    for edge, users in edge_usage.items():
        if len(users) <= 1:
            continue
        for i in range(len(users)):
            for j in range(i + 1, len(users)):
                vid1, r1, p1, em1 = users[i]
                vid2, r2, p2, em2 = users[j]

                var1 = variable_map[(vid1, r1)]
                var2 = variable_map[(vid2, r2)]

                if em1 and not em2:
                    penalty = beta * emergency_boost
                elif em2 and not em1:
                    penalty = beta * emergency_boost
                elif em1 and em2:
                    penalty = beta * 2.0
                else:
                    penalty = beta * 1.0

                Q[(var1, var2)] += penalty

    return dict(Q)


def _compute_route_cost(route, graph, max_cost=None):
    """Compute normalised travel cost for a route.

    Args:
        route: list of node IDs
        graph: networkx graph with travel_time edge attributes
        max_cost: reference value for normalisation; if None the raw total is returned
    """
    total = 0.0
    for i in range(len(route) - 1):
        u, v = route[i], route[i + 1]
        if graph.has_edge(u, v):
            data = graph[u][v]
            if isinstance(data, dict) and 0 in data:
                data = data[0]
            total += data.get("travel_time", data.get("length", 1.0))
        else:
            total += 100.0
    if max_cost is None:
        return total
    return total / max(max_cost, 1.0)


# ==================================================
# 2. MTF ITERATIVE DECOMPOSITION
# ==================================================

def decompose_into_subproblems(vehicles, max_subproblem_size=8):
    """
    Decompose the vehicle set into smaller groups for MTF.
    Emergency vehicles are always in the first sub-problem
    so they get priority.
    """
    emergency = [v for v in vehicles if v.get("type") == "emergency"]
    regular = [v for v in vehicles if v.get("type") != "emergency"]

    subproblems = []

    if emergency:
        subproblems.append(emergency)

    for i in range(0, len(regular), max_subproblem_size):
        chunk = regular[i:i + max_subproblem_size]
        subproblems.append(chunk)

    return subproblems


def create_subproblem_variables(sub_vehicles):
    """Create QUBO variable mapping for a sub-problem."""
    variable_map = {}
    for v in sub_vehicles:
        vid = v["vehicle_id"]
        for r_idx in range(len(v.get("candidate_routes", []))):
            var_name = f"x_{vid}_{r_idx}"
            variable_map[(vid, r_idx)] = var_name
    return variable_map


def solve_subproblem(bqm, method="neal", num_reads=200):
    """
    Solve a single MTF sub-problem.

    Supported methods (all FREE, all LOCAL):
        - "neal"  : D-Wave Neal Simulated Annealing (recommended)
        - "sa"    : dimod basic Simulated Annealing
        - "tabu"  : D-Wave Tabu Search
        - "exact" : Brute-force (tiny problems only, <20 variables)
    Optional (requires D-Wave API token):
        - "dwave" : LeapHybridSampler (cloud)
    """
    if method == "neal":
        try:
            import neal
            sampler = neal.SimulatedAnnealingSampler()
            sampleset = sampler.sample(
                bqm, num_reads=num_reads,
                num_sweeps=1000, beta_range=[0.1, 10.0],
            )
        except ImportError:
            sampler = dimod.SimulatedAnnealingSampler()
            sampleset = sampler.sample(bqm, num_reads=num_reads)

    elif method == "tabu":
        try:
            import tabu
            sampler = tabu.TabuSampler()
            sampleset = sampler.sample(bqm, num_reads=num_reads, timeout=1000)
        except ImportError:
            sampler = dimod.SimulatedAnnealingSampler()
            sampleset = sampler.sample(bqm, num_reads=num_reads)

    elif method == "exact":
        sampler = dimod.ExactSolver()
        sampleset = sampler.sample(bqm)

    elif method == "dwave":
        try:
            from dwave.system import LeapHybridSampler
            sampler = LeapHybridSampler()
            sampleset = sampler.sample(bqm)
        except Exception:
            sampler = dimod.SimulatedAnnealingSampler()
            sampleset = sampler.sample(bqm, num_reads=num_reads)

    # The key addition — direct QPU access for small MTF sub-problems
    elif method == "qpu":
        try:
            from dwave.system import DWaveSampler, EmbeddingComposite
            sampler = EmbeddingComposite(DWaveSampler())
            sampleset = sampler.sample(bqm, num_reads=num_reads)
        except ImportError:
            print("D-Wave system not installed. Falling back to Neal SA.")
            import neal
            sampler = neal.SimulatedAnnealingSampler()
            sampleset = sampler.sample(bqm, num_reads=num_reads)
        except Exception as e:
            print(f"QPU access failed: {e}. Falling back to Neal SA.")
            import neal
            sampler = neal.SimulatedAnnealingSampler()
            sampleset = sampler.sample(bqm, num_reads=num_reads)    

    else:  # "sa" or fallback
        sampler = dimod.SimulatedAnnealingSampler()
        sampleset = sampler.sample(bqm, num_reads=num_reads)

    return sampleset.first.sample


def decode_subproblem(sample, variable_map, sub_vehicles):
    """Decode a sub-problem solution into route selections."""
    selected = {}
    for (vid, r_idx), var_name in variable_map.items():
        if sample.get(var_name, 0) == 1:
            for v in sub_vehicles:
                if v["vehicle_id"] == vid:
                    routes = v.get("candidate_routes", [])
                    if r_idx < len(routes):
                        selected[vid] = routes[r_idx]
                    break
    return selected


def update_congestion(graph, selected_routes):
    """
    After solving a sub-problem, update edge congestion counts
    so subsequent sub-problems account for already-assigned routes.
    Also recomputes travel_time to reflect updated congestion for
    subsequent Hamiltonian builds.
    """
    for vid, route in selected_routes.items():
        for i in range(len(route) - 1):
            u, v = route[i], route[i + 1]
            if graph.has_edge(u, v):
                if isinstance(graph[u][v], dict) and 0 in graph[u][v]:
                    data = graph[u][v][0]
                else:
                    data = graph[u][v]
                data["congestion"] = data.get("congestion", 0) + 1
                # Recompute travel_time to reflect updated congestion
                length_km = data.get("length", 100) / 1000.0
                speed_kmph = max(data.get("speed", 40), 1)
                base_time = (length_km / speed_kmph) * 60
                congestion_factor = 1.0 + (data["congestion"] / 20.0)
                data["travel_time"] = base_time * congestion_factor


# ==================================================
# 3. MAIN MTF PIPELINE
# ==================================================

def priority_aware_mtf_solve(vehicles, graph,
                              max_subproblem_size=8,
                              num_iterations=3,
                              method="neal",
                              alpha=1.0, beta=2.0, gamma=5.0,
                              emergency_boost=10.0):
    """
    Full Priority-Aware MTF pipeline.

    Steps:
    1. Decompose vehicles into sub-problems (ESVs first)
    2. For each sub-problem:
       a. Build Cost Hamiltonian with priority weights
       b. Convert to BQM
       c. Solve on QPU / SA
       d. Update congestion on graph
    3. Iterate to refine with updated congestion
    4. Return final route assignments + metrics
    """
    G = deepcopy(graph)

    final_routes = {}
    iteration_energies = []

    for iteration in range(num_iterations):
        subproblems = decompose_into_subproblems(vehicles, max_subproblem_size)
        iteration_routes = {}

        for sp_idx, sub_vehicles in enumerate(subproblems):
            if not sub_vehicles:
                continue

            valid_vehicles = [v for v in sub_vehicles
                              if len(v.get("candidate_routes", [])) > 0]
            if not valid_vehicles:
                continue

            var_map = create_subproblem_variables(valid_vehicles)
            Q = build_cost_hamiltonian(
                valid_vehicles, var_map, G,
                alpha=alpha, beta=beta, gamma=gamma,
                emergency_boost=emergency_boost
            )

            bqm = dimod.BinaryQuadraticModel.from_qubo(Q)
            sample = solve_subproblem(bqm, method=method)

            energy = bqm.energy(sample)
            iteration_energies.append({
                "iteration": iteration,
                "subproblem": sp_idx,
                "energy": energy,
                "num_vehicles": len(valid_vehicles),
                "has_emergency": any(v.get("type") == "emergency"
                                     for v in valid_vehicles)
            })

            selected = decode_subproblem(sample, var_map, valid_vehicles)
            iteration_routes.update(selected)
            update_congestion(G, selected)

        final_routes.update(iteration_routes)

    metrics = compute_solution_metrics(final_routes, vehicles, graph)
    metrics["iteration_energies"] = iteration_energies

    return final_routes, metrics


# ==================================================
# 4. METRICS / EVALUATION
# ==================================================

def compute_route_travel_time(route, graph):
    """
    Compute the total travel time (in minutes) for a single route.
    Reads the 'travel_time' attribute from graph edges.
    """
    total = 0.0
    for i in range(len(route) - 1):
        u, v = route[i], route[i + 1]
        if graph.has_edge(u, v):
            data = graph[u][v]
            if isinstance(data, dict) and 0 in data:
                data = data[0]
            total += data.get("travel_time", data.get("length", 1.0))
    return total


def compute_solution_metrics(selected_routes, vehicles, graph):
    """
    Compute evaluation metrics for the solution.
    """
    esv_travel_times = []
    regular_travel_times = []

    for v in vehicles:
        vid = v["vehicle_id"]
        route = selected_routes.get(vid)
        if route is None:
            continue

        cost = compute_route_travel_time(route, graph)

        if v.get("type") == "emergency":
            esv_travel_times.append(cost)
        else:
            regular_travel_times.append(cost)

    return {
        "esv_avg_travel_time": float(np.mean(esv_travel_times))
                                if esv_travel_times else 0.0,
        "esv_total_travel_time": float(sum(esv_travel_times)),
        "regular_avg_travel_time": float(np.mean(regular_travel_times))
                                    if regular_travel_times else 0.0,
        "regular_total_travel_time": float(sum(regular_travel_times)),
        "total_vehicles_routed": len(selected_routes),
        "emergency_vehicles_routed": len(esv_travel_times),
        "regular_vehicles_routed": len(regular_travel_times),
        "aggregate_network_latency": float(sum(esv_travel_times)
                                           + sum(regular_travel_times)),
    }


def compare_standard_vs_priority(vehicles, graph, method="neal", seed=42):
    """
    Run both standard (no priority) and priority-aware MTF,
    then compare results. This produces the evaluation data
    mentioned in the abstract.

    Args:
        seed (int): Random seed for reproducible comparisons.
    """
    # --- Standard optimization (all vehicles weight = 1) ---
    random.seed(seed)
    np.random.seed(seed)
    standard_vehicles = deepcopy(vehicles)
    for v in standard_vehicles:
        v["priority_weight"] = 1

    std_routes, std_metrics = priority_aware_mtf_solve(
        standard_vehicles, graph,
        method=method,
        emergency_boost=1.0,
    )

    # --- Priority-Aware optimization ---
    random.seed(seed)
    np.random.seed(seed)
    pri_routes, pri_metrics = priority_aware_mtf_solve(
        vehicles, graph,
        method=method,
        emergency_boost=10.0,
    )

    # --- Comparison ---
    comparison = {
        "standard": std_metrics,
        "priority_aware": pri_metrics,
    }

    if std_metrics["esv_avg_travel_time"] > 0:
        esv_improvement = (
            (std_metrics["esv_avg_travel_time"]
             - pri_metrics["esv_avg_travel_time"])
            / std_metrics["esv_avg_travel_time"] * 100
        )
    else:
        esv_improvement = 0.0

    if std_metrics["aggregate_network_latency"] > 0:
        latency_change = (
            (pri_metrics["aggregate_network_latency"]
             - std_metrics["aggregate_network_latency"])
            / std_metrics["aggregate_network_latency"] * 100
        )
    else:
        latency_change = 0.0

    comparison["esv_travel_time_reduction_pct"] = esv_improvement
    comparison["aggregate_latency_increase_pct"] = latency_change

    return comparison

# ==================================================
# 5. CLASSICAL BASELINES FOR EVALUATION
# ==================================================

def dijkstra_baseline(vehicles, graph):
    """
    Classical Baseline #1: Independent Dijkstra Shortest Path.

    Each vehicle independently gets the shortest path (by travel_time)
    from origin to destination. No inter-vehicle coordination, no
    priority awareness — pure classical shortest-path.

    This is the simplest possible baseline and represents what a
    standard GPS navigation system would do.

    Returns:
        selected_routes (dict): {vehicle_id: route}
        metrics (dict): same structure as compute_solution_metrics
    """
    import networkx as nx
    from copy import deepcopy

    G = deepcopy(graph)
    selected_routes = {}

    for v in vehicles:
        vid = v["vehicle_id"]
        origin = v["origin"]
        destination = v["destination"]
        candidates = v.get("candidate_routes", [])

        try:
            path = nx.shortest_path(G, origin, destination, weight="travel_time")
            selected_routes[vid] = path
        except Exception:
            # Fallback: use the first candidate route if Dijkstra fails
            if candidates:
                selected_routes[vid] = candidates[0]
            else:
                selected_routes[vid] = [origin, destination]

    metrics = compute_solution_metrics(selected_routes, vehicles, graph)
    return selected_routes, metrics


def greedy_priority_baseline(vehicles, graph):
    """
    Classical Baseline #2: Greedy Priority-First Sequential Assignment.

    Vehicles are sorted by priority weight (emergency first, then regular).
    Each vehicle greedily picks the shortest candidate route given the
    CURRENT congestion state, then congestion is updated before the next
    vehicle picks.

    This simulates a smart classical dispatcher that knows about priorities
    but doesn't do joint optimization (no QUBO, no quantum).

    Returns:
        selected_routes (dict): {vehicle_id: route}
        metrics (dict): same structure as compute_solution_metrics
    """
    from copy import deepcopy

    G = deepcopy(graph)
    selected_routes = {}

    # Sort: emergency vehicles first (highest priority_weight first)
    sorted_vehicles = sorted(
        vehicles,
        key=lambda v: v.get("priority_weight", 1),
        reverse=True
    )

    for v in sorted_vehicles:
        vid = v["vehicle_id"]
        candidates = v.get("candidate_routes", [])

        if not candidates:
            selected_routes[vid] = [v["origin"], v["destination"]]
            continue

        # Pick the candidate route with lowest current travel time
        best_route = None
        best_cost = float("inf")

        for route in candidates:
            cost = compute_route_travel_time(route, G)
            if cost < best_cost:
                best_cost = cost
                best_route = route

        if best_route is None:
            best_route = candidates[0]

        selected_routes[vid] = best_route

        # Update congestion on the graph so next vehicles see the load
        for i in range(len(best_route) - 1):
            u, w = best_route[i], best_route[i + 1]
            if G.has_edge(u, w):
                data = G[u][w]
                if isinstance(data, dict) and 0 in data:
                    data = data[0]
                data["congestion"] = data.get("congestion", 0) + 1
                # Recompute travel_time
                length_km = data.get("length", 100) / 1000.0
                speed_kmph = max(data.get("speed", 40), 1)
                base_time = (length_km / speed_kmph) * 60
                congestion_factor = 1.0 + (data["congestion"] / 20.0)
                data["travel_time"] = base_time * congestion_factor

    metrics = compute_solution_metrics(selected_routes, vehicles, graph)
    return selected_routes, metrics


def compare_all_methods(vehicles, graph, method="neal", seed=42):
    """
    Run ALL four methods on the same scenario and return a unified
    comparison dictionary. This is used by evaluation.py and can
    also be called from the Streamlit benchmark tab.

    Methods compared:
        1. Dijkstra Baseline (classical, independent shortest paths)
        2. Greedy Priority-First (classical, sequential with priority)
        3. Standard QUBO MTF (quantum-inspired, no priority weights)
        4. Priority-Aware MTF (quantum-inspired, with ESV green corridors)

    Returns:
        dict with keys: dijkstra, greedy, standard_qubo, priority_mtf,
              plus computed percentage improvements.
    """
    import time as _time
    from copy import deepcopy

    results = {}

    # --- 1. Dijkstra Baseline ---
    random.seed(seed)
    np.random.seed(seed)
    t0 = _time.time()
    _, dij_metrics = dijkstra_baseline(vehicles, graph)
    dij_time = _time.time() - t0
    dij_metrics["solve_time_sec"] = round(dij_time, 3)
    results["dijkstra"] = dij_metrics

    # --- 2. Greedy Priority-First ---
    random.seed(seed)
    np.random.seed(seed)
    t0 = _time.time()
    _, greedy_metrics = greedy_priority_baseline(vehicles, graph)
    greedy_time = _time.time() - t0
    greedy_metrics["solve_time_sec"] = round(greedy_time, 3)
    results["greedy"] = greedy_metrics

    # --- 3. Standard QUBO MTF (all weights = 1, no priority) ---
    random.seed(seed)
    np.random.seed(seed)
    standard_vehicles = deepcopy(vehicles)
    for v in standard_vehicles:
        v["priority_weight"] = 1

    t0 = _time.time()
    _, std_metrics = priority_aware_mtf_solve(
        standard_vehicles, graph,
        method=method,
        emergency_boost=1.0,
    )
    std_time = _time.time() - t0
    std_metrics["solve_time_sec"] = round(std_time, 3)
    results["standard_qubo"] = std_metrics

    # --- 4. Priority-Aware MTF (the main contribution) ---
    random.seed(seed)
    np.random.seed(seed)
    t0 = _time.time()
    _, pri_metrics = priority_aware_mtf_solve(
        vehicles, graph,
        method=method,
        emergency_boost=10.0,
    )
    pri_time = _time.time() - t0
    pri_metrics["solve_time_sec"] = round(pri_time, 3)
    results["priority_mtf"] = pri_metrics

    # --- Percentage Improvements (Priority MTF vs each baseline) ---
    for baseline_key in ["dijkstra", "greedy", "standard_qubo"]:
        bl = results[baseline_key]
        pr = results["priority_mtf"]

        if bl["esv_avg_travel_time"] > 0:
            esv_improv = (
                (bl["esv_avg_travel_time"] - pr["esv_avg_travel_time"])
                / bl["esv_avg_travel_time"] * 100
            )
        else:
            esv_improv = 0.0

        if bl["aggregate_network_latency"] > 0:
            lat_change = (
                (pr["aggregate_network_latency"] - bl["aggregate_network_latency"])
                / bl["aggregate_network_latency"] * 100
            )
        else:
            lat_change = 0.0

        results[f"esv_reduction_vs_{baseline_key}_pct"] = round(esv_improv, 2)
        results[f"latency_change_vs_{baseline_key}_pct"] = round(lat_change, 2)

    return results