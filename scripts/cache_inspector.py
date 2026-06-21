#!/usr/bin/env python3
"""
cache_inspector.py — Live view of the Lockstep Redis semantic cache.

Shows what is in the cache, the W-TinyLFU frequency ratings, Top-K library
rankings, and simulates a cache lookup for any query so you can see exactly
whether it hits or misses and why.

Usage
-----
# Overview — what's in the cache right now
python scripts/cache_inspector.py

# Simulate a query and see hit/miss + cosine score
python scripts/cache_inspector.py --query "make HTTP requests"

# Simulate with a specific library+version (shows doorkeeper + CMS freq too)
python scripts/cache_inspector.py --query "send a GET request" \
    --library pypi:requests --version 2.34.2

# Watch the cache in real time as plan_task fills it (updates every N seconds)
python scripts/cache_inspector.py --watch 5
"""
from __future__ import annotations

import argparse
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import cache as cache_mod
from redis_client import get_client, _text, _cosine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cms_freq(fp: str) -> int:
    try:
        return int(get_client().cms().query(config.CMS_FREQ, [fp])[0])
    except Exception:
        return 0


def _all_cache_entries() -> list[dict]:
    r = get_client()
    entries = []
    for k in r.scan_iter(match="cache:*", count=500):
        try:
            data = r.hgetall(k)
            fp = _text(k).replace("cache:", "")
            entries.append({
                "key": _text(k),
                "fp": fp,
                "library_id": _text(data.get(b"library_id", b"")),
                "version": _text(data.get(b"version", b"")),
                "query": _text(data.get(b"query", b""))[:55],
                "hits": int(_text(data.get(b"hits", b"0"))),
                "freq": _cms_freq(fp),
                "created_at": _text(data.get(b"created_at", b"0")),
            })
        except Exception:
            pass
    return sorted(entries, key=lambda x: x["freq"], reverse=True)


def _nearest_knn(vec: list[float]) -> dict | None:
    vec_bytes = np.asarray(vec, dtype=np.float32).tobytes()
    try:
        raw = get_client().execute_command(
            "FT.SEARCH", config.IDX_CACHE,
            "*=>[KNN 1 @embedding $vec AS score]",
            "PARAMS", "2", "vec", vec_bytes,
            "RETURN", "4", "score", "library_id", "version", "query",
            "SORTBY", "score",
            "LIMIT", "0", "1",
            "DIALECT", "2",
        )
    except Exception:
        return None

    if isinstance(raw, dict):
        total = raw.get(b"total_results") or 0
        results = raw.get(b"results") or []
    elif isinstance(raw, list) and len(raw) >= 3 and raw[0]:
        total = raw[0]
        results = [{"id": raw[1], "extra_attributes": dict(zip(raw[2][::2], raw[2][1::2]))}]
    else:
        return None

    if not total or not results:
        return None

    first = results[0]
    attrs = first.get(b"extra_attributes") or first.get("extra_attributes") or {}
    cosine = _cosine(attrs.get(b"score") or attrs.get("score") or "1")
    return {
        "library_id": _text(attrs.get(b"library_id") or attrs.get("library_id") or b""),
        "version": _text(attrs.get(b"version") or attrs.get("version") or b""),
        "query": _text(attrs.get(b"query") or attrs.get("query") or b"")[:55],
        "cosine": cosine,
    }


# ---------------------------------------------------------------------------
# Display sections
# ---------------------------------------------------------------------------

def show_overview(clear: bool = False) -> None:
    if clear:
        print(f"\n{'─' * 65}  {time.strftime('%H:%M:%S')}")

    r = get_client()
    stats = cache_mod.stats()
    entries = _all_cache_entries()
    max_freq = max((e["freq"] for e in entries), default=1) or 1

    print("\n" + "=" * 65)
    print("  LOCKSTEP CACHE INSPECTOR")
    print("=" * 65)

    # --- Stats ---
    fill_pct = stats["size"] / max(stats["capacity"], 1) * 100
    print(f"\n  Size            {stats['size']} / {stats['capacity']}  ({fill_pct:.1f}% full)")
    print(f"  Scan threshold  {config.CACHE_SCAN_THETA}  (plan_task: Supabase-score + keyword boost must exceed this)")
    print(f"  KNN threshold   {stats['theta']}  (lookup(): Redis cosine must exceed this)")
    print(f"  Embed dim       {config.EMBED_DIM}  ({config.EMBED_MODEL})")
    print(f"  Entry TTL       {config.RECO_TTL_SECONDS}s  ({config.RECO_TTL_SECONDS//3600}h {(config.RECO_TTL_SECONDS%3600)//60}m)")

    # --- Top-K libraries ---
    print(f"\n  TOP-K LIBRARIES  (most queried, tracked by topk:libs)")
    print(f"  {'Rank':<5} {'Library ID'}")
    print(f"  {'-'*5} {'-'*35}")
    if stats["top_libs"]:
        for i, lib in enumerate(stats["top_libs"], 1):
            print(f"  {i:<5} {lib}")
    else:
        print("  (none yet — run plan_task to warm the cache)")

    # --- Cache entries with frequency ratings ---
    print(f"\n  CACHE ENTRIES  (sorted by CMS frequency — higher = more likely to survive eviction)")
    print(f"  {'Library':<26} {'Ver':<10} {'Hits':>4}  {'CMS freq':>8}  {'Evict resist':>12}  Query preview")
    print(f"  {'-'*26} {'-'*10} {'-'*4}  {'-'*8}  {'-'*12}  {'-'*30}")

    if not entries:
        print("  (cache is empty — first plan_task call will populate it)")
    else:
        for e in entries[:25]:
            bar_len = int(e["freq"] / max_freq * 10)
            bar = "█" * bar_len + "░" * (10 - bar_len)
            resist = f"{e['freq'] / max_freq * 100:.0f}%  {bar}"
            print(f"  {e['library_id']:<26} {e['version']:<10} {e['hits']:>4}  {e['freq']:>8}  {resist}  {e['query']}")

    # --- Bloom filter probe ---
    print(f"\n  BLOOM FILTER (bf:doorkeeper)")
    try:
        r.bf().info(config.BF_DOORKEEPER)
        print(f"  Doorkeeper is active — first-sighting fingerprints are gated")
    except Exception:
        print(f"  Doorkeeper not initialised yet (run cache.ensure_structures())")

    print()


