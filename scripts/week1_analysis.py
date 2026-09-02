"""Analyze the Week 1 Marvel Comics hyperlink network.

This script loads the frozen Week-1 dataset from the course data page,
constructs a directed NetworkX graph while preserving isolated nodes,
computes the requested summary statistics, and saves a small set of figures
for use in the course website.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
FIGURE_DIR = REPO_ROOT / "assets" / "figures" / "week1"
FIGURE_DIR.mkdir(parents=True, exist_ok=True)


def load_network() -> tuple[pd.DataFrame, pd.DataFrame, nx.DiGraph]:
    """Load the node and edge files and build a directed graph.

    Important: we add every node id before adding the edges so that the 17
    isolated characters are not silently lost when the edge list is loaded.
    """
    nodes = pd.read_csv(DATA_DIR / "week1_nodes.tsv", sep="\t", comment="#", quoting=3)
    edges = pd.read_csv(DATA_DIR / "week1_edges.tsv", sep="\t", comment="#", names=["source", "target"])

    G = nx.DiGraph()
    G.add_nodes_from(nodes["node_id"].tolist())
    G.add_edges_from(edges[["source", "target"]].itertuples(index=False, name=None))

    return nodes, edges, G


def summarize_degree_distribution(G: nx.DiGraph, label: str, ax, loglog: bool = False) -> None:
    """Plot degree counts for either in-degree or out-degree."""
    if label == "in":
        values = [d for _, d in G.in_degree()]
        title = "In-degree distribution"
    else:
        values = [d for _, d in G.out_degree()]
        title = "Out-degree distribution"

    counts = Counter(values)
    x = sorted(counts)
    y = [counts[k] for k in x]

    if loglog:
        ax.loglog(x, y, "o-")
        ax.set_xlabel("degree k")
        ax.set_ylabel("count N(k)")
        ax.set_title(f"{title} (log-log)")
    else:
        ax.bar(x, y, width=0.8)
        ax.set_xlabel("degree k")
        ax.set_ylabel("count")
        ax.set_title(f"{title} (linear)")

    ax.grid(True, alpha=0.3)


def save_network_figure(G: nx.DiGraph, path: Path) -> None:
    """Save a visualization of the directed network."""
    pos = nx.spring_layout(G, seed=42, k=0.35)
    fig, ax = plt.subplots(figsize=(12, 10))
    nx.draw_networkx(
        G,
        pos=pos,
        ax=ax,
        with_labels=False,
        node_size=35,
        node_color="lightblue",
        edge_color="gray",
        arrows=True,
        alpha=0.8,
    )
    ax.set_title("Marvel Comics Wikipedia hyperlink network (directed)")
    ax.axis("off")
    plt.tight_layout()
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def save_directed_vs_undirected_summary(G: nx.DiGraph, path: Path) -> None:
    """Save a compact comparison plot for directed vs undirected structure."""
    G_und = G.to_undirected()
    edge_counts = {
        "directed": G.number_of_edges(),
        "undirected": G_und.number_of_edges(),
    }
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(edge_counts.keys(), edge_counts.values(), color=["#4c72b0", "#dd8452"])
    ax.set_title("Directed vs undirected edge counts")
    ax.set_ylabel("edges")
    for label, value in edge_counts.items():
        ax.text(label, value + 10, str(value), ha="center", va="bottom")
    plt.tight_layout()
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def save_top_degree_table(top_in, top_out, path: Path) -> None:
    """Save a small JSON table of the top degree nodes."""
    table = {
        "top_in_degree": [{"node": node, "in_degree": degree} for node, degree in top_in],
        "top_out_degree": [{"node": node, "out_degree": degree} for node, degree in top_out],
    }
    path.write_text(json.dumps(table, indent=2), encoding="utf-8")


def main() -> None:
    nodes, edges, G = load_network()

    assert len(nodes) == 303, f"Expected 303 nodes; found {len(nodes)}"
    assert len(edges) == 1784, f"Expected 1784 edges; found {len(edges)}"
    assert G.number_of_nodes() == 303, f"Expected 303 nodes in graph; found {G.number_of_nodes()}"
    assert G.number_of_edges() == 1784, f"Expected 1784 edges in graph; found {G.number_of_edges()}"

    in_deg = sorted(G.in_degree(), key=lambda item: (-item[1], item[0]))
    out_deg = sorted(G.out_degree(), key=lambda item: (-item[1], item[0]))

    G_und = G.to_undirected()
    components = sorted(nx.connected_components(G_und), key=len, reverse=True)
    giant_component = components[0]
    isolates = sorted(nx.isolates(G_und))

    results = {
        "n_nodes": G.number_of_nodes(),
        "n_edges_directed": G.number_of_edges(),
        "n_edges_undirected": G_und.number_of_edges(),
        "n_isolates": len(isolates),
        "largest_component_size": len(giant_component),
        "top_in_degree": [{"node": node, "degree": degree} for node, degree in in_deg[:5]],
        "top_out_degree": [{"node": node, "degree": degree} for node, degree in out_deg[:5]],
        "isolated_nodes": isolates,
        "in_degree_distribution": dict(sorted(Counter(d for _, d in G.in_degree()).items())),
        "out_degree_distribution": dict(sorted(Counter(d for _, d in G.out_degree()).items())),
    }

    summary_path = REPO_ROOT / "assets" / "week1_summary.json"
    summary_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

    save_network_figure(G, FIGURE_DIR / "marvel_network.png")
    save_directed_vs_undirected_summary(G, FIGURE_DIR / "directed_vs_undirected.png")

    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    summarize_degree_distribution(G, "in", axes[0, 0], loglog=False)
    summarize_degree_distribution(G, "out", axes[0, 1], loglog=False)
    summarize_degree_distribution(G, "in", axes[1, 0], loglog=True)
    summarize_degree_distribution(G, "out", axes[1, 1], loglog=True)
    fig.suptitle("Marvel Comics network degree distributions")
    plt.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(FIGURE_DIR / "degree_distributions.png", dpi=200, bbox_inches="tight")
    plt.close(fig)

    save_top_degree_table(in_deg[:5], out_deg[:5], REPO_ROOT / "assets" / "top_degree_table.json")

    print(f"Nodes: {G.number_of_nodes()}")
    print(f"Directed edges: {G.number_of_edges()}")
    print(f"Undirected edges: {G_und.number_of_edges()}")
    print(f"Isolates: {len(isolates)}")
    print(f"Largest connected component: {len(giant_component)}")
    print("Top in-degree:")
    for node, degree in in_deg[:5]:
        print(f"  {node}: {degree}")
    print("Top out-degree:")
    for node, degree in out_deg[:5]:
        print(f"  {node}: {degree}")


if __name__ == "__main__":
    main()
