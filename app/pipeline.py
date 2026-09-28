"""Runs the four pipeline stages one at a time and keeps their results in memory.

The UI calls one stage per request so judges can watch the pipeline run step by
step: Acquisition -> Normalise/Store -> Correlation -> Attribution.
"""

from collections import Counter, defaultdict

from app.acquisition import acquire
from app.correlation import correlate
from app.normalise import identifier_changes, normalise

STAGES = ["acquire", "normalise", "correlate", "attribute"]


class Pipeline:
    def __init__(self):
        self.reset()

    def reset(self):
        self.completed: list[str] = []
        self.sources: list[dict] = []
        self.raw: list[dict] = []
        self.store: list[dict] = []
        self.correlation: dict | None = None
        self.profiles: list[dict] = []

    # ---- stages -----------------------------------------------------------

    def run_stage(self, stage: str) -> dict:
        """Run the named stage. Stages must run in order."""
        expected = STAGES[len(self.completed)] if len(self.completed) < len(STAGES) else None
        if stage != expected:
            raise ValueError(f"next stage is {expected!r}, not {stage!r}")
        summary = getattr(self, f"_{stage}")()
        self.completed.append(stage)
        return {"stage": stage, **summary}

    def _acquire(self) -> dict:
        data = acquire()
        self.sources, self.raw = data["sources"], data["footprints"]
        per_source = Counter(fp["source_name"] for fp in self.raw)
        return {
            "headline": f"Collected {len(self.raw)} footprints from {len(self.sources)} sources",
            "details": [f"{name}: {n} footprints" for name, n in per_source.items()],
        }

    def _normalise(self) -> dict:
        self.store = normalise(self.raw)
        changes = identifier_changes(self.raw, self.store)

        # The interesting changes: identifiers that only match another source once cleaned.
        unlocked, highlight = [], []
        for field in ("pgp_fingerprint", "btc_wallet"):
            groups = defaultdict(list)
            for raw, clean in zip(self.raw, self.store):
                if clean[field]:
                    groups[clean[field]].append((raw[field].strip(), clean))
            for members in groups.values():
                raw_forms = {r for r, _ in members}
                if len(members) > 1 and len(raw_forms) > 1:
                    label = "PGP key" if field == "pgp_fingerprint" else "wallet"
                    handles = " & ".join(c["handle"] for _, c in members)
                    unlocked.append(f"{handles}: {label} written differently, matches after cleaning")
                    highlight += [c["id"] for _, c in members]

        return {
            "headline": f"Normalised {len(changes)} identifiers; {len(unlocked)} cross-source matches unlocked",
            "details": unlocked + ["PGP keys → upper-case hex, no spaces",
                                   "bech32 wallets → lower-case",
                                   "writing samples kept verbatim (casing = style signal)"],
            "highlight": highlight,
        }

    def _correlate(self) -> dict:
        self.correlation = correlate(self.store)
        edges = self.correlation["edges"]
        hard = [e for e in edges if e["hard"]]
        style = [e for e in edges if not e["hard"] and "stylometry" in e["kinds"]]
        infra = [e for e in edges if not e["hard"] and "stylometry" not in e["kinds"]]
        name = {fp["id"]: fp["handle"] for fp in self.store}
        return {
            "headline": f"Found {len(edges)} links: {len(hard)} hard, {len(style)} stylometry, "
                        f"{len(infra)} infrastructure",
            "details": [f"{name[e['source']]} ↔ {name[e['target']]} ({e['confidence']}): "
                        f"{'; '.join(e['reasons'])}" for e in edges],
        }

    def _attribute(self) -> dict:
        self.profiles = self._build_profiles()
        actors = {p["actor"] for p in self.profiles}
        multi = [a for a, n in Counter(p["actor"] for p in self.profiles).items() if n > 1]
        suggested = [p for p in self.profiles if p["suggested_actor"]]
        return {
            "headline": f"{len(self.profiles)} handles attributed to {len(actors)} actors "
                        f"({len(multi)} multi-persona), {len(suggested)} suggested alias",
            "details": [f"{p['handle']} → possible alias of {p['suggested_actor']} "
                        f"({p['top_link']['confidence']}, {p['top_link']['reason']})"
                        for p in suggested],
        }

    # ---- attribution ------------------------------------------------------

    def _build_profiles(self) -> list[dict]:
        result = self.correlation
        actor_of = result["actor_of"]
        graph = result["graph"]
        by_id = {fp["id"]: fp for fp in self.store}
        actor_size = Counter(actor_of.values())

        profiles = []
        for fp in self.store:
            links = []
            for other in graph.neighbors(fp["id"]):
                e = graph.edges[fp["id"], other]
                links.append({
                    "handle": by_id[other]["handle"],
                    "id": other,
                    "confidence": e["confidence"],
                    "hard": e["hard"],
                    "reason": "; ".join(e["reasons"]),
                })
            links.sort(key=lambda link: -link["confidence"])

            # A lone persona with a strong stylometry link into an established actor is a
            # suggested alias (a "migrated persona"). Handles already in a multi-persona
            # actor are not re-flagged; the link is shown from the lone persona's side.
            suggested = None
            if actor_size[actor_of[fp["id"]]] == 1:
                suggested = next(
                    (actor_of[link["id"]] for link in links
                     if not link["hard"] and "writing style" in link["reason"]
                     and actor_size[actor_of[link["id"]]] > 1),
                    None,
                )
            profiles.append({
                "id": fp["id"],
                "actor": actor_of[fp["id"]],
                "suggested_actor": suggested,
                "handle": fp["handle"],
                "source": fp["source_name"],
                "pgp_fingerprint": fp["pgp_fingerprint"],
                "btc_wallet": fp["btc_wallet"],
                "ssl_cert_cn": fp["ssl_cert_cn"],
                "server_banner": fp["server_banner"],
                "writing_sample": fp["writing_sample"],
                "last_seen": fp["last_seen"],
                "confidence": links[0]["confidence"] if links else None,
                "top_link": links[0] if links else None,
                "links": links,
            })
        profiles.sort(key=lambda p: (p["suggested_actor"] or p["actor"], p["actor"], p["handle"].lower()))
        return profiles

    # ---- queries ----------------------------------------------------------

    def search(self, q: str = "", date_from: str = "", date_to: str = "",
               expand: bool = True) -> list[dict]:
        """Filter profiles by handle / wallet / PGP / source text and a last-seen window.

        With expand=True, directly linked handles and every handle of the matched
        actor (or its suggested actor) are included too, so a search for one
        persona brings back the rest of the actor's footprint.
        """
        q = q.strip().lower()

        def matches(p):
            if date_from and p["last_seen"] < date_from:
                return False
            if date_to and p["last_seen"] > date_to:
                return False
            if not q:
                return True
            haystack = [p["handle"], p["source"], p["actor"], p["btc_wallet"] or "",
                        p["pgp_fingerprint"] or "", p["ssl_cert_cn"] or ""]
            return any(q in h.lower() for h in haystack)

        hit_ids = {p["id"] for p in self.profiles if matches(p)}
        if expand and q:
            hits = [p for p in self.profiles if p["id"] in hit_ids]
            actors = {a for p in hits for a in (p["actor"], p["suggested_actor"]) if a}
            for p in hits:
                hit_ids.update(link["id"] for link in p["links"])
            hit_ids.update(p["id"] for p in self.profiles
                           if p["actor"] in actors or p["suggested_actor"] in actors)
        return [dict(p, direct_match=matches(p))
                for p in self.profiles if p["id"] in hit_ids]

    def graph_payload(self) -> dict:
        """Nodes and edges for the UI; detail grows as stages complete."""
        if not self.raw:
            return {"nodes": [], "edges": []}
        records = self.store or self.raw
        actors = {p["id"]: p for p in self.profiles}
        nodes = [{
            "id": fp["id"],
            "handle": fp["handle"],
            "source": fp["source_name"],
            "actor": actors[fp["id"]]["actor"] if fp["id"] in actors else None,
            "suggested_actor": actors[fp["id"]]["suggested_actor"] if fp["id"] in actors else None,
        } for fp in records]
        edges = self.correlation["edges"] if self.correlation else []
        return {"nodes": nodes, "edges": edges}

    def status(self) -> dict:
        return {"stages": STAGES, "completed": self.completed,
                "next": STAGES[len(self.completed)] if len(self.completed) < len(STAGES) else None}
