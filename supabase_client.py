"""Supabase data-plane client for Lockstep.

Reads from three sources:
  - `libraries`     — registry metadata + 384-d MiniLM embeddings
  - `library_tags`  — cross-library tag index
  - `fn_{eco}_{name}` — per-library function catalogs with embeddings

All KNN is done in Python (numpy cosine) because the helper RPCs
(match_libraries, exec_sql) were not installed in the Supabase project.
Embedding matrices are lazy-loaded and memoized per-table so repeated queries
don't refetch thousands of rows.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

import numpy as np

import config

# How many fn rows to fetch per library (PostgREST page size)
_FN_PAGE = 1000


@lru_cache(maxsize=1)
def _client():
    from supabase import create_client

    if not config.SUPABASE_URL or not config.SUPABASE_SERVICE_KEY:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env"
        )
    return create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)


# ---------------------------------------------------------------------------
# Embedding helpers
# ---------------------------------------------------------------------------

def _parse_embedding(raw: Any) -> np.ndarray | None:
    """Parse pgvector-stored embedding (JSON string or Python list) → float32 array."""
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return None
    if isinstance(raw, list) and raw:
        return np.asarray(raw, dtype=np.float32)
    return None


def _cosine_top_k(
    query_vec: list[float],
    rows: list[dict],
    emb_key: str,
    k: int,
) -> list[dict]:
    """Return top-k rows by cosine similarity, adding a 'score' field."""
    q = np.asarray(query_vec, dtype=np.float32)
    scored: list[tuple[float, dict]] = []
    for row in rows:
        emb = _parse_embedding(row.get(emb_key))
        if emb is None:
            continue
        sim = float(np.dot(q, emb) / (np.linalg.norm(q) * np.linalg.norm(emb) + 1e-10))
        scored.append((sim, row))
    scored.sort(key=lambda t: t[0], reverse=True)
    out = []
    for sim, row in scored[:k]:
        r = {k: v for k, v in row.items() if k != emb_key}
        r["score"] = round(sim, 6)
        out.append(r)
    return out


# ---------------------------------------------------------------------------
# Libraries
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _all_libraries() -> list[dict]:
    """Fetch all libraries rows once and cache in-process."""
    rows = (
        _client()
        .table("libraries")
        .select("library_id,ecosystem,name,version,summary,homepage,docs_url,tier,tags,function_table,embedding")
        .execute()
        .data
    )
    return rows or []


def get_library(library_id: str) -> dict | None:
    """Return the libraries row for a library_id, or None if not found."""
    library_id = library_id.strip().lower()
    for row in _all_libraries():
        if row.get("library_id") == library_id:
            return row
    return None


def match_libraries(
    query_vec: list[float],
    k: int,
    *,
    ecosystem: str | None = None,
) -> list[dict]:
    """Top-k libraries by cosine similarity, optionally filtered by ecosystem."""
    rows = _all_libraries()
    if ecosystem:
        rows = [r for r in rows if r.get("ecosystem", "").lower() == ecosystem.lower()]
    return _cosine_top_k(query_vec, rows, "embedding", k)


# ---------------------------------------------------------------------------
# Function tables
# ---------------------------------------------------------------------------

@lru_cache(maxsize=64)
def _load_fn_table(table_name: str) -> list[dict]:
    """Fetch all rows of a per-library function table, memoized."""
    try:
        rows = (
            _client()
            .table(table_name)
            .select("qualified_name,kind,signature,summary,description,returns,source_url,embedding")
            .limit(_FN_PAGE)
            .execute()
            .data
        )
        return rows or []
    except Exception:
        return []


def match_functions(
    function_table: str,
    query_vec: list[float],
    k: int,
) -> list[dict]:
    """Top-k function rows from a library's fn_* table by cosine similarity."""
    rows = _load_fn_table(function_table)
    return _cosine_top_k(query_vec, rows, "embedding", k)


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------

def libraries_by_tag(tag: str) -> list[str]:
    """Return library_ids that carry a given tag (ordered by score desc)."""
    try:
        rows = (
            _client()
            .table("library_tags")
            .select("library_id,score")
            .eq("tag", tag.lower())
            .order("score", desc=True)
            .execute()
            .data
        )
        return [r["library_id"] for r in (rows or [])]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Cache invalidation (call when you know the DB was updated)
# ---------------------------------------------------------------------------

def clear_caches() -> None:
    """Bust the in-process memoized caches (e.g. after a re-ingest)."""
    _all_libraries.cache_clear()
    _load_fn_table.cache_clear()
    _client.cache_clear()
