"""Cross-encoder reranker for RAG shortlist refinement.

Uses ms-marco-MiniLM-L-6-v2 to score (query, passage) pairs and re-order
the top-k results from the hybrid retrieval step.

Enabled via RERANKER_ENABLED=true in .env.  Disabled by default because it
adds ~2–5 s of CPU time per query (model is ~50 MB, loaded lazily on first use).
"""

from __future__ import annotations

from typing import Any

from backend.core.logging import get_logger

log = get_logger(__name__)

_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"
_reranker = None  # lazy singleton


def _get_reranker():
    global _reranker
    if _reranker is None:
        try:
            from sentence_transformers import CrossEncoder
            log.info("reranker_loading", model=_MODEL_NAME)
            _reranker = CrossEncoder(_MODEL_NAME)
            log.info("reranker_loaded", model=_MODEL_NAME)
        except ImportError:
            log.warning("reranker_unavailable", reason="sentence-transformers not installed")
            _reranker = None
    return _reranker


def rerank(
    query: str,
    chunks: list[dict[str, Any]],
    top_n: int = 5,
) -> list[dict[str, Any]]:
    """Score (query, chunk_text) pairs with a cross-encoder and return top_n.

    Args:
        query:   The original incident / search query.
        chunks:  Candidate chunks (each must have a "text" key).
        top_n:   How many to return after reranking.

    Returns:
        Chunks sorted by cross-encoder score descending, with ``rerank_score``
        added to each dict.
    """
    if not chunks:
        return chunks

    try:
        model = _get_reranker()
        pairs = [(query, c["text"]) for c in chunks]
        scores: list[float] = model.predict(pairs).tolist()

        ranked = sorted(
            zip(scores, chunks),
            key=lambda x: x[0],
            reverse=True,
        )

        result = []
        for score, chunk in ranked[:top_n]:
            c = dict(chunk)
            c["rerank_score"] = round(float(score), 4)
            result.append(c)

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
        return chunks[:top_n]
