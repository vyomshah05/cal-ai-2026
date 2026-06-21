"""Chain contract: recommend_library output feeds get_versioned_docs unchanged.

Verifies that (library_id, suggested_version) from a recommendation are valid
inputs to get_versioned_docs — no reshaping needed.

All external calls (Supabase, Anthropic, Redis) are monkeypatched.
"""
from __future__ import annotations

import pytest

SCRAPED_VERSION = "2.34.2"

_FAKE_LIBS = [
    {
        "library_id": "pypi:requests",
        "name": "requests",
        "ecosystem": "pypi",
        "version": SCRAPED_VERSION,
        "summary": "HTTP for Humans",
        "tier": "popular",
        "tags": ["http", "rest", "api"],
        "function_table": "fn_pypi_requests",
        "homepage": "https://requests.readthedocs.io",
        "docs_url": "https://requests.readthedocs.io",
        "score": 0.97,
        "embedding": None,
    }
]

_FAKE_FN_ROWS = [
    {
        "qualified_name": "requests.get",
        "kind": "function",
        "signature": "url, **kwargs",
        "summary": "Sends a GET request.",
        "description": "",
        "returns": "Response",
        "source_url": "https://requests.readthedocs.io/api/",
        "score": 0.95,
    }
]


@pytest.fixture()
def patch_all(monkeypatch):
    import cache
    import supabase_client

    monkeypatch.setattr(supabase_client, "match_libraries", lambda vec, k, ecosystem=None: _FAKE_LIBS)
    monkeypatch.setattr(supabase_client, "get_library", lambda lid: _FAKE_LIBS[0] if lid == "pypi:requests" else None)
    monkeypatch.setattr(supabase_client, "match_functions", lambda ft, vec, k: _FAKE_FN_ROWS[:k])
    monkeypatch.setattr(cache, "lookup", lambda *a, **kw: (None, True))
    monkeypatch.setattr(cache, "store", lambda *a, **kw: True)


def _fallback_rerank(candidates):
    return [{"library_id": c["library_id"], "why": "test", "tradeoffs": "test"} for c in candidates]


def test_recommend_output_chains_into_get_versioned_docs(monkeypatch, patch_all):
    """(library_id, suggested_version) from recommend_library → valid get_versioned_docs input."""
    import tools.recommend as rec_mod
    from tools.docs import get_versioned_docs
    from tools.recommend import recommend_library

    monkeypatch.setattr(rec_mod, "_rerank_with_claude", lambda task, cands: _fallback_rerank(cands))

    reco_result = recommend_library("make HTTP requests")
    recs = reco_result["recommendations"]
    assert recs, "expected at least one recommendation"

    top = recs[0]
    library_id = top["library_id"]
    version = top["suggested_version"]

    # Feed directly into get_versioned_docs — no reshaping
    docs_result = get_versioned_docs(library_id, version, "how to send a GET request")
    assert docs_result["library_id"] == library_id
    assert docs_result["served_version"] == SCRAPED_VERSION
    assert len(docs_result["chunks"]) > 0


def test_recommend_returns_required_fields(monkeypatch, patch_all):
    import tools.recommend as rec_mod
    from tools.recommend import recommend_library

    monkeypatch.setattr(rec_mod, "_rerank_with_claude", lambda task, cands: _fallback_rerank(cands))

    result = recommend_library("parse CSV files", ecosystem="pypi")
    for rec in result["recommendations"]:
        assert "library_id" in rec
        assert "suggested_version" in rec
        assert "why" in rec
        assert "tradeoffs" in rec
        assert "maturity" in rec
        assert "sample_snippet" in rec


def test_recommend_fallback_when_claude_errors(monkeypatch, patch_all):
    """When Claude rerank raises, the fallback keeps the tool functioning."""
    import tools.recommend as rec_mod
    from tools.recommend import recommend_library

    def _raise(*a, **kw):
        raise RuntimeError("simulated API error")

    monkeypatch.setattr(rec_mod, "_rerank_with_claude", _raise)

    result = recommend_library("anything")
    assert result["recommendations"]  # fallback produces output
