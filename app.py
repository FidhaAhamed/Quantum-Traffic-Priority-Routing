"""
app.py
------
Streamlit demo for Priority-Aware Quantum Traffic Optimization
with Emergency Vehicle Green Corridors.

USER POV workflow:
- Auto-build initial traffic scenario on first load
- Show current traffic (blue = regular, green = emergency)
- Allow user to enter start/destination coords, snap to graph nodes, show ORIGINAL path (thin orange)
- On "Optimize Route" run QUBO including the user as a vehicle and show OPTIMIZED route (bold orange)

Do NOT store folium.Map in session_state. Store only lightweight route/graph data.
"""

import streamlit as st
from streamlit_folium import st_folium
import osmnx as ox
import networkx as nx

# Project modules
from network_builder import build_network_pipeline, find_candidate_routes
from traffic_simulator import build_traffic_scenario
from qubo_builder import build_priority_aware_qubo
from solver import solve_traffic_qubo
from visualization import visualize_traffic_map

# Initialize session_state keys we will persist (lightweight data only)
for key in (
    "graph",
    "vehicles",
    "traffic_routes",
    "regular_routes",
    "emergency_routes",
    "original_route",
    "optimized_route",
):
    if key not in st.session_state:
        st.session_state[key] = None

# --------------------------------------------------
# PAGE CONFIG
# --------------------------------------------------

st.set_page_config(
    page_title="Priority-Aware Quantum Traffic Optimization",
    layout="wide"
)

st.title("🚦 Priority-Aware Traffic — User POV")
st.write("This demo shows current traffic, allows you to enter a start/destination, view the original path, and run an optimization that prioritizes emergency vehicles.")


# --------------------------------------------------
# SIDEBAR
# --------------------------------------------------

st.sidebar.header("Simulation Controls")

place = st.sidebar.text_input("City / Area", "Fort Kochi, India")

# Time of day presets (controls simulation scale)
time_of_day = st.sidebar.selectbox(
    "Time of day",
    ["Early Morning", "Morning", "Noon", "Evening", "Night"],
)

# Preset mapping
_time_map = {
    "Early Morning": {"num_vehicles": 4, "emergency_ratio": 0.1},
    "Morning": {"num_vehicles": 12, "emergency_ratio": 0.3},
    "Noon": {"num_vehicles": 8, "emergency_ratio": 0.2},
    "Evening": {"num_vehicles": 15, "emergency_ratio": 0.35},
    "Night": {"num_vehicles": 5, "emergency_ratio": 0.15},
}

# Show sliders for visibility but override their values from the preset
_ = st.sidebar.slider("(Preset) Number of Vehicles", 3, 20, _time_map[time_of_day]["num_vehicles"], key="_num_vis")
_ = st.sidebar.slider("(Preset) Emergency Vehicle Ratio", 0.0, 1.0, _time_map[time_of_day]["emergency_ratio"], step=0.05, key="_em_vis")

# Use preset values
num_vehicles = _time_map[time_of_day]["num_vehicles"]
emergency_ratio = _time_map[time_of_day]["emergency_ratio"]

solver_type = st.sidebar.selectbox(
    "Optimization Method",
    ["Simulated Annealing (Local)", "Quantum-Hybrid (D-Wave)"]
)


run_button = st.sidebar.button("Run Simulation")

# --- New inputs: explicit user start/end coordinates (latitude/longitude)
st.sidebar.markdown("---")
st.sidebar.markdown("### User route inputs (optional)")
user_start_lat = st.sidebar.number_input("User Start Latitude", value=0.0, format="%.6f")
user_start_lon = st.sidebar.number_input("User Start Longitude", value=0.0, format="%.6f")
user_end_lat = st.sidebar.number_input("User Destination Latitude", value=0.0, format="%.6f")
user_end_lon = st.sidebar.number_input("User Destination Longitude", value=0.0, format="%.6f")

optimize_button = st.sidebar.button("Optimize Route")

# --------------------------------------------------
# AUTO-BUILD ON LOAD: build network & simulate traffic if not present
# --------------------------------------------------
if st.session_state.get("graph") is None:
    with st.spinner("Building road network and initial traffic scenario..."):
        network_data = build_network_pipeline(place_name=place, num_vehicles=num_vehicles)
        scenario = build_traffic_scenario(network_data, emergency_ratio=emergency_ratio)

        G = scenario["graph"]
        vehicles = scenario["vehicles"]

        traffic_routes = {}
        regular_routes = []
        emergency_routes = []

        for v in vehicles:
            vid = v["vehicle_id"]
            candidates = v.get("candidate_routes", [])
            chosen = candidates[0] if candidates else []
            traffic_routes[vid] = chosen
            if v.get("type") == "emergency":
                emergency_routes.append(chosen)
            else:
                regular_routes.append(chosen)

        st.session_state["graph"] = G
        st.session_state["vehicles"] = vehicles
        st.session_state["traffic_routes"] = traffic_routes
        st.session_state["regular_routes"] = regular_routes
        st.session_state["emergency_routes"] = emergency_routes


# --------------------------------------------------
# MAIN PIPELINE
# --------------------------------------------------

