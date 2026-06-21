"""Local MiniLM embedding helper (all-MiniLM-L6-v2, 384-d, no API key).

Single source of truth for turning text into the 384-d vectors stored in
Supabase (libraries.embedding, fn_*.embedding) and the Redis semantic cache
(idx:cache). The dimension is asserted against EMBED_DIM so a mismatch
with the ingested data fails loudly instead of returning garbage near-hits.

The model is lazy-loaded and cached in-process on first use (~90 MB download
on cold start, then local). CPU-only inference is fast enough for hackathon
query rates.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np

import config


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer  # lazy import

    return SentenceTransformer("all-MiniLM-L6-v2")


def _check_dim(vec: list[float]) -> list[float]:
    if len(vec) != config.EMBED_DIM:
        raise RuntimeError(
            f"Embedding dim mismatch: model returned {len(vec)} but EMBED_DIM="
            f"{config.EMBED_DIM}. Ensure EMBED_MODEL=all-MiniLM-L6-v2 and EMBED_DIM=384."
        )
    return vec


def embed(text: str, **_kwargs) -> list[float]:
    """Embed a single string into a 384-d list[float]."""
    vec = _model().encode(text, normalize_embeddings=True).tolist()
    return _check_dim(vec)


def embed_batch(texts: list[str], **_kwargs) -> list[list[float]]:
    """Embed many strings (used by test fixtures)."""
    vecs = _model().encode(texts, normalize_embeddings=True).tolist()
    return [_check_dim(v) for v in vecs]


def to_bytes(vec: list[float]) -> bytes:
    """Pack a vector as little-endian float32 bytes for RediSearch KNN params."""
    return np.asarray(vec, dtype=np.float32).tobytes()
