"""Cross-encoder reranker for RAG shortlist refinement.

Uses flashrank (ONNX, no PyTorch) with ms-marco-MiniLM-L-12-v2 to score
(query, passage) pairs and re-order the top-k results from vector retrieval.

Enabled via RERANKER_ENABLED=true in .env.  Disabled by default.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from backend.core.logging import get_logger

log = get_logger(__name__)

_MODEL_NAME = "ms-marco-MiniLM-L-12-v2"


@lru_cache(maxsize=1)
def _get_ranker():
    """Load the flashrank cross-encoder once and cache it."""
    try:
        from flashrank import Ranker
        log.info("reranker_loading", model=_MODEL_NAME)
        ranker = Ranker(model_name=_MODEL_NAME)
        log.info("reranker_loaded", model=_MODEL_NAME)
        return ranker
    except ImportError:
        log.warning("reranker_unavailable", reason="flashrank not installed")
        return None


def rerank(
    query: str,
    chunks: list[dict[str, Any]],
    top_n: int = 5,
) -> list[dict[str, Any]]:
    """Score (query, chunk_text) pairs with a cross-encoder and return top_n.

    Args:
        query:   The original incident / search query.
        chunks:  Candidate chunks (each must have a ``"text"`` key).
        top_n:   How many to return after reranking.

    Returns:
        Chunks sorted by cross-encoder score descending, with ``rerank_score``
        added to each dict.  Falls back to original order if reranker fails.
    """
    if not chunks:
        return chunks

    try:
        ranker = _get_ranker()
        if ranker is None:
            # flashrank unavailable — attach score from vector similarity as rerank_score
            result = []
            for chunk in chunks[:top_n]:
                c = dict(chunk)
                c["rerank_score"] = round(float(c.get("score", 0.0)), 4)
                result.append(c)
            return result

        from flashrank import RerankRequest

        passages = [{"id": i, "text": c["text"]} for i, c in enumerate(chunks)]
        request = RerankRequest(query=query, passages=passages)
        results = ranker.rerank(request)

        # Map scores back to original chunk dicts
        scored: list[dict[str, Any]] = []
        for r in results:
            chunk = dict(chunks[r["id"]])
            chunk["rerank_score"] = round(float(r["score"]), 4)
            scored.append(chunk)

        scored.sort(key=lambda c: c["rerank_score"], reverse=True)
        result = scored[:top_n]

        log.info(
            "rerank_done",
            query_preview=query[:60],
            input=len(chunks),
            output=len(result),
            top_score=result[0]["rerank_score"] if result else None,
        )
        return result

    except Exception as exc:
        log.warning("rerank_failed", error=str(exc))
        result = []
        for chunk in chunks[:top_n]:
            c = dict(chunk)
            c["rerank_score"] = round(float(c.get("score", 0.0)), 4)
            result.append(c)
        return result
