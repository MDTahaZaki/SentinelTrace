"""Stage 3 - Correlation Engine.

Builds an identity graph of footprints (one node per handle) and links them by:
  * hard evidence   - shared PGP fingerprint or BTC wallet (merges handles into one actor)
  * infrastructure  - shared SSL certificate CN or server banner (weak, supporting only)
  * stylometry      - character n-gram TF-IDF cosine similarity of writing samples,
                      which can re-identify a migrated persona that shares no key at all.

When several signals link the same pair, they are combined with noisy-OR:
    confidence = 1 - prod(1 - c_i)
so independent signals reinforce each other without ever exceeding 100.
"""

from collections import defaultdict
from itertools import combinations

import networkx as nx
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Per-signal confidence (0-1). Stylometry uses the similarity score itself.
SIGNAL_WEIGHTS = {
    "pgp": 0.95,
    "wallet": 0.90,
    "ssl_cn": 0.40,
    "banner": 0.15,  # stock banners like "nginx/1.24.0" are common, so this is weak
}
HARD_SIGNALS = {"pgp", "wallet"}
STYLE_THRESHOLD = 0.70   # minimum similarity to propose a stylometry link
MIN_EDGE_CONFIDENCE = 30  # links weaker than this are not shown


def stylometry_matrix(footprints: list[dict]):
    """Pairwise cosine similarity of writing samples.

    Character n-grams (3-5, within word boundaries) capture spelling, punctuation
    and casing habits ("recieve", "!!", "sry ~") rather than topic words, which
    is what matters on short 2-3 sentence samples. lowercase=False keeps casing
    as a signal.
    """
    vectorizer = TfidfVectorizer(
        analyzer="char_wb", ngram_range=(3, 5), lowercase=False, sublinear_tf=True
    )
    tfidf = vectorizer.fit_transform([fp["writing_sample"] for fp in footprints])
    return cosine_similarity(tfidf)


def _pair_signals(footprints: list[dict], sim) -> dict[tuple[str, str], list[dict]]:
    """Collect every piece of evidence linking each pair of footprints."""
    signals = defaultdict(list)

    # Exact-match identifiers: bucket footprints by value, then link within each bucket.
    fields = {
        "pgp": ("pgp_fingerprint", "shared PGP key"),
        "wallet": ("btc_wallet", "shared wallet"),
        "ssl_cn": ("ssl_cert_cn", "same SSL cert CN"),
        "banner": ("server_banner", "same server banner"),
    }
    for kind, (field, label) in fields.items():
        buckets = defaultdict(list)
        for fp in footprints:
            if fp[field]:
                buckets[fp[field]].append(fp["id"])
        for value, ids in buckets.items():
            for a, b in combinations(sorted(ids), 2):
                shown = value if len(value) <= 24 else value[:10] + "…"
                signals[(a, b)].append({
                    "kind": kind,
                    "confidence": SIGNAL_WEIGHTS[kind],
                    "reason": f"{label} {shown}",
                })

    # Stylometry: compare every pair of writing samples.
    for i, j in combinations(range(len(footprints)), 2):
        score = float(sim[i, j])
        if score >= STYLE_THRESHOLD:
            a, b = sorted((footprints[i]["id"], footprints[j]["id"]))
            signals[(a, b)].append({
                "kind": "stylometry",
                "confidence": score,
                "reason": f"writing style {score:.2f} similar",
            })

    return signals


def noisy_or(confidences: list[float]) -> float:
    remaining = 1.0
    for c in confidences:
        remaining *= 1.0 - c
    return 1.0 - remaining


def correlate(footprints: list[dict]) -> dict:
    """Run the correlation engine and return the graph, edges and actor clusters."""
    sim = stylometry_matrix(footprints)

    graph = nx.Graph()
    for fp in footprints:
        graph.add_node(fp["id"], **fp)

    edges = []
    for (a, b), evidence in _pair_signals(footprints, sim).items():
        confidence = round(noisy_or([e["confidence"] for e in evidence]) * 100)
        if confidence < MIN_EDGE_CONFIDENCE:
            continue
        kinds = {e["kind"] for e in evidence}
        edge = {
            "source": a,
            "target": b,
            "confidence": confidence,
            "hard": bool(kinds & HARD_SIGNALS),
            "kinds": sorted(kinds),
            "reasons": [e["reason"] for e in evidence],
        }
        edges.append(edge)
        graph.add_edge(a, b, **edge)

    # Actors are groups of handles joined by hard evidence (a shared key or wallet).
    hard_graph = nx.Graph()
    hard_graph.add_nodes_from(graph.nodes)
    hard_graph.add_edges_from((e["source"], e["target"]) for e in edges if e["hard"])
    components = sorted(
        nx.connected_components(hard_graph),
        key=lambda c: (-len(c), min(c)),  # biggest first, then seed order
    )
    actor_of = {}
    for n, comp in enumerate(components, start=1):
        for fp_id in comp:
            actor_of[fp_id] = f"ACTOR-{n:03d}"

    return {
        "graph": graph,
        "edges": sorted(edges, key=lambda e: -e["confidence"]),
        "actor_of": actor_of,
        "similarity": sim,
    }


def print_similarity_report(footprints: list[dict]) -> None:
    """Print the stylometry matrix plus a summary, for tuning the seed data."""
    sim = stylometry_matrix(footprints)
    handles = [fp["handle"][:12] for fp in footprints]

    print("Stylometry similarity matrix (char_wb 3-5 n-gram TF-IDF, cosine)\n")
    print(" " * 13 + " ".join(f"{h[:5]:>5}" for h in handles))
    for i, h in enumerate(handles):
        row = " ".join(" -- " if i == j else f"{sim[i, j]:5.2f}" for j in range(len(handles)))
        print(f"{h:<12} {row}")

    print("\nTop 10 pairs:")
    pairs = sorted(
        ((float(sim[i, j]), footprints[i]["handle"], footprints[j]["handle"])
         for i, j in combinations(range(len(footprints)), 2)),
        reverse=True,
    )
    for score, a, b in pairs[:10]:
        flag = "LINK" if score >= STYLE_THRESHOLD else ""
        print(f"  {score:.3f}  {a:<14} <-> {b:<14} {flag}")


if __name__ == "__main__":
    from app.acquisition import acquire
    from app.normalise import normalise

    store = normalise(acquire()["footprints"])
    print_similarity_report(store)

    result = correlate(store)
    print("\nCorrelation edges shown in the graph:")
    handle = {fp["id"]: fp["handle"] for fp in store}
    for e in result["edges"]:
        style = "hard     " if e["hard"] else "suggested"
        print(f"  {e['confidence']:>3}  {style}  {handle[e['source']]:<14} <-> "
              f"{handle[e['target']]:<14} {'; '.join(e['reasons'])}")
