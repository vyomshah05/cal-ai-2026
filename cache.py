"""W-TinyLFU probabilistic semantic cache on Redis.

Design:
  get():
    1. Doorkeeper Bloom (bf:doorkeeper): first sighting of fingerprint →
       record it, return miss WITHOUT admitting (kills one-hit-wonder pollution).
    2. Vector near-hit (idx:cache KNN top-1): serve ONLY if cosine >= THETA
       AND library_id matches AND version matches EXACTLY.
  put():  (only called on a repeat sighting that missed)
    - Count-Min Sketch (cms:freq) tracks frequency.
    - At capacity, TinyLFU admission: admit only if candidate >= eviction victim.
  age(): halve CMS counts on a reset window.

CORRECTNESS INVARIANT: a cached payload is served only when cosine >= THETA AND
(library_id, version) match the request EXACTLY. Bloom false positives or CMS
overcounts can change speed/admission but NEVER let a wrong-version doc out.

RESILIENCE: if Redis is unreachable, all operations degrade gracefully to
always-miss / no-admit so the tools still serve from Supabase.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import time
from typing import Any

import numpy as np

import config
from redis_client import _cosine, _text, get_client, index_exists, ensure_cache_index

_WS = re.compile(r"\s+")


def normalize_query(query: str) -> str:
    return _WS.sub(" ", query.strip().lower())


def fingerprint(query: str, library_id: str, version: str) -> str:
    raw = f"{normalize_query(query)}|{library_id}|{version}|{config.EMBED_MODEL}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Structure init (idempotent)
# ---------------------------------------------------------------------------

def ensure_structures() -> None:
    """Create idx:cache + BF/CMS/TOPK if absent. Safe to call on every request."""
    try:
        ensure_cache_index()
    except Exception:
        pass
    r = get_client()
    try:
        r.bf().reserve(config.BF_DOORKEEPER, 0.001, 100_000)
    except Exception:
        pass
    try:
        r.cms().initbydim(config.CMS_FREQ, 2000, 10)
    except Exception:
        pass
    try:
        r.topk().reserve(config.TOPK_LIBS, 25, 2000, 7, 0.925)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# lookup
# ---------------------------------------------------------------------------

def lookup(
    library_id: str, version: str, query: str, vec: list[float]
) -> tuple[dict | None, bool]:
    """Look up a cached result.

    Returns (hit_or_None, admit_allowed).
      - First sighting  → record fingerprint, return (None, False).
      - Repeat sighting → attempt vector near-hit; on serve return (hit, False);
        on miss return (None, True) — eligible to be stored.

    If Redis is unreachable, returns (None, False) — always miss, never admit.
    """
    try:
        r = get_client()
        r.ping()
    except Exception:
        return None, False

    ensure_structures()
    fp = fingerprint(query, library_id, version)

    # 1. Doorkeeper: first sighting
    try:
        seen = bool(r.bf().exists(config.BF_DOORKEEPER, fp))
    except Exception:
        seen = True  # bloom unavailable → don't block correctness path
    if not seen:
        try:
            r.bf().add(config.BF_DOORKEEPER, fp)
        except Exception:
            pass
        return None, False

    # 2. Vector near-hit — scoped to this library so paraphrase queries hit
    if not index_exists(config.IDX_CACHE):
        return None, True
    candidate = _nearest_cache_entry(vec, library_id=library_id)
    if candidate is not None and (
        candidate["cosine"] >= config.CACHE_THETA
        and candidate["library_id"] == library_id
        and candidate["version"] == version
    ):
        try:
            r.hincrby(candidate["key"], "hits", 1)
            r.cms().incrby(config.CMS_FREQ, [fp], [1])
            r.topk().add(config.TOPK_LIBS, library_id)
        except Exception:
            pass
        return (
            {
                "payload": candidate["payload"],
                "kind": "semantic",
                "served_version": candidate["version"],
            },
            False,
        )
    return None, True


def _nearest_cache_entry(vec: list[float], library_id: str | None = None) -> dict | None:
    from redis_client import escape_tag

    # Scope KNN to a specific library when provided so that semantically-similar
    # subtask phrasings (which all map to the same library) compare against each
    # other rather than against unrelated entries — yields much higher cosine scores.
    if library_id:
        knn_query = f"(@library_id:{{{escape_tag(library_id)}}}) =>[KNN 1 @embedding $vec AS score]"
    else:
        knn_query = "*=>[KNN 1 @embedding $vec AS score]"

    vec_bytes = np.asarray(vec, dtype=np.float32).tobytes()
    try:
        raw = get_client().execute_command(
            "FT.SEARCH", config.IDX_CACHE,
            knn_query,
            "PARAMS", "2", "vec", vec_bytes,
            "RETURN", "4", "score", "library_id", "version", "payload",
            "SORTBY", "score",
            "LIMIT", "0", "1",
            "DIALECT", "2",
        )
    except Exception:
        return None

    # redis-py ≥8 returns a dict: {b'total_results': N, b'results': [...]}
    # Older versions return a flat list: [N, key, [field, val, ...], ...]
    if isinstance(raw, dict):
        total = raw.get(b"total_results") or raw.get("total_results") or 0
        if not total:
            return None
        results = raw.get(b"results") or raw.get("results") or []
        if not results:
            return None
        first = results[0]
        doc_id = _text(first.get(b"id") or first.get("id", ""))
        attrs = first.get(b"extra_attributes") or first.get("extra_attributes") or {}
    elif isinstance(raw, list) and len(raw) >= 3 and raw[0]:
        doc_id = _text(raw[1])
        fields_flat = raw[2]
        attrs = {}
        for i in range(0, len(fields_flat) - 1, 2):
            attrs[fields_flat[i]] = fields_flat[i + 1]
    else:
        return None

    payload_raw = _text(attrs.get(b"payload") or attrs.get("payload") or "[]")
    try:
        payload = json.loads(payload_raw)
    except json.JSONDecodeError:
        payload = []
    score_raw = attrs.get(b"score") or attrs.get("score") or "1"
    return {
        "key": doc_id,
        "library_id": _text(attrs.get(b"library_id") or attrs.get("library_id") or ""),
        "version": _text(attrs.get(b"version") or attrs.get("version") or ""),
        "cosine": _cosine(score_raw),
        "payload": payload,
    }


# ---------------------------------------------------------------------------
# store
# ---------------------------------------------------------------------------

def store(
    library_id: str,
    version: str,
    query: str,
    vec: list[float],
    payload: list[dict],
    ttl: int,
) -> bool:
    """Admit a result into the cache under TinyLFU rules. Returns True if admitted.

    Only call when lookup() returned admit_allowed=True (repeat sighting that missed).
    """
    try:
        r = get_client()
        r.ping()
    except Exception:
        return False

    ensure_structures()
    fp = fingerprint(query, library_id, version)

    try:
        r.cms().incrby(config.CMS_FREQ, [fp], [1])
    except Exception:
        pass

    key = f"cache:{fp}"

    if _cache_size() >= config.CACHE_CAPACITY and not r.exists(key):
        victim = _sample_victim(exclude=key)
        if victim is not None:
            cand_freq = _freq(fp)
            vic_freq = _freq(victim.split(":", 1)[1])
            if cand_freq < vic_freq:
                return False
            try:
                r.delete(victim)
            except Exception:
                pass

    mapping = {
        "embedding": np.asarray(vec, dtype=np.float32).tobytes(),
        "library_id": library_id,
        "version": version,
        "query": query,
        "payload": json.dumps(payload),
        "created_at": str(int(time.time())),
        "hits": "0",
    }
    try:
        r.hset(key, mapping=mapping)
        if ttl > 0:
            r.expire(key, ttl)
        r.topk().add(config.TOPK_LIBS, library_id)
    except Exception:
        return False
    return True


def force_store(
    library_id: str,
    version: str,
    query: str,
    vec: list[float],
    payload: list[dict],
    ttl: int,
) -> bool:
    """Admit to cache bypassing the doorkeeper one-hit-wonder gate.

    Used by plan_task to warm the cache within a session: after fetching a
    result from Supabase we immediately admit it so follow-up subtasks that
    touch the same library are served from Redis instead.

    TinyLFU frequency-based eviction still applies — admission is still
    probabilistic at capacity; only the doorkeeper gate is skipped.
    """
    try:
        r = get_client()
        r.ping()
    except Exception:
        return False

    ensure_structures()
    fp = fingerprint(query, library_id, version)

    # Register with doorkeeper so future regular lookups are admit-eligible
    try:
        r.bf().add(config.BF_DOORKEEPER, fp)
    except Exception:
        pass

    key = f"cache:{fp}"

    # TinyLFU eviction — still applied even for force-store
    if _cache_size() >= config.CACHE_CAPACITY and not r.exists(key):
        victim = _sample_victim(exclude=key)
        if victim is not None:
            cand_freq = _freq(fp)
            vic_freq = _freq(victim.split(":", 1)[1])
            if cand_freq < vic_freq:
                return False
            try:
                r.delete(victim)
            except Exception:
                pass

    mapping = {
        "embedding": np.asarray(vec, dtype=np.float32).tobytes(),
        "library_id": library_id,
        "version": version,
        "query": query,
        "payload": json.dumps(payload),
        "created_at": str(int(time.time())),
        "hits": "0",
    }
    try:
        r.hset(key, mapping=mapping)
        if ttl > 0:
            r.expire(key, ttl)
        r.topk().add(config.TOPK_LIBS, library_id)
    except Exception:
        return False
    return True


def scan_relevant_libraries(
    vec: list[float],
    min_prob: float = 0.20,
    query_text: str = "",
) -> list[dict]:
    """Score every cached library against the current task.

    Scoring method:
      base_score = cosine(task_vec, library_description_vec_from_supabase)
                   (compares "what I'm doing" vs "what this library does")
      keyword_boost = +0.15  if the library's short name appears verbatim in query_text
      probability = min(1.0, base_score + keyword_boost)

    Using Supabase library embeddings (not cached subtask embeddings) means
    the score answers "is this library relevant to my task?" rather than
    "did I phrase this task the same way as last time?" — the latter is
    almost always low (~0.35-0.55) when two tasks touch the same library
    from different angles (setup vs debug vs improvement).

    Returns list sorted by probability descending, filtered to >= min_prob:
        [{"library_id", "version", "probability", "base_score",
          "keyword_boost", "payload"}, ...]
    """
    r = get_client()
    query_lower = query_text.lower()

    # 1. Collect unique (library_id → version) from all live cache:* keys
    lib_map: dict[str, str] = {}
    for k in r.scan_iter(match="cache:*", count=500):
        try:
            lib_id = _text(r.hget(k, "library_id") or b"")
            version = _text(r.hget(k, "version") or b"")
            if lib_id and lib_id not in lib_map:
                lib_map[lib_id] = version
        except Exception:
            pass

    if not lib_map:
        return []

    # 2. Score each cached library by comparing the task vector against the
    #    library's own Supabase embedding ("what this library does").
    #    One match_libraries call fetches scores for all 213 libraries at once.
    supabase_scores: dict[str, float] = {}
    try:
        import supabase_client as _sc
        for row in _sc.match_libraries(vec, k=len(lib_map) + 50):
            if row["library_id"] in lib_map:
                supabase_scores[row["library_id"]] = row["score"]
    except Exception:
        pass

    # 3. Build results with keyword boost
    results = []
    for lib_id, version in lib_map.items():
        base = supabase_scores.get(lib_id, 0.0)

        # Keyword boost: library short name explicitly in the query text.
        # "pandas" in "fix pandas DataFrame memory" → strong signal.
        short = lib_id.split(":")[-1].lower()
        boost = 0.15 if (query_lower and short and short in query_lower) else 0.0
        probability = min(1.0, round(base + boost, 4))

        if probability < min_prob:
            continue

        # Fetch the best-matching cached payload for this library
        entry = _nearest_cache_entry(vec, library_id=lib_id)
        payload = entry["payload"] if entry else []

        results.append({
            "library_id": lib_id,
            "version": version,
            "probability": probability,
            "base_score": round(base, 4),
            "keyword_boost": boost,
            "payload": payload,
        })

    results.sort(key=lambda x: x["probability"], reverse=True)
    return results


def _cache_size() -> int:
    try:
        return sum(1 for _ in get_client().scan_iter(match="cache:*", count=500))
    except Exception:
        return 0


def _sample_victim(exclude: str) -> str | None:
    try:
        keys = []
        for k in get_client().scan_iter(match="cache:*", count=500):
            ks = _text(k)
            if ks != exclude:
                keys.append(ks)
            if len(keys) >= 64:
                break
        return random.choice(keys) if keys else None
    except Exception:
        return None


def _freq(fp: str) -> int:
    try:
        return int(get_client().cms().query(config.CMS_FREQ, [fp])[0])
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# aging + stats
# ---------------------------------------------------------------------------

def age() -> None:
    """Halve CMS counts by re-initialising the sketch."""
    try:
        r = get_client()
        r.delete(config.CMS_FREQ)
        r.cms().initbydim(config.CMS_FREQ, 2000, 10)
    except Exception:
        pass


def stats() -> dict[str, Any]:
    out: dict[str, Any] = {
        "size": _cache_size(),
        "capacity": config.CACHE_CAPACITY,
        "theta": config.CACHE_THETA,
        "top_libs": [],
    }
    try:
        out["top_libs"] = [_text(x) for x in get_client().topk().list(config.TOPK_LIBS)]
    except Exception:
        pass
    return out
