"""SignalGuard web app — FastAPI backend + minimal UI.

Endpoints:
  GET  /                       → the web UI
  GET  /api/data               → available source files (real Berkshire letters, etc.)
  POST /api/run                → run the harness, return the full governed result
  GET  /api/runs/{run_id}      → reload a persisted run

The /api/run response bundles the report (signals), the checkpoint pass/fail with itemized
criteria, the guardrail results, the alarms + HITL queue, the OTEL totals, and the source
documents — everything the UI needs to make the harness's governance visible.
"""
from __future__ import annotations

import glob
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from signalguard.config import HarnessConfig
from signalguard.material.adapters import build_material
from signalguard.material.store import ArtifactStore
from signalguard.material.types import SourceType
from signalguard.orchestrator import run as run_harness

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
WEB = os.path.join(ROOT, "web")

app = FastAPI(title="SignalGuard")


# ------------------------------- helpers ---------------------------------- #
def make_agent(name: str):
    if name == "mock":
        from signalguard.agents.mock_agent import MockAgent
        return MockAgent()
    from signalguard.agents.claude_agent import ClaudeAgent
    if name in ("sonnet", "claude-sonnet-4-6"):
        return ClaudeAgent(model="claude-sonnet-4-6")
    if name in ("opus", "claude-opus-4-8"):
        return ClaudeAgent(model="claude-opus-4-8")
    raise HTTPException(400, f"unknown worker: {name}")


def _resolve(rel: str) -> str:
    p = os.path.normpath(os.path.join(DATA, rel))
    if p != DATA and not p.startswith(DATA + os.sep):
        raise HTTPException(400, "invalid path")
    if not os.path.exists(p):
        raise HTTPException(404, f"not found: {rel}")
    return p


def _assemble(store: ArtifactStore, run_id: str) -> dict:
    def load(stage):
        return store.load(run_id, stage) if store.exists(run_id, stage) else None

    report = load("report") or {}
    checkpoints = [load(s)["checkpoint"] for s in ("ingest", "grounding", "synthesize")
                   if load(s)]
    guardrails = [load(os.path.basename(p)[:-5])
                  for p in glob.glob(os.path.join(store.root, run_id, "guardrail_*.json"))]
    material = load("material") or {}
    return {
        "run_id": run_id,
        "report": report,
        "checkpoints": checkpoints,
        "guardrails": guardrails,
        "sources": material.get("docs", []),
    }


# ------------------------------- routes ----------------------------------- #
class RunRequest(BaseModel):
    ticker: str = "BRK.A"
    worker: str = "mock"
    earnings: str | None = None
    podcast: str | None = None
    x: str | None = None


@app.get("/")
def index():
    return FileResponse(os.path.join(WEB, "index.html"))


@app.get("/api/data")
def list_data():
    items = []
    for path in sorted(glob.glob(os.path.join(DATA, "**", "*"), recursive=True)):
        if os.path.isfile(path):
            rel = os.path.relpath(path, DATA)
            kind = ("earnings" if rel.endswith((".pdf", ".txt")) else
                    "x" if rel.endswith(".json") else "other")
            items.append({"path": rel, "kind": kind,
                          "size_kb": round(os.path.getsize(path) / 1024, 1)})
    return {"data": items}


@app.post("/api/run")
def api_run(req: RunRequest):
    sources = []
    if req.earnings:
        sources.append((SourceType.EARNINGS, _resolve(req.earnings)))
    if req.podcast:
        sources.append((SourceType.PODCAST, _resolve(req.podcast)))
    if req.x:
        sources.append((SourceType.X_POSTS, _resolve(req.x)))
    if not sources:
        raise HTTPException(400, "provide at least an earnings source")

    material = build_material(req.ticker, sources)
    store = ArtifactStore()
    run_harness(material, make_agent(req.worker), HarnessConfig(), store=store)
    return JSONResponse(_assemble(store, material.run_id))


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    store = ArtifactStore()
    if not store.exists(run_id, "report"):
        raise HTTPException(404, f"no such run: {run_id}")
    return JSONResponse(_assemble(store, run_id))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
