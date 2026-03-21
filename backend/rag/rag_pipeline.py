"""RAG pipeline: embed query → retrieve chunks → generate LLM answer with citations."""

from typing import Any

from backend.core.config import LLMProvider, settings
from backend.core.logging import get_logger
from backend.rag.embedding_engine import get_embedding_engine
from backend.rag.vector_store import query_collection

log = get_logger(__name__)

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
    2. Retrieve top-k nearest chunks (fetch extra when tag-filtering).
    3. Optionally filter by tags client-side.
    4. Send context + query to the configured LLM.
    5. Return structured results with citations.
    """
    engine = get_embedding_engine()
    query_embedding = engine.embed_one(query)

    # Fetch more results when tag filtering so we have enough after exclusions.
    fetch_k = top_k * 3 if filter_tags else top_k
    raw = query_collection(query_embedding, top_k=fetch_k)

    all_docs: list[str] = raw.get("documents", [[]])[0]
    all_metas: list[dict[str, Any]] = raw.get("metadatas", [[]])[0]
    all_distances: list[float] = raw.get("distances", [[]])[0]

    # Build citation list, applying optional tag filter client-side.
    results: list[dict[str, Any]] = []
    filtered_docs: list[str] = []
    filtered_metas: list[dict[str, Any]] = []

    for doc, meta, dist in zip(all_docs, all_metas, all_distances):
        if filter_tags:
            chunk_tags = [t.strip() for t in meta.get("tags", "").split(",") if t.strip()]
            if not any(t in chunk_tags for t in filter_tags):
                continue

        results.append(
            {
                "text": doc,
                "source": meta.get("source", ""),
                "runbook_id": meta.get("runbook_id", ""),
                "chunk_index": meta.get("chunk_index", 0),
                "score": round(1.0 - dist, 4),  # cosine distance → similarity
            }
        )
        filtered_docs.append(doc)
        filtered_metas.append(meta)

        if len(results) >= top_k:
            break

    if not filtered_docs:
        answer = "No relevant runbook content found for the given query."
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

    log.info(
        "rag_query_complete",
        query_preview=query[:80],
        results_returned=len(results),
    )
    return {"query": query, "results": results, "answer": answer}
