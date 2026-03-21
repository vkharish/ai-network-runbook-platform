"""Tests for the RAG pipeline components."""

import pytest

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Unit tests — no DB/ChromaDB required
# ---------------------------------------------------------------------------

def test_chunk_document_splits_long_text():
    from backend.rag.ingest_documents import chunk_document

    text = "BGP troubleshooting step. " * 200   # ~5000 chars
    chunks = chunk_document(text, source="test.md", runbook_id="test-id-123")
    assert len(chunks) > 1
    for chunk in chunks:
        assert "text" in chunk
        assert "metadata" in chunk
        meta = chunk["metadata"]
        assert meta["source"] == "test.md"
        assert meta["runbook_id"] == "test-id-123"
        assert "chunk_index" in meta


def test_chunk_document_tags_stored_as_string():
    from backend.rag.ingest_documents import chunk_document

    chunks = chunk_document(
        "short text " * 10,
        source="test.md",
        runbook_id="abc",
        tags=["cisco", "bgp"],
    )
    assert chunks[0]["metadata"]["tags"] == "cisco,bgp"


def test_chunk_document_empty_tags():
    from backend.rag.ingest_documents import chunk_document

    chunks = chunk_document("some text " * 10, source="s.md", runbook_id="x")
    assert chunks[0]["metadata"]["tags"] == ""


def test_hybrid_rerank_returns_top_k():
    from backend.rag.hybrid_search import hybrid_rerank

    chunks = [
        {"text": "BGP session stuck in Active state due to TCP timeout", "score": 0.9},
        {"text": "OSPF hello dead timer mismatch prevents adjacency",    "score": 0.8},
        {"text": "BGP MD5 authentication mismatch drops session",        "score": 0.7},
        {"text": "Interface GigabitEthernet1 is administratively down",  "score": 0.6},
        {"text": "BGP hold timer expiry causes session flap",            "score": 0.5},
    ]
    result = hybrid_rerank("BGP session drops", chunks, top_k=3)
    assert len(result) == 3
    for r in result:
        assert "hybrid_score" in r


def test_hybrid_rerank_empty_corpus():
    from backend.rag.hybrid_search import hybrid_rerank

    result = hybrid_rerank("BGP down", [], top_k=5)
    assert result == []


def test_bm25_scores_relevant_doc_higher():
    from backend.rag.hybrid_search import BM25Index

    corpus = [
        "BGP session stuck Active state peer unreachable",
        "OSPF hello timer mismatch adjacency failure",
        "Interface down administratively shutdown",
    ]
    bm25 = BM25Index(corpus)
    ranked = bm25.rank("BGP session Active peer")
    # BGP document should rank first
    assert ranked[0] == 0


def test_rrf_fusion_combines_rankings():
    from backend.rag.hybrid_search import reciprocal_rank_fusion

    # List A ranks: 0, 1, 2  |  List B ranks: 2, 0, 1
    # Doc 0: 1/(60+1) + 1/(60+2) ≈ 0.0164 + 0.0161 = 0.0325
    # Doc 2: 1/(60+3) + 1/(60+1) ≈ 0.0159 + 0.0164 = 0.0323
    # Doc 1: 1/(60+2) + 1/(60+3) ≈ 0.0161 + 0.0159 = 0.0320
    fused = reciprocal_rank_fusion([[0, 1, 2], [2, 0, 1]])
    assert len(fused) == 3
    assert fused[0] == 0   # doc 0 has highest combined RRF score


async def test_rag_query_with_mocked_chromadb(monkeypatch):
    """End-to-end RAG query with mocked ChromaDB and LLM."""
    from backend.rag.rag_pipeline import run_rag_query

    # Mock embedding engine
    class FakeEngine:
        def embed_one(self, text):
            return [0.1] * 384

    # Mock ChromaDB response
    fake_chroma_response = {
        "documents": [["BGP session stuck in Active state.", "Check hold timer settings."]],
        "metadatas": [
            [
                {"source": "bgp_runbook.md", "runbook_id": "r1", "chunk_index": 0, "tags": "cisco,bgp"},
                {"source": "bgp_runbook.md", "runbook_id": "r1", "chunk_index": 1, "tags": "cisco,bgp"},
            ]
        ],
        "distances": [[0.1, 0.2]],
    }

    # Mock LLM response
    fake_llm_answer = "The BGP session is stuck in Active state. Check hold timer."

    monkeypatch.setattr("backend.rag.rag_pipeline.get_embedding_engine", lambda: FakeEngine())
    monkeypatch.setattr("backend.rag.rag_pipeline.query_collection", lambda *a, **kw: fake_chroma_response)
    monkeypatch.setattr("backend.rag.rag_pipeline._call_llm", lambda *a, **kw: fake_llm_answer)

    result = await run_rag_query("BGP session stuck Active state")

    assert result["answer"] == fake_llm_answer
    assert len(result["results"]) == 2
    assert result["results"][0]["source"] == "bgp_runbook.md"
