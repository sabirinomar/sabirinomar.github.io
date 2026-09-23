"""Build the Week 4 community and backbone analysis from the supplied TSV files."""

from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx

try:
    import infomap
except ImportError as error:  # pragma: no cover
    raise SystemExit("Install requirements-week4.txt before running this script.") from error

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
FIGURES = ROOT / "assets" / "figures" / "week4"
SUMMARY = ROOT / "assets" / "week4_summary.json"
FIGURES.mkdir(parents=True, exist_ok=True)
SEED = 20260923
COLORS = ["#e85a98", "#8d63ff", "#e0a62d", "#3f2d52", "#38a89d", "#ee8f55", "#7c6bb2", "#c44f85"]


def tsv_rows(path: Path):
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.reader(handle, delimiter="\t"):
            if not row or row[0].startswith("#") or row[0] in {"source", "node_id"}:
                continue
            yield row


def load_philosophers() -> tuple[dict[str, str], nx.DiGraph]:
    names = {}
    graph = nx.DiGraph()
    for row in tsv_rows(DATA / "week4_philosophers_nodes.tsv"):
        names[row[0]] = row[1]
        graph.add_node(row[0])
    for source, target, *_ in tsv_rows(DATA / "week4_philosophers_edges.tsv"):
        graph.add_edge(source, target)
    return names, graph


def load_supplied_weighted() -> tuple[dict[str, str], nx.Graph]:
    """Load the supplied weighted snapshot; it is the separate Week 1 Marvel graph."""
    names = {}
    nodes_path = DATA / "week1_nodes.tsv"
    if nodes_path.exists():
        for row in tsv_rows(nodes_path):
            names[row[0]] = row[1]
    graph = nx.Graph()
    for source, target, weight in tsv_rows(DATA / "week4_edges_weighted.tsv"):
        graph.add_edge(source, target, weight=int(weight))
    for node in graph:
        names.setdefault(node, node.replace("_", " "))
    return names, graph


def undirected_weighted(directed: nx.DiGraph) -> nx.Graph:
    graph = nx.Graph()
    graph.add_nodes_from(directed)
    for source, target in directed.edges():
        if graph.has_edge(source, target):
            graph[source][target]["weight"] += 1
        else:
            graph.add_edge(source, target, weight=1)
    return graph


def partition_map(communities) -> dict[str, int]:
    ordered = sorted((set(community) for community in communities), key=lambda group: min(group) if group else "")
    return {node: index for index, community in enumerate(ordered) for node in community}


def align_partition(reference: dict[str, int], candidate: dict[str, int]) -> dict[str, int]:
    """Relabel arbitrary community IDs so node-level changes are meaningful."""
    overlaps = []
    for candidate_id in set(candidate.values()):
        candidate_nodes = {node for node, label in candidate.items() if label == candidate_id}
        for reference_id in set(reference.values()):
            overlap = len(candidate_nodes & {node for node, label in reference.items() if label == reference_id})
            overlaps.append((overlap, candidate_id, reference_id))
    mapping = {}
    used_reference = set()
    for overlap, candidate_id, reference_id in sorted(overlaps, reverse=True):
        if candidate_id not in mapping and reference_id not in used_reference:
            mapping[candidate_id] = reference_id
            used_reference.add(reference_id)
    next_label = max(reference.values(), default=-1) + 1
    for candidate_id in set(candidate.values()):
        if candidate_id not in mapping:
            mapping[candidate_id] = next_label
            next_label += 1
    return {node: mapping[label] for node, label in candidate.items()}


def louvain(graph: nx.Graph, weighted: bool) -> dict[str, int]:
    return partition_map(nx.community.louvain_communities(graph, weight="weight" if weighted else None, seed=SEED))


def infomap_partition(graph: nx.Graph) -> dict[str, int]:
    node_to_int = {node: index for index, node in enumerate(graph)}
    int_to_node = {index: node for node, index in node_to_int.items()}
    runner = infomap.Infomap(f"--two-level --num-trials 10 --seed {SEED}")
    for source, target, data in graph.edges(data=True):
        runner.add_link(node_to_int[source], node_to_int[target], data.get("weight", 1))
    runner.run()
    modules = defaultdict(set)
    for node in runner.tree:
        if node.is_leaf:
            modules[node.module_id].add(int_to_node[node.node_id])
    assignments = partition_map(modules.values())
    next_community = len(set(assignments.values()))
    for node in graph:
        if node not in assignments:
            assignments[node] = next_community
            next_community += 1
    return assignments


