"""get_versioned_docs — version-pinned documentation retrieval from Supabase.

Flow:
  1. embed(query)
  2. Semantic cache lookup (cache.lookup) → on hit return immediately
  3. get_library(library_id) → find the scraped version + function_table name
  4. match_functions(function_table, vec, k) → cosine top-k from fn_* table
  5. Shape each fn row into a chunk: "{qualified_name}{signature} — {summary}"
  6. Empty-fn-table fallback (e.g. npm with no scraped functions): synthesize one
     chunk from library summary + tags
  7. cache.store on an admit-eligible miss (long TTL — fn catalogs are immutable)

Correctness invariant: chunks come from exactly one library's fn table at the
single scraped version. Cross-version leakage is structurally impossible.
"""
from __future__ import annotations

import sentry_sdk

import cache
import config
import embeddings
import supabase_client


def _fn_row_to_chunk(row: dict, source_url: str) -> dict:
    """Shape a function-catalog row into the output chunk contract."""
    name = row.get("qualified_name", "")
    sig = row.get("signature", "")
    summary = row.get("summary") or row.get("description") or ""
    text = f"{name}({sig}) — {summary}" if sig else f"{name} — {summary}"
    return {
        "text": text.strip(),
        "source_url": row.get("source_url") or source_url,
        "anchor": name,
        "score": row.get("score", 0.0),
    }


def _budget_trim(chunks: list[dict], max_tokens: int | None) -> list[dict]:
    if not max_tokens or max_tokens <= 0:
        return chunks
    out, used = [], 0
    for ch in sorted(chunks, key=lambda c: c.get("score", 0.0), reverse=True):
        est = max(1, len(ch.get("text", "")) // 4)
        if used + est > max_tokens and out:
            break
        out.append(ch)
        used += est
    return out


def get_versioned_docs(
    library_id: str,
    version: str,
    query: str,
    max_tokens: int | None = None,
) -> dict:
    library_id = library_id.strip().lower()

    with sentry_sdk.start_transaction(op="mcp.tool", name="get_versioned_docs") as txn:
        txn.set_tag("library_id", library_id)
        txn.set_tag("version", version)

        vec = embeddings.embed(query)

        # 2. Cache lookup
        with sentry_sdk.start_span(op="cache.lookup", description="W-TinyLFU semantic lookup"):
            hit, admit_allowed = cache.lookup(library_id, version, query, vec)

        if hit is not None:
            txn.set_tag("cache.result", "hit")
            chunks = _budget_trim(hit["payload"], max_tokens)
            return {
                "library_id": library_id,
                "served_version": hit.get("served_version", version),
                "exact_match": hit.get("served_version", version) == version,
                "chunks": chunks,
                "cache": {"hit": True, "kind": hit["kind"]},
            }

        txn.set_tag("cache.result", "miss")

        # 3. Look up the library in Supabase
        with sentry_sdk.start_span(op="db.query", description=f"Supabase get_library: {library_id}"):
            lib = supabase_client.get_library(library_id)

        if lib is None:
            return {
                "library_id": library_id,
                "served_version": version,
                "exact_match": False,
                "chunks": [],
                "cache": {"hit": False, "kind": None},
            }

        served_version = lib.get("version") or version
        exact_match = (served_version == version)
        txn.set_tag("exact_version_match", exact_match)
        docs_url = lib.get("docs_url") or lib.get("homepage") or ""
        function_table = lib.get("function_table")

        # 4–5. Retrieve from the fn_* function catalog
        chunks: list[dict] = []
        if function_table:
            with sentry_sdk.start_span(op="db.query", description=f"Supabase match_functions: {function_table}"):
                fn_rows = supabase_client.match_functions(function_table, vec, config.DOCS_TOP_K)
            chunks = [_fn_row_to_chunk(r, docs_url) for r in fn_rows]

        # 6. Empty-fn-table fallback: synthesize from summary + tags
        if not chunks:
            summary = lib.get("summary") or ""
            tags = lib.get("tags") or []
            tag_str = ", ".join(tags[:20]) if tags else ""
            text = summary
            if tag_str:
                text = f"{summary}\n\nUse-cases: {tag_str}" if summary else f"Use-cases: {tag_str}"
            if text.strip():
                chunks = [
                    {
                        "text": text.strip(),
                        "source_url": docs_url,
                        "anchor": "",
                        "score": 1.0,
                    }
                ]

        chunks = _budget_trim(chunks, max_tokens)
        txn.set_data("chunk_count", len(chunks))

        # 7. Admit to cache on eligible miss
        if chunks and admit_allowed:
            with sentry_sdk.start_span(op="cache.store", description="Admit result to W-TinyLFU cache"):
                cache.store(
                    library_id, served_version, query, vec, chunks, config.DOCS_TTL_SECONDS
                )

        return {
            "library_id": library_id,
            "served_version": served_version,
            "exact_match": exact_match,
            "chunks": chunks,
            "cache": {"hit": False, "kind": None},
        }
