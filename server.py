"""Lockstep MCP server entrypoint.

Registers the three Lockstep tools and exposes both transports:
  - stdio  (Claude Code / Cursor / Windsurf local)
  - streamable-http (remote / multi-client)

Smoke-test mode: set LOCKSTEP_HARDCODED=1 to return hardcoded payloads without
touching Supabase or Redis — used to prove the MCP transport end-to-end before
real retrieval is needed.

Tool I/O contract (outputs chain into inputs):
  resolve_version → {resolved:[{library_id,locked_version,...}], unresolved:[...]}
  recommend_library → {recommendations:[{library_id,suggested_version,...}]}
  get_versioned_docs → {library_id,served_version,exact_match,chunks,cache}
"""
from __future__ import annotations

import argparse
import os

from mcp.server.fastmcp import FastMCP

import config

mcp = FastMCP("lockstep", host=config.LOCKSTEP_HOST, port=config.LOCKSTEP_PORT)

_HARDCODED = os.getenv("LOCKSTEP_HARDCODED") == "1"


# ---------------------------------------------------------------------------
# Tool: plan_task  (primary entry point — call this first with the raw prompt)
# ---------------------------------------------------------------------------

@mcp.tool()
def plan_task(
    prompt: str,
    ecosystem: str | None = None,
    session_id: str | None = None,
) -> dict:
    """Decompose a coding prompt and return a library + docs plan for each subtask.

    This is the primary tool — call it once at the start of any coding session
    with the full user prompt. It will:
      1. Break the prompt into 2-6 concrete subtasks (via Claude).
      2. For each subtask: check the Redis semantic cache first, fall back to
         Supabase if not cached, then warm the cache for follow-up queries.
      3. Return a structured plan with the best library and key function docs
         for each subtask, so code can be written against accurate, non-deprecated APIs.

    Args:
        prompt: The full user coding request, exactly as given.
        ecosystem: Optional — "pypi", "npm", "cargo", "go". Narrows library search.
        session_id: Optional opaque string (e.g. conversation ID). When provided,
            results are force-admitted to the Redis cache after Supabase fetch so
            follow-up subtasks in this session that touch the same library are
            served from cache rather than Supabase.

    Returns:
        {
            "prompt": str,
            "plan": [
                {
                    "task": str,
                    "library_id": str,       # e.g. "pypi:requests"
                    "version": str,           # pinned version from Supabase
                    "key_functions": [...],   # relevant function signatures + summaries
                    "why": str,               # one-line library summary
                    "source": "cache"|"supabase"|"none"
                }
            ]
        }
    (library_id, version) in each plan entry are valid get_versioned_docs inputs.
    """
    if _HARDCODED:
        return {
            "prompt": prompt,
            "plan": [
                {
                    "task": "make HTTP requests",
                    "library_id": "pypi:requests",
                    "version": "2.34.2",
                    "key_functions": [
                        {
                            "text": "requests.get(url, **kwargs) — Sends a GET request.",
                            "source_url": "https://requests.readthedocs.io/en/latest/api/",
                            "anchor": "requests.get",
                            "score": 0.97,
                        }
                    ],
                    "why": "[hardcoded] HTTP for Humans.",
                    "source": "cache",
                }
            ],
        }
    from tools.plan import plan_task as _impl

    return _impl(prompt=prompt, ecosystem=ecosystem, session_id=session_id)


# ---------------------------------------------------------------------------
# Tool: resolve_version
# ---------------------------------------------------------------------------

