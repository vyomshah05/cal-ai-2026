"""Centralized configuration. Loads .env once and exposes typed constants.

Every module imports from here so the embedding model/dim, Redis URL, Supabase
credentials, and cache knobs are defined in exactly one place.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# --- Supabase (data plane: libraries, library_tags, fn_* tables) ---
SUPABASE_URL: str | None = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY: str | None = os.getenv("SUPABASE_SERVICE_KEY")

# --- Redis (W-TinyLFU semantic cache only) ---
REDIS_HOST: str = os.getenv("REDIS_HOST") or "observant-collar-patient-38243.db.redis.io"
REDIS_PORT: int = int(os.getenv("REDIS_PORT") or "17716")
REDIS_USERNAME: str = os.getenv("REDIS_USERNAME") or "default"
REDIS_PASSWORD: str | None = os.getenv("REDIS_PASSWORD") or None

# --- Anthropic (recommend_library rerank/synthesis) ---
ANTHROPIC_API_KEY: str | None = os.getenv("ANTHROPIC_API_KEY")
RERANK_MODEL: str = os.getenv("RERANK_MODEL", "claude-sonnet-4-6")

# --- Embeddings (MUST match the ingest side — all-MiniLM-L6-v2, 384-d) ---
EMBED_MODEL: str = os.getenv("EMBED_MODEL", "all-MiniLM-L6-v2")
EMBED_DIM: int = int(os.getenv("EMBED_DIM", "384"))

# --- Cache tuning ---
CACHE_CAPACITY: int = int(os.getenv("CACHE_CAPACITY", "1000"))
CACHE_THETA: float = float(os.getenv("CACHE_THETA", "0.92"))
# Threshold for the Supabase-based probability scan (different scale from CACHE_THETA
# because library-description cosines are lower than subtask-to-subtask cosines).
CACHE_SCAN_THETA: float = float(os.getenv("CACHE_SCAN_THETA", "0.40"))
DOCS_TTL_SECONDS: int = int(os.getenv("DOCS_TTL_SECONDS", str(30 * 24 * 3600)))
RECO_TTL_SECONDS: int = int(os.getenv("RECO_TTL_SECONDS", "900"))

# --- Retrieval ---
DOCS_TOP_K: int = int(os.getenv("DOCS_TOP_K", "8"))
LIBS_TOP_K: int = int(os.getenv("LIBS_TOP_K", "8"))

# --- Transport ---
LOCKSTEP_HOST: str = os.getenv("LOCKSTEP_HOST", "127.0.0.1")
LOCKSTEP_PORT: int = int(os.getenv("LOCKSTEP_PORT", "8000"))

# --- Contract-frozen Redis cache structure names (do NOT change) ---
IDX_CACHE = "idx:cache"
BF_DOORKEEPER = "bf:doorkeeper"
CMS_FREQ = "cms:freq"
TOPK_LIBS = "topk:libs"
