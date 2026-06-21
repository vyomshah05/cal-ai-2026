"""Pydantic request/response models for the Lockstep webapp ingestion API.

Mirrors the schema in CONTRACT.md exactly so payloads map 1:1 onto
librariesintodatabase/db.py's upsert_* functions.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Ecosystem = Literal["npm", "pypi", "cargo", "go", "maven", "rubygems"]
Tier = Literal["popular", "niche"]


class FunctionIn(BaseModel):
    qualified_name: str
    kind: str | None = "function"
    signature: str | None = None
    summary: str | None = None
    description: str | None = None
    params: dict[str, Any] | list[Any] | None = None
    returns: str | None = None
    source_url: str | None = None


class LibraryIngestRequest(BaseModel):
    ecosystem: Ecosystem
    name: str
    version: str | None = None
    summary: str | None = None
    homepage: str | None = None
    docs_url: str | None = None
    tier: Tier = "niche"
    tags: list[str] = Field(default_factory=list)
    functions: list[FunctionIn] = Field(default_factory=list)


class LibraryIngestResponse(BaseModel):
    library_id: str
    function_table: str
    functions_upserted: int
    tags_upserted: int
