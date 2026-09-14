"""Build the Week 2 models and null-model results for the Marvel network."""

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
import plotly.graph_objects as go
from plotly.subplots import make_subplots

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
FIGURE_DIR = REPO_ROOT / "assets" / "figures" / "week2"
SUMMARY_PATH = REPO_ROOT / "assets" / "week2_summary.json"
FIGURE_DIR.mkdir(parents=True, exist_ok=True)

RNG_SEED = 20260909
SHUFFLE_COUNT = 100
COLORS = {"marvel": "#e85a98", "random": "#8d63ff", "ba": "#e0a62d", "null": "#b9abff"}


def load_marvel_network() -> tuple[pd.DataFrame, pd.DataFrame, nx.DiGraph]:
    """Load Week 1's frozen data while preserving all nodes, including isolates."""
    nodes = pd.read_csv(DATA_DIR / "week1_nodes.tsv", sep="\t", comment="#", quoting=3)
    edges = pd.read_csv(DATA_DIR / "week1_edges.tsv", sep="\t", comment="#", names=["source", "target"])
    graph = nx.DiGraph()
    graph.add_nodes_from(nodes["node_id"].tolist())
    graph.add_edges_from(edges[["source", "target"]].itertuples(index=False, name=None))
    return nodes, edges, graph


def calculate_degree_distribution(graph: nx.Graph) -> dict[str, list[float]]:
    """Return a compact CCDF that is suitable for both JSON and Plotly."""
    degrees = [degree for _, degree in graph.degree()]
    counts = Counter(degrees)
    total = len(degrees)
    running = 0
    pairs = []
    for degree in sorted(counts, reverse=True):
        running += counts[degree]
        pairs.append((degree, running / total))
    pairs.reverse()
    return {"degree": [degree for degree, _ in pairs], "ccdf": [value for _, value in pairs]}


def generate_random_network(graph: nx.Graph) -> nx.Graph:
    """Create an Erdős–Rényi fixed-edge comparator."""
    return nx.gnm_random_graph(graph.number_of_nodes(), graph.number_of_edges(), seed=RNG_SEED)


def generate_ba_network(graph: nx.Graph) -> tuple[nx.Graph, int]:
    """Create a BA network with m chosen to match the observed average degree."""
    m = min(max(1, round(graph.number_of_edges() / graph.number_of_nodes())), graph.number_of_nodes() - 1)
    return nx.barabasi_albert_graph(graph.number_of_nodes(), m, seed=RNG_SEED), m


def degree_preserving_shuffle(graph: nx.DiGraph, rng: random.Random) -> nx.DiGraph:
    """Swap directed edge endpoints without changing any in- or out-degree."""
    shuffled = graph.copy()
    edges = list(shuffled.edges())
    # A few passes over the edge list are enough to decorrelate this graph while
    # keeping the reproducible 100-shuffle run practical on a course laptop.
    for _ in range(max(1000, len(edges) * 4)):
        first, second = rng.sample(edges, 2)
        u, v = first
        x, y = second
        if len({u, v, x, y}) < 4 or shuffled.has_edge(u, y) or shuffled.has_edge(x, v):
            continue
        shuffled.remove_edges_from((first, second))
        shuffled.add_edges_from(((u, y), (x, v)))
        edges = list(shuffled.edges())
    return shuffled


def calculate_network_metrics(graph: nx.DiGraph) -> dict[str, float]:
    """Measure properties whose interpretation can be tested against the null model."""
    undirected = nx.Graph(graph)
    degrees = dict(undirected.degree())
    total_degree = sum(degrees.values())
    largest_component = max((len(component) for component in nx.connected_components(undirected)), default=0)
    return {
        "reciprocity": float(nx.reciprocity(graph) or 0),
        "triangles": float(sum(nx.triangles(undirected).values()) / 3),
        "components": float(nx.number_connected_components(undirected)),
        "largest_component": float(largest_component),
        "max_degree": float(max(degrees.values(), default=0)),
        "hub_share": max(degrees.values(), default=0) / total_degree if total_degree else 0,
        "clustering": float(nx.average_clustering(undirected)),
    }


