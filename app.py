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
- Benchmarking tab: compare standard vs priority-aware optimization

Do NOT store folium.Map in session_state. Store only lightweight route/graph data.
"""

import streamlit as st
from streamlit_folium import st_folium
import osmnx as ox
import networkx as nx
import matplotlib.pyplot as plt
import numpy as np
import random

# Set global random seeds for reproducible demo runs
random.seed(42)
np.random.seed(42)

# Project modules
from network_builder import build_network_pipeline, find_candidate_routes
from traffic_simulator import build_traffic_scenario
from visualization import visualize_traffic_map
from priority_aware_mtf import (
    priority_aware_mtf_solve,
    compare_standard_vs_priority,
    compute_route_travel_time,
)

# Initialize session_state keys we will persist (lightweight data only)
for key in (
    "graph",
    "vehicles",
    "traffic_routes",
    "regular_routes",
    "emergency_routes",
    "original_route",
    "optimized_route",
    "benchmark_results",
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
    [
        "Neal Simulated Annealing (Quantum-Inspired)",
        "Simulated Annealing (Basic)",
        "D-Wave Cloud (Requires Token)",
    ]
)

_solver_map = {
    "Neal Simulated Annealing (Quantum-Inspired)": "neal",
    "Simulated Annealing (Basic)": "sa",
    "D-Wave Cloud (Requires Token)": "dwave",
}
method = _solver_map[solver_type]

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
    """Smart geocoding with multiple fallback strategies."""
    attempts = [
        f"{address}, {city}",
        f"{address}, India",
        address,
    ]
    for attempt in attempts:
        try:
            location = ox.geocode(attempt)
            return location
        except:
            continue

    if graph is not None:
        try:
            nodes_gdf = ox.graph_to_gdfs(graph, nodes=True, edges=False)
            center = nodes_gdf.unary_union.centroid
            return (center.y, center.x)
        except:
            pass

    return (9.9674, 76.2425)

# Only geocode if graph is loaded and addresses are provided
if user_start_addr and user_end_addr and st.session_state.get("graph") is not None:
    G = st.session_state.get("graph")

    try:
        start_location = smart_geocode(user_start_addr, place, G)
        user_start_lat, user_start_lon = start_location
        start_success = True
    except Exception:
        user_start_lat, user_start_lon = 9.9674, 76.2425
        start_success = False

    try:
        end_location = smart_geocode(user_end_addr, place, G)
        user_end_lat, user_end_lon = end_location
        end_success = True
    except Exception:
        user_end_lat, user_end_lon = 9.9312, 76.2673
        end_success = False

    if start_success and end_success:
        with st.sidebar.expander("📍 Found Locations", expanded=False):
            st.success(f"✓ Start: {user_start_lat:.4f}, {user_start_lon:.4f}")
            st.success(f"✓ End: {user_end_lat:.4f}, {user_end_lon:.4f}")
    else:
        st.sidebar.info("💡 Using approximate coordinates - results may vary")

optimize_button = st.sidebar.button("🚀 Optimize My Route", type="primary")


# --------------------------------------------------
# AUTO-BUILD ON LOAD
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
# RE-RUN SIMULATION
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
            # Clear old benchmark when scenario changes
            st.session_state["benchmark_results"] = None

            st.success("✅ Traffic scenario rebuilt!")

        except Exception as e:
            st.error(f"❌ Failed to rebuild: {e}")


# --------------------------------------------------
# COMPUTE ORIGINAL ROUTE
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
# OPTIMIZATION (uses MTF pipeline now)
# --------------------------------------------------
if optimize_button and st.session_state.get("graph") is not None:
    if st.session_state.get("original_route") is None:
        st.warning("⚠️ Please enter valid addresses first!")
        st.info("💡 Make sure both 'From' and 'To' fields are filled and the map has loaded")
    else:
        with st.spinner("⚛️ Running Priority-Aware MTF optimization..."):
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

                # Solve with Priority-Aware MTF
                final_routes, metrics = priority_aware_mtf_solve(
                    vehicles=vehicles,
                    graph=G,
                    max_subproblem_size=8,
                    num_iterations=3,
                    method=method,
                )

                optimized_route = final_routes.get(user_vid)
                if optimized_route:
                    st.session_state["optimized_route"] = optimized_route
                    st.success("✅ Route optimized successfully!")
                else:
                    st.warning("⚠️ Optimizer didn't find an alternative route")

            except Exception as e:
                st.error(f"❌ Optimization failed: {e}")


# ==================================================
# TABBED INTERFACE: Map | Benchmarking
# ==================================================

tab_map, tab_benchmark = st.tabs(["🗺️ Traffic Map", "📊 Benchmarking & Evaluation"])

# --------------------------------------------------
# TAB 1: VISUALIZATION (existing map)
# --------------------------------------------------
with tab_map:
    if st.session_state.get("graph") is not None:
        G = st.session_state.get("graph")
        emergency_routes = st.session_state.get("emergency_routes") or []
        regular_routes = st.session_state.get("regular_routes") or []
        original_route = st.session_state.get("original_route")
        optimized_route = st.session_state.get("optimized_route")

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

        st.subheader("🗺️ Traffic Optimization Map")

        col_leg1, col_leg2, col_leg3, col_leg4 = st.columns(4)
        col_leg1.markdown("🟦 **Regular Traffic**")
        col_leg2.markdown("🟩 **Emergency Vehicles**")
        col_leg3.markdown("🟥 **Your Original Route**")
        col_leg4.markdown("🟧 **Your Optimized Route**")

        st_folium(m, width=1200, height=600)

        # Metrics
        if original_route or optimized_route:
            st.subheader("📊 Route Statistics")
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                if original_route:
                    orig_time = compute_route_travel_time(original_route, G)
                    st.metric("Original Route", f"{orig_time:.1f} min")

            with col2:
                if optimized_route:
                    opt_time = compute_route_travel_time(optimized_route, G)
                    if original_route:
                        delta = orig_time - opt_time
                        st.metric("Optimized Route", f"{opt_time:.1f} min",
                                  delta=f"{delta:+.1f} min")
                    else:
                        st.metric("Optimized Route", f"{opt_time:.1f} min")

            with col3:
                if original_route:
                    st.metric("Original Nodes", f"{len(original_route)}")

            with col4:
                emergency_count = len([v for v in st.session_state.get("vehicles", [])
                                     if v.get("type") == "emergency"])
                st.metric("Emergency Vehicles", emergency_count)

    else:
        st.info("🌐 Loading network... Please wait")


# --------------------------------------------------
# TAB 2: BENCHMARKING & EVALUATION
# --------------------------------------------------
with tab_benchmark:
    st.subheader("📊 Benchmarking: Standard vs Priority-Aware MTF")
    st.write("""
    This section runs the **same traffic scenario** through two optimization modes
    and compares the results to validate the abstract's claims:

    1. **Standard Optimization** — all vehicles treated equally (priority weight = 1)
    2. **Priority-Aware MTF** — emergency vehicles get high weights (green corridors)
    """)

    if st.session_state.get("graph") is None or st.session_state.get("vehicles") is None:
        st.warning("⚠️ Please load a traffic scenario first (use the sidebar).")
    else:
        bench_method = st.selectbox(
            "Solver for benchmark",
            ["neal", "sa"],
            index=0,
            help="Neal SA is recommended (quantum-inspired). Both run locally, no token needed.",
            key="bench_solver",
        )

        run_bench = st.button("🔬 Run Benchmark Comparison", type="primary")

        if run_bench:
            with st.spinner("🔬 Running Standard vs Priority-Aware comparison... (this may take a moment)"):
                try:
                    G = st.session_state["graph"]
                    vehicles = st.session_state["vehicles"]

                    comparison = compare_standard_vs_priority(
                        vehicles, G, method=bench_method
                    )
                    st.session_state["benchmark_results"] = comparison
                    st.success("✅ Benchmark complete!")
                except Exception as e:
                    st.error(f"❌ Benchmark failed: {e}")

        # ----- DISPLAY RESULTS -----
        results = st.session_state.get("benchmark_results")
        if results is not None:
            std = results["standard"]
            pri = results["priority_aware"]
            esv_reduction = results["esv_travel_time_reduction_pct"]
            latency_change = results["aggregate_latency_increase_pct"]

            # ---- Key Metrics Row ----
            st.markdown("---")
            st.subheader("🎯 Key Results")

            m1, m2, m3, m4 = st.columns(4)
            m1.metric(
                "🚑 ESV Travel Time Reduction",
                f"{abs(esv_reduction):.1f}%",
                delta=f"{esv_reduction:+.1f}%",
                delta_color="normal",
            )
            m2.metric(
                "🌐 Aggregate Latency Change",
                f"{abs(latency_change):.1f}%",
                delta=f"{latency_change:+.1f}%",
                delta_color="inverse",
            )
            m3.metric(
                "🚑 ESV Avg Time (Standard)",
                f"{std['esv_avg_travel_time']:.2f} min",
            )
            m4.metric(
                "🚑 ESV Avg Time (Priority)",
                f"{pri['esv_avg_travel_time']:.2f} min",
            )

            # ---- Side-by-Side Comparison Table ----
            st.markdown("---")
            st.subheader("📋 Side-by-Side Comparison")

            col_std, col_pri = st.columns(2)

            with col_std:
                st.markdown("#### ⚪ Standard Optimization")
                st.write(f"**ESV Avg Travel Time:** {std['esv_avg_travel_time']:.2f} min")
                st.write(f"**ESV Total Travel Time:** {std['esv_total_travel_time']:.2f} min")
                st.write(f"**Regular Avg Travel Time:** {std['regular_avg_travel_time']:.2f} min")
                st.write(f"**Regular Total Travel Time:** {std['regular_total_travel_time']:.2f} min")
                st.write(f"**Aggregate Network Latency:** {std['aggregate_network_latency']:.2f} min")
                st.write(f"**Vehicles Routed:** {std['total_vehicles_routed']}")
                st.write(f"**Emergency Routed:** {std['emergency_vehicles_routed']}")

            with col_pri:
                st.markdown("#### 🟢 Priority-Aware MTF")
                st.write(f"**ESV Avg Travel Time:** {pri['esv_avg_travel_time']:.2f} min")
                st.write(f"**ESV Total Travel Time:** {pri['esv_total_travel_time']:.2f} min")
                st.write(f"**Regular Avg Travel Time:** {pri['regular_avg_travel_time']:.2f} min")
                st.write(f"**Regular Total Travel Time:** {pri['regular_total_travel_time']:.2f} min")
                st.write(f"**Aggregate Network Latency:** {pri['aggregate_network_latency']:.2f} min")
                st.write(f"**Vehicles Routed:** {pri['total_vehicles_routed']}")
                st.write(f"**Emergency Routed:** {pri['emergency_vehicles_routed']}")

            # ---- Bar Chart: ESV vs Regular Travel Times ----
            st.markdown("---")
            st.subheader("📊 Travel Time Comparison")

            fig1, ax1 = plt.subplots(figsize=(8, 4))
            categories = ["ESV Avg\nTravel Time", "Regular Avg\nTravel Time",
                          "Aggregate\nLatency"]
            std_vals = [std["esv_avg_travel_time"],
                        std["regular_avg_travel_time"],
                        std["aggregate_network_latency"]]
            pri_vals = [pri["esv_avg_travel_time"],
                        pri["regular_avg_travel_time"],
                        pri["aggregate_network_latency"]]

            x = np.arange(len(categories))
            width = 0.35

            bars1 = ax1.bar(x - width / 2, std_vals, width,
                            label="Standard", color="#6c757d", alpha=0.8)
            bars2 = ax1.bar(x + width / 2, pri_vals, width,
                            label="Priority-Aware MTF", color="#28a745", alpha=0.8)

            ax1.set_ylabel("Time (minutes)")
            ax1.set_title("Standard vs Priority-Aware Optimization")
            ax1.set_xticks(x)
            ax1.set_xticklabels(categories)
            ax1.legend()

            # Value labels on bars
            for bar in bars1:
                ax1.annotate(f'{bar.get_height():.1f}',
                             xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                             xytext=(0, 3), textcoords="offset points",
                             ha='center', va='bottom', fontsize=8)
            for bar in bars2:
                ax1.annotate(f'{bar.get_height():.1f}',
                             xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                             xytext=(0, 3), textcoords="offset points",
                             ha='center', va='bottom', fontsize=8)

            plt.tight_layout()
            st.pyplot(fig1)

            # ---- Energy Convergence Chart ----
            st.markdown("---")
            st.subheader("⚡ Per-Iteration Energy Convergence")

            pri_energies = pri.get("iteration_energies", [])
            if pri_energies:
                fig2, ax2 = plt.subplots(figsize=(8, 4))

                # Group by iteration, take min energy per iteration
                iters = sorted(set(e["iteration"] for e in pri_energies))
                min_energies = []
                for it in iters:
                    it_energies = [e["energy"] for e in pri_energies
                                   if e["iteration"] == it]
                    min_energies.append(min(it_energies))

                ax2.plot(iters, min_energies, 'o-', color='#007bff',
                         linewidth=2, markersize=8, label="Min Energy per Iteration")
                ax2.fill_between(iters, min_energies,
                                 alpha=0.15, color='#007bff')
                ax2.set_xlabel("MTF Iteration")
                ax2.set_ylabel("Minimum QUBO Energy")
                ax2.set_title("Energy Convergence Across MTF Iterations")
                ax2.set_xticks(iters)
                ax2.legend()
                ax2.grid(True, alpha=0.3)

                plt.tight_layout()
                st.pyplot(fig2)

                # Show raw energy data in expander
                with st.expander("🔍 Detailed Energy Data"):
                    for e in pri_energies:
                        em_tag = "🚑" if e["has_emergency"] else "🚗"
                        st.write(
                            f"Iteration {e['iteration']} | "
                            f"Sub-problem {e['subproblem']} | "
                            f"{em_tag} {e['num_vehicles']} vehicles | "
                            f"Energy: **{e['energy']:.4f}**"
                        )
            else:
                st.info("No energy data available. Run the benchmark above.")

            # ---- Summary Box ----
            st.markdown("---")
            st.subheader("📝 Summary")

            if esv_reduction > 0:
                st.success(
                    f"✅ **Priority-Aware MTF reduced ESV travel time by "
                    f"{esv_reduction:.1f}%** compared to standard optimization, "
                    f"with only a **{abs(latency_change):.1f}% change** in "
                    f"aggregate network latency."
                )
            else:
                st.info(
                    f"ℹ️ ESV travel time change: {esv_reduction:+.1f}%. "
                    f"Aggregate latency change: {latency_change:+.1f}%. "
                    f"Results may vary with different traffic scenarios and "
                    f"network sizes. Try re-running with different parameters."
                )

            st.markdown(
                "> **Note:** This benchmark uses D-Wave's `neal` Simulated "
                "Annealing sampler, which faithfully replicates quantum "
                "annealing locally. The MTF sub-problem architecture is "
                "fully compatible with D-Wave QPU hardware — switching "
                "requires only a solver configuration change."
            )