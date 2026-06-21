"""Test fixtures for Lockstep.

Cache tests (test_cache_invariant.py) require a real Redis Stack at REDIS_URL.
They are skipped automatically if Redis is unreachable.

Supabase tests (test_docs_supabase.py, test_chaining.py) use monkeypatches —
no network access required.

embeddings.embed is monkeypatched to a deterministic local function so tests
never download the MiniLM model.
"""
from __future__ import annotations

import hashlib

import numpy as np
import pytest

import config

FIXTURE_LIB = "pypi:lockstep-fixture"
FIXTURE_VERSIONS = ["1.0.0", "2.0.0"]


def _fake_vec(text: str) -> list[float]:
    """Deterministic unit vector from text — same text => identical vector."""
    seed = int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big")
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(config.EMBED_DIM).astype(np.float32)
    v /= np.linalg.norm(v) or 1.0
    return v.tolist()


def _redis_ok() -> bool:
    try:
        import redis  # noqa: F401

        from redis_client import get_client

        c = get_client()
        c.ping()
        c.bf().reserve("__lockstep_probe__", 0.01, 100)
        c.delete("__lockstep_probe__")
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def redis_available():
    return _redis_ok()


@pytest.fixture(scope="session", autouse=True)
def _require_redis_for_cache(request, redis_available):
    """Skip only if no Redis AND the test needs it. Non-Redis tests run always."""
    # This fixture is a no-op; individual cache tests call pytest.skip themselves
    # via the redis_available fixture.
    pass


@pytest.fixture(autouse=True)
def _fake_embeddings(monkeypatch):
    import embeddings

    monkeypatch.setattr(embeddings, "embed", lambda text, **_: _fake_vec(text))
    monkeypatch.setattr(
        embeddings, "embed_batch", lambda texts, **_: [_fake_vec(t) for t in texts]
    )
    yield


def _ensure_cache_index():
    from redis_client import ensure_cache_index

    ensure_cache_index()


def _cleanup_cache(lib_ids: list[str]):
    from redis_client import _text, get_client

    c = get_client()
    for k in c.scan_iter(match="cache:*", count=500):
        try:
            stored = c.hget(k, "library_id")
            if stored and _text(stored) in lib_ids:
                c.delete(k)
        except Exception:
            pass


@pytest.fixture()
def seeded_cache(redis_available):
    """Ensure Redis cache index exists and yield cleanup."""
    if not redis_available:
        pytest.skip("Redis Stack not reachable at REDIS_URL")
    _ensure_cache_index()
    yield {"library_id": FIXTURE_LIB, "versions": FIXTURE_VERSIONS, "fake_vec": _fake_vec}
    _cleanup_cache([FIXTURE_LIB])


@pytest.fixture()
def fake_vec():
    return _fake_vec
