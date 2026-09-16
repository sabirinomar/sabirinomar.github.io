"""Build the browser payload for the Week 3 interactive playground.

This reads the frozen Week 1 network and existing Week 3 outputs. It does not
change any analysis definitions; it only packages the graph, a fixed layout,
removal outcomes, attack curves, and null-model samples for client-side use.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import networkx as nx
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUTPUT = ROOT / "assets" / "week3" / "network_game.json"
SEED = 20260916
NULL_SHUFFLES = 200


def load_graph() -> tuple[pd.DataFrame, nx.Graph]:
    nodes = pd.read_csv(DATA / "week1_nodes.tsv", sep="\t", comment="#", quoting=3)
    edges = pd.read_csv(DATA / "week1_edges.tsv", sep="\t", comment="#", names=["source", "target"])
    directed = nx.DiGraph()
    directed.add_nodes_from(nodes["node_id"].tolist())
    directed.add_edges_from(edges[["source", "target"]].itertuples(index=False, name=None))
    graph = nx.Graph(directed)
    giant_nodes = max(nx.connected_components(graph), key=len)
    return nodes, graph.subgraph(giant_nodes).copy()


def degree_preserving_shuffle(graph: nx.Graph, rng: random.Random) -> nx.Graph:
    shuffled = graph.copy()
    nx.double_edge_swap(
        shuffled,
        nswap=max(1000, shuffled.number_of_edges() * 3),
        max_tries=max(5000, shuffled.number_of_edges() * 20),
        seed=rng,
    )
    return shuffled


def removal_detail(graph: nx.Graph, node: str) -> dict:
    damaged = graph.copy()
    damaged.remove_node(node)
    components = sorted(nx.connected_components(damaged), key=len, reverse=True)
    giant = components[0] if components else set()
    return {
        "giant_after": len(giant),
        "component_count_after": len(components),
        "nodes_outside_giant": graph.number_of_nodes() - len(giant) - 1,
        "separated": sorted(giant.symmetric_difference(set(damaged)) - set(giant)),
        "components": [sorted(component) for component in components],
    }


def main() -> None:
    nodes, graph = load_graph()
    names = nodes.set_index("node_id")["name"].to_dict()
    metrics = pd.read_csv(ROOT / "assets" / "week3" / "knockout_metrics.csv")
    metrics = metrics.set_index("node_id")
    attacks = pd.read_csv(ROOT / "assets" / "week3" / "attack_curves.csv")

    positions = nx.spring_layout(graph, seed=SEED, k=0.35, iterations=80)
    xs = [point[0] for point in positions.values()]
    ys = [point[1] for point in positions.values()]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)

    nodes_payload = []
    for node in sorted(graph):
        row = metrics.loc[node]
        point = positions[node]
        nodes_payload.append(
            {
                "id": node,
                "name": names.get(node, node),
                "x": round((point[0] - x_min) / (x_max - x_min), 6),
                "y": round((point[1] - y_min) / (y_max - y_min), 6),
                "degree": int(row["degree"]),
                "betweenness": float(row["betweenness"]),
                "closeness": float(row["closeness"]),
                "pagerank": float(row["pagerank"]),
                "knockout_damage": float(row["fragmentation_score"]),
                "nodes_outside_giant": int(row["nodes_outside_giant"]),
                "betweenness_z": float(row["betweenness_z"]),
                "betweenness_rank": int(row["betweenness_rank"]),
                "fragmentation_rank": int(row["fragmentation_rank"]),
            }
        )

    rng = random.Random(SEED)
    null_targets = [
        "Rockman_(character)",
        "Spider-Man",
        "Wolverine_(character)",
        "Black_Widow_(Natasha_Romanova)",
    ]
    null_samples = {node: [] for node in null_targets}
    for _ in range(NULL_SHUFFLES):
        shuffled = degree_preserving_shuffle(graph, rng)
        values = nx.betweenness_centrality(shuffled)
        for node in null_targets:
            null_samples[node].append(float(values[node]))

    removals = {}
    for node in graph:
        detail = removal_detail(graph, node)
        removals[node] = {
            "giant_after": detail["giant_after"],
            "component_count_after": detail["component_count_after"],
            "nodes_outside_giant": detail["nodes_outside_giant"],
            "separated": detail["separated"],
        }

    selected = [
        "Spider-Man",
        "Black_Widow_(Natasha_Romanova)",
        "Doctor_Strange",
        "Deadpool",
        "Wolverine_(character)",
        "Rockman_(character)",
    ]
    quiz = [
        ["Wolverine_(character)", "Black_Widow_(Natasha_Romanova)"],
        ["Rockman_(character)", "Doctor_Strange"],
        ["Deadpool", "Wolverine_(character)"],
    ]
    attack_payload = {}
    for strategy, rows in attacks.groupby("strategy"):
        attack_payload[strategy] = [
            {
                "removed": int(row.removed),
                "remaining": float(row.remaining_giant_fraction),
            }
            for row in rows.sort_values("removed").itertuples()
        ]

    payload = {
        "nodes": nodes_payload,
        "edges": [[u, v] for u, v in graph.edges()],
        "original_nodes": graph.number_of_nodes(),
        "removals": removals,
        "selected": selected,
        "quiz": quiz,
        "attacks": attack_payload,
        "null_samples": null_samples,
        "null_shuffles": NULL_SHUFFLES,
        "correlations": {
            "pearson": float(metrics["betweenness"].corr(metrics["fragmentation_score"])),
            "spearman": float(metrics["betweenness"].corr(metrics["fragmentation_score"], method="spearman")),
        },
    }
    OUTPUT.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
