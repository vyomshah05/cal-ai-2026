"""get_versioned_docs — Supabase-backed retrieval tests.

All Supabase and Redis calls are monkeypatched; no network access required.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SCRAPED_VERSION = "2.34.2"

_FAKE_LIB = {
    "library_id": "pypi:requests",
    "version": SCRAPED_VERSION,
    "summary": "HTTP for Humans",
    "homepage": "https://requests.readthedocs.io",
    "docs_url": "https://requests.readthedocs.io",
    "tier": "popular",
    "tags": ["http", "rest", "api"],
    "function_table": "fn_pypi_requests",
    "embedding": None,
}

_FAKE_FN_ROWS = [
    {
        "qualified_name": "requests.get",
        "kind": "function",
        "signature": "url, **kwargs",
        "summary": "Sends a GET request.",
        "description": "Sends a GET request to the given URL.",
        "returns": "Response",
        "source_url": "https://requests.readthedocs.io/en/latest/api/",
        "score": 0.95,
    },
    {
        "qualified_name": "requests.post",
        "kind": "function",
        "signature": "url, data=None, json=None, **kwargs",
        "summary": "Sends a POST request.",
        "description": "Sends a POST request to the given URL.",
        "returns": "Response",
        "source_url": "https://requests.readthedocs.io/en/latest/api/",
        "score": 0.85,
    },
]


@pytest.fixture()
def patch_supabase(monkeypatch):
    import supabase_client

    monkeypatch.setattr(supabase_client, "get_library", lambda lid: _FAKE_LIB if lid == "pypi:requests" else None)
    monkeypatch.setattr(supabase_client, "match_functions", lambda ft, vec, k: _FAKE_FN_ROWS[:k])


@pytest.fixture()
def patch_cache_miss(monkeypatch):
    import cache

    monkeypatch.setattr(cache, "lookup", lambda *a, **kw: (None, True))
    monkeypatch.setattr(cache, "store", lambda *a, **kw: True)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_exact_version_returns_chunks(patch_supabase, patch_cache_miss):
    from tools.docs import get_versioned_docs

    res = get_versioned_docs("pypi:requests", SCRAPED_VERSION, "how to send http")
    assert res["library_id"] == "pypi:requests"
    assert res["served_version"] == SCRAPED_VERSION
    assert res["exact_match"] is True
    assert len(res["chunks"]) > 0
    assert res["cache"]["hit"] is False


def test_wrong_version_sets_exact_match_false(patch_supabase, patch_cache_miss):
    from tools.docs import get_versioned_docs

    res = get_versioned_docs("pypi:requests", "99.0.0", "how to send http")
    assert res["exact_match"] is False
    assert res["served_version"] == SCRAPED_VERSION


def test_chunk_text_contains_function_name(patch_supabase, patch_cache_miss):
    from tools.docs import get_versioned_docs

    res = get_versioned_docs("pypi:requests", SCRAPED_VERSION, "get request")
    texts = [c["text"] for c in res["chunks"]]
    assert any("requests.get" in t for t in texts)


def test_unknown_library_returns_empty_chunks(monkeypatch, patch_cache_miss):
    import supabase_client

    monkeypatch.setattr(supabase_client, "get_library", lambda lid: None)
    from tools.docs import get_versioned_docs

    res = get_versioned_docs("pypi:does-not-exist", "1.0.0", "anything")
    assert res["chunks"] == []
    assert res["exact_match"] is False


def test_empty_fn_table_falls_back_to_summary(monkeypatch, patch_cache_miss):
    """When the fn_* table has no rows, synthesize a chunk from summary + tags."""
    import supabase_client

    lib_no_fns = {**_FAKE_LIB, "library_id": "npm:d3", "function_table": "fn_npm_d3"}
    monkeypatch.setattr(supabase_client, "get_library", lambda lid: lib_no_fns)
    monkeypatch.setattr(supabase_client, "match_functions", lambda ft, vec, k: [])
    from tools.docs import get_versioned_docs

    res = get_versioned_docs("npm:d3", SCRAPED_VERSION, "charts")
    assert len(res["chunks"]) == 1
    assert "HTTP for Humans" in res["chunks"][0]["text"] or "http" in res["chunks"][0]["text"].lower()


def test_cache_hit_returned_immediately(monkeypatch):
    """On a cache hit, Supabase is never consulted."""
    import cache
    import supabase_client

    fake_hit = {
        "payload": [{"text": "from cache", "source_url": "", "anchor": "", "score": 1.0}],
        "kind": "semantic",
        "served_version": SCRAPED_VERSION,
    }
    monkeypatch.setattr(cache, "lookup", lambda *a, **kw: (fake_hit, False))
    called = []
    monkeypatch.setattr(supabase_client, "get_library", lambda lid: called.append(lid) or None)
    from tools.docs import get_versioned_docs

    res = get_versioned_docs("pypi:requests", SCRAPED_VERSION, "anything")
    assert res["cache"]["hit"] is True
    assert res["chunks"][0]["text"] == "from cache"
    assert not called, "Supabase should not be queried on a cache hit"


def test_chunks_never_cross_library(monkeypatch, patch_cache_miss):
    """All returned chunks belong to the requested library_id (invariant)."""
    import supabase_client

    monkeypatch.setattr(supabase_client, "get_library", lambda lid: _FAKE_LIB)
    monkeypatch.setattr(supabase_client, "match_functions", lambda ft, vec, k: _FAKE_FN_ROWS[:k])
    from tools.docs import get_versioned_docs

    res = get_versioned_docs("pypi:requests", SCRAPED_VERSION, "http client")
    # Chunks don't carry library_id in their output shape, but they must derive
    # from the requested library's fn table (verified by source_url heuristic)
    for chunk in res["chunks"]:
        assert "requests" in chunk.get("source_url", "").lower() or chunk.get("anchor", "").startswith("requests.")