def simulate_query(query: str, library_id: str | None, version: str | None) -> None:
    from embeddings import embed

    print("\n" + "=" * 65)
    print("  QUERY SIMULATION")
    print("=" * 65)
    print(f"\n  Query:    {query!r}")
    if library_id:
        print(f"  Library:  {library_id}   version: {version or '(any)'}")

    vec = embed(query)
    print(f"\n  [1] Embedded query → {config.EMBED_DIM}-d MiniLM vector")

    # --- Doorkeeper + CMS if library+version given ---
    if library_id and version:
        fp = cache_mod.fingerprint(query, library_id, version)
        r = get_client()

        try:
            seen = bool(r.bf().exists(config.BF_DOORKEEPER, fp))
        except Exception:
            seen = True

        freq = _cms_freq(fp)
        key = f"cache:{fp}"
        exists = bool(r.exists(key))

        print(f"\n  [2] Doorkeeper (Bloom filter)")
        print(f"      Fingerprint : {fp[:24]}...")
        print(f"      Seen before : {seen}")
        if not seen:
            print(f"      → First sighting: recorded, NOT admitted (one-hit-wonder gate)")
        else:
            print(f"      → Known fingerprint: KNN lookup will proceed")

        print(f"\n  [3] Count-Min Sketch frequency")
        print(f"      CMS count for this (query, library, version): {freq}")
        if freq == 0:
            print(f"      → Never stored; will query Supabase on miss")
        else:
            print(f"      → Has been queried {freq}x; high eviction resistance")

        print(f"\n  [4] Cache key exists in Redis: {exists}")
        if exists:
            hits = _text(r.hget(key, "hits") or b"0")
            print(f"      Direct hits served from this key: {hits}")

    # --- KNN vector search ---
    print(f"\n  [{'5' if library_id else '2'}] Vector KNN search in idx:cache (cosine threshold: {config.CACHE_THETA})")
    nn = _nearest_knn(vec)

    if nn is None:
        print(f"      Cache is empty — will query Supabase")
        return

    print(f"      Nearest entry : {nn['library_id']} v{nn['version']}")
    print(f"      Query preview : {nn['query']!r}")
    print(f"      Cosine score  : {nn['cosine']:.4f}  (need ≥ {config.CACHE_THETA} for a hit)")

    if nn["cosine"] >= config.CACHE_THETA:
        if library_id is None or (nn["library_id"] == library_id and nn["version"] == (version or nn["version"])):
            print(f"\n  ✅ CACHE HIT  — cosine {nn['cosine']:.4f} ≥ {config.CACHE_THETA}, library+version match")
            print(f"     Supabase is NOT queried. Docs served from Redis.")
        else:
            print(f"\n  ❌ CACHE MISS — cosine OK but library/version mismatch")
            print(f"     Requested : {library_id} v{version}")
            print(f"     Found     : {nn['library_id']} v{nn['version']}")
            print(f"     → Will query Supabase (cross-version invariant enforced)")
    else:
        gap = config.CACHE_THETA - nn["cosine"]
        print(f"\n  ❌ CACHE MISS — cosine {nn['cosine']:.4f} is {gap:.4f} below threshold")
        print(f"     → Will query Supabase, then store result in Redis")

    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Lockstep cache inspector — see what's cached and why"
    )
    parser.add_argument("--query", "-q", help="Simulate a cache lookup for this query string")
    parser.add_argument("--library", "-l", help="Library ID e.g. pypi:requests")
    parser.add_argument("--version", "-v", help="Version e.g. 2.34.2")
    parser.add_argument("--watch", "-w", type=int, metavar="SECONDS",
                        help="Refresh the overview every N seconds (Ctrl+C to stop)")
    args = parser.parse_args()

    try:
        get_client().ping()
    except Exception:
        print("ERROR: Redis unreachable. Check REDIS_URL in .env")
        sys.exit(1)

    if args.watch:
        print(f"Watching cache (refreshing every {args.watch}s) — Ctrl+C to stop")
        try:
            while True:
                show_overview(clear=True)
                time.sleep(args.watch)
        except KeyboardInterrupt:
            print("\nStopped.")
    else:
        show_overview()
        if args.query:
            simulate_query(args.query, args.library, args.version)


if __name__ == "__main__":
    main()
