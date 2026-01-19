import matplotlib.pyplot as plt
import networkx as nx


def visualize_traffic(G, regular_routes, emergency_routes):
    pos = nx.spring_layout(G, seed=42)

    fig, ax = plt.subplots(figsize=(10, 8))

    # Base graph
    nx.draw(
        G, pos,
        node_size=5,
        edge_color="lightgray",
        with_labels=False,
        ax=ax
    )

    # Regular routes (blue)
    for route in regular_routes:
        edges = [(route[i], route[i+1]) for i in range(len(route)-1)]
        nx.draw_networkx_edges(
            G, pos,
            edgelist=edges,
            edge_color="blue",
            width=2,
            alpha=0.6,
            ax=ax
        )

    # Emergency routes (green)
    for route in emergency_routes:
        edges = [(route[i], route[i+1]) for i in range(len(route)-1)]
        nx.draw_networkx_edges(
            G, pos,
            edgelist=edges,
            edge_color="green",
            width=3,
            ax=ax
        )

    ax.set_title("Green: Emergency Corridors | Blue: Regular Traffic")
    return fig
#D:\mini_project\Quantum-Traffic-Priority-Routing\visualization.py