"""Analyze communities and backbones in the frozen Week 1 hyperlink network.

The edge list contains directed hyperlinks but no explicit weight column. For
Week 4, the weighted undirected graph uses reciprocal hyperlinks as tie weight:
a one-way pair has weight 1 and a reciprocal pair has weight 2. This is derived
from the supplied data rather than added as a new measurement.

The script writes one machine-readable summary for the website and four static
PNG figures. Community detection is seeded where the library supports it.
"""

from __future__ import annotations

import json
import math
import os
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd

try:
    import infomap
except ImportError as error:  # pragma: no cover - exercised only without the dependency
    raise SystemExit("Week 4 requires the Python package 'infomap'. Install it with pip.") from error

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
FIGURE_DIR = REPO_ROOT / "assets" / "figures" / "week4"
SUMMARY_PATH = REPO_ROOT / "assets" / "week4_summary.json"
FIGURE_DIR.mkdir(parents=True, exist_ok=True)

SEED = 20260923
COLORS = ["#e85a98", "#8d63ff", "#e0a62d", "#3f2d52", "#38a89d", "#ee8f55", "#7c6bb2", "#c44f85"]


def load_network() -> tuple[pd.DataFrame, nx.DiGraph]:
    """Load every node before edges so isolates remain in the graph."""
    nodes = pd.read_csv(DATA_DIR / "week1_nodes.tsv", sep="\t", comment="#", quoting=3)
    edges = pd.read_csv(DATA_DIR / "week1_edges.tsv", sep="\t", comment="#", names=["source", "target"])
    graph = nx.DiGraph()
    graph.add_nodes_from(nodes["node_id"].tolist())
    graph.add_edges_from(edges[["source", "target"]].itertuples(index=False, name=None))
    return nodes, graph


def weighted_graph(directed: nx.DiGraph) -> tuple[nx.Graph, nx.Graph]:
    """Return unweighted and reciprocal-count weighted undirected graphs."""
    unweighted = nx.Graph()
    unweighted.add_nodes_from(directed.nodes())
    unweighted.add_edges_from(directed.to_undirected().edges())

    weighted = nx.Graph()
    weighted.add_nodes_from(directed.nodes())
    for source, target in directed.edges():
        if weighted.has_edge(source, target):
            weighted[source][target]["weight"] += 1
        else:
            weighted.add_edge(source, target, weight=1)
    return unweighted, weighted


def partition_map(communities: list[set[str]]) -> dict[str, int]:
    """Give each node a stable integer community label."""
    ordered = sorted(communities, key=lambda community: min(community) if community else "")
    return {node: index for index, community in enumerate(ordered) for node in community}


def louvain_partition(graph: nx.Graph, weighted: bool = False) -> dict[str, int]:
    """Run NetworkX's seeded Louvain implementation."""
    weight = "weight" if weighted else None
    return partition_map(list(nx.community.louvain_communities(graph, weight=weight, seed=SEED)))


def infomap_partition(graph: nx.Graph, weighted: bool = False) -> dict[str, int]:
    """Run Infomap and normalize its module ids to stable integer labels."""
    node_ids = {node: index for index, node in enumerate(graph.nodes())}
    original_ids = {index: node for node, index in node_ids.items()}
    links = [
        (node_ids[source], node_ids[target], data.get("weight", 1))
        for source, target, data in graph.edges(data=True)
    ]
    try:
        result = infomap.run(links, seed=SEED, num_trials=10, two_level=True, directed=False)
    except AttributeError:
        # Infomap 2.15 exposes the runner from a submodule on some installations.
        from infomap._run import run

        result = run(links, seed=SEED, num_trials=10, two_level=True, directed=False)
    raw = result.modules()
    communities = defaultdict(set)
    for node, module in raw.items():
        communities[str(module)].add(original_ids[node])
    communities_list = list(communities.values())
    assignments = partition_map(communities_list)
    for node in graph:
        assignments.setdefault(node, len(communities_list))
    return assignments


