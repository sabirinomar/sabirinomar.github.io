"""Compare language similarity across linked and length-matched Marvel pages.

Wikipedia extracts are fetched from the English Wikipedia API and cached outside
version control. Revision IDs are recorded so the analysis can be reproduced
without silently switching to later article versions.
"""

from __future__ import annotations

import bisect
import csv
import gzip
import json
import math
import random
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, unquote, urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUTPUT = ROOT / "assets" / "week5_summary.json"
SOURCE_MANIFEST = ROOT / "assets" / "week5_source_revisions.json"
CACHE = ROOT / ".cache" / "week5_wikipedia_text.json.gz"
FIGURE = ROOT / "assets" / "figures" / "week5" / "linked-language-similarity.svg"
API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "02805-Exercise-5.9/1.0 (https://github.com/sabirinomar/sabirinomar.github.io)"
SEED = 20260930
TOKEN_RE = re.compile(r"[^\W_]+(?:[-'’][^\W_]+)*", re.UNICODE)
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")

STOPWORDS = set(
    """
    a about above after again against all am an and any are aren't as at be because
    been before being below between both but by can cannot could couldn't did didn't
    do does doesn't doing don't down during each few for from further had hadn't has
    hasn't have haven't having he he'd he'll he's her here here's hers herself him
    himself his how how's i i'd i'll i'm i've if in into is isn't it it's its itself
    just me more most mustn't my myself no nor not of off on once only or other ought
    our ours ourselves out over own same shan't she she'd she'll she's should shouldn't
    so some such than that that's the their theirs them themselves then there there's
    these they they'd they'll they're they've this those through to too under until up
    very was wasn't we we'd we'll we're we've were weren't what what's when when's
    where where's which while who who's whom why why's with won't would wouldn't you
    you'd you'll you're you've your yours yourself yourselves
    """.split()
)


def read_tsv(path: Path) -> list[dict[str, str]]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line and not line.startswith("#")]
    if not lines:
        raise ValueError(f"No data rows found in {path}")
    reader = csv.DictReader(lines, delimiter="\t")
    return list(reader)


def load_nodes() -> list[dict[str, str]]:
    nodes = read_tsv(DATA / "week1_nodes.tsv")
    expected = {"node_id", "name", "url"}
    if not nodes or not expected.issubset(nodes[0]):
        raise ValueError("week1_nodes.tsv must contain node_id, name, and url columns")
    if len(nodes) != 303:
        raise ValueError(f"Expected 303 Marvel character rows, found {len(nodes)}")
    return nodes


def load_edges(node_ids: set[str]) -> list[tuple[str, str]]:
    path = DATA / "week1_edges.tsv"
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        fields = next(csv.reader([line], delimiter="\t"))
        if fields[0] == "source":
            continue
        if len(fields) < 2 or fields[0] not in node_ids or fields[1] not in node_ids:
            raise ValueError(f"Invalid Marvel edge row: {line}")
        rows.append((fields[0], fields[1]))
    if len(rows) != 1784:
        raise ValueError(f"Expected 1,784 directed Marvel links, found {len(rows)}")
    return rows


def title_from_url(url: str) -> str:
    path = urlparse(url).path
    if "/wiki/" not in path:
        raise ValueError(f"Unexpected Wikipedia URL: {url}")
    return unquote(path.split("/wiki/", 1)[1]).replace("_", " ")


def api_query(params: dict[str, str]) -> dict:
    query = urlencode({"action": "query", "format": "json", "formatversion": "2", **params})
    request = Request(f"{API}?{query}", headers={"User-Agent": USER_AGENT})
    for attempt in range(6):
        try:
            with urlopen(request, timeout=60) as response:
                payload = json.load(response)
        except HTTPError as error:
            if error.code not in {429, 503} or attempt == 5:
                raise RuntimeError(f"Wikipedia API request failed: {error}") from error
            retry_after = error.headers.get("Retry-After")
            delay = float(retry_after) if retry_after and retry_after.isdigit() else min(60, 5 * (2**attempt))
            time.sleep(delay)
            continue
        except (URLError, TimeoutError) as error:
            raise RuntimeError(f"Wikipedia API request failed: {error}") from error
        if "error" in payload:
            raise RuntimeError(f"Wikipedia API returned an error: {payload['error']}")
        return payload
    raise RuntimeError("Wikipedia API retry limit exceeded")


