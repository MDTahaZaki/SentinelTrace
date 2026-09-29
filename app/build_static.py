"""Snapshot the pipeline into static/snapshot.json for the GitHub Pages build.

Pages can't run the FastAPI backend, so the UI replays these precomputed
stage results instead (see the static fallback in static/app.js).

Run:  python -m app.build_static
"""

import json
from pathlib import Path

from app.pipeline import STAGES, Pipeline

OUT = Path(__file__).resolve().parent.parent / "static" / "snapshot.json"


def build() -> dict:
    pipeline = Pipeline()
    stages = {}
    for stage in STAGES:
        summary = pipeline.run_stage(stage)
        stages[stage] = {"summary": summary, "graph": pipeline.graph_payload()}
    return {"stages": stages, "profiles": pipeline.profiles}


if __name__ == "__main__":
    OUT.write_text(json.dumps(build(), ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT}")
