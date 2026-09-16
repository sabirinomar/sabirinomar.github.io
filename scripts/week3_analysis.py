"""Week 3: investigate which nodes hold the Marvel hyperlink network together.

The directed graph is retained for PageRank, while the undirected giant
component is used for shortest paths, centrality, removal, and robustness
experiments. Every output is generated from the frozen Week 1 data.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import networkx as nx
import pandas as pd
import plotly.graph_objects as go

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
FIGURE_DIR = REPO_ROOT / "assets" / "figures" / "week3"
OUTPUT_DIR = REPO_ROOT / "assets" / "week3"
POST_PATH = REPO_ROOT / "posts" / "week3" / "index.html"
FIGURE_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
POST_PATH.parent.mkdir(parents=True, exist_ok=True)

SEED = 20260916
NULL_SHUFFLES = 200
RANDOM_ATTACK_RUNS = 100


def load_network() -> tuple[pd.DataFrame, nx.DiGraph]:
    """Load every node before edges so isolates remain in the graph."""
    nodes = pd.read_csv(DATA_DIR / "week1_nodes.tsv", sep="\t", comment="#", quoting=3)
    edges = pd.read_csv(
        DATA_DIR / "week1_edges.tsv",
        sep="\t",
        comment="#",
        names=["source", "target"],
    )
    directed = nx.DiGraph()
    directed.add_nodes_from(nodes["node_id"].tolist())
    directed.add_edges_from(edges[["source", "target"]].itertuples(index=False, name=None))
    return nodes, directed


def top_items(values: dict[str, float], names: dict[str, str], count: int = 10) -> list[dict]:
    return [
        {"node_id": node, "name": names.get(node, node), "value": value}
        for node, value in sorted(values.items(), key=lambda item: (-item[1], item[0]))[:count]
    ]


def removal_metrics(graph: nx.Graph, node: str) -> dict[str, float | str]:
    """Measure structural damage after removing exactly one original node."""
    damaged = graph.copy()
    damaged.remove_node(node)
    components = sorted((len(component) for component in nx.connected_components(damaged)), reverse=True)
    giant = components[0] if components else 0
    remaining = damaged.number_of_nodes()
    return {
        "node_id": node,
        "giant_after": giant,
        "giant_fraction_remaining": giant / remaining if remaining else 0,
        "component_count_after": len(components),
        "nodes_outside_giant": remaining - giant,
        "fragmentation_score": (remaining - giant) / graph.number_of_nodes(),
    }


def attack_curve(
    original: nx.Graph,
    ranking: list[str],
    label: str,
) -> list[dict[str, float | str]]:
    graph = original.copy()
    rows = [{"strategy": label, "removed": 0, "remaining_giant_fraction": 1.0}]
    for step, node in enumerate(ranking, start=1):
        if node in graph:
            graph.remove_node(node)
        giant = max((len(component) for component in nx.connected_components(graph)), default=0)
        rows.append(
            {
                "strategy": label,
                "removed": step,
                "remaining_giant_fraction": giant / original.number_of_nodes(),
            }
        )
    return rows


def adaptive_betweenness_attack(original: nx.Graph) -> list[dict[str, float | str]]:
    graph = original.copy()
    rows = [{"strategy": "Adaptive betweenness", "removed": 0, "remaining_giant_fraction": 1.0}]
    for step in range(1, original.number_of_nodes() + 1):
        if not graph:
            break
        node = max(nx.betweenness_centrality(graph).items(), key=lambda item: (item[1], item[0]))[0]
        graph.remove_node(node)
        giant = max((len(component) for component in nx.connected_components(graph)), default=0)
        rows.append(
            {
                "strategy": "Adaptive betweenness",
                "removed": step,
                "remaining_giant_fraction": giant / original.number_of_nodes(),
            }
        )
    return rows


def random_attack_curves(original: nx.Graph) -> list[dict[str, float | str]]:
    rng = random.Random(SEED)
    values = [[] for _ in range(original.number_of_nodes() + 1)]
    nodes = list(original.nodes())
    for _ in range(RANDOM_ATTACK_RUNS):
        graph = original.copy()
        rng.shuffle(nodes)
        values[0].append(1.0)
        for step, node in enumerate(nodes, start=1):
            graph.remove_node(node)
            giant = max((len(component) for component in nx.connected_components(graph)), default=0)
            values[step].append(giant / original.number_of_nodes())
    rows = []
    for removed, samples in enumerate(values):
        mean = sum(samples) / len(samples)
        variance = sum((sample - mean) ** 2 for sample in samples) / max(1, len(samples) - 1)
        sd = variance**0.5
        rows.append(
            {
                "strategy": "Random removal",
                "removed": removed,
                "remaining_giant_fraction": mean,
                "lower": max(0, mean - sd),
                "upper": min(1, mean + sd),
            }
        )
    return rows


def degree_preserving_shuffle(graph: nx.Graph, rng: random.Random) -> nx.Graph:
    """Shuffle undirected edges while preserving every node degree."""
    shuffled = graph.copy()
    nx.double_edge_swap(
        shuffled,
        nswap=max(1000, shuffled.number_of_edges() * 3),
        max_tries=max(5000, shuffled.number_of_edges() * 20),
        seed=rng,
    )
    return shuffled


def save_bar(rows: list[dict], path: Path) -> None:
    rows = sorted(rows, key=lambda row: row["fragmentation_score"], reverse=True)[:15]
    rows = list(reversed(rows))
    figure = go.Figure(
        go.Bar(
            x=[row["fragmentation_score"] for row in rows],
            y=[row["name"] for row in rows],
            orientation="h",
            marker_color="#e85a98",
            customdata=[[row["nodes_outside_giant"], row["giant_after"]] for row in rows],
            hovertemplate="<b>%{y}</b><br>Fragmentation score: %{x:.3f}<br>Outside giant: %{customdata[0]}<br>Giant after: %{customdata[1]}<extra></extra>",
        )
    )
    figure.update_layout(
        title="Who breaks the Marvel universe?",
        xaxis_title="Fragmentation score",
        yaxis_title="Character",
        template="simple_white",
        margin={"l": 170, "r": 30, "t": 70, "b": 55},
    )
    figure.write_html(path, include_plotlyjs="cdn", full_html=True)


def save_scatter(rows: list[dict], path: Path) -> None:
    top = sorted(rows, key=lambda row: row["fragmentation_score"], reverse=True)[:8]
    figure = go.Figure(
        go.Scatter(
            x=[row["betweenness"] for row in rows],
            y=[row["fragmentation_score"] for row in rows],
            mode="markers",
            text=[row["name"] for row in rows],
            marker={"color": "#b9abff", "size": 8, "opacity": 0.72},
            hovertemplate="<b>%{text}</b><br>Betweenness: %{x:.4f}<br>Fragmentation: %{y:.3f}<extra></extra>",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=[row["betweenness"] for row in top],
            y=[row["fragmentation_score"] for row in top],
            text=[row["name"] for row in top],
            mode="markers+text",
            textposition="top center",
            marker={"color": "#f0579f", "size": 10},
            name="Largest knockouts",
            hoverinfo="skip",
        )
    )
    figure.update_layout(
        title="Does betweenness predict who holds the network together?",
        xaxis_title="Betweenness centrality",
        yaxis_title="Fragmentation score after one removal",
        template="simple_white",
        legend={"orientation": "h"},
        margin={"t": 80, "b": 60},
    )
    figure.write_html(path, include_plotlyjs="cdn", full_html=True)


def save_attack_plot(rows: list[dict], path: Path) -> None:
    figure = go.Figure()
    colors = {
        "Degree (static)": "#e85a98",
        "Betweenness (static)": "#8d63ff",
        "Closeness (static)": "#e0a62d",
        "Adaptive betweenness": "#1d264b",
        "Random removal": "#b9abff",
    }
    for strategy in colors:
        series = [row for row in rows if row["strategy"] == strategy]
        if not series:
            continue
        figure.add_trace(
            go.Scatter(
                x=[row["removed"] for row in series],
                y=[row["remaining_giant_fraction"] for row in series],
                mode="lines",
                name=strategy,
                line={"color": colors[strategy]},
            )
        )
        if strategy == "Random removal":
            figure.add_trace(
                go.Scatter(
                    x=[row["removed"] for row in series] + [row["removed"] for row in reversed(series)],
                    y=[row["upper"] for row in series] + [row["lower"] for row in reversed(series)],
                    fill="toself",
                    fillcolor="rgba(185,171,255,0.2)",
                    line={"color": "rgba(0,0,0,0)"},
                    name="Random ± 1 SD",
                    hoverinfo="skip",
                )
            )
    figure.update_layout(
        title="Attack the Marvel universe",
        xaxis_title="Characters removed",
        yaxis_title="Largest component / original giant component",
        yaxis={"range": [0, 1.05]},
        template="simple_white",
        legend={"orientation": "h"},
        margin={"t": 85, "b": 60},
    )
    figure.write_html(path, include_plotlyjs="cdn", full_html=True)


def save_null_plot(rows: list[dict], path: Path) -> None:
    rows = sorted(rows, key=lambda row: row["betweenness_z"], reverse=True)
    figure = go.Figure(
        go.Scatter(
            x=[row["degree"] for row in rows],
            y=[row["betweenness_z"] for row in rows],
            mode="markers",
            text=[row["name"] for row in rows],
            marker={"color": "#ff7bb4", "size": 8, "opacity": 0.75},
            hovertemplate="<b>%{text}</b><br>Degree: %{x}<br>Betweenness z-score: %{y:.2f}<extra></extra>",
        )
    )
    outliers = rows[:5] + sorted(rows, key=lambda row: row["betweenness_z"])[:5]
    figure.add_trace(
        go.Scatter(
            x=[row["degree"] for row in outliers],
            y=[row["betweenness_z"] for row in outliers],
            text=[row["name"] for row in outliers],
            mode="markers+text",
            textposition="top center",
            marker={"color": "#1d264b", "size": 10},
            name="Outliers",
            hoverinfo="skip",
        )
    )
    figure.add_hline(y=0, line_dash="dash", line_color="#625473")
    figure.update_layout(
        title="Broker — or just popular?",
        xaxis_title="Undirected degree",
        yaxis_title="Betweenness z-score vs degree-preserving null",
        template="simple_white",
        legend={"orientation": "h"},
        margin={"t": 80, "b": 60},
    )
    figure.write_html(path, include_plotlyjs="cdn", full_html=True)


def build_post(summary: dict, names: dict[str, str]) -> None:
    baseline = summary["baseline"]
    awards = summary["structural_surprises"]
    top = summary["knockout"][:5]
    top_name = top[0]["name"]
    corr = summary["correlations"]
    post = f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Week 3 · Who holds the Marvel universe together?</title>
    <meta name="description" content="Week 3 robustness and centrality analysis of the Marvel hyperlink network." />
    <link rel="stylesheet" href="../../assets/css/styles.css" />
  </head>
  <body>
    <header class="site-header"><div class="container nav"><div class="brand">Social Graphs Group</div>
      <nav aria-label="Main navigation"><ul class="nav-links">
        <li><a href="../../index.html">Home</a></li><li><a href="../week1/index.html">Week 1</a></li>
        <li><a href="../week2/index.html">Week 2</a></li><li><a href="index.html" aria-current="page">Week 3</a></li>
      </ul></nav></div></header>
    <main class="container main-content"><article class="article">
      <span class="eyebrow">Week 3 · Robustness &amp; centrality</span>
      <h1>Who holds the Marvel universe together?</h1>
      <p class="lead">A character can be highly connected, close to everyone, or strategically positioned between groups. We asked a more destructive question: what happens to the hyperlink network when one character disappears?</p>
      <div class="summary-grid">
        <div class="metric"><span class="label">Giant component</span><span class="value">{baseline["giant_nodes"]}</span></div>
        <div class="metric"><span class="label">Giant fraction</span><span class="value">{baseline["giant_fraction"]:.1%}</span></div>
        <div class="metric"><span class="label">Average path</span><span class="value">{baseline["average_path"]:.2f}</span></div>
        <div class="metric"><span class="label">Diameter</span><span class="value">{baseline["diameter"]}</span></div>
      </div>
      <div class="callout research-question"><strong>Directed versus undirected</strong><p>PageRank is calculated on the original directed hyperlink graph. Shortest paths, centrality comparisons, node removal, and robustness use the undirected giant component so that connected-component fragmentation is well-defined.</p></div>
      <h2>The knockout experiment</h2>
      <p>For each of the {baseline["giant_nodes"]} characters in the original giant component, we copied the same graph, removed exactly one node, and measured the new giant component, component count, and nodes outside the giant. The fragmentation score is the number outside the new giant divided by the original giant-component size.</p>
      <div class="figure-block"><iframe src="../../assets/figures/week3/knockout_fragmentation.html" title="Characters whose removal causes the most fragmentation" loading="lazy"></iframe><p class="figure-caption">Figure 1. Single-node knockouts ranked by structural damage.</p></div>
      <p><strong>{top_name}</strong> causes the largest single-node fragmentation in this experiment, followed by {top[1]["name"]}, {top[2]["name"]}, and {top[3]["name"]}. This is evidence about the graph's counterfactual structure, not about what would happen to fictional storylines.</p>
      <h2>Does betweenness predict fragility?</h2>
      <p>The Pearson correlation between betweenness and fragmentation is <strong>{corr["pearson"]:.3f}</strong>; the Spearman rank correlation is <strong>{corr["spearman"]:.3f}</strong>. These values describe association, not proof that betweenness causes damage. The scatterplot makes the disagreements visible: some bridges are replaceable, while some nodes cause disproportionate damage relative to their centrality.</p>
      <div class="figure-block"><iframe src="../../assets/figures/week3/betweenness_vs_fragmentation.html" title="Betweenness versus fragmentation" loading="lazy"></iframe><p class="figure-caption">Figure 2. Betweenness versus single-node fragmentation.</p></div>
      <h2>Attack the Marvel universe</h2>
      <p>We started every strategy from the same original giant component. Degree, betweenness, and closeness use static rankings computed once. Adaptive betweenness recomputes after every removal. Random removal is the mean of {RANDOM_ATTACK_RUNS} fixed-seed runs with a one-standard-deviation band.</p>
      <div class="figure-block"><iframe src="../../assets/figures/week3/attack_strategies.html" title="Targeted attack strategies" loading="lazy"></iframe><p class="figure-caption">Figure 3. Remaining giant-component fraction as characters are removed.</p></div>
      <h2>Broker — or just popular?</h2>
      <p>We generated {NULL_SHUFFLES} degree-preserving undirected rewires. Every shuffle preserves each node's degree, so the null asks whether a character's betweenness is unusual beyond degree alone. A positive z-score means more broker-like than the rewired baseline; it does not mean “more important” in the real Marvel universe.</p>
      <div class="figure-block"><iframe src="../../assets/figures/week3/betweenness_null_model.html" title="Degree versus betweenness z-score" loading="lazy"></iframe><p class="figure-caption">Figure 4. Degree versus betweenness z-score under the degree-preserving null.</p></div>
      <h2>Structural surprises</h2>
      <div class="table-wrap"><table><thead><tr><th>Category</th><th>Character</th><th>Evidence</th></tr></thead><tbody>
        <tr><td>Biggest structural bottleneck</td><td>{awards["biggest_bottleneck"]["name"]}</td><td>Highest fragmentation score: {awards["biggest_bottleneck"]["fragmentation_score"]:.3f}</td></tr>
        <tr><td>Strong broker beyond degree</td><td>{awards["strong_broker"]["name"]}</td><td>Highest null-model betweenness z-score: {awards["strong_broker"]["betweenness_z"]:.2f}</td></tr>
        <tr><td>High betweenness, less destructive</td><td>{awards["high_betweenness_replaceable"]["name"]}</td><td>High betweenness rank but relatively low knockout damage</td></tr>
      </tbody></table></div>
      <h2>Takeaway</h2>
      <p>The network has several kinds of “fame.” Degree counts links, closeness captures reachability, betweenness captures shortest-path brokerage, and PageRank rewards incoming links from central pages. The knockout experiment adds a robustness perspective: the most central-looking character is not automatically the one whose removal fragments the network most. The degree-preserving null is the comparison that keeps the interpretation honest.</p>
    </article></main>
    <footer class="site-footer"><div class="container">Social Graphs Group · Week 3</div></footer>
  </body>
</html>
"""
    POST_PATH.write_text(post, encoding="utf-8")


