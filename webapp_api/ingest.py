"""Orchestrates user-submitted library docs into Supabase.

Thin wrapper around librariesintodatabase/db.py — reuses the exact upsert
primitives the scraper (scrape.py) uses, in the same call order, so manually
submitted libraries land in the same shape as scraped ones.
"""
from __future__ import annotations

import librariesintodatabase.db as db
import embeddings

from webapp_api.schemas import LibraryIngestRequest, LibraryIngestResponse


def ingest_library(payload: LibraryIngestRequest) -> LibraryIngestResponse:
    library_id = f"{payload.ecosystem}:{payload.name}".lower()
    table = db.sanitize_table_name(payload.ecosystem, payload.name)

    lib_text = " . ".join(
        filter(None, [payload.summary, *payload.tags[:15]])
    ) or f"{payload.ecosystem}:{payload.name}"
    lib_embedding = embeddings.embed(lib_text)

    db.upsert_library(
        {
            "library_id": library_id,
            "ecosystem": payload.ecosystem,
            "name": payload.name,
            "version": payload.version,
            "summary": payload.summary,
            "homepage": payload.homepage,
            "docs_url": payload.docs_url,
            "tier": payload.tier,
            "tags": payload.tags,
            "function_table": table,
            "embedding": lib_embedding,
        }
    )

    db.create_function_table(table, payload.tags)

    functions_upserted = 0
    if payload.functions:
        rows = []
        for fn in payload.functions:
            fn_text = f"{fn.qualified_name}: {fn.summary or ''}"
            rows.append(
                {
                    "qualified_name": fn.qualified_name,
                    "kind": fn.kind,
                    "signature": fn.signature,
                    "summary": fn.summary,
                    "description": fn.description,
                    "params": fn.params,
                    "returns": fn.returns,
                    "source_url": fn.source_url,
                    "embedding": embeddings.embed(fn_text),
                }
            )
        functions_upserted = db.upsert_functions(table, rows)

    tags_upserted = 0
    if payload.tags:
        db.upsert_tags(library_id, [(t, 1.0) for t in payload.tags])
        db.set_library_tags_array(library_id, payload.tags)
        tags_upserted = len(payload.tags)

    return LibraryIngestResponse(
        library_id=library_id,
        function_table=table,
        functions_upserted=functions_upserted,
        tags_upserted=tags_upserted,
    )
