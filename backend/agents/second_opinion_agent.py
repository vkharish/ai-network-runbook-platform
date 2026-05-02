"""SecondOpinionAgent — re-investigates with refined queries when confidence is low.

Given the initial InvestigationContext and a low-confidence AnalysisResult, this agent
builds targeted RAG queries derived from the initial root cause hypothesis and fetches
additional runbook chunks to supplement the existing context.
"""

from backend.agents.analysis_agent import AnalysisResult
from backend.agents.investigation_agent import InvestigationAgent, InvestigationContext
from backend.core.logging import get_logger
from backend.rag.embedding_engine import get_embedding_engine
from backend.rag.vector_store import query_collection

log = get_logger(__name__)


class SecondOpinionAgent:
    """Re-investigates an incident using the initial analysis as a search hint.

    Builds refined queries from:
    1. The initial root_cause string
    2. Affected components extracted from the first analysis
    3. Key evidence phrases

    Merges the new chunks with the existing context (deduplicating by source+index)
    and returns an enriched InvestigationContext for a second AnalysisAgent pass.
    """

    def run_toon(
        self,
        toon_ctx: str,
        toon_analysis: str,
        original_context: InvestigationContext,
    ) -> InvestigationContext:
        """Re-investigate using TOON-compressed prior context + analysis.

        Builds refined RAG queries from the compressed analysis,
        fetches new chunks, merges into the original context.
        Saves tokens by passing compressed strings instead of full objects.
        """
        import json
        try:
            analysis_dict = json.loads(toon_analysis)
            root_cause = analysis_dict.get("rc", "")
            evidence = analysis_dict.get("ev", [])
            components = analysis_dict.get("comp", [])
            confidence = analysis_dict.get("conf", 0.5)
        except Exception:
            root_cause, evidence, components, confidence = "", [], [], 0.5

        queries: list[str] = []
        if root_cause:
            queries.append(root_cause)
        for ev in evidence[:2]:
            if len(ev) > 15:
                queries.append(ev[:200])
        for comp in components[:2]:
            queries.append(f"{comp} troubleshooting")
        if not queries:
            queries.append(f"{original_context.title} resolution steps")

        new_chunks = self._retrieve_chunks(queries[:4], top_k=3)
        merged = self._merge_chunks(original_context.runbook_chunks, new_chunks)

        log.info(
            "second_opinion_toon_reinvestigated",
            inc_ref=original_context.inc_ref,
            new_chunks=len(new_chunks),
            merged_total=len(merged),
            prior_confidence=confidence,
        )

        return InvestigationContext(
            incident_id=original_context.incident_id,
            inc_ref=original_context.inc_ref,
            title=original_context.title,
            description=original_context.description,
            severity=original_context.severity,
            affected_device=original_context.affected_device,
            affected_protocol=original_context.affected_protocol,
            runbook_chunks=merged,
            cli_outputs=original_context.cli_outputs,
            citations=list({c["source"] for c in merged if c.get("source")}),
            topology_neighbors=original_context.topology_neighbors,
        )

    def run(
        self,
        context: InvestigationContext,
        initial_analysis: AnalysisResult,
    ) -> InvestigationContext:
        refined_queries = self._build_refined_queries(context, initial_analysis)
        new_chunks = self._retrieve_chunks(refined_queries, top_k=5)
        merged = self._merge_chunks(context.runbook_chunks, new_chunks)

        log.info(
            "second_opinion_reinvestigated",
            inc_ref=context.inc_ref,
            incident_id=context.incident_id,
            refined_queries=len(refined_queries),
            new_chunks=len(new_chunks),
            merged_total=len(merged),
            initial_confidence=initial_analysis.confidence,
        )

        # Return a new context with the enriched chunk set; CLI/topology stay the same.
        return InvestigationContext(
            incident_id=context.incident_id,
            inc_ref=context.inc_ref,
            title=context.title,
            description=context.description,
            severity=context.severity,
            affected_device=context.affected_device,
            affected_protocol=context.affected_protocol,
            runbook_chunks=merged,
            cli_outputs=context.cli_outputs,
            citations=list({c["source"] for c in merged if c.get("source")}),
            topology_neighbors=context.topology_neighbors,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_refined_queries(
        self, context: InvestigationContext, analysis: AnalysisResult
    ) -> list[str]:
        """Derive targeted queries from the initial analysis output."""
        queries: list[str] = []

        # Root cause as a direct search query
        if analysis.root_cause and "undetermined" not in analysis.root_cause.lower():
            queries.append(analysis.root_cause)

        # Top evidence phrases (up to 2)
        for ev in analysis.evidence[:2]:
            if len(ev) > 15:
                queries.append(ev[:200])

        # Affected components (e.g. "R1-CORE GigabitEthernet1 troubleshooting")
        for comp in analysis.affected_components[:2]:
            queries.append(f"{comp} troubleshooting resolution")

        # Fallback: original title + "resolution"
        if not queries:
            queries.append(f"{context.title} resolution steps")

        return queries[:4]  # cap at 4 refined queries

    def _retrieve_chunks(self, queries: list[str], top_k: int = 5) -> list[dict]:
        engine = get_embedding_engine()
        seen: set[tuple[str, int]] = set()
        merged: list[dict] = []

        for query in queries:
            try:
                embedding = engine.embed_one(query)
                raw = query_collection(embedding, top_k=top_k)
                docs: list[str] = raw.get("documents", [[]])[0]
                metas: list[dict] = raw.get("metadatas", [[]])[0]
                distances: list[float] = raw.get("distances", [[]])[0]

                for doc, meta, dist in zip(docs, metas, distances):
                    key = (meta.get("source", ""), meta.get("chunk_index", 0))
                    if key not in seen:
                        seen.add(key)
                        merged.append(
                            {
                                "text": doc,
                                "source": meta.get("source", ""),
                                "runbook_id": meta.get("runbook_id", ""),
                                "chunk_index": meta.get("chunk_index", 0),
                                "score": round(1.0 - dist, 4),
                            }
                        )
            except Exception as exc:
                log.warning("second_opinion_rag_failed", query_preview=query[:60], error=str(exc))

        merged.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        return merged[:8]

    def _merge_chunks(
        self, existing: list[dict], new_chunks: list[dict]
    ) -> list[dict]:
        """Merge new chunks into existing, deduplicating by (source, chunk_index)."""
        seen: set[tuple[str, int]] = {
            (c.get("source", ""), c.get("chunk_index", 0)) for c in existing
        }
        combined = list(existing)
        for chunk in new_chunks:
            key = (chunk.get("source", ""), chunk.get("chunk_index", 0))
            if key not in seen:
                seen.add(key)
                combined.append(chunk)

        combined.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        return combined[:12]  # cap total context at 12 chunks
