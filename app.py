"""
app.py
------
Streamlit demo for Priority-Aware Quantum Traffic Optimization
with Emergency Vehicle Green Corridors.

This file orchestrates:
- Network building
- Traffic simulation
- QUBO formulation
- Optimization (quantum-ready)
- Visualization

Author: Your Team
"""

import streamlit as st

# --------------------------------------------------
# PROJECT MODULE IMPORTS
# --------------------------------------------------

from network_builder import build_network_pipeline
from traffic_simulator import build_traffic_scenario
from qubo_builder import build_priority_aware_qubo
from solver import solve_traffic_qubo
from visualization import visualize_traffic


# --------------------------------------------------
# STREAMLIT PAGE CONFIG
# --------------------------------------------------

st.set_page_config(
    page_title="Priority-Aware Quantum Traffic Optimization",
    layout="wide"
)

st.title("🚦 Priority-Aware Quantum Traffic Optimization")
st.subheader("Emergency Vehicle Green Corridor Demonstration")


# --------------------------------------------------
# SIDEBAR CONTROLS
# --------------------------------------------------

st.sidebar.header("Simulation Controls")

place = st.sidebar.text_input(
    "City / Area",
    value="Fort Kochi, India"
)

num_vehicles = st.sidebar.slider(
    "Number of Vehicles",
    min_value=3,
    max_value=15,
    value=6
)

emergency_ratio = st.sidebar.slider(
    "Emergency Vehicle Ratio",
    min_value=0.1,
    max_value=0.5,
    value=0.3
)

solver_type = st.sidebar.selectbox(
    "Optimization Method",
    ["Simulated Annealing (Local)", "Quantum-Hybrid (D-Wave)"]
)

run_button = st.sidebar.button("Run Optimization")


# --------------------------------------------------
# MAIN EXECUTION PIPELINE
# --------------------------------------------------

if run_button:

    # -------------------------------
    # 1. BUILD ROAD NETWORK
    # -------------------------------
    st.info("Building real-world road network...")

    network_data = build_network_pipeline(
        place_name=place,
        num_vehicles=num_vehicles
    )

    # -------------------------------
    # 2. SIMULATE TRAFFIC
    # -------------------------------
    st.info("Simulating traffic scenario...")

    scenario = build_traffic_scenario(
        network_data,
        emergency_ratio=emergency_ratio
    )

    G = scenario["graph"]
    vehicles = scenario["vehicles"]

    emergency_vehicles = [v for v in vehicles if v["type"] == "emergency"]

    st.success(f"Total Vehicles: {len(vehicles)}")
    st.success(f"Emergency Vehicles: {len(emergency_vehicles)}")

    # -------------------------------
    # 3. BUILD PRIORITY-AWARE QUBO
    # -------------------------------
    st.info("Formulating Priority-Aware QUBO model...")

    bqm, variable_map = build_priority_aware_qubo(vehicles)

    # -------------------------------
    # 4. SOLVE OPTIMIZATION PROBLEM
    # -------------------------------
    st.info("Solving optimization problem...")

    method = "sa" if "Simulated" in solver_type else "dwave"

    with st.spinner("Running quantum-ready optimization..."):
        selected_routes = solve_traffic_qubo(
            bqm=bqm,
            variable_map=variable_map,
            vehicles=vehicles,
            method=method
        )

    # -------------------------------
    # 5. SEPARATE ROUTES
    # -------------------------------
    emergency_routes = []
    regular_routes = []

    for v in vehicles:
        vid = v["vehicle_id"]
        if vid in selected_routes:
            if v["type"] == "emergency":
                emergency_routes.append(selected_routes[vid])
            else:
                regular_routes.append(selected_routes[vid])

    # -------------------------------
    # 6. VISUALIZATION
    # -------------------------------
    st.subheader("🗺️ Optimized Traffic Flow")
    st.caption("🟩 Green = Emergency Corridors | 🟦 Blue = Regular Traffic")

    fig = visualize_traffic(
        G,
        regular_routes=regular_routes,
        emergency_routes=emergency_routes
    )

    st.pyplot(fig)

    # -------------------------------
    # 7. RESULTS SUMMARY
    # -------------------------------
    st.subheader("📊 Optimization Summary")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 🚑 Emergency Vehicles")
        for v in emergency_vehicles:
            st.write(f"Vehicle {v['vehicle_id']} → Priority route assigned")

    with col2:
        st.markdown("### 🚗 Regular Vehicles")
        for i, _ in enumerate(regular_routes):
            st.write(f"Vehicle {i} → Optimized route assigned")

else:
    st.info("Set parameters in the sidebar and click **Run Optimization** to start.")