def analyze_friendship_paradox(graph: nx.Graph, nodes: pd.DataFrame) -> dict:
    """Compare each character's degree with the mean degree of its neighbours."""
    names = nodes.set_index("node_id")["name"].to_dict()
    degrees = dict(graph.degree())
    rows = []
    for node in graph:
        neighbors = list(graph.neighbors(node))
        if not neighbors:
            continue
        average = sum(degrees[neighbor] for neighbor in neighbors) / len(neighbors)
        rows.append({
            "node": node,
            "name": names.get(node, node),
            "degree": degrees[node],
            "average_neighbor_degree": average,
            "difference": average - degrees[node],
        })
    local_maxima = [row for row in rows if all(row["degree"] >= degrees[n] for n in graph.neighbors(row["node"]))]
    strongest = sorted(rows, key=lambda row: row["difference"], reverse=True)[:8]
    paradox_rows = [row for row in rows if row["difference"] > 0]
    return {
        "rows": rows,
        "connected_nodes": len(rows),
        "nodes_with_more_connected_neighbors": len(paradox_rows),
        "share_with_more_connected_neighbors": len(paradox_rows) / len(rows),
        "average_node_degree": sum(row["degree"] for row in rows) / len(rows),
        "average_neighbor_degree": sum(row["average_neighbor_degree"] for row in rows) / len(rows),
        "local_maxima": sorted(local_maxima, key=lambda row: (-row["degree"], row["name"])),
        "strongest_effect": strongest,
    }


def run_shuffle_tests(graph: nx.DiGraph) -> dict:
    """Generate degree-preserving null networks and compare every metric."""
    real = calculate_network_metrics(graph)
    rng = random.Random(RNG_SEED)
    values = {metric: [] for metric in real}
    for _ in range(SHUFFLE_COUNT):
        shuffled = calculate_network_metrics(degree_preserving_shuffle(graph, rng))
        for metric, value in shuffled.items():
            values[metric].append(value)
    distributions = {}
    for metric, samples in values.items():
        mean = sum(samples) / len(samples)
        variance = sum((sample - mean) ** 2 for sample in samples) / (len(samples) - 1)
        sd = variance**0.5
        extreme = sum(abs(sample - mean) >= abs(real[metric] - mean) for sample in samples)
        distributions[metric] = {
            "real": real[metric],
            "shuffled": samples,
            "mean": mean,
            "sd": sd,
            "p_value": (extreme + 1) / (len(samples) + 1),
            "z_score": (real[metric] - mean) / sd if sd else 0,
        }
    return distributions


def save_degree_plot(series: dict[str, dict]) -> None:
    figure = go.Figure()
    for label, values, color in [
        ("Marvel", series["Marvel network"], COLORS["marvel"]),
        ("Random", series["Random graph"], COLORS["random"]),
        ("BA", series["Barabasi-Albert"], COLORS["ba"]),
    ]:
        degree = [x for x in values["degree"] if x > 0]
        ccdf = values["ccdf"][len(values["degree"]) - len(degree):]
        figure.add_trace(go.Scatter(x=degree, y=ccdf, mode="lines+markers", name=label,
                                    line={"color": color}, hovertemplate=f"k=%{{x}}<br>CCDF=%{{y:.3f}}<extra>{label}</extra>"))
    figure.update_layout(title="Marvel degree CCDF versus model networks", xaxis_title="Undirected degree k",
                         yaxis_title="P(K ≥ k)", xaxis_type="log", yaxis_type="log", template="simple_white",
                         legend={"orientation": "h"}, margin={"t": 70, "b": 55})
    figure.write_html(FIGURE_DIR / "degree_ccdf_models.html", include_plotlyjs="cdn", full_html=True)


def save_friendship_plot(result: dict) -> None:
    rows = result["rows"]
    figure = go.Figure(go.Scatter(
        x=[row["degree"] for row in rows], y=[row["average_neighbor_degree"] for row in rows],
        mode="markers", marker={"color": [COLORS["marvel"] if row["difference"] > 0 else COLORS["ba"] for row in rows],
        "size": 8, "opacity": 0.72}, text=[row["name"] for row in rows],
        customdata=[[row["difference"]] for row in rows],
        hovertemplate="<b>%{text}</b><br>Degree: %{x}<br>Average neighbour degree: %{y:.2f}<br>Difference: %{customdata[0]:.2f}<extra></extra>"))
    limit = max(max(row["degree"] for row in rows), max(row["average_neighbor_degree"] for row in rows)) + 5
    figure.add_trace(go.Scatter(x=[0, limit], y=[0, limit], mode="lines", name="Equal degree",
                                line={"color": COLORS["null"], "dash": "dash"}))
    figure.update_layout(title="The friendship paradox in the Marvel network", xaxis_title="Character degree",
                         yaxis_title="Average neighbour degree", template="simple_white", hovermode="closest",
                         legend={"orientation": "h"}, margin={"t": 70, "b": 55})
    figure.write_html(FIGURE_DIR / "friendship_paradox.html", include_plotlyjs="cdn", full_html=True)


