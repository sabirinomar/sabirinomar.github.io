"""Analyze Week 2 models and null models for the Marvel network.

The script reuses the frozen Week-1 node and edge files, preserving all 303
characters before adding edges. It produces static figures and a JSON summary
for the Week-2 course page.
"""

from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
FIGURE_DIR = REPO_ROOT / "assets" / "figures" / "week2"
SUMMARY_PATH = REPO_ROOT / "assets" / "week2_summary.json"
FIGURE_DIR.mkdir(parents=True, exist_ok=True)

RNG_SEED = 20260909
SHUFFLE_COUNT = 100


def load_network() -> tuple[pd.DataFrame, pd.DataFrame, nx.DiGraph]:
    """Load the Week-1 data and build a directed graph with all nodes."""
    nodes = pd.read_csv(DATA_DIR / "week1_nodes.tsv", sep="\t", comment="#", quoting=3)
    edges = pd.read_csv(
        DATA_DIR / "week1_edges.tsv",
        sep="\t",
        comment="#",
        names=["source", "target"],
    )

    graph = nx.DiGraph()
    graph.add_nodes_from(nodes["node_id"].tolist())
    graph.add_edges_from(edges[["source", "target"]].itertuples(index=False, name=None))
    return nodes, edges, graph


def ccdf(values: list[int]) -> tuple[list[int], list[float]]:
    """Return x values and P(K >= x) for a degree sequence."""
    counts = Counter(values)
    total = len(values)
    running = 0
    x_values = []
    probabilities = []
    for degree in sorted(counts, reverse=True):
        running += counts[degree]
        x_values.append(degree)
        probabilities.append(running / total)
    pairs = sorted(zip(x_values, probabilities))
    return [x for x, _ in pairs], [probability for _, probability in pairs]


def comparable_models(graph: nx.DiGraph) -> tuple[nx.Graph, nx.Graph, int]:
    """Create fixed-edge random and preferential-attachment comparators."""
    undirected = graph.to_undirected()
    n = undirected.number_of_nodes()
    edge_count = undirected.number_of_edges()
    ba_m = max(1, round(edge_count / n))
    ba_m = min(ba_m, n - 1)

    random_graph = nx.gnm_random_graph(n, edge_count, seed=RNG_SEED)
    ba_graph = nx.barabasi_albert_graph(n, ba_m, seed=RNG_SEED)
    return random_graph, ba_graph, ba_m


def save_ccdf_plot(
    real_graph: nx.Graph,
    random_graph: nx.Graph,
    ba_graph: nx.Graph,
    path: Path,
) -> dict:
    """Plot complementary cumulative degree distributions."""
    series = {
        "Marvel network": ccdf([degree for _, degree in real_graph.degree()]),
        "Random graph": ccdf([degree for _, degree in random_graph.degree()]),
        "Barabasi-Albert": ccdf([degree for _, degree in ba_graph.degree()]),
    }
    colors = {"Marvel network": "#ff5ea8", "Random graph": "#8d63ff", "Barabasi-Albert": "#e0a62d"}

    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    for label, (x_values, probabilities) in series.items():
        filtered = [(x, probability) for x, probability in zip(x_values, probabilities) if x > 0]
        ax.loglog(
            [x for x, _ in filtered],
            [probability for _, probability in filtered],
            "o-",
            ms=4,
            lw=1.8,
            label=label,
            color=colors[label],
        )
    ax.set_xlabel("Undirected degree k")
    ax.set_ylabel("P(K ≥ k)")
    ax.set_title("Marvel degree CCDF versus model networks")
    ax.grid(True, which="both", alpha=0.25)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return {
        label: {"degree": x_values, "ccdf": probabilities}
        for label, (x_values, probabilities) in series.items()
    }


