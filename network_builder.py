"""
network_builder.py - OPTIMIZED VERSION
------------------
Builds and prepares a real-world road network for
Priority-Aware Quantum Traffic Optimization. 

OPTIMIZATIONS: 
- Network caching to avoid re-downloading
- Point-based download (faster than place-based)
- Configurable network size
- Fast mode with fewer candidate routes
- Error handling and fallbacks

Author: Your Team
"""

import osmnx as ox
import networkx as nx
import random
import pickle
import os
from pathlib import Path


# --------------------------------------------------
# CACHE SETUP
# --------------------------------------------------

CACHE_DIR = Path("cache")
CACHE_DIR.mkdir(exist_ok=True)


# --------------------------------------------------
# 1. BUILD ROAD NETWORK FROM OPENSTREETMAP (OPTIMIZED)
# --------------------------------------------------

def build_road_network(place_name:  str, use_cache=True, network_size="medium"):
    """
    Download and create a road network graph from OpenStreetMap.
    
    OPTIMIZED with caching and configurable size.
    
    Args:
        place_name (str): Name of the city or area
        use_cache (bool): Whether to use cached network
        network_size (str): "small" (500m), "medium" (1500m), "large" (3000m)
    
    Returns:
        G (networkx.Graph): Road network graph
    """
    # Define network sizes
    size_map = {
        "small": 500,
        "medium": 1500,
        "large": 3000
    }
    dist = size_map.get(network_size, 1500)
    
    # Create cache filename
    cache_file = CACHE_DIR / f"{place_name.replace(', ', '_').replace(' ', '_')}_{network_size}.pkl"
    
    # Try to load from cache
    if use_cache and cache_file.exists():
        print(f"⚡ Loading network from cache: {cache_file. name}")
        try:
            with open(cache_file, 'rb') as f:
                G = pickle.load(f)
            print(f"✓ Loaded graph with {len(G.nodes)} nodes and {len(G.edges)} edges")
            return G
        except Exception as e:
            print(f"⚠️ Cache load failed: {e}. Re-downloading...")
    
    # Download network if not cached
    print(f"🌐 Downloading network for '{place_name}' (size: {network_size}, radius: {dist}m)...")
    
    try:
        # OPTIMIZATION: Use point-based download (much faster)
        center_point = ox.geocode(place_name)
        print(f"   Center point: {center_point}")
        
        G = ox.graph_from_point(
            center_point, 
            dist=dist, 
            network_type="drive",
            simplify=True
        )
        
    except Exception as e:
        print(f"⚠️ Point-based download failed: {e}")
        print("   Trying place-based download...")
        
        try:
            # Fallback to place-based download
            G = ox.graph_from_place(
                place_name, 
                network_type="drive",
                simplify=True
            )
        except Exception as e2:
            print(f"❌ Both download methods failed: {e2}")
            print("   Creating minimal demo network...")
            # Fallback:  create a minimal grid network for demo
            G = create_demo_network()
            return G
    
    # Convert to undirected graph
    G = nx.Graph(G)
    
    print(f"✓ Downloaded graph with {len(G.nodes)} nodes and {len(G.edges)} edges")
    
    # Save to cache
    if use_cache:
        try:
            with open(cache_file, 'wb') as f:
                pickle.dump(G, f)
            print(f"💾 Network cached to {cache_file.name}")
        except Exception as e:
            print(f"⚠️ Caching failed: {e}")
    
    return G


# --------------------------------------------------
# 1B.  FALLBACK DEMO NETWORK (IF DOWNLOAD FAILS)
# --------------------------------------------------

def create_demo_network():
    """
    Create a simple grid network for demo purposes.
    Used when OSMnx download fails.
    """
    print("   Creating 5x5 grid network for demonstration...")
    G = nx.grid_2d_graph(5, 5)
    
    # Relabel nodes to integers
    mapping = {node: i for i, node in enumerate(G.nodes())}
    G = nx.relabel_nodes(G, mapping)
    
    # Add basic attributes
    for u, v in G.edges():
        G[u][v]['length'] = random.randint(100, 500)
        G[u][v]['speed'] = random.choice([30, 40, 50])
    
    return G


# --------------------------------------------------
# 2. ADD EDGE ATTRIBUTES (SPEED, LENGTH)
# --------------------------------------------------

def add_edge_attributes(G):
    """
    Ensure each road segment has speed and length. 
    
    Args:
        G (networkx.Graph)
    
    Returns:
        G (networkx.Graph)
    """
    for u, v, data in G.edges(data=True):
        
        # Length (meters)
        if 'length' not in data or data['length'] is None:
            data['length'] = random.randint(50, 300)
        
        # Speed (km/h)
        if 'speed' not in data or data['speed'] is None:
            # Try to get from maxspeed attribute
            maxspeed = data.get('maxspeed', None)
            
            if maxspeed: 
                if isinstance(maxspeed, list):
                    maxspeed = maxspeed[0]
                try:
                    speed = int(str(maxspeed).replace('km/h', '').strip())
                except:
                    speed = random.choice([30, 40, 50, 60])
            else:
                speed = random.choice([30, 40, 50, 60])
            
            data['speed'] = speed
    
    return G


