"""Lockstep webapp API — FastAPI backend for the React dashboard.

Exposes the existing librariesintodatabase ingestion pipeline (db.py) over
HTTP so the "Add your documentation" form can write to Supabase without
shelling out to the scrape.py CLI.

Quick start:
  python3 -m webapp_api.main          (starts on WEBAPP_API_PORT, default 8002)
"""
from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import librariesintodatabase.db as db
from webapp_api.ingest import ingest_library
from webapp_api.schemas import LibraryIngestRequest, LibraryIngestResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s")
log = logging.getLogger("lockstep.webapp_api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        db.ensure_ready()
    except Exception as e:  # surfaced at startup, not swallowed
        log.warning("db.ensure_ready() failed at startup: %s", e)
    yield


app = FastAPI(title="Lockstep Webapp API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/libraries", response_model=LibraryIngestResponse)
def add_library(payload: LibraryIngestRequest) -> LibraryIngestResponse:
    try:
        return ingest_library(payload)
    except Exception as e:
        log.exception("ingest_library failed")
        raise HTTPException(status_code=500, detail=str(e))


def main() -> None:
    port = int(os.getenv("WEBAPP_API_PORT", "8002"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