def friendship_paradox(graph: nx.Graph, nodes: pd.DataFrame, path: Path) -> dict:
    """Measure neighbor-degree excess and identify popular local maxima."""
    names = nodes.set_index("node_id")["name"].to_dict()
    degrees = dict(graph.degree())
    neighbor_averages = {}
    excess = {}
    for node in graph.nodes():
        neighbors = list(graph.neighbors(node))
        average = sum(degrees[neighbor] for neighbor in neighbors) / len(neighbors) if neighbors else 0
        neighbor_averages[node] = average
        excess[node] = average - degrees[node]

    connected_nodes = [node for node in graph if degrees[node] > 0]
    paradox_nodes = [node for node in connected_nodes if excess[node] > 0]
    local_maxima = [
        node
        for node in connected_nodes
        if all(degrees[node] >= degrees[neighbor] for neighbor in graph.neighbors(node))
    ]
    popular_friend_counts = Counter(
        neighbor for node in paradox_nodes for neighbor in graph.neighbors(node)
    )
    top_popular_friends = [
        {
            "node": node,
            "name": names.get(node, node),
            "degree": degrees[node],
            "friend_appearances": count,
        }
        for node, count in popular_friend_counts.most_common(8)
    ]

    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    x_values = [degrees[node] for node in connected_nodes]
    y_values = [neighbor_averages[node] for node in connected_nodes]
    ax.scatter(x_values, y_values, s=28, alpha=0.55, color="#8d63ff", edgecolors="none")
    maximum_nodes = set(local_maxima)
    ax.scatter(
        [degrees[node] for node in maximum_nodes],
        [neighbor_averages[node] for node in maximum_nodes],
        s=42,
        color="#ff5ea8",
        label="No neighbour is more connected",
        zorder=3,
    )
    limit = max(x_values + y_values) + 2
    ax.plot([0, limit], [0, limit], "--", color="#6f647e", lw=1.2, label="Equal degree")
    ax.set_xlabel("Character degree")
    ax.set_ylabel("Average neighbour degree")
    ax.set_title("The friendship paradox in the Marvel network")
    ax.grid(alpha=0.2)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)

    node_average = sum(degrees[node] for node in connected_nodes) / len(connected_nodes)
    neighbor_average = sum(y_values) / len(y_values)
    return {
        "connected_nodes": len(connected_nodes),
        "nodes_with_more_connected_neighbors": len(paradox_nodes),
        "share_with_more_connected_neighbors": len(paradox_nodes) / len(connected_nodes),
        "average_node_degree": node_average,
        "average_neighbor_degree": neighbor_average,
        "local_maxima": [
            {"node": node, "name": names.get(node, node), "degree": degrees[node]}
            for node in sorted(local_maxima, key=lambda item: (-degrees[item], item))
        ],
        "top_popular_friends": top_popular_friends,
    }


def degree_preserving_shuffle(graph: nx.DiGraph, rng: random.Random) -> nx.DiGraph:
    """Swap directed edge endpoints while preserving every in/out degree."""
    shuffled = graph.copy()
    edges = list(shuffled.edges())
    attempts = max(1000, len(edges) * 20)
    for _ in range(attempts):
        first, second = rng.sample(edges, 2)
        u, v = first
        x, y = second
        if len({u, v, x, y}) < 4 or shuffled.has_edge(u, y) or shuffled.has_edge(x, v):
            continue
        shuffled.remove_edges_from([first, second])
        shuffled.add_edges_from([(u, y), (x, v)])
        edges = list(shuffled.edges())
    return shuffled


def network_metrics(graph: nx.DiGraph) -> dict[str, float]:
    """Return properties used in the shuffle comparison."""
    undirected = graph.to_undirected()
    total_degree = sum(degree for _, degree in undirected.degree())
    return {
        "reciprocity": nx.reciprocity(graph) or 0.0,
        "triangles": float(sum(nx.triangles(undirected).values()) / 3),
        "clustering": nx.average_clustering(undirected),
        "components": float(nx.number_connected_components(undirected)),
        "largest_hub_share": max(dict(undirected.degree()).values(), default=0) / total_degree
        if total_degree
        else 0.0,
    }