def save_shuffle_plot(result: dict) -> None:
    metrics = list(result)
    figure = make_subplots(rows=1, cols=1)
    first = metrics[0]
    for index, metric in enumerate(metrics):
        samples = result[metric]["shuffled"]
        visibility = [index == 0] * len(metrics)
        figure.add_trace(go.Histogram(x=samples, name=metric.replace("_", " ").title(),
                                      marker_color=COLORS["null"], nbinsx=16, visible=index == 0,
                                      hovertemplate="%{x}<extra></extra>"), row=1, col=1)
        figure.add_vline(x=result[metric]["real"], line_color=COLORS["marvel"], line_width=3,
                         annotation_text="Marvel", visible=index == 0)
    buttons = []
    for index, metric in enumerate(metrics):
        visible = [False] * len(metrics)
        visible[index] = True
        buttons.append({"label": metric.replace("_", " ").title(), "method": "update",
                        "args": [{"visible": visible}, {
                            "title": f"Shuffle distribution: {metric.replace('_', ' ').title()}",
                            "shapes": [{"visible": shape_index == index} for shape_index in range(len(metrics))],
                        }]})
    figure.update_layout(title=f"Shuffle distribution: {first.replace('_', ' ').title()}", template="simple_white",
                         xaxis_title="Metric value", yaxis_title="Number of shuffles",
                         updatemenus=[{"buttons": buttons, "x": 0, "y": 1.18, "xanchor": "left"}],
                         margin={"t": 115, "b": 55})
    figure.write_html(FIGURE_DIR / "shuffle_test.html", include_plotlyjs="cdn", full_html=True)


def save_ba_plot(real: nx.Graph, ba: nx.Graph, m: int) -> None:
    figure = make_subplots(rows=1, cols=2, subplot_titles=("Ranked degree profile", "Degree CCDF"))
    for graph, label, color, column in [(real, "Marvel", COLORS["marvel"], 1), (ba, f"BA (m={m})", COLORS["ba"], 1)]:
        degrees = sorted((degree for _, degree in graph.degree()), reverse=True)
        figure.add_trace(go.Scatter(x=list(range(1, len(degrees) + 1)), y=degrees, mode="lines", name=label,
                                    line={"color": color}), row=1, col=1)
        ccdf = calculate_degree_distribution(graph)
        degree = [x for x in ccdf["degree"] if x > 0]
        values = ccdf["ccdf"][len(ccdf["degree"]) - len(degree):]
        figure.add_trace(go.Scatter(x=degree, y=values, mode="lines+markers", name=f"{label} CCDF",
                                    line={"color": color}, legendgroup=label), row=1, col=2)
    figure.update_xaxes(title_text="Node rank", row=1, col=1)
    figure.update_yaxes(title_text="Degree", row=1, col=1)
    figure.update_xaxes(title_text="Degree k", type="log", row=1, col=2)
    figure.update_yaxes(title_text="P(K ≥ k)", type="log", row=1, col=2)
    figure.update_layout(title="Real Marvel versus preferential attachment", template="simple_white",
                         legend={"orientation": "h"}, margin={"t": 85, "b": 60})
    figure.write_html(FIGURE_DIR / "preferential_attachment.html", include_plotlyjs="cdn", full_html=True)


def network_summary(graph: nx.Graph) -> dict[str, float]:
    degrees = dict(graph.degree())
    return {
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "average_degree": sum(degrees.values()) / graph.number_of_nodes(),
        "maximum_degree": max(degrees.values(), default=0),
        "clustering": nx.average_clustering(graph),
        "largest_component": max((len(c) for c in nx.connected_components(graph)), default=0),
        "components": nx.number_connected_components(graph),
    }


def main() -> None:
    nodes, edges, directed = load_marvel_network()
    real = nx.Graph(directed)
    random_graph = generate_random_network(real)
    ba_graph, ba_m = generate_ba_network(real)
    series = {
        "Marvel network": calculate_degree_distribution(real),
        "Random graph": calculate_degree_distribution(random_graph),
        "Barabasi-Albert": calculate_degree_distribution(ba_graph),
    }
    friendship = analyze_friendship_paradox(real, nodes)
    shuffle = run_shuffle_tests(directed)
    save_degree_plot(series)
    save_friendship_plot(friendship)
    save_shuffle_plot(shuffle)
    save_ba_plot(real, ba_graph, ba_m)
    summary = {
        "n_nodes": directed.number_of_nodes(), "directed_edges": directed.number_of_edges(),
        "undirected_edges": real.number_of_edges(), "directed": True, "ba_m": ba_m,
        "ccdf": series, "friendship_paradox": friendship, "shuffle_test": shuffle,
        "preferential_attachment": {"real": network_summary(real), "model": network_summary(ba_graph)},
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Saved Week 2 outputs to {FIGURE_DIR}")


if __name__ == "__main__":
    main()