def nmi(first: dict[str, int], second: dict[str, int]) -> float:
    """Calculate normalized mutual information without adding sklearn as a dependency."""
    nodes = sorted(set(first) & set(second))
    if not nodes:
        return 0.0
    first_counts = Counter(first[node] for node in nodes)
    second_counts = Counter(second[node] for node in nodes)
    joint = Counter((first[node], second[node]) for node in nodes)
    total = len(nodes)
    mutual_information = 0.0
    for (first_label, second_label), count in joint.items():
        mutual_information += (count / total) * math.log((count * total) / (first_counts[first_label] * second_counts[second_label]))
    entropy_first = -sum((count / total) * math.log(count / total) for count in first_counts.values())
    entropy_second = -sum((count / total) * math.log(count / total) for count in second_counts.values())
    denominator = (entropy_first + entropy_second) / 2
    return mutual_information / denominator if denominator else 1.0


def names_for(nodes: pd.DataFrame) -> dict[str, str]:
    return nodes.set_index("node_id")["name"].to_dict()


def node_rows(assignments: dict[str, int], names: dict[str, str], other: dict[str, int] | None = None) -> list[dict]:
    """Serialize node assignments for the browser and mark disagreements."""
    rows = []
    for node_id, community in assignments.items():
        row = {"id": node_id, "name": names.get(node_id, node_id), "community": community}
        if other is not None:
            row["other_community"] = other[node_id]
            row["changed"] = community != other[node_id]
        rows.append(row)
    return rows


def disparity_alpha(graph: nx.Graph, source: str, target: str) -> float:
    """Return the disparity-filter alpha for one endpoint of an edge."""
    degree = graph.degree(source)
    strength = graph.degree(source, weight="weight")
    if degree <= 1 or not strength:
        return 0.0
    share = graph[source][target].get("weight", 1) / strength
    return (1 - share) ** (degree - 1)


def backbone_at_alpha(graph: nx.Graph, alpha: float) -> tuple[nx.Graph, dict]:
    """Keep salient edges while alpha increases the filtering strictness."""
    backbone = nx.Graph()
    backbone.add_nodes_from(graph.nodes())
    raw_threshold = 1 - alpha
    for source, target, data in graph.edges(data=True):
        edge_alpha = min(disparity_alpha(graph, source, target), disparity_alpha(graph, target, source))
        if edge_alpha <= raw_threshold:
            backbone.add_edge(source, target, weight=data.get("weight", 1), alpha=edge_alpha)
    components = sorted((len(component) for component in nx.connected_components(backbone)), reverse=True)
    giant = components[0] if components else 0
    return backbone, {
        "alpha": alpha,
        "nodes": backbone.number_of_nodes(),
        "edges": backbone.number_of_edges(),
        "giant_component": giant,
        "components": len(components),
        "fragmentation": (backbone.number_of_nodes() - giant) / backbone.number_of_nodes() if backbone.number_of_nodes() else 0,
    }


def backbone_analysis(graph: nx.Graph, names: dict[str, str]) -> dict:
    """Find the largest observed giant-component drop and three local thresholds."""
    candidates = sorted({1 - min(disparity_alpha(graph, source, target), disparity_alpha(graph, target, source)) for source, target in graph.edges()})
    measurements = [backbone_at_alpha(graph, alpha)[1] for alpha in candidates]
    drops = [0] + [
        measurements[index - 1]["giant_component"] - measurements[index]["giant_component"]
        for index in range(1, len(measurements))
    ]
    break_index = max(range(len(measurements)), key=lambda index: (drops[index], -measurements[index]["alpha"]))
    chosen_indices = {break_index}
    for offset in (-1, 1, -2, 2):
        candidate_index = break_index + offset
        if 0 <= candidate_index < len(measurements):
            chosen_indices.add(candidate_index)
        if len(chosen_indices) == 3:
            break
    selected = [measurements[index] for index in sorted(chosen_indices)]
    break_alpha = measurements[break_index]["alpha"]
    previous_graph, _ = backbone_at_alpha(graph, measurements[max(0, break_index - 1)]["alpha"])
    current_graph, _ = backbone_at_alpha(graph, break_alpha)
    previous_edges = {frozenset(edge) for edge in previous_graph.edges()}
    current_edges = {frozenset(edge) for edge in current_graph.edges()}
    removed_edges = previous_edges - current_edges
    incident = Counter(node for edge in removed_edges for node in edge)
    associated_node = max(graph.nodes(), key=lambda node: (incident[node], graph.degree(node), node))
    return {
        "selected": selected,
        "break_alpha": break_alpha,
        "break_drop": drops[break_index],
        "associated_node": {"id": associated_node, "name": names.get(associated_node, associated_node), "removed_edges_incident": incident[associated_node]},
        "candidate_count": len(candidates),
    }