if run_button:
    # Re-run building the scenario (manual trigger)
    st.info("Rebuilding road network and traffic scenario...")
    network_data = build_network_pipeline(place_name=place, num_vehicles=num_vehicles)
    scenario = build_traffic_scenario(network_data, emergency_ratio=emergency_ratio)

    G = scenario["graph"]
    vehicles = scenario["vehicles"]

    traffic_routes = {}
    regular_routes = []
    emergency_routes = []

    for v in vehicles:
        vid = v["vehicle_id"]
        candidates = v.get("candidate_routes", [])
        chosen = candidates[0] if candidates else []
        traffic_routes[vid] = chosen
        if v.get("type") == "emergency":
            emergency_routes.append(chosen)
        else:
            regular_routes.append(chosen)

    st.session_state["graph"] = G
    st.session_state["vehicles"] = vehicles
    st.session_state["traffic_routes"] = traffic_routes
    st.session_state["regular_routes"] = regular_routes
    st.session_state["emergency_routes"] = emergency_routes

# If user provides coordinates (non-zero), snap and compute original route
has_user_coords = not (
    user_start_lat == 0.0
    and user_start_lon == 0.0
    and user_end_lat == 0.0
    and user_end_lon == 0.0
)

if has_user_coords and st.session_state.get("graph") is not None:
    G = st.session_state.get("graph")
    try:
        start_node = ox.nearest_nodes(G, user_start_lon, user_start_lat)
        end_node = ox.nearest_nodes(G, user_end_lon, user_end_lat)
        try:
            original_route = nx.shortest_path(G, start_node, end_node, weight="length")
            st.session_state["original_route"] = original_route
        except Exception as e:
            st.warning(f"Could not compute original shortest path: {e}")
            st.session_state["original_route"] = None
    except Exception as e:
        st.warning(f"Could not snap user coordinates to graph nodes: {e}")
        st.session_state["original_route"] = None

# Optimization: when user clicks optimize_button, include the user as a vehicle and solve
if optimize_button and st.session_state.get("graph") is not None:
    if st.session_state.get("original_route") is None:
        st.warning("Please enter valid start/end coordinates (and ensure they snap to the graph) before optimizing.")
    else:
        G = st.session_state.get("graph")
        vehicles = list(st.session_state.get("vehicles") or [])

        user_orig = st.session_state.get("original_route")
        user_start_node = user_orig[0]
        user_end_node = user_orig[-1]

        # Build candidate routes for the user (k-shortest)
        user_candidates = find_candidate_routes(G, user_start_node, user_end_node, k=3)

        # Create user vehicle and append
        user_vid = len(vehicles)
        user_vehicle = {
            "vehicle_id": user_vid,
            "origin": user_start_node,
            "destination": user_end_node,
            "type": "user",
            "priority_weight": 1,
            "candidate_routes": user_candidates,
        }
        vehicles.append(user_vehicle)

        st.info("Building priority-aware QUBO (including user vehicle)...")
        bqm, variable_map = build_priority_aware_qubo(vehicles)

        st.info("Solving optimization problem...")
        method = "sa" if "Simulated" in solver_type else "dwave"

        selected_routes = solve_traffic_qubo(
            bqm=bqm,
            variable_map=variable_map,
            vehicles=vehicles,
            method=method,
        )

        optimized_route = selected_routes.get(user_vid)
        if optimized_route:
            st.session_state["optimized_route"] = optimized_route
        else:
            st.warning("Optimizer did not return a route for the user.")
else:
    st.info("Set parameters and click **Run Optimization** to start.")

# If we have a stored graph, rebuild the folium.Map each rerun from session_state
if st.session_state.get("graph") is not None:
    G = st.session_state.get("graph")
    emergency_routes = st.session_state.get("emergency_routes") or []
    regular_routes = st.session_state.get("regular_routes") or []
    original_route = st.session_state.get("original_route")
    optimized_route = st.session_state.get("optimized_route")

    # Compute user start/end for markers (prefer original_route then optimized_route)
    if original_route and len(original_route) >= 1:
        start_node = original_route[0]
        end_node = original_route[-1]
        user_start = (G.nodes[start_node]["y"], G.nodes[start_node]["x"])
        user_end = (G.nodes[end_node]["y"], G.nodes[end_node]["x"])
    elif optimized_route and len(optimized_route) >= 1:
        start_node = optimized_route[0]
        end_node = optimized_route[-1]
        user_start = (G.nodes[start_node]["y"], G.nodes[start_node]["x"])
        user_end = (G.nodes[end_node]["y"], G.nodes[end_node]["x"])
    else:
        first_node = next(iter(G.nodes))
        user_start = (G.nodes[first_node]["y"], G.nodes[first_node]["x"])
        user_end = user_start

    m = visualize_traffic_map(
        G=G,
        regular_routes=regular_routes,
        emergency_routes=emergency_routes,
        original_route=original_route,
        optimized_route=optimized_route,
        user_start=user_start,
        user_end=user_end,
    )

    st.subheader("🗺️ Traffic — User POV")
    st_folium(m, width=1000, height=600)
else:
    st.info("Waiting for network build...")