"""The two load-bearing cache properties:

  1. NEVER cross-version: a cached payload for v1 is never served for v2,
     even when the query vector is identical (cosine = 1).
  2. Doorkeeper one-hit rejection: a fingerprint seen for the first time is
     recorded but NOT admitted (no near-hit lookup attempted).

These tests require a real Redis Stack (skipped otherwise).
"""
from __future__ import annotations

import json
import uuid

import numpy as np
import pytest

import cache
import config
from redis_client import get_client


def _seed_cache_entry(library_id, version, query, vec, payload):
    key = f"cache:{cache.fingerprint(query, library_id, version)}"
    get_client().hset(
        key,
        mapping={
            "embedding": np.asarray(vec, np.float32).tobytes(),
            "library_id": library_id,
            "version": version,
            "query": query,
            "payload": json.dumps(payload),
            "created_at": "0",
            "hits": "0",
        },
    )
    return key


def test_cache_never_serves_wrong_version(seeded_cache, fake_vec):
    lib = seeded_cache["library_id"]
    query = f"identical query {uuid.uuid4()}"
    vec = fake_vec(query)

    cache.ensure_structures()
    _seed_cache_entry(
        lib, "1.0.0", query, vec,
        [{"text": "WRONG-VERSION", "source_url": "", "anchor": "", "score": 1.0}],
    )

    fp_v2 = cache.fingerprint(query, lib, "2.0.0")
    get_client().bf().add(config.BF_DOORKEEPER, fp_v2)

    hit, _admit = cache.lookup(lib, "2.0.0", query, vec)
    assert hit is None, "cache must not serve a v1.0.0 payload for a v2.0.0 request"


def test_cache_serves_on_exact_version_match(seeded_cache, fake_vec):
    lib = seeded_cache["library_id"]
    query = f"matching query {uuid.uuid4()}"
    vec = fake_vec(query)

    cache.ensure_structures()
    payload = [{"text": "RIGHT", "source_url": "u", "anchor": "#a", "score": 1.0}]
    _seed_cache_entry(lib, "2.0.0", query, vec, payload)

    get_client().bf().add(config.BF_DOORKEEPER, cache.fingerprint(query, lib, "2.0.0"))

    hit, _admit = cache.lookup(lib, "2.0.0", query, vec)
    assert hit is not None
    assert hit["kind"] == "semantic"
    assert hit["payload"][0]["text"] == "RIGHT"


def test_doorkeeper_rejects_one_hit_wonder(seeded_cache, fake_vec):
    lib = seeded_cache["library_id"]
    query = f"one hit wonder {uuid.uuid4()}"
    vec = fake_vec(query)
    payload = [{"text": "cached", "source_url": "", "anchor": "", "score": 1.0}]

    cache.ensure_structures()
    fp = cache.fingerprint(query, lib, "1.0.0")
    key = f"cache:{fp}"

    # First sighting: miss, NOT eligible for admission
    hit1, admit1 = cache.lookup(lib, "1.0.0", query, vec)
    assert hit1 is None
    assert admit1 is False
    assert bool(get_client().bf().exists(config.BF_DOORKEEPER, fp))
    assert not get_client().exists(key), "must not cache on first sight"

    # Second sighting: still a miss but now admit-eligible
    hit2, admit2 = cache.lookup(lib, "1.0.0", query, vec)
    assert hit2 is None
    assert admit2 is True

    # Store on the eligible miss; third sighting hits the cache
    assert cache.store(lib, "1.0.0", query, vec, payload, 60) is True
    assert get_client().exists(key)
    hit3, _ = cache.lookup(lib, "1.0.0", query, vec)
    assert hit3 is not None and hit3["payload"][0]["text"] == "cached"