def save_shuffle_plot(graph: nx.DiGraph, path: Path) -> dict:
    """Run degree-preserving shuffles and plot metric null distributions."""
    rng = random.Random(RNG_SEED)
    real_values = network_metrics(graph)
    shuffled_values = {metric: [] for metric in real_values}
    for _ in range(SHUFFLE_COUNT):
        metrics = network_metrics(degree_preserving_shuffle(graph, rng))
        for metric, value in metrics.items():
            shuffled_values[metric].append(value)

    fig, axes = plt.subplots(2, 3, figsize=(12, 7))
    axes = axes.flat
    for axis, (metric, values) in zip(axes, shuffled_values.items()):
        axis.hist(values, bins=14, color="#b9abff", edgecolor="#5b3c76", alpha=0.85)
        axis.axvline(real_values[metric], color="#ff5ea8", lw=2.5, label="Marvel")
        axis.set_title(metric.replace("_", " ").title())
        axis.grid(axis="y", alpha=0.2)
        axis.legend(frameon=False, fontsize=8)
    axes[-1].axis("off")
    fig.suptitle("What survives a degree-preserving shuffle?", y=1.01)
    fig.tight_layout()
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)

    distributions = {
        metric: {
            "real": real_values[metric],
            "shuffled": values,
            "shuffled_mean": sum(values) / len(values),
            "shuffled_min": min(values),
            "shuffled_max": max(values),
        }
        for metric, values in shuffled_values.items()
    }
    return distributions


def save_preferential_attachment_plot(graph: nx.Graph, ba_graph: nx.Graph, path: Path) -> dict:
    """Compare real and BA networks using structural summary statistics."""
    def statistics(network: nx.Graph) -> dict[str, float]:
        return {
            "nodes": network.number_of_nodes(),
            "edges": network.number_of_edges(),
            "average degree": sum(dict(network.degree()).values()) / network.number_of_nodes(),
            "largest degree": max(dict(network.degree()).values()),
            "triangles": sum(nx.triangles(network).values()) / 3,
            "clustering": nx.average_clustering(network),
        }

    real = statistics(graph)
    model = statistics(ba_graph)
    labels = ["average degree", "largest degree", "triangles", "clustering"]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.5))
    for axis, network, title, color in [
        (axes[0], graph, "Real Marvel network", "#ff5ea8"),
        (axes[1], ba_graph, "Preferential attachment (m=5)", "#8d63ff"),
    ]:
        degrees = sorted((degree for _, degree in network.degree()), reverse=True)
        axis.bar(range(1, len(degrees) + 1), degrees, color=color, width=1.0)
        axis.set_title(title)
        axis.set_xlabel("Ranked node")
        axis.set_ylabel("Degree")
        axis.grid(axis="y", alpha=0.2)
    fig.suptitle("The model gets the hub shape, not the whole story")
    fig.tight_layout()
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return {"real": real, "preferential_attachment": model}


def main() -> None:
    nodes, edges, directed_graph = load_network()
    assert len(nodes) == 303, f"Expected 303 nodes; found {len(nodes)}"
    assert len(edges) == 1784, f"Expected 1784 edges; found {len(edges)}"

    real_graph = directed_graph.to_undirected()
    random_graph, ba_graph, ba_m = comparable_models(directed_graph)
    ccdf_results = save_ccdf_plot(
        real_graph,
        random_graph,
        ba_graph,
        FIGURE_DIR / "degree_ccdf_models.png",
    )
    paradox_results = friendship_paradox(
        real_graph,
        nodes,
        FIGURE_DIR / "friendship_paradox.png",
    )
    shuffle_results = save_shuffle_plot(directed_graph, FIGURE_DIR / "shuffle_test.png")
    model_results = save_preferential_attachment_plot(
        real_graph,
        ba_graph,
        FIGURE_DIR / "preferential_attachment.png",
    )

    results = {
        "n_nodes": directed_graph.number_of_nodes(),
        "directed_edges": directed_graph.number_of_edges(),
        "undirected_edges": real_graph.number_of_edges(),
        "ba_m": ba_m,
        "ccdf": ccdf_results,
        "friendship_paradox": paradox_results,
        "shuffle_test": shuffle_results,
        "preferential_attachment": model_results,
    }
    SUMMARY_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Saved Week 2 figures to {FIGURE_DIR}")
    print(f"Saved Week 2 summary to {SUMMARY_PATH}")
    print(f"BA parameter m: {ba_m}")
    print(
        "Friendship paradox: "
        f"{paradox_results['nodes_with_more_connected_neighbors']}/"
        f"{paradox_results['connected_nodes']} connected nodes"
    )


if __name__ == "__main__":
    main()
