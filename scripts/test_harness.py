#!/usr/bin/env python3
"""
test_harness.py — Lockstep probability-based cache test.

Project: AI Stock Price Predictor
  A full-stack ML application with a data pipeline, scikit-learn model,
  FastAPI backend, Redis cache, Streamlit dashboard, and periodic Celery jobs.

Structure:
  BUILD phases 1-4: Cold start — each introduces new libraries into cache.
  ITERATE phases 5-10: Debug, improve, and extend existing code.
    These prompts NAME the libraries already in cache, triggering keyword boost.
    Expected: high cache hit rate because it's the same stack being iterated on.

Scoring method (NEW):
  probability = cosine(task, library_description_from_supabase) + keyword_boost
  keyword_boost = +0.15 if library short name appears in the subtask text
  threshold = CACHE_SCAN_THETA (0.40)

  Why this is better than the old approach:
    OLD: cosine(new_subtask_text, cached_subtask_text) → 0.35-0.55 even for same library
         because "Install Celery" vs "Fix Celery retry" are phrased differently.
    NEW: cosine(task, "Distributed Task Queue") + 0.15 (keyword) → 0.65
         because we measure "does this library fit this task?" not "did I say it the same way?"

Run:
    python scripts/test_harness.py

Side-by-side with cache inspector:
    Terminal 1:  python scripts/cache_inspector.py --watch 3
    Terminal 2:  python scripts/test_harness.py
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from redis_client import get_client, _text
from tools.plan import plan_task
import cache as cache_mod
from embeddings import embed

PROJECT = "AI Stock Price Predictor"

# ---------------------------------------------------------------------------
# BUILD phases — establish the cache, cold start expected
# ---------------------------------------------------------------------------
BUILD_PHASES = [
    {
        "phase": 1,
        "name": "Data Fetching Pipeline (cold)",
        "prompt": (
            "Build a pandas data pipeline to fetch historical OHLCV stock price data "
            "from a REST API using httpx. Parse the JSON response into a pandas DataFrame "
            "with proper datetime indexing. Add data cleaning: forward-fill missing values, "
            "remove duplicate timestamps, and normalize column names."
        ),
        "expect_hits": 0,
        "expect_libraries": ["pandas", "httpx"],
    },
    {
        "phase": 2,
        "name": "scikit-learn Prediction Model (pandas warm)",
        "prompt": (
            "Build a scikit-learn stock price direction prediction model. "
            "Use pandas and numpy to engineer features from OHLCV data: 5/20-day moving averages, "
            "RSI, MACD, and Bollinger Bands. Train a scikit-learn RandomForestClassifier, "
            "evaluate with sklearn classification_report, and serialize the trained model with joblib."
        ),
        "expect_hits": ">=1",
        "expect_libraries": ["scikit-learn", "numpy", "pandas", "joblib"],
    },
    {
        "phase": 3,
        "name": "FastAPI Prediction Server (sklearn+redis warm)",
        "prompt": (
            "Build a FastAPI REST API to serve stock price predictions. "
            "Accept a ticker symbol as a Pydantic-validated request body, load the scikit-learn "
            "model at FastAPI startup using joblib, run inference, and cache the prediction in "
            "Redis for 5 minutes to avoid recomputing on repeated requests for the same ticker."
        ),
        "expect_hits": ">=1",
        "expect_libraries": ["fastapi", "pydantic", "redis", "scikit-learn", "joblib"],
    },
    {
        "phase": 4,
        "name": "Streamlit Dashboard (fastapi+pandas warm)",
        "prompt": (
            "Build a Streamlit dashboard for the stock price predictor. "
            "Let users enter a ticker symbol, call the FastAPI prediction endpoint using httpx, "
            "display the prediction and confidence score, and render a pandas DataFrame of the "
            "last 30 days of prices as a Plotly candlestick chart."
        ),
        "expect_hits": ">=2",
        "expect_libraries": ["streamlit", "plotly", "pandas", "httpx"],
    },
]

# ---------------------------------------------------------------------------
# ITERATE phases — debug, improve, extend. Prompts name specific libraries.
# Keyword boost + Supabase scoring should yield high cache hit rate.
# ---------------------------------------------------------------------------
ITERATE_PHASES = [
    {
        "phase": 5,
        "name": "DEBUG: pandas OOM on 10 years of data",
        "prompt": (
            "The pandas DataFrame in the stock data pipeline is running out of memory when "
            "loading 10 years of OHLCV data for 500 tickers — it's using 8 GB of RAM. "
            "Fix pandas memory usage: use pandas astype to downcast float64 columns to float32, "
            "use numpy chunked array operations instead of pandas apply, "
            "and profile memory with pandas DataFrame.memory_usage(deep=True). "
            "Also fix the httpx client to use connection pooling with a persistent session."
        ),
        "expect_hits": ">=2",
        "expect_libraries": ["pandas", "numpy", "httpx"],
    },
    {
        "phase": 6,
        "name": "DEBUG: FastAPI endpoint takes 12 seconds",
        "prompt": (
            "The FastAPI stock prediction endpoint takes 12 seconds per request. "
            "Two bugs found: the scikit-learn model is being loaded from disk via joblib on every "
            "FastAPI request instead of once at startup, and the Redis cache key is malformed "
            "so cache misses happen every time. "
            "Fix: use FastAPI lifespan to load the scikit-learn model once into app.state, "
            "fix the Redis cache key format to use the Pydantic-validated ticker symbol, "
            "and add a Pydantic response model with a cache_hit boolean field."
        ),
        "expect_hits": ">=3",
        "expect_libraries": ["fastapi", "scikit-learn", "redis", "pydantic", "joblib"],
    },
    {
        "phase": 7,
        "name": "IMPROVE: sklearn model accuracy",
        "prompt": (
            "The scikit-learn RandomForestClassifier for stock direction prediction has only "
            "51% accuracy. Improve it: add more numpy feature engineering (volatility ratio, "
            "volume-weighted price), use a scikit-learn Pipeline with StandardScaler preprocessing, "
            "tune hyperparameters with scikit-learn GridSearchCV on the pandas training DataFrame "
            "split by date, and compare RandomForest vs GradientBoosting with scikit-learn cross_val_score."
        ),
        "expect_hits": ">=3",
        "expect_libraries": ["scikit-learn", "numpy", "pandas"],
    },
    {
        "phase": 8,
        "name": "FEATURE: Celery data refresh jobs",
        "prompt": (
            "Add Celery background tasks to the stock prediction platform to keep data fresh. "
            "A daily Celery task fetches new OHLCV data using httpx and appends it to the "
            "pandas DataFrame stored on disk. A weekly Celery task retrains the scikit-learn model "
            "with the latest data and serializes it with joblib. Use Redis as the Celery broker "
            "and result backend. Configure Celery beat schedule so tasks run automatically."
        ),
        "expect_hits": ">=4",
        "expect_libraries": ["celery", "httpx", "pandas", "scikit-learn", "redis", "joblib"],
    },
    {
        "phase": 9,
        "name": "FEATURE: Real-time WebSocket updates",
        "prompt": (
            "Add WebSocket support to the FastAPI stock prediction server so the Streamlit "
            "dashboard receives real-time price alerts without polling. "
            "When a Celery worker finishes processing new OHLCV data, it publishes to a "
            "Redis pub/sub channel. The FastAPI WebSocket endpoint subscribes and broadcasts "
            "to all connected Streamlit clients. Use Pydantic to validate the WebSocket message schema."
        ),
        "expect_hits": ">=3",
        "expect_libraries": ["fastapi", "redis", "celery", "pydantic"],
    },
    {
        "phase": 10,
        "name": "FEATURE: Portfolio tracker + SQLAlchemy",
        "prompt": (
            "Add a portfolio tracking feature to the stock prediction app. "
            "Use SQLAlchemy async models to store user holdings (ticker, shares, purchase_price). "
            "Add FastAPI endpoints for buy, sell, and get_portfolio operations with Pydantic "
            "request/response schemas. Cache the current portfolio value in Redis so the "
            "Streamlit dashboard can display it without hitting the database every refresh. "
            "Add an Alembic migration to create the portfolio_positions table."
        ),
        "expect_hits": ">=4",
        "expect_libraries": ["sqlalchemy", "fastapi", "pydantic", "redis", "alembic"],
    },
]

ALL_PHASES = BUILD_PHASES + ITERATE_PHASES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cache_size() -> int:
    try:
        return sum(1 for _ in get_client().scan_iter(match="cache:*", count=500))
    except Exception:
        return 0


def _cached_library_ids() -> list[str]:
    r = get_client()
    seen: set[str] = set()
    for k in r.scan_iter(match="cache:*", count=500):
        try:
            lib_id = _text(r.hget(k, "library_id") or b"")
            if lib_id:
                seen.add(lib_id)
        except Exception:
            pass
    return sorted(seen)


def _flush_cache() -> None:
    r = get_client()
    keys = list(r.scan_iter(match="cache:*", count=500))
    if keys:
        r.delete(*keys)
    for key in [config.BF_DOORKEEPER, config.CMS_FREQ, config.TOPK_LIBS, config.IDX_CACHE]:
        try:
            r.delete(key)
        except Exception:
            pass
    cache_mod.ensure_structures()


def _run_plan(prompt: str) -> tuple[dict, float]:
    t0 = time.perf_counter()
    result = plan_task(prompt=prompt, session_id="stock-test")
    return result, time.perf_counter() - t0


def _bar(prob: float, width: int = 10) -> str:
    filled = round(prob * width)
    return "█" * filled + "░" * (width - filled)


# ---------------------------------------------------------------------------
# Phase runner
# ---------------------------------------------------------------------------

def run_phase(phase_def: dict, section: str = "") -> dict:
    phase_num = phase_def["phase"]
    name = phase_def["name"]
    prompt = phase_def["prompt"]
    expect_hits = phase_def.get("expect_hits", 0)

    size_before = _cache_size()
    cached_libs_before = _cached_library_ids()

    label = f"[{section}] " if section else ""
    print(f"\n{'═' * 74}")
    print(f"  {label}PHASE {phase_num}: {name.upper()}")
    print(f"{'═' * 74}")
    print(f"\n  {prompt[:100]}...")
    print(f"\n  Cache before: {size_before} entries  |  TTL: {config.RECO_TTL_SECONDS}s")
    if cached_libs_before:
        print(f"  Cached libs:  {', '.join(cached_libs_before)}")
    else:
        print(f"  Cached libs:  (none — cold start)")

    # Pre-scan: show probability of each cached library for this prompt.
    # Uses Supabase embeddings + keyword boost, same method as _resolve_subtask.
    print(f"\n  ── Cache relevance scan (full prompt) ──")
    print(f"  Method: cosine(prompt, library_description) + 0.15 if name in prompt")
    print(f"  Serve threshold: CACHE_SCAN_THETA = {config.CACHE_SCAN_THETA}")
    vec = embed(prompt)
    scored = cache_mod.scan_relevant_libraries(vec, min_prob=0.0, query_text=prompt)

    if not scored:
        print(f"  (cache empty)")
    else:
        print(f"  {'Library':<32} {'Base':>5}  {'Boost':>5}  {'Prob':>5}  {'Bar':<10}  Status")
        print(f"  {'─'*32} {'─'*5}  {'─'*5}  {'─'*5}  {'─'*10}  {'─'*20}")
        for entry in scored:
            base = entry["base_score"]
            boost = entry["keyword_boost"]
            prob = entry["probability"]
            bar = _bar(prob)
            if prob >= config.CACHE_SCAN_THETA:
                status = f"✅ WILL SERVE (≥{config.CACHE_SCAN_THETA})"
            elif prob >= 0.30:
                status = f"🟡 relevant — subtask may clear"
            elif prob >= 0.20:
                status = f"⚪ weak"
            else:
                status = f"✗"
            boost_str = f"+{boost:.2f}" if boost > 0 else "  —  "
            print(f"  {entry['library_id']:<32} {base:>5.3f}  {boost_str:>5}  {prob:>5.3f}  {bar:<10}  {status}")
        print(f"\n  Note: per-subtask scores (below) are always higher because subtask text")
        print(f"  is focused on one concept and contains the library name more explicitly.")

    # Run plan_task
    print(f"\n  ── plan_task decomposition + resolution ──")
    result, elapsed = _run_plan(prompt)

    cache_hits = 0
    supabase_hits = 0
    chosen_libs = []

    for item in result.get("plan", []):
        lib = item.get("library_id") or "none"
        ver = item.get("version") or "?"
        src = item.get("source", "?")
        prob = item.get("probability")
        task = item.get("task", "")
        why = item.get("why", "")
        key_fns = item.get("key_functions", [])
        candidates = item.get("cache_candidates", [])

        src_icon = "💾" if src == "cache" else "🌐" if src == "supabase" else "✗"
        prob_str = f"p={prob:.3f}" if prob is not None else "      "
        chosen_libs.append(lib)

        if src == "cache":
            cache_hits += 1
        elif src == "supabase":
            supabase_hits += 1

        print(f"\n    {src_icon} [{src:<8}] {prob_str}  {lib:<30} v{ver}")
        # What part of the task this library handles
        print(f"       TASK:    {task}")
        # What the library is / why it was chosen
        if src == "cache":
            print(f"       WHY:     Previously cached for a similar task — served without hitting Supabase")
        else:
            print(f"       WHY:     {why[:90]}")
        # The specific functions/capabilities matched for this subtask
        if key_fns:
            top_fn = key_fns[0].get("text", "")[:100]
            print(f"       USES:    {top_fn}")
            if len(key_fns) > 1:
                fn2 = key_fns[1].get("text", "")[:100]
                print(f"                {fn2}")

        # Cache candidates considered (only show if didn't hit cache)
        if candidates and src != "cache":
            top = [c for c in candidates if c["probability"] >= 0.25][:3]
            if top:
                strs = []
                for c in top:
                    kw = "+kw" if c.get("keyword_boost", 0) > 0 else ""
                    strs.append(f"{c['library_id']}(p={c['probability']:.3f}{kw})")
                print(f"       CACHE SCANNED: {', '.join(strs)} — none cleared {config.CACHE_SCAN_THETA}")

    size_after = _cache_size()
    admitted = supabase_hits   # each supabase hit calls force_store
    net = size_after - size_before

    print(f"\n  ⏱  {elapsed:.1f}s  |  💾 cache hits: {cache_hits}  |  🌐 supabase: {supabase_hits}")
    print(f"  Cache: {size_before} → {size_after}  (admitted ~{admitted}, net {'+' if net >= 0 else ''}{net})")

    # Verdict
    print(f"\n  ── Verdict ──")
    if expect_hits == 0:
        print(f"  Cold start — 0 hits expected ✅  Libraries now in cache for future phases.")
    elif isinstance(expect_hits, str) and expect_hits.startswith(">="):
        n = int(expect_hits[2:])
        if cache_hits >= n:
            print(f"  ✅ {cache_hits} cache hit(s) — probability scanner working correctly")
        else:
            print(f"  ⚠️  {cache_hits} hit(s) — expected {expect_hits}")
            if cache_hits == 0 and scored:
                best = scored[0]
                print(f"     Best scan score was {best['library_id']} p={best['probability']:.3f}")
                print(f"     Claude may have chosen a library not yet in cache")

    return {
        "phase": phase_num,
        "name": name,
        "section": section,
        "elapsed": elapsed,
        "cache_hits": cache_hits,
        "supabase_hits": supabase_hits,
        "size_before": size_before,
        "size_after": size_after,
        "chosen_libs": chosen_libs,
        "expect_hits": expect_hits,
    }


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def print_summary(build_results: list[dict], iter_results: list[dict]) -> None:
    all_results = build_results + iter_results
    total_cache = sum(r["cache_hits"] for r in all_results)
    total_calls = sum(r["cache_hits"] + r["supabase_hits"] for r in all_results)
    iter_cache = sum(r["cache_hits"] for r in iter_results)
    iter_calls = sum(r["cache_hits"] + r["supabase_hits"] for r in iter_results)

    print(f"\n{'═' * 74}")
    print(f"  FINAL SUMMARY — {PROJECT}")
    print(f"{'═' * 74}")

    print(f"\n  BUILD PHASES (establishing cache — expect cold starts):")
    print(f"  {'Ph':<3} {'Name':<36} {'Time':>6}  {'💾':>4}  {'🌐':>5}  {'Cache'}  Verdict")
    print(f"  {'──':<3} {'─'*36} {'─'*6}  {'─'*4}  {'─'*5}  {'─'*12}  {'─'*12}")
    for r in build_results:
        expect = r["expect_hits"]
        if expect == 0:
            verdict = "✅ cold OK"
        elif isinstance(expect, str) and expect.startswith(">="):
            n = int(expect[2:])
            verdict = f"✅ {r['cache_hits']} hits" if r["cache_hits"] >= n else f"⚠️  {r['cache_hits']} hits"
        else:
            verdict = ""
        cache_str = f"{r['size_before']}→{r['size_after']}"
        print(f"  {r['phase']:<3} {r['name']:<36} {r['elapsed']:>5.0f}s  {r['cache_hits']:>4}  {r['supabase_hits']:>5}  {cache_str:<12}  {verdict}")

    print(f"\n  ITERATE PHASES (debug/improve/extend — cache should hit):")
    print(f"  {'Ph':<3} {'Name':<36} {'Time':>6}  {'💾':>4}  {'🌐':>5}  {'Cache'}  Verdict")
    print(f"  {'──':<3} {'─'*36} {'─'*6}  {'─'*4}  {'─'*5}  {'─'*12}  {'─'*12}")
    for r in iter_results:
        expect = r["expect_hits"]
        if isinstance(expect, str) and expect.startswith(">="):
            n = int(expect[2:])
            verdict = f"✅ {r['cache_hits']} hits" if r["cache_hits"] >= n else f"⚠️  {r['cache_hits']} hits (want {expect})"
        else:
            verdict = ""
        cache_str = f"{r['size_before']}→{r['size_after']}"
        print(f"  {r['phase']:<3} {r['name']:<36} {r['elapsed']:>5.0f}s  {r['cache_hits']:>4}  {r['supabase_hits']:>5}  {cache_str:<12}  {verdict}")

    print(f"\n  ── Overall ──")
    overall_pct = total_cache / max(total_calls, 1) * 100
    iter_pct = iter_cache / max(iter_calls, 1) * 100
    print(f"  All phases:    {total_cache:>3} / {total_calls:>3} subtasks from cache  ({overall_pct:.0f}%)")
    print(f"  Iterate only:  {iter_cache:>3} / {iter_calls:>3} subtasks from cache  ({iter_pct:.0f}%)")

    if iter_pct >= 50:
        print(f"\n  ✅ Strong cache reuse — iterate phases are hitting cached libraries")
    elif iter_pct >= 30:
        print(f"\n  🟡 Good cache reuse — some subtasks still going to Supabase for new libraries")
    else:
        print(f"\n  ⚠️  Low cache reuse — Claude may be choosing uncached libraries")
        print(f"     Check: are the expected libraries actually in the Supabase catalog?")

    print(f"\n  Config: CACHE_SCAN_THETA={config.CACHE_SCAN_THETA}  CACHE_THETA={config.CACHE_THETA}")
    print(f"          RECO_TTL={config.RECO_TTL_SECONDS}s  EMBED={config.EMBED_MODEL} ({config.EMBED_DIM}d)")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"\n  Lockstep Test Harness — {PROJECT}")
    print(f"  Redis: {config.REDIS_HOST}:{config.REDIS_PORT}")
    print(f"  Scan threshold: {config.CACHE_SCAN_THETA}  |  KNN threshold: {config.CACHE_THETA}")
    print(f"  TTL: {config.RECO_TTL_SECONDS}s ({config.RECO_TTL_SECONDS//3600}h)")

    try:
        get_client().ping()
        print(f"  Redis: ✅ connected")
    except Exception as e:
        print(f"  Redis: ❌ {e}")
        sys.exit(1)

    print(f"\n  Flushing cache for a clean run...")
    _flush_cache()
    print(f"  Cache cleared.\n")

    print(f"  ╔{'═'*70}╗")
    print(f"  ║  SECTION 1: BUILD  —  establish cache (expect cold starts)            ║")
    print(f"  ╚{'═'*70}╝")
    build_results = []
    for pd in BUILD_PHASES:
        build_results.append(run_phase(pd, section="BUILD"))

    print(f"\n\n  ╔{'═'*70}╗")
    print(f"  ║  SECTION 2: ITERATE  —  debug, improve, extend existing stack         ║")
    print(f"  ║  Prompts name specific libraries → keyword boost → high hit rate      ║")
    print(f"  ╚{'═'*70}╝")
    iter_results = []
    for pd in ITERATE_PHASES:
        iter_results.append(run_phase(pd, section="ITERATE"))

    print_summary(build_results, iter_results)