def main() -> None:
    nodes, directed = load_network()
    assert directed.number_of_nodes() == 303
    assert directed.number_of_edges() == 1784
    names = nodes.set_index("node_id")["name"].to_dict()
    undirected = nx.Graph(directed)
    giant_nodes = max(nx.connected_components(undirected), key=len)
    giant = undirected.subgraph(giant_nodes).copy()

    baseline = {
        "directed_nodes": directed.number_of_nodes(),
        "directed_edges": directed.number_of_edges(),
        "undirected_nodes": undirected.number_of_nodes(),
        "undirected_edges": undirected.number_of_edges(),
        "giant_nodes": giant.number_of_nodes(),
        "giant_fraction": giant.number_of_nodes() / undirected.number_of_nodes(),
        "average_path": nx.average_shortest_path_length(giant),
        "diameter": nx.diameter(giant),
    }
    degree = dict(giant.degree())
    degree_centrality = nx.degree_centrality(giant)
    closeness = nx.closeness_centrality(giant)
    betweenness = nx.betweenness_centrality(giant)
    pagerank = nx.pagerank(directed)
    centrality_rows = []
    for node in giant:
        centrality_rows.append(
            {
                "node_id": node,
                "name": names.get(node, node),
                "degree": degree[node],
                "degree_centrality": degree_centrality[node],
                "closeness": closeness[node],
                "betweenness": betweenness[node],
                "pagerank": pagerank.get(node, 0.0),
            }
        )
    centrality_rows.sort(key=lambda row: (-row["betweenness"], row["name"]))

    knockout = []
    for node in giant:
        row = removal_metrics(giant, node)
        row["name"] = names.get(node, node)
        row["degree"] = degree[node]
        row["betweenness"] = betweenness[node]
        row["closeness"] = closeness[node]
        row["pagerank"] = pagerank.get(node, 0.0)
        knockout.append(row)
    knockout.sort(key=lambda row: (-row["fragmentation_score"], row["name"]))

    x = pd.Series([row["betweenness"] for row in knockout])
    y = pd.Series([row["fragmentation_score"] for row in knockout])
    correlations = {"pearson": float(x.corr(y, method="pearson")), "spearman": float(x.corr(y, method="spearman"))}
    static_rankings = {
        "Degree (static)": [node for node, _ in sorted(degree.items(), key=lambda item: (-item[1], item[0]))],
        "Betweenness (static)": [node for node, _ in sorted(betweenness.items(), key=lambda item: (-item[1], item[0]))],
        "Closeness (static)": [node for node, _ in sorted(closeness.items(), key=lambda item: (-item[1], item[0]))],
    }
    attacks = []
    for label, ranking in static_rankings.items():
        attacks.extend(attack_curve(giant, ranking, label))
    attacks.extend(adaptive_betweenness_attack(giant))
    attacks.extend(random_attack_curves(giant))

    rng = random.Random(SEED)
    null_values = {node: [] for node in giant}
    for _ in range(NULL_SHUFFLES):
        shuffled = degree_preserving_shuffle(giant, rng)
        assert dict(shuffled.degree()) == dict(giant.degree()), "Degree-preserving shuffle changed a node degree"
        shuffled_betweenness = nx.betweenness_centrality(shuffled)
        for node, value in shuffled_betweenness.items():
            null_values[node].append(value)
    for node in giant:
        mean = sum(null_values[node]) / len(null_values[node])
        variance = sum((value - mean) ** 2 for value in null_values[node]) / max(1, len(null_values[node]) - 1)
        sd = variance**0.5
        for row in knockout:
            if row["node_id"] == node:
                row["null_betweenness_mean"] = mean
                row["null_betweenness_sd"] = sd
                row["betweenness_z"] = (betweenness[node] - mean) / sd if sd else 0.0
                break

    by_betweenness = {row["node_id"]: index + 1 for index, row in enumerate(sorted(knockout, key=lambda row: (-row["betweenness"], row["name"])))}
    by_fragmentation = {row["node_id"]: index + 1 for index, row in enumerate(knockout)}
    for row in knockout:
        row["betweenness_rank"] = by_betweenness[row["node_id"]]
        row["fragmentation_rank"] = by_fragmentation[row["node_id"]]
    sorted_by_z = sorted(knockout, key=lambda row: (-row["betweenness_z"], row["name"]))
    high_betweenness_replaceable = max(
        (row for row in knockout if row["betweenness_rank"] <= 20),
        key=lambda row: (row["fragmentation_rank"], row["name"]),
    )
    structural_surprises = {
        "biggest_bottleneck": knockout[0],
        "strong_broker": sorted_by_z[0],
        "high_betweenness_replaceable": high_betweenness_replaceable,
    }
    summary = {
        "baseline": baseline,
        "centrality_top10": {
            "degree": top_items(degree, names),
            "degree_centrality": top_items(degree_centrality, names),
            "closeness": top_items(closeness, names),
            "betweenness": top_items(betweenness, names),
            "pagerank": top_items(pagerank, names),
        },
        "knockout": knockout,
        "correlations": correlations,
        "attacks": attacks,
        "structural_surprises": structural_surprises,
        "null_shuffles": NULL_SHUFFLES,
        "random_attack_runs": RANDOM_ATTACK_RUNS,
    }
    (OUTPUT_DIR / "week3_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    pd.DataFrame(centrality_rows).to_csv(OUTPUT_DIR / "centrality_metrics.csv", index=False)
    pd.DataFrame(knockout).to_csv(OUTPUT_DIR / "knockout_metrics.csv", index=False)
    pd.DataFrame(attacks).to_csv(OUTPUT_DIR / "attack_curves.csv", index=False)
    save_bar(knockout, FIGURE_DIR / "knockout_fragmentation.html")
    save_scatter(knockout, FIGURE_DIR / "betweenness_vs_fragmentation.html")
    save_attack_plot(attacks, FIGURE_DIR / "attack_strategies.html")
    save_null_plot(knockout, FIGURE_DIR / "betweenness_null_model.html")
    build_post(summary, names)
    print("Top 10 by betweenness:")
    for row in summary["centrality_top10"]["betweenness"]:
        print(f'  {row["name"]}: {row["value"]:.6f}')
    print("Top 10 by PageRank:")
    for row in summary["centrality_top10"]["pagerank"]:
        print(f'  {row["name"]}: {row["value"]:.6f}')
    print(json.dumps({
        "baseline": baseline,
        "top_knockout": [(row["name"], row["fragmentation_score"]) for row in knockout[:10]],
        "correlations": correlations,
        "structural_surprises": {key: value["name"] for key, value in structural_surprises.items()},
    }, indent=2))


if __name__ == "__main__":
    main()
