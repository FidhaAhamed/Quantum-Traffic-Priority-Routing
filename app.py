"""
app.py
------
Streamlit demo for Priority-Aware Quantum Traffic Optimization
with Emergency Vehicle Green Corridors.
"""

import streamlit as st
import folium
from streamlit_folium import st_folium

# Project modules
from network_builder import build_network_pipeline
from traffic_simulator import build_traffic_scenario
from qubo_builder import build_priority_aware_qubo
from solver import solve_traffic_qubo
from visualization import visualize_traffic_map

if "results" not in st.session_state:
    st.session_state.results = None

# --------------------------------------------------
# PAGE CONFIG
# --------------------------------------------------

st.set_page_config(
    page_title="Priority-Aware Quantum Traffic Optimization",
    layout="wide"
)

st.title("🚦 Priority-Aware Quantum Traffic Optimization")
st.subheader("Emergency Vehicle Green Corridor Demonstration")


# --------------------------------------------------
# SIDEBAR
# --------------------------------------------------

st.sidebar.header("Simulation Controls")

place = st.sidebar.text_input("City / Area", "Fort Kochi, India")

num_vehicles = st.sidebar.slider("Number of Vehicles", 3, 15, 6)

emergency_ratio = st.sidebar.slider("Emergency Vehicle Ratio", 0.1, 0.5, 0.3)

solver_type = st.sidebar.selectbox(
    "Optimization Method",
    ["Simulated Annealing (Local)", "Quantum-Hybrid (D-Wave)"]
)

run_button = st.sidebar.button("Run Optimization")


# --------------------------------------------------
# MAIN PIPELINE
# --------------------------------------------------

if run_button:
    st.session_state.results = None

    st.info("Building road network...")
    network_data = build_network_pipeline(
        place_name=place,
        num_vehicles=num_vehicles
    )

    st.info("Simulating traffic...")
    scenario = build_traffic_scenario(
        network_data,
        emergency_ratio=emergency_ratio
    )

    G = scenario["graph"]
    vehicles = scenario["vehicles"]

    st.info("Building priority-aware QUBO...")
    bqm, variable_map = build_priority_aware_qubo(vehicles)

    method = "sa"

    with st.spinner("Running optimization..."):
        selected_routes = solve_traffic_qubo(
            bqm,
            variable_map,
            vehicles,
            method
        )

    st.session_state.results = {
        "graph": G,
        "vehicles": vehicles,
        "selected_routes": selected_routes
    }


else:
    st.info("Set parameters and click **Run Optimization** to start.")