def nmi(first: dict[str, int], second: dict[str, int]) -> float:
    nodes = sorted(set(first) & set(second))
    total = len(nodes)
    if not total:
        return 0.0
    first_counts = Counter(first[node] for node in nodes)
    second_counts = Counter(second[node] for node in nodes)
    joint = Counter((first[node], second[node]) for node in nodes)
    mutual = sum((count / total) * math.log(count * total / (first_counts[a] * second_counts[b])) for (a, b), count in joint.items())
    entropy_first = -sum((count / total) * math.log(count / total) for count in first_counts.values())
    entropy_second = -sum((count / total) * math.log(count / total) for count in second_counts.values())
    return mutual / ((entropy_first + entropy_second) / 2) if entropy_first + entropy_second else 1.0


def rows_for(assignments, names, other=None):
    return [{"id": node, "name": names.get(node, node), "community": assignments[node], "other_community": other[node] if other else None, "changed": bool(other and assignments[node] != other[node])} for node in assignments]


def disparity_p(graph: nx.Graph, source: str, target: str) -> float:
    degree = graph.degree(source)
    strength = graph.degree(source, weight="weight")
    if degree <= 1 or strength <= 0:
        return 0.0
    share = graph[source][target].get("weight", 1) / strength
    return (1 - share) ** (degree - 1)


def backbone(graph: nx.Graph, alpha: float) -> nx.Graph:
    filtered = nx.Graph()
    filtered.add_nodes_from(graph)
    for source, target, data in graph.edges(data=True):
        p_value = min(disparity_p(graph, source, target), disparity_p(graph, target, source))
        if p_value <= alpha:
            filtered.add_edge(source, target, weight=data.get("weight", 1), p_value=p_value)
    return filtered


def backbone_analysis(graph: nx.Graph, names: dict[str, str]) -> dict:
    thresholds = sorted({min(disparity_p(graph, source, target), disparity_p(graph, target, source)) for source, target in graph.edges()}, reverse=True)
    measurements = []
    for alpha in thresholds:
        filtered = backbone(graph, alpha)
        components = sorted((len(component) for component in nx.connected_components(filtered)), reverse=True)
        giant = components[0] if components else 0
        measurements.append({"alpha": alpha, "nodes": filtered.number_of_nodes(), "edges": filtered.number_of_edges(), "giant_component": giant, "components": len(components), "fragmentation": (filtered.number_of_nodes() - giant) / filtered.number_of_nodes() if filtered else 0})
    drops = [measurements[i]["giant_component"] - measurements[i + 1]["giant_component"] for i in range(len(measurements) - 1)]
    break_index = max(range(len(drops)), key=lambda index: (drops[index], measurements[index + 1]["alpha"]))
    critical_alpha = measurements[break_index + 1]["alpha"]
    previous = backbone(graph, measurements[break_index]["alpha"])
    current = backbone(graph, critical_alpha)
    removed = {frozenset(edge) for edge in previous.edges()} - {frozenset(edge) for edge in current.edges()}
    incident = Counter(node for edge in removed for node in edge)
    responsible = max(graph, key=lambda node: (incident[node], graph.degree(node), node))
    selected_indexes = sorted({max(0, break_index - 1), break_index, break_index + 1})
    return {"selected": [measurements[index] for index in selected_indexes], "break_alpha": critical_alpha, "break_drop": drops[break_index], "associated_node": {"id": responsible, "name": names.get(responsible, responsible), "removed_edges_incident": incident[responsible]}, "candidate_count": len(thresholds)}


def positions(graph: nx.Graph):
    return nx.spring_layout(graph, seed=SEED, k=0.28, iterations=70)


def draw_partition(axis, graph, assignment, position, title, changed=None):
    nx.draw_networkx_edges(graph, position, ax=axis, edge_color="#b8a9c8", alpha=0.13, width=0.35)
    nx.draw_networkx_nodes(graph, position, ax=axis, node_size=13, node_color=[COLORS[assignment[node] % len(COLORS)] for node in graph], linewidths=[1.4 if changed and node in changed else 0 for node in graph], edgecolors="#34283f")
    axis.set_title(title, color="#3f2d52", fontweight="bold")
    axis.axis("off")


