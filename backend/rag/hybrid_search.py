"""Hybrid BM25 + vector retrieval with Reciprocal Rank Fusion (RRF).

Combines lexical (BM25) and semantic (cosine similarity) ranking via RRF:
    hybrid_score(doc) = 1/(k + rank_bm25) + 1/(k + rank_vector)

No external dependencies — BM25 is implemented in pure Python.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from backend.core.logging import get_logger

log = get_logger(__name__)

_RRF_K = 60  # standard RRF constant; higher = less aggressive fusion


# ---------------------------------------------------------------------------
# BM25
# ---------------------------------------------------------------------------


class BM25Index:
    """Pure-Python BM25 scorer (k1=1.5, b=0.75, Okapi BM25 formula)."""

    def __init__(self, corpus: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.tokenized = [self._tokenize(doc) for doc in corpus]
        self.N = len(corpus)
        self.avgdl = (
            sum(len(d) for d in self.tokenized) / self.N if self.N else 1.0
        )
        self.df: dict[str, int] = {}
        for doc in self.tokenized:
            for term in set(doc):
                self.df[term] = self.df.get(term, 0) + 1

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return re.findall(r"[a-z0-9]+", text.lower())

    def score(self, query: str, doc_idx: int) -> float:
        terms = self._tokenize(query)
        doc = self.tokenized[doc_idx]
        dl = len(doc)
        tf_cnt = Counter(doc)
        total = 0.0
        for term in terms:
            df = self.df.get(term, 0)
            if df == 0:
                continue
            idf = math.log((self.N - df + 0.5) / (df + 0.5) + 1.0)
            tf = tf_cnt.get(term, 0)
            num = tf * (self.k1 + 1)
            den = tf + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
            total += idf * (num / den) if den else 0.0
        return total

    def rank(self, query: str) -> list[int]:
        """Return doc indices sorted by BM25 score descending."""
        scores = [(i, self.score(query, i)) for i in range(self.N)]
        scores.sort(key=lambda x: x[1], reverse=True)
        return [i for i, _ in scores]


# ---------------------------------------------------------------------------
# RRF fusion
# ---------------------------------------------------------------------------


def reciprocal_rank_fusion(
    ranked_lists: list[list[int]],
    k: int = _RRF_K,
) -> list[int]:
    """Fuse multiple ranked lists via Reciprocal Rank Fusion.

    score(doc) = sum over lists of  1 / (k + rank_in_list)
    Returns doc indices sorted by fused score descending.
    """
    scores: dict[int, float] = {}
    for ranked in ranked_lists:
        for rank, doc_idx in enumerate(ranked, start=1):
            scores[doc_idx] = scores.get(doc_idx, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda d: scores[d], reverse=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def hybrid_rerank(
    query: str,
    chunks: list[dict[str, Any]],
    top_k: int = 8,
) -> list[dict[str, Any]]:
    """Re-rank *chunks* using hybrid BM25 + vector RRF fusion.

    Args:
        query:  The primary search query (used for BM25 scoring).
        chunks: Already-retrieved chunks, each must have a "score" key
                (vector cosine similarity) and "text" key.
        top_k:  Number of chunks to return.

    Returns:
        Top-k chunks sorted by hybrid RRF score, with an added
        ``hybrid_score`` field.
    """
    if not chunks:
        return chunks

    texts = [c["text"] for c in chunks]

    # BM25 ranking over the candidate set
    bm25 = BM25Index(texts)
    bm25_ranked: list[int] = bm25.rank(query)

    # Vector ranking (already encoded in the "score" field)
    vector_ranked: list[int] = sorted(
        range(len(chunks)),
        key=lambda i: chunks[i].get("score", 0.0),
        reverse=True,
    )

    # RRF fusion
    fused_ranked = reciprocal_rank_fusion([bm25_ranked, vector_ranked])

    result = []
    for rank, idx in enumerate(fused_ranked[:top_k], start=1):
        chunk = dict(chunks[idx])
        chunk["hybrid_score"] = round(1.0 / (_RRF_K + rank), 6)
        result.append(chunk)

    log.info(
        "hybrid_rerank_done",
        query_preview=query[:60],
        input_chunks=len(chunks),
        output_chunks=len(result),
    )
    return result