def fetch_by_titles(nodes: list[dict[str, str]]) -> tuple[dict[str, str], list[dict]]:
    if CACHE.exists():
        with gzip.open(CACHE, "rt", encoding="utf-8") as handle:
            progress = json.load(handle)
        extracts = progress.get("extracts", {})
        manifest_by_node = {row["node_id"]: row for row in progress.get("pages", [])}
    else:
        extracts = {}
        manifest_by_node = {}

    for node in nodes:
        if node["node_id"] in extracts and node["node_id"] in manifest_by_node:
            continue
        batch = [node]
        requested_titles = [title_from_url(row["url"]) for row in batch]
        payload = api_query(
            {
                "prop": "extracts|revisions",
                "explaintext": "1",
                "rvprop": "ids|timestamp",
                "redirects": "1",
                "titles": "|".join(requested_titles),
            }
        )
        query = payload["query"]
        aliases = {item["from"]: item["to"] for key in ("normalized", "redirects") for item in query.get(key, [])}

        def canonical(title: str) -> str:
            seen = set()
            while title in aliases and title not in seen:
                seen.add(title)
                title = aliases[title]
            return title.casefold()

        pages = {page["title"].casefold(): page for page in query.get("pages", [])}
        for node, requested in zip(batch, requested_titles):
            page = pages.get(canonical(requested))
            if page is None or page.get("missing") or not page.get("extract"):
                raise RuntimeError(f"Wikipedia returned no article text for {node['node_id']} ({requested})")
            revisions = page.get("revisions", [])
            if not revisions:
                raise RuntimeError(f"Wikipedia returned no revision ID for {node['node_id']}")
            revision = revisions[0]
            extracts[node["node_id"]] = page["extract"]
            manifest_by_node[node["node_id"]] = {
                    "node_id": node["node_id"],
                    "name": node["name"],
                    "url": node["url"],
                    "page_title": page["title"],
                    "page_id": page["pageid"],
                    "revision_id": revision["revid"],
                    "revision_timestamp": revision["timestamp"],
                }
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(CACHE, "wt", encoding="utf-8") as handle:
                json.dump({"extracts": extracts, "pages": list(manifest_by_node.values())}, handle)
        time.sleep(0.2)
    return extracts, list(manifest_by_node.values())


def fetch_by_revisions(manifest: list[dict]) -> dict[str, str]:
    extracts = {}
    for row in manifest:
        batch = [row]
        revisions = [str(row["revision_id"]) for row in batch]
        payload = api_query({"prop": "extracts|revisions", "explaintext": "1", "rvprop": "ids", "revids": "|".join(revisions)})
        pages_by_revision = {}
        for page in payload.get("query", {}).get("pages", []):
            page_revisions = page.get("revisions", [])
            if page_revisions and page.get("extract"):
                pages_by_revision[page_revisions[0]["revid"]] = page["extract"]
        for row in batch:
            text = pages_by_revision.get(row["revision_id"])
            if not text:
                raise RuntimeError(f"Could not retrieve pinned Wikipedia revision {row['revision_id']} for {row['node_id']}")
            extracts[row["node_id"]] = text
        time.sleep(0.2)
    return extracts


