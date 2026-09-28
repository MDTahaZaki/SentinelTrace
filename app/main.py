"""SentinelTrace API + static UI.

Run:  uvicorn app.main:app --port 8000
Then open http://127.0.0.1:8000
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from app.export import to_csv, to_json
from app.pipeline import STAGES, Pipeline

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="SentinelTrace", description="SIH26151 demo - synthetic data only")
pipeline = Pipeline()


# ---- pipeline control -----------------------------------------------------

@app.get("/api/pipeline")
def pipeline_status():
    return pipeline.status()


@app.post("/api/pipeline/reset")
def pipeline_reset():
    pipeline.reset()
    return pipeline.status()


@app.post("/api/pipeline/{stage}")
def pipeline_run_stage(stage: str):
    if stage not in STAGES:
        raise HTTPException(404, f"unknown stage {stage!r}")
    try:
        summary = pipeline.run_stage(stage)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return {"summary": summary, "status": pipeline.status()}


# ---- results --------------------------------------------------------------

def _search(q: str, date_from: str, date_to: str, expand: bool):
    if "attribute" not in pipeline.completed:
        raise HTTPException(409, "run the pipeline first")
    return pipeline.search(q, date_from, date_to, expand)


SearchQ = Query("", description="handle, wallet, PGP fingerprint, source or actor id")


@app.get("/api/actors")
def actors(q: str = SearchQ, date_from: str = "", date_to: str = "", expand: bool = True):
    return _search(q, date_from, date_to, expand)


@app.get("/api/graph")
def graph():
    return pipeline.graph_payload()


@app.get("/api/export.csv")
def export_csv(q: str = SearchQ, date_from: str = "", date_to: str = "", expand: bool = True):
    body = to_csv(_search(q, date_from, date_to, expand))
    return Response(body, media_type="text/csv", headers={
        "Content-Disposition": 'attachment; filename="sentineltrace_export.csv"'})


@app.get("/api/export.json")
def export_json(q: str = SearchQ, date_from: str = "", date_to: str = "", expand: bool = True):
    query = {"q": q, "date_from": date_from, "date_to": date_to, "expand": expand}
    body = to_json(_search(q, date_from, date_to, expand), query)
    return Response(body, media_type="application/json", headers={
        "Content-Disposition": 'attachment; filename="sentineltrace_export.json"'})


# The UI. Mounted last so it doesn't shadow the /api routes.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="ui")
