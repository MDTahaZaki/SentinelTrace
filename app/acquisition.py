"""Stage 1 - Acquisition.

In a real deployment this stage would be a set of sandboxed collectors run by an
authorised agency. For the demo it reads a local JSON fixture of SYNTHETIC
footprints. There is deliberately no networking code in this module.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

SEED_FILE = Path(__file__).resolve().parent.parent / "data" / "seed_footprints.json"


def acquire(seed_file: Path = SEED_FILE) -> dict:
    """Load raw footprints and tag each one with its collection metadata."""
    with open(seed_file, encoding="utf-8") as f:
        seed = json.load(f)

    sources = {s["id"]: s for s in seed["sources"]}
    collected_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    raw = []
    for fp in seed["footprints"]:
        record = dict(fp)
        record["source_name"] = sources[fp["source"]]["name"]
        record["source_type"] = sources[fp["source"]]["type"]
        record["collected_at"] = collected_at
        raw.append(record)

    return {"sources": list(sources.values()), "footprints": raw}