def get_page_texts(nodes: list[dict[str, str]]) -> tuple[dict[str, str], list[dict]]:
    if SOURCE_MANIFEST.exists():
        manifest_data = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
        manifest = manifest_data["pages"]
        if {row["node_id"] for row in manifest} != {row["node_id"] for row in nodes}:
            raise ValueError("Saved Wikipedia revision manifest does not match the 303 Marvel nodes")
    else:
        extracts, manifest = fetch_by_titles(nodes)
        manifest_data = {
            "source": "English Wikipedia MediaWiki API",
            "retrieved_utc": datetime.now(timezone.utc).isoformat(),
            "text_license": "Wikipedia text is available under CC BY-SA; source page URLs and revision IDs are listed per page.",
            "pages": sorted(manifest, key=lambda row: row["node_id"]),
        }
        SOURCE_MANIFEST.write_text(json.dumps(manifest_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(CACHE, "wt", encoding="utf-8") as handle:
            json.dump({"revisions": {row["node_id"]: row["revision_id"] for row in manifest}, "extracts": extracts}, handle)
        return extracts, manifest_data["pages"]

    expected_revisions = {row["node_id"]: row["revision_id"] for row in manifest}
    if CACHE.exists():
        with gzip.open(CACHE, "rt", encoding="utf-8") as handle:
            cached = json.load(handle)
        if cached.get("revisions") == expected_revisions and set(cached.get("extracts", {})) == set(expected_revisions):
            return cached["extracts"], manifest

    extracts = fetch_by_revisions(manifest)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(CACHE, "wt", encoding="utf-8") as handle:
        json.dump({"revisions": expected_revisions, "extracts": extracts}, handle)
    return extracts, manifest


def tokenize(text: str) -> list[str]:
    return [token.casefold() for token in TOKEN_RE.findall(text) if not token.isdecimal()]


def name_terms(nodes: list[dict[str, str]]) -> set[str]:
    result = set()
    for node in nodes:
        for candidate in (node["name"].split("(", 1)[0], node["node_id"].replace("_", " ").split("(", 1)[0]):
            result.update(tokenize(candidate))
    return result


def preprocess(texts: dict[str, str], names: set[str], remove_names: bool) -> tuple[dict[str, Counter], dict[str, int]]:
    documents = {}
    raw_lengths = {}
    for node_id, text in texts.items():
        raw = tokenize(text)
        raw_lengths[node_id] = len(raw)
        terms = [
            term
            for term in raw
            if term not in STOPWORDS
            and (not remove_names or (term not in names and re.sub(r"['’]s$", "", term) not in names))
        ]
        documents[node_id] = Counter(terms)
    return documents, raw_lengths


def tfidf_vectors(documents: dict[str, Counter]) -> tuple[dict[str, dict[str, float]], int]:
    document_frequency = Counter()
    for terms in documents.values():
        document_frequency.update(terms.keys())
    document_count = len(documents)
    excluded = {term for term, count in document_frequency.items() if count < 2 or count >= math.ceil(document_count * 0.5)}
    vocabulary = set(document_frequency) - excluded
    idf = {term: math.log((document_count + 1) / (document_frequency[term] + 1)) + 1 for term in vocabulary}
    vectors = {}
    for node_id, terms in documents.items():
        vector = {term: (1 + math.log(count)) * idf[term] for term, count in terms.items() if term in vocabulary}
        norm = math.sqrt(sum(value * value for value in vector.values()))
        vectors[node_id] = {term: value / norm for term, value in vector.items()} if norm else {}
    return vectors, len(vocabulary)


def cosine(first: dict[str, float], second: dict[str, float]) -> float:
    if len(first) > len(second):
        first, second = second, first
    return sum(value * second.get(term, 0.0) for term, value in first.items())


def unique_pairs(edges: list[tuple[str, str]]) -> list[tuple[str, str]]:
    pairs = {tuple(sorted((source, target))) for source, target in edges if source != target}
    return sorted(pairs)


def matched_nonlinks(
    positive_pairs: list[tuple[str, str]],
    active_nodes: set[str],
    linked_pairs: set[tuple[str, str]],
    lengths: dict[str, int],
) -> list[tuple[str, str]]:
    negative_pairs = [
        (first, second)
        for index, first in enumerate(sorted(active_nodes))
        for second in sorted(active_nodes)[index + 1 :]
        if (first, second) not in linked_pairs
    ]
    sorted_controls = sorted((lengths[first] + lengths[second], first, second) for first, second in negative_pairs)
    keys = [row[0] for row in sorted_controls]
    used = set()
    matches = []
    for first, second in sorted(positive_pairs, key=lambda pair: (lengths[pair[0]] + lengths[pair[1]], pair)):
        target = lengths[first] + lengths[second]
        position = bisect.bisect_left(keys, target)
        left, right = position - 1, position
        chosen = None
        while left >= 0 or right < len(sorted_controls):
            left_distance = abs(keys[left] - target) if left >= 0 else math.inf
            right_distance = abs(keys[right] - target) if right < len(sorted_controls) else math.inf
            index = left if left_distance <= right_distance else right
            if (index, sorted_controls[index][1], sorted_controls[index][2]) not in used:
                chosen = sorted_controls[index]
                used.add((index, chosen[1], chosen[2]))
                break
            if index == left:
                left -= 1
            else:
                right += 1
        if chosen is None:
            raise RuntimeError("Ran out of non-linked comparison pairs for length matching")
        matches.append(((first, second), (chosen[1], chosen[2])))
    return matches


def quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    location = (len(ordered) - 1) * probability
    low = math.floor(location)
    high = math.ceil(location)
    if low == high:
        return ordered[low]
    return ordered[low] * (high - location) + ordered[high] * (location - low)


def distribution(values: list[float]) -> dict[str, float]:
    return {
        "median": quantile(values, 0.5),
        "q1": quantile(values, 0.25),
        "q3": quantile(values, 0.75),
        "mean": sum(values) / len(values) if values else 0.0,
    }


def score_pairs(pairs: list[tuple[str, str]], vectors: dict[str, dict[str, float]]) -> list[float]:
    return [cosine(vectors[first], vectors[second]) for first, second in pairs]


def top_shared_terms(first: str, second: str, documents: dict[str, Counter], document_frequency: Counter) -> list[str]:
    shared = set(documents[first]) & set(documents[second])
    return sorted(shared, key=lambda term: (min(documents[first][term], documents[second][term]) * math.log(304 / (document_frequency[term] + 1)), term), reverse=True)[:5]


def evidence_excerpt(text: str, terms: list[str]) -> str:
    sentences = [sentence.strip() for sentence in SENTENCE_RE.split(text) if sentence.strip()]
    for sentence in sentences:
        if any(re.search(rf"(?<!\w){re.escape(term)}(?!\w)", sentence, flags=re.IGNORECASE) for term in terms):
            return sentence[:240]
    return sentences[0][:240] if sentences else ""


def save_figure(linked: list[float], controls: list[float]) -> None:
    width, height = 920, 590
    left, right, top, bottom = 95, 35, 84, 90
    plot_width, plot_height = width - left - right, height - top - bottom
    maximum = max(linked + controls, default=0.1)
    y_max = max(0.1, math.ceil(maximum * 10) / 10)
    rng = random.Random(SEED)
    pieces = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">Cosine similarity: linked pages and length-matched non-links</title>',
        '<desc id="desc">Distribution of TF-IDF cosine similarity after stopword, character-name, and high-document-frequency term removal.</desc>',
        '<rect width="100%" height="100%" fill="#f4f0e7"/>',
        f'<text x="{left}" y="34" font-family="Arial, sans-serif" font-size="20" font-weight="700" fill="#142b3b">Do linked Marvel pages speak more alike?</text>',
        f'<text x="{left}" y="58" font-family="Arial, sans-serif" font-size="12" fill="#465963">TF–IDF cosine after removing character-name terms, stopwords and corpus-wide boilerplate</text>',
    ]

    def y(value: float) -> float:
        return top + plot_height * (1 - value / y_max)

    for tick in range(6):
        value = y_max * tick / 5
        ypos = y(value)
        pieces.append(f'<line x1="{left}" y1="{ypos:.1f}" x2="{width-right}" y2="{ypos:.1f}" stroke="#d4d0c7" stroke-width="1"/>')
        pieces.append(f'<text x="{left-12}" y="{ypos+4:.1f}" text-anchor="end" font-family="Arial, sans-serif" font-size="11" fill="#465963">{value:.2f}</text>')
    pieces.extend(
        [
            f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top+plot_height}" stroke="#142b3b" stroke-width="1.5"/>',
            f'<line x1="{left}" y1="{top+plot_height}" x2="{width-right}" y2="{top+plot_height}" stroke="#142b3b" stroke-width="1.5"/>',
            f'<text x="24" y="{top+plot_height/2}" transform="rotate(-90 24 {top+plot_height/2})" text-anchor="middle" font-family="Arial, sans-serif" font-size="13" fill="#142b3b">Cosine similarity (higher = more similar)</text>',
        ]
    )
    series = [
        ("Linked page pairs", linked, 0.31, "#df754d"),
        ("Length-matched non-links", controls, 0.69, "#2f7580"),
    ]
    for label, values, x_fraction, color in series:
        center = left + plot_width * x_fraction
        stats = distribution(values)
        for value in values:
            jitter = rng.uniform(-62, 62)
            pieces.append(f'<circle cx="{center+jitter:.1f}" cy="{y(value):.1f}" r="2" fill="{color}" fill-opacity="0.17"/>')
        box_width = 46
        pieces.append(f'<line x1="{center}" y1="{y(stats["q1"]):.1f}" x2="{center}" y2="{y(stats["q3"]):.1f}" stroke="#142b3b" stroke-width="2"/>')
        pieces.append(f'<line x1="{center-box_width/2}" y1="{y(stats["q1"]):.1f}" x2="{center+box_width/2}" y2="{y(stats["q1"]):.1f}" stroke="#142b3b" stroke-width="2"/>')
        pieces.append(f'<line x1="{center-box_width/2}" y1="{y(stats["q3"]):.1f}" x2="{center+box_width/2}" y2="{y(stats["q3"]):.1f}" stroke="#142b3b" stroke-width="2"/>')
        pieces.append(f'<rect x="{center-box_width/2}" y="{y(stats["q3"]):.1f}" width="{box_width}" height="{max(1,y(stats["q1"])-y(stats["q3"])):.1f}" fill="{color}" fill-opacity="0.3" stroke="#142b3b" stroke-width="1.5"/>')
        pieces.append(f'<line x1="{center-box_width/2}" y1="{y(stats["median"]):.1f}" x2="{center+box_width/2}" y2="{y(stats["median"]):.1f}" stroke="#142b3b" stroke-width="3"/>')
        pieces.append(f'<text x="{center}" y="{top+plot_height+26}" text-anchor="middle" font-family="Arial, sans-serif" font-size="13" font-weight="700" fill="#142b3b">{label}</text>')
        pieces.append(f'<text x="{center}" y="{top+plot_height+47}" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#465963">median {stats["median"]:.3f}</text>')
    pieces.append(f'<text x="{left}" y="{height-16}" font-family="Arial, sans-serif" font-size="11" fill="#465963">Each dot is one of {len(linked):,} distinct pairs per group; controls are matched on the pair’s combined article word count.</text>')
    pieces.append("</svg>")
    FIGURE.parent.mkdir(parents=True, exist_ok=True)
    FIGURE.write_text("\n".join(pieces) + "\n", encoding="utf-8")