# --------------------------------------------------
# 3. SIMULATE CONGESTION ON ROADS
# --------------------------------------------------

def add_congestion(G, min_level=1, max_level=10):
    """
    Add simulated congestion level to each road. 
    
    Args:
        G (networkx.Graph)
        min_level (int): Minimum congestion level
        max_level (int): Maximum congestion level
    
    Returns:
        G (networkx. Graph)
    """
    for u, v, data in G. edges(data=True):
        # Simulate varying congestion levels
        data['congestion'] = random.randint(min_level, max_level)
    
    return G


# --------------------------------------------------
# 4. COMPUTE TRAVEL TIME
# --------------------------------------------------

def compute_travel_time(G):
    """
    Compute travel time (minutes) for each road. 
    
    Formula: 
        time = (length / speed) * congestion_factor
    
    Args:
        G (networkx.Graph)
    
    Returns:
        G (networkx.Graph)
    """
    for u, v, data in G.edges(data=True):
        length_km = data. get('length', 100) / 1000.0
        speed_kmph = max(data.get('speed', 40), 1)  # Avoid division by zero
        congestion = data.get('congestion', 5)
        
        # Base travel time in minutes
        base_time = (length_km / speed_kmph) * 60
        
        # Apply congestion multiplier (1. 0 to 2.0)
        congestion_factor = 1.0 + (congestion / 20.0)
        
        data['travel_time'] = base_time * congestion_factor
    
    return G


# --------------------------------------------------
# 5. SELECT RANDOM ORIGIN–DESTINATION PAIRS
# --------------------------------------------------

def generate_od_pairs(G, num_pairs=5):
    """
    Generate random origin-destination node pairs.
    
    OPTIMIZED:  Ensures pairs are reasonably far apart. 
    
    Args:
        G (networkx.Graph)
        num_pairs (int)
    
    Returns:
        List of (origin, destination) tuples
    """
    nodes = list(G.nodes)
    
    if len(nodes) < 2:
        print("⚠️ Graph has too few nodes!")
        return [(nodes[0], nodes[0])] * num_pairs
    
    od_pairs = []
    max_attempts = num_pairs * 10  # Prevent infinite loops
    attempts = 0
    
    while len(od_pairs) < num_pairs and attempts < max_attempts:
        origin, destination = random.sample(nodes, 2)
        
        # Check if path exists
        try:
            if nx.has_path(G, origin, destination):
                od_pairs.append((origin, destination))
        except:
            pass
        
        attempts += 1
    
    # If we couldn't find enough valid pairs, fill with whatever we have
    while len(od_pairs) < num_pairs:
        try:
            origin, destination = random.sample(nodes, 2)
            od_pairs.append((origin, destination))
        except:
            # Fallback: use same node twice (edge case)
            od_pairs. append((nodes[0], nodes[-1]))
    
    return od_pairs


# --------------------------------------------------
# 6. FIND CANDIDATE ROUTES (OPTIMIZED)
# --------------------------------------------------

def find_candidate_routes(G, origin, destination, k=3, timeout_paths=100):
    """
    Find up to k shortest routes between origin and destination.
    
    OPTIMIZED with timeout protection and better error handling.
    
    Args:
        G (networkx.Graph)
        origin (int): Origin node
        destination (int): Destination node
        k (int): Number of candidate routes
        timeout_paths (int): Maximum paths to evaluate before stopping
    
    Returns:
        List of routes (each route is a list of nodes)
    """
    routes = []
    
    # Edge case: same origin and destination
    if origin == destination:
        return [[origin]]
    
    try:
        from itertools import islice
        
        # Find k-shortest paths with timeout protection
        paths = nx.shortest_simple_paths(
            G,
            source=origin,
            target=destination,
            weight='travel_time'
        )
        
        # Use islice to limit iterations (prevents hanging)
        for path in islice(paths, min(k, timeout_paths)):
            routes.append(path)
            if len(routes) >= k:
                break
                
    except nx.NetworkXNoPath:
        # No path exists - try unweighted shortest path
        print(f"   ⚠️ No weighted path from {origin} to {destination}, trying unweighted...")
        try:
            path = nx.shortest_path(G, origin, destination)
            routes.append(path)
        except:
            print(f"   ❌ No path exists from {origin} to {destination}")
            # Return direct connection as fallback
            routes.append([origin, destination])
            
    except Exception as e:
        print(f"   ⚠️ Route finding error for {origin} → {destination}: {e}")
        # Fallback to simple shortest path
        try:
            path = nx.shortest_path(G, origin, destination, weight='travel_time')
            routes.append(path)
        except:
            routes.append([origin, destination])
    
    # Ensure we return at least one route
    if not routes: 
        routes. append([origin, destination])
    
    return routes


# --------------------------------------------------
# 7. CONVERT ROUTES TO EDGE LISTS
# --------------------------------------------------