@mcp.tool()
def resolve_version(
    manifest_files: list[dict] | None = None,
    project_root: str | None = None,
) -> dict:
    """Parse lockfiles and return pinned dependency versions.

    Args:
        manifest_files: list of {filename, content} dicts — use over HTTP transport.
        project_root: local filesystem path — use over stdio (Claude Code / Cursor).

    Returns {resolved: [{library_id, requested_range, locked_version, source_file}],
             unresolved: [{name, reason, source_file}]}.
    library_id values are valid inputs to get_versioned_docs.
    Supported: package-lock.json, yarn.lock, requirements.txt, poetry.lock,
    Cargo.lock, go.mod.
    """
    if _HARDCODED:
        return {
            "resolved": [
                {
                    "library_id": "pypi:requests",
                    "requested_range": ">=2.28",
                    "locked_version": "2.34.2",
                    "source_file": "requirements.txt",
                }
            ],
            "unresolved": [],
        }
    from tools.resolve import resolve_version as _impl

    return _impl(manifest_files=manifest_files, project_root=project_root)


# ---------------------------------------------------------------------------
# Tool: recommend_library
# ---------------------------------------------------------------------------

@mcp.tool()
def recommend_library(
    task: str,
    ecosystem: str | None = None,
    constraints: dict | None = None,
) -> dict:
    """Recommend libraries for a coding task, reranked by Claude Sonnet.

    Args:
        task: free-text description of what you need to build or do.
        ecosystem: optional filter — "pypi", "npm", "cargo", "go", etc.
        constraints: optional dict; "license" key is noted but best-effort.

    Returns {recommendations: [{library_id, suggested_version, why, tradeoffs,
    maturity, sample_snippet}]}. (library_id, suggested_version) are valid
    inputs to get_versioned_docs without reshaping.
    """
    if _HARDCODED:
        return {
            "recommendations": [
                {
                    "library_id": "pypi:requests",
                    "suggested_version": "2.34.2",
                    "why": "[hardcoded] great HTTP library.",
                    "tradeoffs": "[hardcoded] no async support.",
                    "maturity": {"stars": None, "last_release": None, "open_issues": None, "tier": "popular"},
                    "sample_snippet": "requests.get(url) — Sends a GET request.",
                }
            ]
        }
    from tools.recommend import recommend_library as _impl

    return _impl(task=task, ecosystem=ecosystem, constraints=constraints)


# ---------------------------------------------------------------------------
# Tool: get_versioned_docs
# ---------------------------------------------------------------------------

@mcp.tool()
def get_versioned_docs(
    library_id: str,
    version: str,
    query: str,
    max_tokens: int | None = None,
) -> dict:
    """Return documentation chunks for a library at a specific version.

    Args:
        library_id: "{ecosystem}:{name}", e.g. "pypi:requests" or "npm:react".
        version: the version to pin docs to, e.g. "2.34.2".
        query: what you want to know (free text).
        max_tokens: optional token budget to trim the chunk set.

    Chunks are sourced from the library's function catalog (fn_* table in
    Supabase). If the exact version has no catalog, served_version reports what
    was actually available and exact_match is set to false.
    """
    if _HARDCODED:
        return {
            "library_id": library_id,
            "served_version": version,
            "exact_match": True,
            "chunks": [
                {
                    "text": f"[hardcoded] docs for {library_id}@{version} re: {query!r}",
                    "source_url": "https://example.test/docs",
                    "anchor": "#hardcoded",
                    "score": 1.0,
                }
            ],
            "cache": {"hit": False, "kind": None},
        }

    from tools.docs import get_versioned_docs as _impl

    return _impl(library_id, version, query, max_tokens)


# ---------------------------------------------------------------------------
# Debug resource: cache_stats
# ---------------------------------------------------------------------------

@mcp.resource("lockstep://cache_stats")
def cache_stats() -> dict:
    """Live semantic-cache readout: size, capacity, theta, hottest libraries."""
    if _HARDCODED:
        return {
            "size": 0,
            "capacity": config.CACHE_CAPACITY,
            "theta": config.CACHE_THETA,
            "top_libs": [],
        }
    import cache

    return cache.stats()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Lockstep MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default=os.getenv("LOCKSTEP_TRANSPORT", "stdio"),
        help="stdio (default) or http (streamable HTTP)",
    )
    args = parser.parse_args()

    if args.transport == "http":
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