def layout(graph: nx.Graph) -> dict[str, tuple[float, float]]:
    """Use one seeded layout so all figures and browser overlays agree."""
    return nx.spring_layout(graph, seed=SEED, k=0.28, iterations=80)


def draw_partition(ax, graph: nx.Graph, assignments: dict[str, int], positions: dict, title: str, changed: set[str] | None = None) -> None:
    nx.draw_networkx_edges(graph, positions, ax=ax, edge_color="#b8a9c8", alpha=0.18, width=0.45)
    colors = [COLORS[assignments[node] % len(COLORS)] for node in graph.nodes()]
    nx.draw_networkx_nodes(graph, positions, ax=ax, node_size=23, node_color=colors, linewidths=[1.8 if changed and node in changed else 0 for node in graph], edgecolors="#34283f")
    ax.set_title(title, color="#3f2d52", fontweight="bold")
    ax.axis("off")


def save_louvain_infomap(graph: nx.Graph, louvain: dict, infomap_assignments: dict, positions: dict) -> None:
    changed = {node for node in graph if louvain[node] != infomap_assignments[node]}
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), facecolor="#fffaf5")
    draw_partition(axes[0], graph, louvain, positions, "Louvain · modularity")
    draw_partition(axes[1], graph, infomap_assignments, positions, "Infomap · information flow", changed)
    fig.suptitle("Community assignments: disagreement outlined", color="#34283f", fontsize=16, fontweight="bold")
    fig.text(0.5, 0.02, f"Dark outlines mark {len(changed)} assignment differences", ha="center", color="#6f647e")
    fig.tight_layout(rect=(0, 0.05, 1, 0.94))
    fig.savefig(FIGURE_DIR / "louvain_vs_infomap.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def save_aristotle(graph: nx.Graph, names: dict[str, str], assignments: dict) -> dict:
    """Create an honest figure when the requested philosopher is absent."""
    matches = [node for node, name in names.items() if "aristotle" in name.lower() or "aristotle" in node.lower()]
    fig, ax = plt.subplots(figsize=(10, 6), facecolor="#fffaf5")
    ax.set_facecolor("#fffaf5")
    if matches:
        target = matches[0]
        neighbourhood = set(graph.neighbors(target)) | {target}
        subgraph = graph.subgraph(neighbourhood)
        pos = nx.spring_layout(subgraph, seed=SEED)
        nx.draw_networkx_edges(subgraph, pos, ax=ax, edge_color="#b8a9c8", alpha=0.6)
        nx.draw_networkx_nodes(subgraph, pos, ax=ax, node_color=["#e85a98" if node == target else COLORS[assignments[node] % len(COLORS)] for node in subgraph], node_size=[700 if node == target else 260 for node in subgraph], edgecolors="#34283f")
        nx.draw_networkx_labels(subgraph, pos, ax=ax, labels={node: names[node] for node in subgraph}, font_size=7)
        result = {"present": True, "node_id": target, "name": names[target], "community": assignments[target], "neighbors": [names[node] for node in graph.neighbors(target)]}
    else:
        ax.text(0.5, 0.58, "Aristotle is not a node in this dataset", ha="center", va="center", fontsize=20, color="#3f2d52", fontweight="bold")
        ax.text(0.5, 0.42, "The supplied network contains Marvel character pages,\nso no community or direct-link claim is possible.", ha="center", va="center", fontsize=12, color="#6f647e")
        result = {"present": False, "name": "Aristotle", "community": None, "neighbors": []}
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "aristotle_community.png", dpi=180, bbox_inches="tight")
    plt.close(fig)
    return result