def save_community_figure(graph, first, second, position, path, titles):
    changed = {node for node in graph if first[node] != second[node]}
    figure, axes = plt.subplots(1, 2, figsize=(14, 6), facecolor="#fffaf5")
    draw_partition(axes[0], graph, first, position, titles[0])
    draw_partition(axes[1], graph, second, position, titles[1], changed)
    figure.suptitle(f"Community assignments: {len(changed)} disagreements outlined", color="#34283f", fontsize=15, fontweight="bold")
    figure.tight_layout()
    figure.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def save_aristotle(graph, names, louvain_assignment, clique_communities):
    target = next(node for node, name in names.items() if name.lower() == "aristotle")
    ego_nodes = {target} | set(graph.neighbors(target))
    ego = graph.subgraph(ego_nodes)
    position = nx.spring_layout(ego, seed=SEED, k=0.8)
    memberships = {node: index for index, community in enumerate(clique_communities) for node in community}
    figure, axis = plt.subplots(figsize=(11, 8), facecolor="#fffaf5")
    nx.draw_networkx_edges(ego, position, ax=axis, edge_color=[COLORS[memberships.get(neighbor, louvain_assignment[neighbor]) % len(COLORS)] for source, neighbor in ego.edges()], alpha=0.46, width=1.2)
    nx.draw_networkx_nodes(ego, position, ax=axis, node_size=[900 if node == target else 100 for node in ego], node_color=["#34283f" if node == target else COLORS[memberships.get(node, louvain_assignment[node]) % len(COLORS)] for node in ego], edgecolors="#fffaf5", linewidths=1.2)
    labels = {node: names[node] for node in ego if node == target or graph.degree(node) >= 12}
    nx.draw_networkx_labels(ego, position, labels=labels, ax=axis, font_size=7, font_color="#34283f")
    axis.set_title("Aristotle's direct neighborhood, links colored by k-clique community", color="#3f2d52", fontweight="bold")
    axis.axis("off")
    figure.tight_layout()
    figure.savefig(FIGURES / "aristotle_community.png", dpi=180, bbox_inches="tight")
    plt.close(figure)
    neighbor_communities = sorted({memberships.get(node, louvain_assignment[node]) for node in graph.neighbors(target)})
    return {"present": True, "node_id": target, "name": names[target], "community": louvain_assignment[target], "neighbors": [names[node] for node in graph.neighbors(target)], "degree": graph.degree(target), "k": 4, "clique_communities": len(clique_communities), "aristotle_clique_memberships": sum(target in community for community in clique_communities), "neighbor_community_count": len(neighbor_communities), "bridge": len(neighbor_communities) > 1}


