"""ChromaDB client wrapper for the runbook vector store."""

from __future__ import annotations

import uuid
from typing import Any

import chromadb

from backend.core.config import settings
from backend.core.logging import get_logger

log = get_logger(__name__)

# Module-level client singleton.
_client: chromadb.HttpClient | None = None  # type: ignore[type-arg]


def get_chroma_client() -> chromadb.HttpClient:  # type: ignore[type-arg]
    global _client
    if _client is None:
        _client = chromadb.HttpClient(
            host=settings.chroma_host,
            port=settings.chroma_port,
        )
        log.info(
            "chroma_client_initialized",
            host=settings.chroma_host,
            port=settings.chroma_port,
        )
    return _client


def get_or_create_collection(
    client: chromadb.HttpClient | None = None,  # type: ignore[type-arg]
) -> Any:
    c = client or get_chroma_client()
    return c.get_or_create_collection(
        name=settings.chroma_collection_name,
        metadata={"hnsw:space": "cosine"},
    )


def add_chunks(
    chunks: list[dict[str, Any]],
    embeddings: list[list[float]],
) -> list[str]:
    """Store embedded chunks in ChromaDB and return their generated IDs."""
    collection = get_or_create_collection()
    ids = [str(uuid.uuid4()) for _ in chunks]

    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=[c["text"] for c in chunks],
        metadatas=[c["metadata"] for c in chunks],
    )
    log.info("chunks_added_to_chroma", count=len(ids))
    return ids


def query_collection(
    query_embedding: list[float],
    top_k: int = 5,
    where_filter: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the top-k nearest neighbours for a query embedding.

    Args:
        where_filter: Optional ChromaDB metadata filter, e.g. ``{"vendor": "cisco"}``.
                      When supplied, only chunks matching the filter are searched.
    """
    collection = get_or_create_collection()
    kwargs: dict[str, Any] = {
        "query_embeddings": [query_embedding],
        "n_results": top_k,
        "include": ["documents", "metadatas", "distances"],
    }
    if where_filter:
        kwargs["where"] = where_filter
    results = collection.query(**kwargs)
    return results  # type: ignore[return-value]


def delete_by_runbook_id(runbook_id: str) -> int:
    """Delete all chunks belonging to *runbook_id* and return the count removed."""
    collection = get_or_create_collection()
    results = collection.get(where={"runbook_id": runbook_id})
    ids: list[str] = results.get("ids", [])
    if ids:
        collection.delete(ids=ids)
    log.info("chunks_deleted_from_chroma", runbook_id=runbook_id, count=len(ids))
    return len(ids)
