"""plan_task — proactive planning agent.

Takes a raw user prompt, decomposes it into concrete subtasks via Claude,
then for each subtask resolves the best library and relevant documentation
by checking the Redis semantic cache first, falling back to Supabase.

Cache flow per subtask:
  1. Embed the subtask query.
  2. match_libraries() — in-memory cosine over ~213 rows, picks top library.
  3. cache.lookup() — Redis KNN on idx:cache for (subtask, library, version).
     Hit  → serve cached function chunks immediately.
     Miss → match_functions() from Supabase fn_* table.
  4. cache.force_store() — admits Supabase result to cache, bypassing the
     doorkeeper one-hit-wonder gate so follow-up subtasks in this session
     that touch the same library are served from cache. TinyLFU eviction
     still applies (probabilistic admission is preserved).

Output chains: each plan entry's (library_id, version) are valid inputs to
get_versioned_docs for deeper follow-up without reshaping.
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

    # 1. Find best-matching library (in-memory cosine over ~213 rows — fast)
    candidates = supabase_client.match_libraries(vec, 3, ecosystem=ecosystem)
    if not candidates:
        return _empty(subtask, "No matching library found in catalog.")

    top = candidates[0]
    lib_id = top["library_id"]
    version = top.get("version") or "latest"
    summary = top.get("summary", "")
    docs_url = top.get("docs_url", "")

    # 2. Check Redis semantic cache for (subtask, library_id, version)
    hit, admit = cache_mod.lookup(lib_id, version, subtask, vec)
    if hit is not None:
        return {
            "task": subtask,
            "library_id": lib_id,
            "version": version,
            "key_functions": hit["payload"],
            "why": summary,
            "source": "cache",
        }

    # 3. Supabase function lookup
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

    # 4. Admit to cache — bypasses doorkeeper so same-session follow-ups hit cache.
    #    If admit flag is already True (doorkeeper second sighting), use regular store.
    #    If force_admit (session_id present) or admit, force-store regardless.
    if admit or force_admit:
        cache_mod.force_store(lib_id, version, subtask, vec, key_fns, config.RECO_TTL_SECONDS)

    return {
        "task": subtask,
        "library_id": lib_id,
        "version": version,
        "key_functions": key_fns,
        "why": summary,
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


def _empty(subtask: str, reason: str) -> dict:
    return {
        "task": subtask,
        "library_id": None,
        "version": None,
        "key_functions": [],
        "why": reason,
        "source": "none",
    }
