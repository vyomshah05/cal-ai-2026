"""recommend_library — library selection RAG + Claude rerank.

Flow:
  1. embed(task)
  2. match_libraries(vec, k=8, ecosystem=ecosystem) — cosine top-k from Supabase
  3. Claude Sonnet rerank: given task + candidate summaries/tags, produce
     why / tradeoffs per candidate and sort by best fit
  4. For each rec, pull a sample_snippet (top-1 function) from the fn_* table
  5. Return ranked recommendations; (library_id, suggested_version) chain directly
     into get_versioned_docs without reshaping

Fallback: if the Anthropic call fails, fall back to the cosine rank order with
templated why/tradeoffs so the tool never hard-errors.
"""
from __future__ import annotations

import json

import sentry_sdk

import config
import embeddings
import supabase_client


def _sample_snippet(lib: dict) -> str:
    """Pull the top-1 function signature from the library's fn_* table."""
    ft = lib.get("function_table")
    if not ft:
        return ""
    # Use the library summary embedding to pull the most representative fn
    summary = lib.get("summary") or lib.get("name") or ""
    try:
        vec = embeddings.embed(summary)
        rows = supabase_client.match_functions(ft, vec, 1)
        if rows:
            r = rows[0]
            name = r.get("qualified_name", "")
            sig = r.get("signature", "")
            summ = r.get("summary") or r.get("description") or ""
            return f"{name}({sig}) — {summ}" if sig else f"{name} — {summ}"
    except Exception:
        pass
    return ""


def _rerank_with_claude(task: str, candidates: list[dict]) -> list[dict]:
    """Call Claude Sonnet to rerank candidates and add why/tradeoffs."""
    import anthropic

    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    cand_text = "\n\n".join(
        f"{i+1}. {c['library_id']} (v{c.get('version','?')}, {c.get('ecosystem','?')})\n"
        f"   Summary: {c.get('summary','')}\n"
        f"   Tags: {', '.join((c.get('tags') or [])[:15])}\n"
        f"   Tier: {c.get('tier','')}"
        for i, c in enumerate(candidates)
    )

    prompt = f"""You are a software library advisor. A developer needs help choosing a library.

Task: {task}

Candidates (already pre-filtered by semantic similarity):
{cand_text}

Return a JSON object with key "recommendations" — an array of objects, one per candidate, in ranked order (best first). Each object must have:
- "library_id": exact string from above
- "why": 1-2 sentences on why this fits the task
- "tradeoffs": 1 sentence on the main tradeoff or caveat

Return ONLY the JSON object, no prose."""

    sentry_sdk.add_breadcrumb(
        category="llm",
        message="Calling Claude for library reranking",
        data={"model": config.RERANK_MODEL, "candidate_count": len(candidates)},
        level="info",
    )
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=config.RERANK_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())["recommendations"]


def _fallback_rerank(candidates: list[dict]) -> list[dict]:
    """Cosine-order fallback used when Claude is unavailable."""
    return [
        {
            "library_id": c["library_id"],
            "why": f"Semantically similar to your task (score {c.get('score', 0):.3f}).",
            "tradeoffs": "Reranking unavailable; order is by embedding similarity only.",
        }
        for c in candidates
    ]


def recommend_library(
    task: str,
    ecosystem: str | None = None,
    constraints: dict | None = None,
) -> dict:
    """Return ranked library recommendations for a coding task.

    Args:
        task: free-text description of what you need to build or do.
        ecosystem: optional filter — "pypi", "npm", "cargo", "go", etc.
        constraints: optional dict; "license" key noted but best-effort
                     (Supabase schema has no license column).

    Returns:
        { recommendations: [{library_id, suggested_version, why, tradeoffs,
          maturity, sample_snippet}] }
        (library_id, suggested_version) are valid inputs to get_versioned_docs.
    """
    with sentry_sdk.start_transaction(op="mcp.tool", name="recommend_library") as txn:
        txn.set_tag("ecosystem", ecosystem or "any")

        with sentry_sdk.start_span(op="db.search", description="Supabase KNN library candidates"):
            vec = embeddings.embed(task)
            candidates = supabase_client.match_libraries(vec, config.LIBS_TOP_K, ecosystem=ecosystem)

        if not candidates:
            return {"recommendations": []}

        txn.set_data("candidate_count", len(candidates))

        # Rerank with Claude; fall back to cosine order on error
        try:
            with sentry_sdk.start_span(op="llm.rerank", description="Claude library rerank"):
                ranked = _rerank_with_claude(task, candidates)
            txn.set_tag("rerank.source", "claude")
        except Exception as e:
            sentry_sdk.capture_exception(e)
            sentry_sdk.capture_message(
                "Claude rerank unavailable — falling back to cosine order",
                level="warning",
            )
            ranked = _fallback_rerank(candidates)
            txn.set_tag("rerank.source", "cosine_fallback")

        # Build the library_id -> candidate lookup for version / maturity
        lib_map = {c["library_id"]: c for c in candidates}

        notes = []
        if constraints and constraints.get("license"):
            notes.append("license filtering is not supported in this data source")

        recommendations = []
        for rec in ranked:
            lid = rec.get("library_id", "")
            lib = lib_map.get(lid, {})
            snippet = _sample_snippet(lib)
            recommendations.append(
                {
                    "library_id": lid,
                    "suggested_version": lib.get("version") or "latest",
                    "why": rec.get("why", ""),
                    "tradeoffs": rec.get("tradeoffs", ""),
                    "maturity": {
                        "stars": None,
                        "last_release": None,
                        "open_issues": None,
                        "tier": lib.get("tier"),
                    },
                    "sample_snippet": snippet,
                }
            )

        txn.set_data("recommendation_count", len(recommendations))
        result: dict = {"recommendations": recommendations}
        if notes:
            result["notes"] = notes
        return result
