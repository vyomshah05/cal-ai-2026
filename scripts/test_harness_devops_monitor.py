#!/usr/bin/env python3
"""
test_harness_devops_monitor.py — Lockstep cache test #2.

Project: AI-Powered DevOps Monitoring Platform
  A full-stack observability system that ingests logs, collects Prometheus
  metrics, fires intelligent alerts, and displays a live Streamlit dashboard.

Completely different library stack from the stock predictor:
  Core: loguru, prometheus-client, opentelemetry-api, sqlalchemy, alembic
  API:  fastapi, pydantic, redis
  Async: celery
  UI:   streamlit

BUILD phases 1-4: Cold start — different libraries from stock predictor.
ITERATE phases 5-10: Debug, improve, and extend using the same stack.
  Every prompt names the libraries already in cache → keyword boost → high hit rate.

Run:
    python scripts/test_harness_devops_monitor.py

Side-by-side with cache inspector:
    Terminal 1:  python scripts/cache_inspector.py --watch 3
    Terminal 2:  python scripts/test_harness_devops_monitor.py
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

PROJECT = "AI-Powered DevOps Monitoring Platform"

# ---------------------------------------------------------------------------
# BUILD phases — establish the cache, cold start expected
# ---------------------------------------------------------------------------
BUILD_PHASES = [
    {
        "phase": 1,
        "name": "Log Ingestion Pipeline (cold)",
        "prompt": (
            "Build a structured log ingestion pipeline for a DevOps monitoring platform. "
            "Use loguru to parse and normalize incoming log lines (stdout, stderr, JSON structured logs) "
            "from multiple services. Store normalized log entries in a SQLAlchemy async model with "
            "Alembic migration for the log_entries table, indexed by service name and severity level."
        ),
        "expect_hits": 0,
        "expect_libraries": ["loguru", "sqlalchemy", "alembic"],
    },
    {
        "phase": 2,
        "name": "Prometheus Metrics Collection (sqlalchemy warm)",
        "prompt": (
            "Add Prometheus metrics collection to the DevOps monitoring platform. "
            "Use prometheus-client to define custom counters, gauges, and histograms tracking "
            "log ingestion rate, error rate per service, and processing latency. "
            "Expose a FastAPI /metrics endpoint that renders the prometheus-client registry "
            "in the standard text exposition format. Store metric snapshots in SQLAlchemy."
        ),
        "expect_hits": ">=1",
        "expect_libraries": ["prometheus-client", "fastapi", "sqlalchemy"],
    },
    {
        "phase": 3,
        "name": "Alert Engine (prometheus+fastapi warm)",
        "prompt": (
            "Build an intelligent alert engine for the monitoring platform. "
            "Define alert rules using Pydantic models with threshold conditions "
            "on prometheus-client metric values. Use FastAPI endpoints to CRUD alert rules. "
            "Store active alert state and deduplication keys in Redis with TTLs "
            "to avoid alert storms. Persist fired alerts in SQLAlchemy with Alembic migration."
        ),
        "expect_hits": ">=2",
        "expect_libraries": ["pydantic", "fastapi", "redis", "sqlalchemy", "alembic"],
    },
    {
        "phase": 4,
        "name": "Streamlit Monitoring Dashboard (fastapi+redis warm)",
        "prompt": (
            "Build a Streamlit real-time monitoring dashboard. "
            "Poll the FastAPI metrics endpoint every 5 seconds using httpx, "
            "display prometheus-client metric values as live Plotly gauges and time-series charts, "
            "show the last 50 loguru log entries from the FastAPI logs API, "
            "and display active Redis-deduped alerts in a color-coded severity table."
        ),
        "expect_hits": ">=2",
        "expect_libraries": ["streamlit", "plotly", "fastapi", "redis"],
    },
]

# ---------------------------------------------------------------------------
# ITERATE phases — debug, improve, extend. All prompts name specific libraries.
# ---------------------------------------------------------------------------
ITERATE_PHASES = [
    {
        "phase": 5,
        "name": "DEBUG: loguru JSON breaking SQLAlchemy insert",
        "prompt": (
            "The loguru log ingestion pipeline is crashing with SQLAlchemy IntegrityError. "
            "loguru is emitting multi-line JSON stacktraces that exceed the SQLAlchemy "
            "column VARCHAR(1024) limit, and loguru's JSON serializer is producing unicode "
            "escape sequences that SQLAlchemy's asyncpg driver rejects. "
            "Fix loguru's formatter to truncate long messages before writing, "
            "change the SQLAlchemy log_entries column to TEXT type with an Alembic migration, "
            "and add a SQLAlchemy column check constraint for valid UTF-8."
        ),
        "expect_hits": ">=2",
        "expect_libraries": ["loguru", "sqlalchemy", "alembic"],
    },
    {
        "phase": 6,
        "name": "DEBUG: Prometheus metrics endpoint causing FastAPI latency",
        "prompt": (
            "The FastAPI /metrics endpoint is adding 800ms to every response. "
            "The prometheus-client registry is being re-iterated on every FastAPI request "
            "instead of being cached. The SQLAlchemy query that joins log counts "
            "into a prometheus-client gauge is running without an index. "
            "Fix: cache the prometheus-client metrics text output in Redis with a 15-second TTL, "
            "add a SQLAlchemy index on log_entries(service_name, created_at) via Alembic migration, "
            "and add a FastAPI background task to refresh the prometheus-client registry async."
        ),
        "expect_hits": ">=3",
        "expect_libraries": ["fastapi", "prometheus-client", "redis", "sqlalchemy", "alembic"],
    },
    {
        "phase": 7,
        "name": "IMPROVE: Add OpenTelemetry distributed tracing",
        "prompt": (
            "Add OpenTelemetry distributed tracing to the DevOps monitoring platform. "
            "Instrument all FastAPI endpoints with opentelemetry-api spans so request traces "
            "propagate across services. Add opentelemetry-api trace context to loguru log records "
            "so every log line includes its trace_id and span_id. "
            "Export traces to a local OTLP collector. "
            "Store trace metadata in SQLAlchemy so the Streamlit dashboard can link logs to traces."
        ),
        "expect_hits": ">=3",
        "expect_libraries": ["opentelemetry-api", "fastapi", "loguru", "sqlalchemy", "streamlit"],
    },
    {
        "phase": 8,
        "name": "FEATURE: Celery async alert dispatch + log rotation",
        "prompt": (
            "Add Celery background workers to the DevOps monitoring platform. "
            "A Celery task fires alert notifications (Slack webhook via httpx) when "
            "the FastAPI alert engine triggers an alert, checking Redis deduplication "
            "before sending. A Celery beat periodic task runs nightly to archive "
            "SQLAlchemy log_entries older than 30 days using Alembic-managed partitions. "
            "Use Redis as the Celery broker and store Celery task results in SQLAlchemy."
        ),
        "expect_hits": ">=4",
        "expect_libraries": ["celery", "fastapi", "redis", "sqlalchemy", "httpx"],
    },
    {
        "phase": 9,
        "name": "FEATURE: Real-time WebSocket alert feed",
        "prompt": (
            "Add a real-time WebSocket alert feed to the DevOps monitoring platform. "
            "When the FastAPI alert engine fires a new Pydantic-validated alert, "
            "publish it to a Redis pub/sub channel. The FastAPI WebSocket endpoint "
            "subscribes to Redis and broadcasts to all connected Streamlit clients. "
            "Update the Streamlit dashboard to show a live alert feed with loguru-formatted "
            "severity badges, auto-scrolling, and Redis-backed read/unread state per client."
        ),
        "expect_hits": ">=3",
        "expect_libraries": ["fastapi", "redis", "pydantic", "streamlit", "loguru"],
    },
    {
        "phase": 10,
        "name": "IMPROVE: SQLAlchemy query optimization + Alembic migration",
        "prompt": (
            "The DevOps monitoring platform's log search FastAPI endpoint is timing out for "
            "queries over large SQLAlchemy log_entries tables. "
            "Optimize: add a SQLAlchemy composite index on (service_name, severity, created_at) "
            "via Alembic migration, switch the SQLAlchemy query to use keyset pagination "
            "instead of OFFSET, add Redis cache for frequently-searched service+severity combos "
            "with a 30-second TTL, and add Pydantic query parameter validation with "
            "max_results capped at 500 on the FastAPI endpoint."
        ),
        "expect_hits": ">=4",
        "expect_libraries": ["sqlalchemy", "alembic", "redis", "fastapi", "pydantic"],
    },
]

ALL_PHASES = BUILD_PHASES + ITERATE_PHASES


# ---------------------------------------------------------------------------
# Helpers (identical to stock predictor harness)
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
    result = plan_task(prompt=prompt, session_id="devops-test")
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

    print(f"\n  ── Cache relevance scan (full prompt) ──")
    print(f"  Method: cosine(prompt, library_description) + 0.15 if name in prompt")
    print(f"  Serve threshold: CACHE_SCAN_THETA = {config.CACHE_SCAN_THETA}")
    vec = embed(prompt)
    scored = cache_mod.scan_relevant_libraries(vec, min_prob=0.0, query_text=prompt)

    if not scored:
        print(f"  (cache empty)")
    else:
        print(f"  {'Library':<34} {'Base':>5}  {'Boost':>5}  {'Prob':>5}  {'Bar':<10}  Status")
        print(f"  {'─'*34} {'─'*5}  {'─'*5}  {'─'*5}  {'─'*10}  {'─'*20}")
        for entry in scored:
            base = entry["base_score"]
            boost = entry["keyword_boost"]
            prob = entry["probability"]
            bar = _bar(prob)
            if prob >= config.CACHE_SCAN_THETA:
                status = f"✅ WILL SERVE (≥{config.CACHE_SCAN_THETA})"
            elif prob >= 0.30:
                status = f"🟡 subtask may clear"
            elif prob >= 0.20:
                status = f"⚪ weak"
            else:
                status = f"✗"
            boost_str = f"+{boost:.2f}" if boost > 0 else "  —  "
            print(f"  {entry['library_id']:<34} {base:>5.3f}  {boost_str:>5}  {prob:>5.3f}  {bar:<10}  {status}")
        print(f"\n  Note: per-subtask scores are higher — subtask text focuses on one library.")

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

        print(f"\n    {src_icon} [{src:<8}] {prob_str}  {lib:<32} v{ver}")
        print(f"       TASK:  {task}")
        if src == "cache":
            print(f"       WHY:   Previously cached — served without hitting Supabase")
        else:
            print(f"       WHY:   {why[:90]}")
        if key_fns:
            print(f"       USES:  {key_fns[0].get('text','')[:100]}")
            if len(key_fns) > 1:
                print(f"              {key_fns[1].get('text','')[:100]}")
        if candidates and src != "cache":
            top = [c for c in candidates if c["probability"] >= 0.25][:3]
            if top:
                strs = [f"{c['library_id']}(p={c['probability']:.3f}{'+kw' if c.get('keyword_boost',0)>0 else ''})" for c in top]
                print(f"       CACHE SCANNED: {', '.join(strs)} — none cleared {config.CACHE_SCAN_THETA}")

    size_after = _cache_size()
    net = size_after - size_before
    print(f"\n  ⏱  {elapsed:.1f}s  |  💾 cache hits: {cache_hits}  |  🌐 supabase: {supabase_hits}")
    print(f"  Cache: {size_before} → {size_after}  (admitted ~{supabase_hits}, net {'+' if net>=0 else ''}{net})")

    print(f"\n  ── Verdict ──")
    if expect_hits == 0:
        print(f"  Cold start — 0 hits expected ✅  Libraries admitted for future phases.")
    elif isinstance(expect_hits, str) and expect_hits.startswith(">="):
        n = int(expect_hits[2:])
        if cache_hits >= n:
            print(f"  ✅ {cache_hits} cache hit(s) — probability scanner working correctly")
        else:
            print(f"  ⚠️  {cache_hits} hit(s) — expected {expect_hits}")

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

    print(f"\n  BUILD PHASES:")
    print(f"  {'Ph':<3} {'Name':<38} {'Time':>6}  {'💾':>4}  {'🌐':>5}  Cache       Verdict")
    print(f"  {'──':<3} {'─'*38} {'─'*6}  {'─'*4}  {'─'*5}  {'─'*10}  {'─'*12}")
    for r in build_results:
        expect = r["expect_hits"]
        if expect == 0:
            verdict = "✅ cold OK"
        elif isinstance(expect, str) and expect.startswith(">="):
            n = int(expect[2:])
            verdict = f"✅ {r['cache_hits']} hits" if r["cache_hits"] >= n else f"⚠️  {r['cache_hits']} hits"
        else:
            verdict = ""
        print(f"  {r['phase']:<3} {r['name']:<38} {r['elapsed']:>5.0f}s  {r['cache_hits']:>4}  {r['supabase_hits']:>5}  {r['size_before']}→{r['size_after']:<8}  {verdict}")

    print(f"\n  ITERATE PHASES:")
    print(f"  {'Ph':<3} {'Name':<38} {'Time':>6}  {'💾':>4}  {'🌐':>5}  Cache       Verdict")
    print(f"  {'──':<3} {'─'*38} {'─'*6}  {'─'*4}  {'─'*5}  {'─'*10}  {'─'*12}")
    for r in iter_results:
        expect = r["expect_hits"]
        if isinstance(expect, str) and expect.startswith(">="):
            n = int(expect[2:])
            verdict = f"✅ {r['cache_hits']} hits" if r["cache_hits"] >= n else f"⚠️  {r['cache_hits']} hits (want {expect})"
        else:
            verdict = ""
        print(f"  {r['phase']:<3} {r['name']:<38} {r['elapsed']:>5.0f}s  {r['cache_hits']:>4}  {r['supabase_hits']:>5}  {r['size_before']}→{r['size_after']:<8}  {verdict}")

    print(f"\n  ── Overall ──")
    overall_pct = total_cache / max(total_calls, 1) * 100
    iter_pct = iter_cache / max(iter_calls, 1) * 100
    print(f"  All phases:    {total_cache:>3} / {total_calls:>3} subtasks from cache  ({overall_pct:.0f}%)")
    print(f"  Iterate only:  {iter_cache:>3} / {iter_calls:>3} subtasks from cache  ({iter_pct:.0f}%)")

    if iter_pct >= 50:
        print(f"\n  ✅ Strong cache reuse across a completely different project stack")
    elif iter_pct >= 30:
        print(f"\n  🟡 Good cache reuse — some new libraries introduced in iterate phases")
    else:
        print(f"\n  ⚠️  Low cache reuse — check library coverage in Supabase catalog")

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
