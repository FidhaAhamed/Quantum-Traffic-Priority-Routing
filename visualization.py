import folium

import osmnx as ox   # ⭐ MUST BE HERE


def visualize_traffic_map(
    G,
    original_route=None,
    optimized_route=None,
    emergency_routes=None,
    regular_routes=None,
    user_start=None,
    user_end=None,
):
    """Build a Folium map visualizing traffic and user routes.

    The map is centered on the graph centroid by default (computed at runtime).
    If `user_start` is provided it will be used as the map center instead.

    Args:
        G (networkx.Graph): Graph with node attributes 'x' (lon) and 'y' (lat).
        original_route (list, optional): node list for original (pre-optimization) route (RED dashed).
        optimized_route (list, optional): node list for optimized user route (ORANGE thick).
        emergency_routes (list[list], optional): list of node lists for emergency traffic (GREEN).
        regular_routes (list[list], optional): list of node lists for regular traffic (BLUE).
        user_start (tuple, optional): (lat, lon) to place the start marker and prefer as center.
        user_end (tuple, optional): (lat, lon) to place the end marker.

    Returns:
        folium.Map: A Folium map object (freshly created; nothing is executed at module level).
    """

    # Requirement: compute centroid here using the exact call
    center = ox.graph_to_gdfs(G, nodes=True, edges=False).geometry.unary_union.centroid
    map_center = (center.y, center.x)
    if user_start:
        map_center = user_start
    m = folium.Map(location=map_center, zoom_start=13)

    # Start & End markers (only if coordinates supplied)
    if user_start is not None:
        folium.Marker(
            location=user_start,
            popup="Your Start",
            icon=folium.Icon(color="orange", icon="play"),
        ).add_to(m)

    if user_end is not None:
        folium.Marker(
            location=user_end,
            popup="Your Destination",
            icon=folium.Icon(color="red", icon="stop"),
        ).add_to(m)

    # REGULAR ROUTES (BLUE)
    if regular_routes:
        for route in regular_routes:
            if not route:
                continue
            coords = [_safe_node_latlon(G, n) for n in route]
            folium.PolyLine(coords, color="blue", weight=2, opacity=0.6).add_to(m)

    # EMERGENCY ROUTES (GREEN)
    if emergency_routes:
        for route in emergency_routes:
            if not route:
                continue
            coords = [_safe_node_latlon(G, n) for n in route]
            folium.PolyLine(coords, color="green", weight=4, opacity=0.9).add_to(m)

    # ORIGINAL USER ROUTE (RED dashed, weight=3)
    if original_route:
        coords = [_safe_node_latlon(G, n) for n in original_route]
        folium.PolyLine(
            coords,
            color="red",
            weight=3,
            opacity=0.9,
            dash_array="6, 6",
            tooltip="Original (pre-optimization) Route",
        ).add_to(m)

    # OPTIMIZED USER ROUTE (ORANGE thick, weight=7, opacity=1.0)
    if optimized_route:
        coords = [_safe_node_latlon(G, n) for n in optimized_route]
        folium.PolyLine(
            coords,
            color="orange",
            weight=7,
            opacity=1.0,
            tooltip="Optimized Route",
        ).add_to(m)

    return m


def _safe_node_latlon(G, node):
    """Return (lat, lon) for a node in G, with safe fallbacks.

    This helper avoids raising if expected attributes are missing.
    Accepts typical OSMnx attributes 'y'/'x' or alternative 'lat'/'lon'.
    """
    data = G.nodes.get(node, {}) if hasattr(G, "nodes") else {}
    lat = data.get("y") if data is not None else None
    lon = data.get("x") if data is not None else None

    if lat is None or lon is None:
        # try alternative keys
        lat = data.get("lat", lat) if data is not None else lat
        lon = data.get("lon", lon) if data is not None else lon

    # Final fallbacks to 0.0 to avoid exceptions during drawing
    lat = lat if lat is not None else 0.0
    lon = lon if lon is not None else 0.0
    return (lat, lon)
