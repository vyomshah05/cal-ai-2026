"""Redis Stack connection + RediSearch helpers for the semantic cache.

The data plane (docs, libs) is now Supabase. Redis is used exclusively for the
W-TinyLFU semantic cache (idx:cache, bf:doorkeeper, cms:freq, topk:libs).
The server owns index creation for idx:cache; the ingest side is gone.

Binary-safe: the client is opened with decode_responses=False because vectors
are raw float32 bytes. Text/TAG fields are decoded explicitly via `_text()`.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

import numpy as np

import config

_TAG_SPECIAL = set(r''' :.\-/@{}[]()|<>=~!&"'$%^*+?,;''') | {"\\"}


@lru_cache(maxsize=1)
def get_client():
    import redis

    return redis.Redis(
        host=config.REDIS_HOST,
        port=config.REDIS_PORT,
        username=config.REDIS_USERNAME,
        password=config.REDIS_PASSWORD,
        decode_responses=False,
    )


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return "" if value is None else str(value)


def escape_tag(value: str) -> str:
    out = []
    for ch in value:
        if ch in _TAG_SPECIAL:
            out.append("\\")
        out.append(ch)
    return "".join(out)


def index_exists(index: str) -> bool:
    try:
        get_client().ft(index).info()
        return True
    except Exception:
        return False


def _cache_index_dim() -> int | None:
    """Return the configured vector dim of idx:cache, or None if unknowable."""
    try:
        info = get_client().ft(config.IDX_CACHE).info()
        # info is a flat list of alternating key/value pairs
        attrs = dict(zip(info[::2], info[1::2])) if isinstance(info, list) else {}
        # Look for the attributes section
        for field_info in (attrs.get(b"attributes") or attrs.get("attributes") or []):
            # Each attribute is itself a flat list
            if isinstance(field_info, list):
                fa = dict(zip(field_info[::2], field_info[1::2]))
                if fa.get(b"type") == b"VECTOR" or fa.get("type") == "VECTOR":
                    dim_val = fa.get(b"dim") or fa.get("dim")
                    if dim_val is not None:
                        return int(dim_val)
    except Exception:
        pass
    return None


def ensure_cache_index() -> None:
    """Create idx:cache if it doesn't exist, or recreate it if the dim changed.

    The server now owns this index (the old ingest side is gone). Safe to call
    multiple times — it's a no-op when the index already exists with the correct dim.
    """
    if index_exists(config.IDX_CACHE):
        existing_dim = _cache_index_dim()
        if existing_dim is None or existing_dim == config.EMBED_DIM:
            return  # index is fine
        # Dim mismatch (e.g. old 1024-d index with new 384-d model) — drop and recreate
        try:
            get_client().ft(config.IDX_CACHE).dropindex(delete_documents=False)
        except Exception:
            pass
    try:
        from redis.commands.search.field import TagField, TextField, VectorField
        from redis.commands.search.index_definition import IndexDefinition, IndexType

        vec_attrs = {
            "TYPE": "FLOAT32",
            "DIM": config.EMBED_DIM,
            "DISTANCE_METRIC": "COSINE",
        }
        get_client().ft(config.IDX_CACHE).create_index(
            [
                VectorField("embedding", "HNSW", vec_attrs),
                TagField("library_id"),
                TagField("version"),
                TextField("query"),
                TextField("payload"),
                TextField("created_at"),
                TextField("hits"),
            ],
            definition=IndexDefinition(
                prefix=["cache:"], index_type=IndexType.HASH
            ),
        )
    except Exception:
        pass  # already exists or Redis unavailable — cache.py handles resilience


def _cosine(score_field: Any) -> float:
    """COSINE distance field → cosine similarity (higher is closer)."""
    try:
        return 1.0 - float(_text(score_field))
    except (TypeError, ValueError):
        return 0.0
