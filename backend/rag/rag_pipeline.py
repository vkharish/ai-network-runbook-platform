"""RAG pipeline: embed query → retrieve chunks → generate LLM answer with citations."""

import time
from typing import Any

from backend.core.config import LLMProvider, settings
from backend.core.logging import get_logger
from backend.rag.embedding_engine import get_embedding_engine
from backend.rag.reranker import rerank
from backend.rag.vector_store import query_collection

log = get_logger(__name__)

try:
    from prometheus_client import Counter, Histogram

    _RAG_QUERY_DURATION = Histogram(
        "rag_query_duration_seconds",
        "End-to-end RAG query latency (embed + retrieve + LLM)",
    )
    _RAG_QUERY_TOTAL = Counter(
        "rag_query_total",
        "Total RAG queries",
        ["outcome"],  # success | no_results | llm_error
    )
    _RAG_RESULTS_RETURNED = Histogram(
        "rag_results_returned",
        "Number of chunks returned per RAG query",
        buckets=[0, 1, 2, 3, 5, 10],
    )
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False

_SYSTEM_PROMPT = (
    "You are a network operations expert assistant. "
    "Answer the engineer's question using ONLY the provided context from network runbooks. "
    "Structure your answer with clear steps when applicable. "
    "If the context does not contain enough information, say so explicitly. "
    "Always cite the source document(s) you used."
)


# ---------------------------------------------------------------------------
# LLM answer generation
# ---------------------------------------------------------------------------

def _build_user_message(context: str, query: str) -> str:
    return (
        f"### Runbook Context\n\n{context}\n\n"
        f"### Engineer Question\n\n{query}"
    )


def _format_context(docs: list[str], metadatas: list[dict[str, Any]]) -> str:
    sections: list[str] = []
    for i, (doc, meta) in enumerate(zip(docs, metadatas), 1):
        source = meta.get("source", "unknown")
        sections.append(f"[{i}] **{source}**\n{doc}")
    return "\n\n---\n\n".join(sections)


def _call_llm(context: str, query: str) -> str:
    user_msg = _build_user_message(context, query)

    if settings.llm_provider == LLMProvider.OPENAI:
        from openai import OpenAI

        client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )
        response = client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=1024,
            temperature=0.2,
        )
        return response.choices[0].message.content or ""

    elif settings.llm_provider == LLMProvider.ANTHROPIC:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=settings.llm_model,
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        return response.content[0].text  # type: ignore[union-attr]

    else:  # Ollama
        import ollama

        response = ollama.chat(
            model=settings.ollama_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
        )
        return response["message"]["content"]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_rag_query(
    query: str,
    top_k: int = 5,
    filter_tags: list[str] | None = None,
) -> dict[str, Any]:
    """
    Full RAG pipeline:
    1. Embed the query.
    2. Retrieve top-k nearest chunks (fetch extra when tag-filtering or reranking).
    3. Optionally rerank with cross-encoder (RERANKER_ENABLED=true).
    4. Optionally filter by tags client-side.
    5. Send context + query to the configured LLM.
    6. Return structured results with citations.
    """
    _t0 = time.perf_counter()
    engine = get_embedding_engine()
    query_embedding = engine.embed_one(query)

    # Fetch wider candidate set when tag-filtering or reranking.
    fetch_k = top_k * 3 if (filter_tags or settings.reranker_enabled) else top_k
    raw = query_collection(query_embedding, top_k=fetch_k)

    all_docs: list[str] = raw.get("documents", [[]])[0]
    all_metas: list[dict[str, Any]] = raw.get("metadatas", [[]])[0]
    all_distances: list[float] = raw.get("distances", [[]])[0]

    # Build candidate list from retrieval results.
    candidates: list[dict[str, Any]] = []
    for doc, meta, dist in zip(all_docs, all_metas, all_distances):
        if filter_tags:
            chunk_tags = [t.strip() for t in meta.get("tags", "").split(",") if t.strip()]
            if not any(t in chunk_tags for t in filter_tags):
                continue
        candidates.append(
            {
                "text": doc,
                "source": meta.get("source", ""),
                "runbook_id": meta.get("runbook_id", ""),
                "chunk_index": meta.get("chunk_index", 0),
                "score": round(1.0 - dist, 4),
                "metadata": meta,
            }
        )

    # Rerank with cross-encoder when enabled — replaces cosine ordering.
    if settings.reranker_enabled and candidates:
        candidates = rerank(query, candidates, top_n=top_k)
    else:
        candidates = candidates[:top_k]

    results: list[dict[str, Any]] = []
    filtered_docs: list[str] = []
    filtered_metas: list[dict[str, Any]] = []

    for c in candidates:
        entry = {
            "text": c["text"],
            "source": c["source"],
            "runbook_id": c["runbook_id"],
            "chunk_index": c["chunk_index"],
            "score": c["score"],
        }
        if "rerank_score" in c:
            entry["rerank_score"] = c["rerank_score"]
        results.append(entry)
        filtered_docs.append(c["text"])
        filtered_metas.append(c["metadata"])

    _outcome = "success"
    if not filtered_docs:
        answer = "No relevant runbook content found for the given query."
        _outcome = "no_results"
    else:
        context = _format_context(filtered_docs, filtered_metas)
        try:
            answer = _call_llm(context, query)
        except Exception as exc:
            log.error("rag_llm_error", error=str(exc))
            answer = (
                f"Retrieved {len(filtered_docs)} relevant chunk(s) but the LLM "
                f"answer generation failed: {exc}"
            )
            _outcome = "llm_error"

    if _PROMETHEUS_AVAILABLE:
        _elapsed = time.perf_counter() - _t0
        _RAG_QUERY_DURATION.observe(_elapsed)
        _RAG_QUERY_TOTAL.labels(outcome=_outcome).inc()
        _RAG_RESULTS_RETURNED.observe(len(results))

    log.info(
        "rag_query_complete",
        query_preview=query[:80],
        results_returned=len(results),
    )
    return {"query": query, "results": results, "answer": answer}
