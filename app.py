"""
app.py
------
Streamlit demo for Priority-Aware Quantum Traffic Optimization
with Emergency Vehicle Green Corridors.

USER POV workflow:
- Auto-build initial traffic scenario on first load
- Show current traffic (blue = regular, green = emergency)
- Allow user to enter start/destination, snap to graph nodes, show ORIGINAL path
- On "Optimize Route" run QUBO including the user as a vehicle and show OPTIMIZED route

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

st.title("🚦 Priority-Aware Traffic Optimization")
st.write("Enter your journey details to see how quantum optimization creates efficient routes while prioritizing emergency vehicles.")


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

# --------------------------------------------------
# USER ROUTE INPUTS
# --------------------------------------------------
st.sidebar.markdown("---")
st.sidebar.markdown("### 📍 Your Journey")

user_start_addr = st.sidebar.text_input(
    "From", 
    "Fort Kochi",
    help="Enter your starting location"
)

user_end_addr = st.sidebar.text_input(
    "To", 
    "Ernakulam",
    help="Enter your destination"
)

# Auto-geocode addresses to coordinates
user_start_lat, user_start_lon = 0.0, 0.0
user_end_lat, user_end_lon = 0.0, 0.0

def smart_geocode(address, city, graph=None):
    """
    Smart geocoding with multiple fallback strategies.
    """
    # Strategy 1: Try full address
    attempts = [
        f"{address}, {city}",
        f"{address}, India",
        address,
    ]
    
    for attempt in attempts:
        try:
            location = ox.geocode(attempt)
            return location  # Returns (lat, lon)
        except:
            continue
    
    # Strategy 2: If we have a graph, use its center as fallback
    if graph is not None:
        try:
            # Get graph bounding box center
            nodes_gdf = ox.graph_to_gdfs(graph, nodes=True, edges=False)
            center = nodes_gdf.unary_union.centroid
            return (center.y, center.x)
        except:
            pass
    
    # Strategy 3: Default to Fort Kochi coordinates
    return (9.9674, 76.2425)  # Fort Kochi area

# Only geocode if graph is loaded and addresses are provided
if user_start_addr and user_end_addr and st.session_state.get("graph") is not None:
    G = st.session_state.get("graph")
    
    # Geocode start
    try:
        start_location = smart_geocode(user_start_addr, place, G)
        user_start_lat, user_start_lon = start_location
        start_success = True
    except Exception as e:
        st.sidebar.warning(f"⚠️ Using approximate location for start")
        user_start_lat, user_start_lon = 9.9674, 76.2425
        start_success = False
    
    # Geocode end
    try:
        end_location = smart_geocode(user_end_addr, place, G)
        user_end_lat, user_end_lon = end_location
        end_success = True
    except Exception as e:
        st.sidebar.warning(f"⚠️ Using approximate location for destination")
        user_end_lat, user_end_lon = 9.9312, 76.2673
        end_success = False
    
    # Show results
    if start_success and end_success:
        with st.sidebar.expander("📍 Found Locations", expanded=False):
            st.success(f"✓ Start: {user_start_lat:.4f}, {user_start_lon:.4f}")
            st.success(f"✓ End: {user_end_lat:.4f}, {user_end_lon:.4f}")
    else:
        st.sidebar.info("💡 Using approximate coordinates - results may vary")

optimize_button = st.sidebar.button("🚀 Optimize My Route", type="primary")


# --------------------------------------------------
# AUTO-BUILD ON LOAD: build network & simulate traffic if not present
# --------------------------------------------------
if st.session_state.get("graph") is None:
    with st.spinner("🌐 Loading road network..."):
        try:
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
            
        except Exception as e:
            st.error(f"❌ Failed to load network: {e}")
            st.info("💡 Try a different city or check internet connection")
            st.stop()


# --------------------------------------------------
# RE-RUN SIMULATION (if button clicked)
# --------------------------------------------------
if run_button:
    with st.spinner("🔄 Rebuilding traffic scenario..."):
        try:
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
            
            st.success("✅ Traffic scenario rebuilt!")
            
        except Exception as e:
            st.error(f"❌ Failed to rebuild: {e}")


# --------------------------------------------------
# COMPUTE ORIGINAL ROUTE (if addresses provided)
# --------------------------------------------------
has_user_coords = not (user_start_lat == 0.0 and user_start_lon == 0.0 
                       and user_end_lat == 0.0 and user_end_lon == 0.0)

if has_user_coords and st.session_state.get("graph") is not None:
    G = st.session_state.get("graph")
    try:
        start_node = ox.nearest_nodes(G, user_start_lon, user_start_lat)
        end_node = ox.nearest_nodes(G, user_end_lon, user_end_lat)
        
        try:
            original_route = nx.shortest_path(G, start_node, end_node, weight="length")
            st.session_state["original_route"] = original_route
            st.sidebar.success(f"✓ Route found: {len(original_route)} waypoints")
        except Exception as e:
            st.sidebar.warning(f"⚠️ No path found: {e}")
            st.session_state["original_route"] = None
    except Exception as e:
        st.sidebar.warning(f"⚠️ Couldn't snap to road: {e}")
        st.session_state["original_route"] = None


# --------------------------------------------------
# OPTIMIZATION (if button clicked)
# --------------------------------------------------
if optimize_button and st.session_state.get("graph") is not None:
    if st.session_state.get("original_route") is None:
        st.warning("⚠️ Please enter valid addresses first!")
        st.info("💡 Make sure both 'From' and 'To' fields are filled and the map has loaded")
    else:
        with st.spinner("⚛️ Running quantum optimization..."):
            try:
                G = st.session_state.get("graph")
                vehicles = list(st.session_state.get("vehicles") or [])

                user_orig = st.session_state.get("original_route")
                user_start_node = user_orig[0]
                user_end_node = user_orig[-1]

                # Build candidate routes for user
                user_candidates = find_candidate_routes(G, user_start_node, user_end_node, k=3)

                # Create user vehicle
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

                # Build QUBO
                bqm, variable_map = build_priority_aware_qubo(vehicles)

                # Solve
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
                    st.success("✅ Route optimized successfully!")
                else:
                    st.warning("⚠️ Optimizer didn't find an alternative route")
                    
            except Exception as e:
                st.error(f"❌ Optimization failed: {e}")


# --------------------------------------------------
# VISUALIZATION
# --------------------------------------------------
if st.session_state.get("graph") is not None:
    G = st.session_state.get("graph")
    emergency_routes = st.session_state.get("emergency_routes") or []
    regular_routes = st.session_state.get("regular_routes") or []
    original_route = st.session_state.get("original_route")
    optimized_route = st.session_state.get("optimized_route")

    # Get user markers
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

    # Create map
    m = visualize_traffic_map(
        G=G,
        regular_routes=regular_routes,
        emergency_routes=emergency_routes,
        original_route=original_route,
        optimized_route=optimized_route,
        user_start=user_start,
        user_end=user_end,
    )

    # Display
    st.subheader("🗺️ Traffic Optimization Map")
    
    # Legend
    col_leg1, col_leg2, col_leg3, col_leg4 = st.columns(4)
    col_leg1.markdown("🟦 **Regular Traffic**")
    col_leg2.markdown("🟩 **Emergency Vehicles**")
    col_leg3.markdown("🟥 **Your Original Route**")
    col_leg4.markdown("🟧 **Your Optimized Route**")
    
    # Map
    st_folium(m, width=1200, height=600)
    
    # Metrics (if user has route)
    if original_route or optimized_route:
        st.subheader("📊 Route Statistics")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if original_route:
                st.metric("Original Route", f"{len(original_route)} nodes")
        
        with col2:
            if optimized_route:
                improvement = len(original_route) - len(optimized_route) if original_route else 0
                st.metric("Optimized Route", f"{len(optimized_route)} nodes", 
                         delta=f"{improvement:+d} nodes")
        
        with col3:
            emergency_count = len([v for v in st.session_state.get("vehicles", []) 
                                 if v.get("type") == "emergency"])
            st.metric("Emergency Vehicles", emergency_count)

else:
    st.info("🌐 Loading network... Please wait")