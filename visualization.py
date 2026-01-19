import folium


def visualize_traffic_map(
    G,
    user_route,
    emergency_routes,
    regular_routes,
    user_start,
    user_end
):
    # Center map at USER start
    m = folium.Map(location=user_start, zoom_start=13)

    # Start & End markers
    folium.Marker(
        user_start,
        popup="Your Start",
        icon=folium.Icon(color="orange", icon="play")
    ).add_to(m)

    folium.Marker(
        user_end,
        popup="Your Destination",
        icon=folium.Icon(color="red", icon="stop")
    ).add_to(m)

    # USER ROUTE (ORANGE)
    user_coords = [(G.nodes[n]["y"], G.nodes[n]["x"]) for n in user_route]
    folium.PolyLine(user_coords, color="orange", weight=6).add_to(m)

    # EMERGENCY ROUTES (GREEN)
    for route in emergency_routes:
        coords = [(G.nodes[n]["y"], G.nodes[n]["x"]) for n in route]
        folium.PolyLine(coords, color="green", weight=4, opacity=0.8).add_to(m)

    # REGULAR ROUTES (BLUE)
    for route in regular_routes:
        coords = [(G.nodes[n]["y"], G.nodes[n]["x"]) for n in route]
        folium.PolyLine(coords, color="blue", weight=2, opacity=0.5).add_to(m)

    return m