def main():
    philosopher_names, directed = load_philosophers()
    philosopher_graph = undirected_weighted(directed)
    marvel_names, supplied_weighted = load_supplied_weighted()
    supplied_unweighted = nx.Graph()
    supplied_unweighted.add_nodes_from(supplied_weighted)
    supplied_unweighted.add_edges_from(supplied_weighted.edges())

    philosopher_position = positions(philosopher_graph)
    marvel_position = positions(supplied_weighted)
    philosopher_louvain = louvain(philosopher_graph, weighted=False)
    philosopher_infomap = align_partition(philosopher_louvain, infomap_partition(philosopher_graph))
    marvel_unweighted = louvain(supplied_unweighted, weighted=False)
    marvel_weighted = align_partition(marvel_unweighted, louvain(supplied_weighted, weighted=True))
    clique_communities = list(nx.community.k_clique_communities(philosopher_graph, 4))
    backbone_result = backbone_analysis(philosopher_graph, philosopher_names)

    save_community_figure(philosopher_graph, philosopher_louvain, philosopher_infomap, philosopher_position, FIGURES / "louvain_vs_infomap.png", ("Louvain · density", "Infomap · flow"))
    aristotle = save_aristotle(philosopher_graph, philosopher_names, philosopher_louvain, clique_communities)
    figure, axes = plt.subplots(1, 3, figsize=(15, 5), facecolor="#fffaf5")
    for axis, measure in zip(axes, backbone_result["selected"]):
        filtered = backbone(philosopher_graph, measure["alpha"])
        giant = max(nx.connected_components(filtered), key=len, default=set())
        nx.draw_networkx_edges(filtered, philosopher_position, ax=axis, edge_color="#b8a9c8", alpha=0.22, width=0.4)
        nx.draw_networkx_nodes(filtered, philosopher_position, ax=axis, node_size=13, node_color=["#e85a98" if node in giant else "#f9d778" for node in filtered])
        axis.set_title(f"alpha = {measure['alpha']:.6g}\nGiant: {measure['giant_component']}", color="#3f2d52", fontweight="bold")
        axis.axis("off")
    figure.suptitle("Disparity-filter backbone around the critical break", color="#34283f", fontsize=15, fontweight="bold")
    figure.tight_layout()
    figure.savefig(FIGURES / "backbone_alpha.png", dpi=180, bbox_inches="tight")
    plt.close(figure)
    save_community_figure(supplied_unweighted, marvel_unweighted, marvel_weighted, marvel_position, FIGURES / "weighted_vs_unweighted.png", ("Supplied graph · unweighted", "Supplied graph · weighted"))

    community_disagreements = [{"id": node, "name": philosopher_names[node], "louvain": philosopher_louvain[node], "infomap": philosopher_infomap[node]} for node in philosopher_graph if philosopher_louvain[node] != philosopher_infomap[node]]
    moved = [{"id": node, "name": marvel_names[node], "weighted": marvel_weighted[node], "unweighted": marvel_unweighted[node]} for node in supplied_weighted if marvel_weighted[node] != marvel_unweighted[node]]
    summary = {
        "data_provenance": {"primary": "week4_philosophers_nodes.tsv + week4_philosophers_edges.tsv", "weighted_comparison": "week4_edges_weighted.tsv (the file is the 303-node Week 1 Marvel snapshot, not the philosopher graph)"},
        "network": {"nodes": philosopher_graph.number_of_nodes(), "directed_edges": directed.number_of_edges(), "undirected_edges": philosopher_graph.number_of_edges()},
        "positions": {node: {"x": float(point[0]), "y": float(point[1])} for node, point in philosopher_position.items()},
        "community_comparison": {"louvain_communities": len(set(philosopher_louvain.values())), "infomap_communities": len(set(philosopher_infomap.values())), "nmi": nmi(philosopher_louvain, philosopher_infomap), "disagreements": community_disagreements, "louvain_nodes": rows_for(philosopher_louvain, philosopher_names, philosopher_infomap), "infomap_nodes": rows_for(philosopher_infomap, philosopher_names, philosopher_louvain)},
        "aristotle": aristotle,
        "backbone": backbone_result,
        "weighted_comparison": {"data_nodes": supplied_weighted.number_of_nodes(), "weighted_communities": len(set(marvel_weighted.values())), "unweighted_communities": len(set(marvel_unweighted.values())), "nmi": nmi(marvel_weighted, marvel_unweighted), "moved_count": len(moved), "moved": moved, "weighted_nodes": rows_for(marvel_weighted, marvel_names, marvel_unweighted), "unweighted_nodes": rows_for(marvel_unweighted, marvel_names, marvel_weighted)},
        "edges": [[source, target, data.get("weight", 1), min(disparity_p(philosopher_graph, source, target), disparity_p(philosopher_graph, target, source))] for source, target, data in philosopher_graph.edges(data=True)],
        "weighted_positions": {node: {"x": float(point[0]), "y": float(point[1])} for node, point in marvel_position.items()},
        "weighted_edges": [[source, target, data.get("weight", 1)] for source, target, data in supplied_weighted.edges(data=True)],
    }
    SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({"louvain_communities": summary["community_comparison"]["louvain_communities"], "infomap_communities": summary["community_comparison"]["infomap_communities"], "louvain_infomap_nmi": summary["community_comparison"]["nmi"], "backbone_break_alpha": backbone_result["break_alpha"], "backbone_associated_philosopher": backbone_result["associated_node"]["name"], "weighted_unweighted_nmi": summary["weighted_comparison"]["nmi"], "weighted_unweighted_moved": len(moved), "aristotle_degree": aristotle["degree"]}, indent=2))


if __name__ == "__main__":
    main()