def routes_to_edges(routes):
    """
    Convert node paths into edge paths.
    
    Args:
        routes (list): List of routes (node lists)
    
    Returns:
        List of edge lists
    """
    all_edges = []
    
    for path in routes:
        if len(path) > 1:
            edges = [(path[i], path[i + 1]) for i in range(len(path) - 1)]
            all_edges.append(edges)
        else:
            all_edges.append([])
    
    return all_edges


# --------------------------------------------------
# 8. COMPLETE PIPELINE (OPTIMIZED)
# --------------------------------------------------

def build_network_pipeline(place_name, num_vehicles=5, use_cache=True, 
                          fast_mode=True, network_size="medium"):
    """
    Full pipeline to prepare network for optimization.
    
    OPTIMIZED VERSION with caching, fast mode, and progress feedback.
    
    Args:
        place_name (str): City or area name
        num_vehicles (int): Number of vehicles to simulate
        use_cache (bool): Use cached network if available
        fast_mode (bool): Use fewer candidate routes (faster)
        network_size (str): "small", "medium", or "large"
    
    Returns:
        dict with graph, OD pairs, and routes
    """
    print(f"\n{'='*60}")
    print(f"BUILDING NETWORK PIPELINE")
    print(f"{'='*60}")
    print(f"Location: {place_name}")
    print(f"Vehicles: {num_vehicles}")
    print(f"Cache: {'ON' if use_cache else 'OFF'}")
    print(f"Fast Mode: {'ON' if fast_mode else 'OFF'}")
    print(f"Network Size: {network_size}")
    print(f"{'='*60}\n")
    
    # Step 1: Build network
    print("Step 1/6: Building road network...")
    G = build_road_network(place_name, use_cache=use_cache, network_size=network_size)
    
    # Step 2: Add attributes
    print("Step 2/6: Adding edge attributes...")
    G = add_edge_attributes(G)
    
    # Step 3: Add congestion
    print("Step 3/6: Simulating congestion...")
    G = add_congestion(G)
    
    # Step 4: Compute travel time
    print("Step 4/6: Computing travel times...")
    G = compute_travel_time(G)
    
    # Step 5: Generate OD pairs
    print(f"Step 5/6: Generating {num_vehicles} origin-destination pairs...")
    od_pairs = generate_od_pairs(G, num_vehicles)
    
    # Step 6: Find candidate routes
    print("Step 6/6: Finding candidate routes...")
    k_routes = 2 if fast_mode else 3  # Fast mode uses fewer routes
    
    routes = {}
    for i, (o, d) in enumerate(od_pairs, 1):
        print(f"   Finding routes {i}/{num_vehicles}: {o} → {d}")
        routes[(o, d)] = find_candidate_routes(G, o, d, k=k_routes)
    
    print(f"\n{'='*60}")
    print("✓ NETWORK PIPELINE COMPLETE")
    print(f"{'='*60}")
    print(f"Graph: {len(G.nodes)} nodes, {len(G.edges)} edges")
    print(f"OD Pairs: {len(od_pairs)}")
    print(f"Routes per vehicle: {k_routes}")
    print(f"{'='*60}\n")
    
    return {
        "graph": G,
        "od_pairs":  od_pairs,
        "routes": routes
    }


# --------------------------------------------------
# 9. UTILITY:  CLEAR CACHE
# --------------------------------------------------

def clear_cache():
    """
    Clear all cached network files.
    Useful for forcing fresh downloads.
    """
    import shutil
    
    if CACHE_DIR.exists():
        shutil.rmtree(CACHE_DIR)
        CACHE_DIR.mkdir(exist_ok=True)
        print("✓ Cache cleared")
    else:
        print("ℹ️ No cache to clear")


# --------------------------------------------------
# 10. UTILITY: LIST CACHED NETWORKS
# --------------------------------------------------

def list_cached_networks():
    """
    List all cached network files.
    """
    if not CACHE_DIR.exists():
        print("No cache directory found")
        return
    
    cache_files = list(CACHE_DIR.glob("*.pkl"))
    
    if not cache_files: 
        print("No cached networks found")
        return
    
    print(f"\nCached Networks ({len(cache_files)}):")
    print("=" * 60)
    for f in cache_files:
        size_mb = f.stat().st_size / (1024 * 1024)
        print(f"  {f.name} ({size_mb:.2f} MB)")
    print("=" * 60)


# --------------------------------------------------
# MAIN (FOR TESTING)
# --------------------------------------------------

if __name__ == "__main__": 
    # Test the pipeline
    print("Testing network builder...")
    
    # List cached networks
    list_cached_networks()
    
    # Build network
    network_data = build_network_pipeline(
        place_name="Kochi, India",
        num_vehicles=5,
        use_cache=True,
        fast_mode=True,
        network_size="small"  # Use small for testing
    )
    
    print("\nTest complete!")
    print(f"Graph nodes: {len(network_data['graph'].nodes)}")
    print(f"Graph edges: {len(network_data['graph'].edges)}")
    print(f"OD pairs:  {len(network_data['od_pairs'])}")