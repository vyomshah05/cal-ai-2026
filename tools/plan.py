"""plan_task — proactive planning agent.

Takes a raw user prompt, decomposes it into concrete subtasks via Claude,
then for each subtask resolves the best library and relevant documentation
using a probability-based cache scan before falling back to Supabase.

Cache flow per subtask:
  1. Embed the subtask query.
  2. scan_relevant_libraries() — scores every cached library against the
     subtask vector. Returns ranked list with probability (cosine) scores.
  3. If top cached library >= CACHE_THETA → serve it, skip Supabase entirely.
     Otherwise → fall through to Supabase with ranked cache_candidates in output.
  4. Supabase: match_libraries() (cosine over 213 rows) → match_functions()
     from fn_* table. Result is force_store()d so future phases can score it.

Output fields per plan entry:
  - source: "cache" | "supabase" | "none"
  - probability: cosine of how well this library matched the subtask
  - cache_candidates: [{library_id, probability}] — all scored cached libs

Output chains: (library_id, version) are valid get_versioned_docs inputs.
"""
from __future__ import annotations

import json

import config
import cache as cache_mod
import supabase_client
from embeddings import embed

_DECOMPOSE_SYSTEM = (
    "You are a software planning assistant. Break the user's coding request "
    "into 2-6 concrete, independent subtasks. Each subtask should be specific "
    "enough that a single library can address it. "
    'Respond ONLY with valid JSON — no markdown fences: {"subtasks": ["...", ...]}'
)


def plan_task(
    prompt: str,
    ecosystem: str | None = None,
    session_id: str | None = None,
) -> dict:
    """Decompose a coding prompt and fetch library + doc context for each subtask.

    Args:
        prompt: The full user coding request.
        ecosystem: Optional filter — "pypi", "npm", "cargo", "go".
        session_id: Optional opaque string; reserved for future per-session
            cache namespacing. Currently used to signal that force_store
            should always run (vs. relying on doorkeeper admit flag).

    Returns:
        {
            "prompt": str,
            "plan": [
                {
                    "task": str,
                    "library_id": str | None,
                    "version": str | None,
                    "key_functions": [{"text", "source_url", "anchor", "score"}],
                    "why": str,
                    "source": "cache" | "supabase" | "none",
                }
            ]
        }

    (library_id, version) in each plan entry are valid get_versioned_docs inputs.
    """
    subtasks = _decompose(prompt)
    plan = [_resolve_subtask(task, ecosystem, force_admit=session_id is not None) for task in subtasks]
    return {"prompt": prompt, "plan": plan}


# ---------------------------------------------------------------------------
# Decomposition
# ---------------------------------------------------------------------------

def _decompose(prompt: str) -> list[str]:
    """Ask Claude to break the prompt into 2-6 subtasks. Falls back to [prompt]."""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model=config.RERANK_MODEL,
            max_tokens=512,
            system=_DECOMPOSE_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        subtasks = json.loads(raw).get("subtasks", [])
        cleaned = [s for s in subtasks if isinstance(s, str) and s.strip()]
        if cleaned:
            return cleaned[:6]
    except Exception:
        pass
    return [prompt]


# ---------------------------------------------------------------------------
# Per-subtask resolution
# ---------------------------------------------------------------------------

def _resolve_subtask(subtask: str, ecosystem: str | None, force_admit: bool) -> dict:
    vec = embed(subtask)

    # 1. Score every library already in the Redis cache against this subtask.
    #    Uses Supabase library embeddings + keyword boost (see cache.scan_relevant_libraries).
    #    min_prob=0.20 — collect anything; CACHE_SCAN_THETA filters what we actually serve.
    cached_scored = cache_mod.scan_relevant_libraries(vec, min_prob=0.20, query_text=subtask)
    cache_candidates = [
        {"library_id": c["library_id"], "probability": c["probability"],
         "base_score": c.get("base_score", 0.0), "keyword_boost": c.get("keyword_boost", 0.0)}
        for c in cached_scored
    ]

    # 2. If the highest-scoring cached library clears the confidence threshold,
    #    serve it directly — no Supabase call needed.
    if cached_scored and cached_scored[0]["probability"] >= config.CACHE_SCAN_THETA:
        top = cached_scored[0]
        return {
            "task": subtask,
            "library_id": top["library_id"],
            "version": top["version"],
            "key_functions": top["payload"],
            "why": "Served from cache",
            "probability": top["probability"],
            "cache_candidates": cache_candidates,
            "source": "cache",
        }

    # 3. Cache insufficient — query Supabase for the best library match.
    candidates = supabase_client.match_libraries(vec, 3, ecosystem=ecosystem)
    if not candidates:
        return _empty(subtask, "No matching library found.", cache_candidates)

    top = candidates[0]
    lib_id = top["library_id"]
    version = top.get("version") or "latest"
    summary = top.get("summary", "")
    docs_url = top.get("docs_url", "")

    fn_table = top.get("function_table") or ""
    key_fns: list[dict] = []
    if fn_table:
        rows = supabase_client.match_functions(fn_table, vec, 5)
        key_fns = [_fn_chunk(r, docs_url) for r in rows]

    if not key_fns:
        tags = top.get("tags") or []
        tag_str = f" [{', '.join(tags)}]" if tags else ""
        key_fns = [{
            "text": f"{top.get('name', lib_id)}: {summary}{tag_str}",
            "source_url": docs_url,
            "anchor": "",
            "score": top.get("score", 0.0),
        }]

    # 4. Admit to cache so future phases can score this library.
    if force_admit:
        cache_mod.force_store(lib_id, version, subtask, vec, key_fns, config.RECO_TTL_SECONDS)

    return {
        "task": subtask,
        "library_id": lib_id,
        "version": version,
        "key_functions": key_fns,
        "why": summary,
        "probability": round(top.get("score", 0.0), 4),
        "cache_candidates": cache_candidates,
        "source": "supabase",
    }


def _fn_chunk(row: dict, fallback_url: str) -> dict:
    name = row.get("qualified_name", "")
    sig = row.get("signature", "")
    blurb = row.get("summary") or row.get("description", "")
    return {
        "text": f"{name}({sig}) — {blurb}",
        "source_url": row.get("source_url") or fallback_url,
        "anchor": name,
        "score": row.get("score", 0.0),
    }


def _empty(subtask: str, reason: str, cache_candidates: list | None = None) -> dict:
    return {
        "task": subtask,
        "library_id": None,
        "version": None,
        "key_functions": [],
        "why": reason,
        "cache_candidates": cache_candidates or [],
        "source": "none",
    }