def main() -> None:
    nodes = load_nodes()
    node_ids = {node["node_id"] for node in nodes}
    edges = load_edges(node_ids)
    texts, manifest = get_page_texts(nodes)
    if len(texts) != len(nodes):
        raise RuntimeError(f"Expected text for all {len(nodes)} Marvel pages; retrieved {len(texts)}")

    manifest_by_node = {row["node_id"]: row for row in manifest}
    ids_by_page = Counter(row["page_id"] for row in manifest)
    excluded_nodes = {
        node["node_id"]
        for node in nodes
        if title_from_url(node["url"]).casefold() != manifest_by_node[node["node_id"]]["page_title"].casefold()
        or ids_by_page[manifest_by_node[node["node_id"]]["page_id"]] > 1
    }
    analysis_nodes = [node for node in nodes if node["node_id"] not in excluded_nodes]
    analysis_texts = {node["node_id"]: texts[node["node_id"]] for node in analysis_nodes}
    analysis_edges = [(source, target) for source, target in edges if source not in excluded_nodes and target not in excluded_nodes]
    linked_pairs = unique_pairs(analysis_edges)
    linked_set = set(linked_pairs)
    active_nodes = {node for pair in linked_pairs for node in pair}
    names = name_terms(nodes)
    clean_docs, raw_lengths = preprocess(analysis_texts, names, remove_names=True)
    named_docs, _ = preprocess(analysis_texts, names, remove_names=False)
    matches = matched_nonlinks(linked_pairs, active_nodes, linked_set, raw_lengths)
    positive_pairs = [pair for pair, _ in matches]
    control_pairs = [pair for _, pair in matches]

    clean_vectors, clean_vocabulary = tfidf_vectors(clean_docs)
    named_vectors, named_vocabulary = tfidf_vectors(named_docs)
    clean_linked_scores = score_pairs(positive_pairs, clean_vectors)
    clean_control_scores = score_pairs(control_pairs, clean_vectors)
    named_linked_scores = score_pairs(positive_pairs, named_vectors)
    named_control_scores = score_pairs(control_pairs, named_vectors)

    document_frequency = Counter()
    for terms in clean_docs.values():
        document_frequency.update(terms.keys())
    linked_results = []
    for (first, second), score in zip(positive_pairs, clean_linked_scores):
        shared = top_shared_terms(first, second, clean_docs, document_frequency)
        linked_results.append(
            {
                "first": first,
                "first_name": next(node["name"] for node in nodes if node["node_id"] == first),
                "first_url": next(node["url"] for node in nodes if node["node_id"] == first),
                "second": second,
                "second_name": next(node["name"] for node in nodes if node["node_id"] == second),
                "second_url": next(node["url"] for node in nodes if node["node_id"] == second),
                "cosine_similarity": score,
                "shared_terms": shared,
            }
        )
    linked_results.sort(key=lambda row: (-row["cosine_similarity"], row["first"], row["second"]))
    for result in linked_results[:3]:
        result["first_excerpt"] = evidence_excerpt(texts[result["first"]], result["shared_terms"])
        result["second_excerpt"] = evidence_excerpt(texts[result["second"]], result["shared_terms"])
    clean_linked = distribution(clean_linked_scores)
    clean_control = distribution(clean_control_scores)
    named_linked = distribution(named_linked_scores)
    named_control = distribution(named_control_scores)
    paired_differences = [linked - control for linked, control in zip(clean_linked_scores, clean_control_scores)]
    length_differences = [
        abs((raw_lengths[first_a] + raw_lengths[first_b]) - (raw_lengths[second_a] + raw_lengths[second_b]))
        / max(1, raw_lengths[first_a] + raw_lengths[first_b])
        for (first_a, first_b), (second_a, second_b) in matches
    ]

    summary = {
        "question": "Do directly linked Marvel character pages use more similar language than comparable non-linked pages?",
        "provenance": {
            "nodes": "data/week1_nodes.tsv",
            "edges": "data/week1_edges.tsv",
            "page_text": "English Wikipedia extracts pinned by assets/week5_source_revisions.json; full extracts cached locally under .cache/ and not committed.",
            "nodes_total": len(nodes),
            "active_nodes": len(active_nodes),
            "directed_links": len(edges),
            "distinct_undirected_linked_pairs": len(linked_pairs),
            "retrieved_page_count": len(texts),
            "analyzed_unique_page_count": len(analysis_nodes),
            "excluded_redirect_or_duplicate_pages": [
                {
                    "node_id": node["node_id"],
                    "name": node["name"],
                    "requested_title": title_from_url(node["url"]),
                    "resolved_title": manifest_by_node[node["node_id"]]["page_title"],
                    "page_id": manifest_by_node[node["node_id"]]["page_id"],
                }
                for node in nodes
                if node["node_id"] in excluded_nodes
            ],
            "preprocessing": {
                "extract": "Plain-text English Wikipedia article extracts",
                "tokenization": "Unicode letter/number tokens; internal hyphens and apostrophes remain part of a token; lowercase with casefold; numeric-only tokens excluded.",
                "stopwords": "Embedded English stopword list removed.",
                "character_names": "Tokens appearing in any Marvel node display name or node ID (excluding parenthetical disambiguators) removed in the primary analysis; a retained-name sensitivity check is also computed.",
                "boilerplate": "Terms occurring in at least half of the 303 pages and terms appearing in only one page are excluded from each TF-IDF vocabulary.",
                "lemmatization": "None; surface forms are retained.",
                "weighting": "Sublinear term frequency and smoothed inverse document frequency; L2-normalized document vectors; cosine similarity.",
                "redirects": "Pages that currently redirect to a different title or share a page ID with another Marvel node are excluded, so duplicate/re-targeted pages cannot create artificial perfect similarities.",
                "controls": "One distinct non-link pair per linked pair, sampled greedily without replacement to minimize absolute difference in the pair's combined raw word count; comparison set restricted to analyzed nodes incident to at least one link.",
            },
            "clean_vocabulary_size": clean_vocabulary,
            "name_retained_vocabulary_size": named_vocabulary,
        },
        "primary_result": {
            "linked": clean_linked,
            "length_matched_nonlinks": clean_control,
            "median_paired_difference": quantile(paired_differences, 0.5),
            "fraction_linked_pairs_more_similar_than_match": sum(value > 0 for value in paired_differences) / len(paired_differences),
            "median_relative_word_count_mismatch": quantile(length_differences, 0.5),
            "matched_pair_count": len(matches),
        },
        "name_retained_sensitivity": {
            "linked": named_linked,
            "length_matched_nonlinks": named_control,
            "median_paired_difference": quantile([linked - control for linked, control in zip(named_linked_scores, named_control_scores)], 0.5),
        },
        "most_similar_linked_pairs": linked_results[:20],
        "figure": "assets/figures/week5/linked-language-similarity.svg",
        "source_manifest": "assets/week5_source_revisions.json",
    }
    save_figure(clean_linked_scores, clean_control_scores)
    OUTPUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "pages": len(texts),
                "active_nodes": len(active_nodes),
                "linked_pairs": len(linked_pairs),
                "linked_median": clean_linked["median"],
                "matched_nonlink_median": clean_control["median"],
                "median_paired_difference": summary["primary_result"]["median_paired_difference"],
                "names_retained_median_difference": summary["name_retained_sensitivity"]["median_paired_difference"],
                "top_linked_pair": linked_results[0] if linked_results else None,
                "summary": str(OUTPUT.relative_to(ROOT)),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