def save_backbone(graph: nx.Graph, analysis: dict, positions: dict) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), facecolor="#fffaf5")
    for ax, measurement in zip(axes, analysis["selected"]):
        backbone, _ = backbone_at_alpha(graph, measurement["alpha"])
        nx.draw_networkx_edges(backbone, positions, ax=ax, edge_color="#b8a9c8", alpha=0.28, width=0.55)
        giant = max(nx.connected_components(backbone), key=len, default=set())
        nx.draw_networkx_nodes(backbone, positions, ax=ax, node_size=22, node_color=["#e85a98" if node in giant else "#f9d778" for node in backbone], linewidths=0)
        ax.set_title(f"α = {measurement['alpha']:.4f}\nGiant: {measurement['giant_component']}", color="#3f2d52", fontweight="bold")
        ax.axis("off")
    fig.suptitle("Disparity-filter backbone across observed alpha thresholds", color="#34283f", fontsize=15, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(FIGURE_DIR / "backbone_alpha.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def save_weighted_comparison(graph: nx.Graph, weighted: dict, unweighted: dict, positions: dict) -> None:
    changed = {node for node in graph if weighted[node] != unweighted[node]}
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), facecolor="#fffaf5")
    draw_partition(axes[0], graph, unweighted, positions, "Unweighted")
    draw_partition(axes[1], graph, weighted, positions, "Reciprocal-weighted", changed)
    fig.suptitle("Weight changes outlined", color="#34283f", fontsize=16, fontweight="bold")
    fig.text(0.5, 0.02, f"Dark outlines mark {len(changed)} community moves", ha="center", color="#6f647e")
    fig.tight_layout(rect=(0, 0.05, 1, 0.94))
    fig.savefig(FIGURE_DIR / "weighted_vs_unweighted.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    nodes, directed = load_network()
    names = names_for(nodes)
    graph, weighted = weighted_graph(directed)
    positions = layout(graph)

    louvain = louvain_partition(graph)
    infomap_assignments = infomap_partition(graph)
    weighted_louvain = louvain_partition(weighted, weighted=True)
    unweighted_louvain = louvain
    community_disagreements = [
        {"id": node, "name": names[node], "louvain": louvain[node], "infomap": infomap_assignments[node]}
        for node in graph if louvain[node] != infomap_assignments[node]
    ]
    moved = [
        {"id": node, "name": names[node], "weighted": weighted_louvain[node], "unweighted": unweighted_louvain[node]}
        for node in graph if weighted_louvain[node] != unweighted_louvain[node]
    ]
    backbone = backbone_analysis(weighted, names)
    aristotle = save_aristotle(graph, names, louvain)

    save_louvain_infomap(graph, louvain, infomap_assignments, positions)
    save_backbone(weighted, backbone, positions)
    save_weighted_comparison(graph, weighted_louvain, unweighted_louvain, positions)

    summary = {
        "network": {"nodes": graph.number_of_nodes(), "directed_edges": directed.number_of_edges(), "undirected_edges": graph.number_of_edges(), "reciprocal_weighted_edges": weighted.number_of_edges()},
        "weight_definition": "Undirected edge weight equals the number of directed hyperlinks in the pair: 1 for one-way, 2 for reciprocal.",
        "positions": {node: {"x": float(position[0]), "y": float(position[1])} for node, position in positions.items()},
        "community_comparison": {
            "louvain_communities": len(set(louvain.values())),
            "infomap_communities": len(set(infomap_assignments.values())),
            "nmi": nmi(louvain, infomap_assignments),
            "disagreements": community_disagreements,
            "louvain_nodes": node_rows(louvain, names, infomap_assignments),
            "infomap_nodes": node_rows(infomap_assignments, names, louvain),
        },
        "aristotle": aristotle,
        "backbone": backbone,
        "weighted_comparison": {
            "weighted_communities": len(set(weighted_louvain.values())),
            "unweighted_communities": len(set(unweighted_louvain.values())),
            "nmi": nmi(weighted_louvain, unweighted_louvain),
            "moved_count": len(moved),
            "moved": moved,
            "weighted_nodes": node_rows(weighted_louvain, names, unweighted_louvain),
            "unweighted_nodes": node_rows(unweighted_louvain, names, weighted_louvain),
        },
        "edges": [
            [source, target, data.get("weight", 1), 1 - min(disparity_alpha(weighted, source, target), disparity_alpha(weighted, target, source))]
            for source, target, data in weighted.edges(data=True)
        ],
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({
        "louvain_communities": summary["community_comparison"]["louvain_communities"],
        "infomap_communities": summary["community_comparison"]["infomap_communities"],
        "louvain_infomap_nmi": summary["community_comparison"]["nmi"],
        "backbone_break_alpha": backbone["break_alpha"],
        "backbone_associated_philosopher": backbone["associated_node"]["name"],
        "weighted_unweighted_nmi": summary["weighted_comparison"]["nmi"],
        "weighted_unweighted_moved": len(moved),
        "aristotle_present": aristotle["present"],
    }, indent=2))


if __name__ == "__main__":
    main()
