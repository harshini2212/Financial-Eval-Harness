"""FastAPI app: JSON API over the pipeline + serves the single-page UI."""

from __future__ import annotations

import collections
import os
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import service

_STATIC = Path(__file__).parent / "static"

app = FastAPI(title="tieout", docs_url="/api/docs")

# Protect a public "Run live" button from running up the Anthropic bill: cap live
# runs per rolling hour. Tune via the TIEOUT_RUN_LIMIT env var (0 = unlimited).
_RUN_LIMIT = int(os.environ.get("TIEOUT_RUN_LIMIT", "40"))
_RUN_TIMES: collections.deque = collections.deque()


@app.get("/api/filings")
def filings():
    return service.filings_index()


@app.get("/api/registry")
def registry():
    return service.registry_json()


@app.get("/api/search")
def search(q: str = ""):
    return service.search_companies(q)


@app.get("/api/health")
def health():
    import os
    return {"api_key": bool(os.environ.get("ANTHROPIC_API_KEY"))}


@app.get("/api/analysis/{ticker}")
def analysis(ticker: str):
    try:
        return service.analyze(ticker)
    except Exception as exc:  # surface a clean error to the UI
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/analysis/{ticker}/run")
def analysis_live(ticker: str):
    if _RUN_LIMIT:
        now = time.time()
        while _RUN_TIMES and now - _RUN_TIMES[0] > 3600:
            _RUN_TIMES.popleft()
        if len(_RUN_TIMES) >= _RUN_LIMIT:
            raise HTTPException(status_code=429,
                                detail="Live-run limit reached for this hour — "
                                       "try again later (this protects the demo's API budget).")
        _RUN_TIMES.append(now)
    try:
        return service.analyze(ticker, force=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/")
def index():
    return FileResponse(_STATIC / "index.html")


app.mount("/", StaticFiles(directory=_STATIC), name="static")
