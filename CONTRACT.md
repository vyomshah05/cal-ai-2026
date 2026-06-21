# Lockstep Shared Contract

This file is the single source of truth for the data schema. **Do not change a
field name, table name, or index name without updating this file.**

## Data Plane: Supabase (Postgres + pgvector)

The library corpus and function catalogs live in Supabase. The server reads from
these tables via PostgREST (supabase-py); it does NOT write to them.

### Identifiers

- `library_id = "{ecosystem}:{name}"`, lowercase.
- `ecosystem ∈ {npm, pypi, cargo, go, maven, rubygems}`.
- Versions: one scraped version per library (as ingested by the separate pipeline).

### Embeddings

- `EMBED_MODEL = all-MiniLM-L6-v2` (local, no API key)
- `EMBED_DIM = 384`
- Both the ingest pipeline and the server MUST use this model. Mismatches silently
  break retrieval.

### Table `libraries`

One row per library:

| column         | type          | notes                                    |
|----------------|---------------|------------------------------------------|
| library_id     | text PK       | `{ecosystem}:{name}`                     |
| ecosystem      | text          |                                          |
| name           | text          |                                          |
| version        | text          | scraped/pinned version                   |
| summary        | text          |                                          |
| homepage       | text          |                                          |
| docs_url       | text          |                                          |
| tier           | text          | "popular" \| "niche"                     |
| tags           | text[]        | top-50 use-case tags                     |
| function_table | text          | name of the per-library fn_* table       |
| embedding      | vector(384)   | MiniLM embedding of summary+tags         |
| scraped_at     | timestamptz   |                                          |

No `stars`, `last_release`, or `open_issues` columns — `maturity.tier` is the
available signal.

### Table `library_tags`

Cross-library tag index (used by `recommend_library` tag filtering):

| column     | type  |
|------------|-------|
| library_id | text  |
| tag        | text  |
| score      | real  |

PK: `(library_id, tag)`.

### Per-library function tables `fn_{ecosystem}_{sanitized_name}`

One table per library. Naming: lowercase, non-alphanumerics → `_`, `@scope/pkg`
→ `scope_pkg`, truncated to 63 chars.

| column        | type        | notes                           |
|---------------|-------------|---------------------------------|
| id            | bigserial   | PK                              |
| qualified_name| text UNIQUE |                                 |
| kind          | text        | function \| class \| method     |
| signature     | text        |                                 |
| summary       | text        | first docstring line            |
| description   | text        | full docstring                  |
| params        | jsonb       |                                 |
| returns       | text        |                                 |
| source_url    | text        |                                 |
| embedding     | vector(384) | MiniLM embedding of signature+summary |

---

## Cache Plane: Redis Stack

The W-TinyLFU semantic cache lives on Redis. The **server owns** all Redis
structures (creates them on startup). Nothing on the ingest side touches Redis.

### Index `idx:cache`

- Keys: `cache:{fingerprint}`
- Prefix: `cache:`
- Fields:
  - `embedding` — VECTOR, HNSW, COSINE, dim = `EMBED_DIM` (384)
  - `library_id` — TAG
  - `version` — TAG
  - `query` — TEXT
  - `payload` — JSON string of chunks
  - `created_at` — TEXT (unix timestamp)
  - `hits` — TEXT (integer)

### Probabilistic structures (RedisBloom)

- `bf:doorkeeper` — Bloom filter. One-hit-wonder gate.
- `cms:freq` — Count-Min Sketch. TinyLFU frequency.
- `topk:libs` — Top-K. Hottest library_ids.

### Fingerprint

`fingerprint = sha256(normalize(query) | library_id | version | EMBED_MODEL)` (hex),
where `normalize` lowercases and collapses whitespace.

---

## Tool I/O Contract (outputs chain into inputs without reshaping)

```
resolve_version(manifest_files?, project_root?)
  → { resolved: [{library_id, requested_range, locked_version, source_file}],
      unresolved: [{name, reason, source_file}] }

recommend_library(task, ecosystem?, constraints?)
  → { recommendations: [{library_id, suggested_version, why, tradeoffs,
       maturity:{stars,last_release,open_issues,tier}, sample_snippet}] }
    (library_id, suggested_version) are valid inputs to get_versioned_docs.

get_versioned_docs(library_id, version, query, max_tokens?)
  → { library_id, served_version, exact_match,
      chunks:[{text,source_url,anchor,score}],
      cache:{hit,kind} }
```

### Version semantics

Supabase stores one scraped version per library. `served_version` equals that
scraped version. `exact_match=true` when the requested version equals the scraped
version; `exact_match=false` otherwise (no cross-version data is available).

### Correctness invariant

`get_versioned_docs` NEVER returns a chunk that does not belong to the requested
`library_id`. Cross-version leakage is structurally impossible because chunks come
from a single library's fn_* table. The probabilistic cache gates performance only;
correctness is enforced by the cosine threshold + exact (library_id, version) match.
