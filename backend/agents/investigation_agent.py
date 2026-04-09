"""InvestigationAgent — gathers all context needed for diagnosis.

Responsibilities:
  1. Build multiple RAG queries from incident fields.
  2. Retrieve and deduplicate runbook chunks from ChromaDB.
  3. Load simulated CLI outputs for the affected device.
"""

from dataclasses import dataclass, field
from typing import Any

from backend.automation.device_gateway import DeviceGateway
from backend.core.config import settings
from backend.core.logging import get_logger
from backend.rag.embedding_engine import get_embedding_engine
from backend.rag.vector_store import query_collection

log = get_logger(__name__)

_device_gateway = DeviceGateway()


@dataclass
class InvestigationContext:
    incident_id: str
    inc_ref: str          # human-readable: INC-0001
    title: str
    description: str
    severity: str
    affected_device: str | None
    affected_protocol: str | None
    runbook_chunks: list[dict[str, Any]]
    cli_outputs: dict[str, str]
    citations: list[str] = field(default_factory=list)
    topology_neighbors: list[dict[str, Any]] = field(default_factory=list)


class InvestigationAgent:
    """Collects incident context, RAG knowledge, and CLI evidence."""

    def run(self, incident: Any, topology_graph: dict[str, Any] | None = None) -> InvestigationContext:
        vendor_hint = self._detect_vendor(incident.affected_device)
        queries = self._build_queries(incident)
        chunks = self._retrieve_chunks(queries, top_k=5, vendor_hint=vendor_hint)
        cli = self._load_cli_outputs(incident.affected_device)
        topology_neighbors: list[dict[str, Any]] = []

        # If topology available, load CLI for direct neighbors too
        if topology_graph and incident.affected_device:
            topology_neighbors, neighbor_cli = self._load_topology_context(
                topology_graph, incident.affected_device
            )
            cli.update(neighbor_cli)

        citations = list({c["source"] for c in chunks if c.get("source")})

        # Optional cross-encoder reranking
        if settings.reranker_enabled and chunks:
            try:
                from backend.rag.reranker import rerank
                primary_query = queries[0] if queries else incident.title
                chunks = rerank(primary_query, chunks, top_n=8)
            except Exception as exc:
                log.warning("reranker_skipped", error=str(exc))

        inc_ref = f"INC-{str(incident.incident_number or 0).zfill(4)}"
        log.info(
            "investigation_complete",
            inc_ref=inc_ref,
            incident_id=str(incident.id),
            queries=len(queries),
            chunks=len(chunks),
            cli_files=len(cli),
            topology_neighbors=len(topology_neighbors),
        )
        return InvestigationContext(
            incident_id=str(incident.id),
            inc_ref=inc_ref,
            title=incident.title,
            description=incident.description,
            severity=incident.severity,
            affected_device=incident.affected_device,
            affected_protocol=incident.affected_protocol,
            runbook_chunks=chunks,
            cli_outputs=cli,
            citations=citations,
            topology_neighbors=topology_neighbors,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_queries(self, incident: Any) -> list[str]:
        """Generate up to 3 complementary queries to maximise RAG recall."""
        queries: list[str] = [incident.title]
        if incident.affected_protocol:
            queries.append(f"{incident.affected_protocol} troubleshooting steps")
        if incident.affected_device and incident.affected_protocol:
            queries.append(f"{incident.affected_device} {incident.affected_protocol} failure diagnosis")
        elif len(incident.description) > 20:
            queries.append(incident.description[:200])
        return queries

    def _retrieve_chunks(
        self,
        queries: list[str],
        top_k: int = 5,
        vendor_hint: str | None = None,
    ) -> list[dict[str, Any]]:
        """Run each query against ChromaDB, merge, deduplicate, and vendor-filter results."""
        engine = get_embedding_engine()
        seen: set[tuple[str, int]] = set()
        merged: list[dict[str, Any]] = []

        # Try ChromaDB native vendor filter first (faster, higher precision).
        # Falls back to unfiltered query + post-filter if the collection has no
        # vendor-tagged chunks yet (e.g. runbooks uploaded before this feature).
        native_filter: dict | None = (
            {"vendor": vendor_hint} if vendor_hint and vendor_hint != "generic" else None
        )

        def _run_queries(where: dict | None) -> list[dict]:
            results: list[dict] = []
            _seen: set[tuple[str, int]] = set()
            for query in queries:
                try:
                    embedding = engine.embed_one(query)
                    raw = query_collection(embedding, top_k=top_k, where_filter=where)
                    docs: list[str] = raw.get("documents", [[]])[0]
                    metas: list[dict] = raw.get("metadatas", [[]])[0]
                    distances: list[float] = raw.get("distances", [[]])[0]
                    for doc, meta, dist in zip(docs, metas, distances):
                        key = (meta.get("source", ""), meta.get("chunk_index", 0))
                        if key not in _seen:
                            _seen.add(key)
                            results.append({
                                "text": doc,
                                "source": meta.get("source", ""),
                                "runbook_id": meta.get("runbook_id", ""),
                                "chunk_index": meta.get("chunk_index", 0),
                                "score": round(1.0 - dist, 4),
                                "tags": meta.get("tags", ""),
                                "vendor": meta.get("vendor", "generic"),
                            })
                except Exception as exc:
                    log.warning("rag_query_failed", query_preview=query[:60], error=str(exc))
            return results

        # Phase 1: vendor-specific query
        if native_filter:
            try:
                merged = _run_queries(native_filter)
                if len(merged) >= 2:
                    log.info("vendor_native_filter_applied", vendor=vendor_hint, chunks=len(merged))
                else:
                    # Phase 2: not enough vendor chunks — fall back to unfiltered
                    log.info("vendor_native_filter_fallback", vendor=vendor_hint, found=len(merged))
                    merged = _run_queries(None)
            except Exception as exc:
                log.warning("vendor_native_filter_error", vendor=vendor_hint, error=str(exc))
                merged = _run_queries(None)
        else:
            merged = _run_queries(None)

        # Hybrid BM25 + vector RRF re-rank when we have enough candidates
        if len(merged) > top_k:
            try:
                from backend.rag.hybrid_search import hybrid_rerank
                primary_query = queries[0] if queries else ""
                merged = hybrid_rerank(primary_query, merged, top_k=len(merged))
            except Exception as exc:
                log.warning("hybrid_rerank_failed", error=str(exc))
                merged.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        else:
            merged.sort(key=lambda x: x.get("score", 0.0), reverse=True)

        # Post-filter fallback: if native filter returned generic chunks, prefer vendor ones
        if vendor_hint and not native_filter:
            vendor_chunks = [
                c for c in merged
                if vendor_hint in c.get("tags", "").lower()
                or vendor_hint in c.get("source", "").lower()
                or c.get("vendor") == vendor_hint
            ]
            if len(vendor_chunks) >= 2:
                log.info("vendor_post_filter_applied", vendor=vendor_hint, chunks=len(vendor_chunks))
                return vendor_chunks[:8]

        return merged[:8]

    @staticmethod
    def _detect_vendor(device: str | None) -> str | None:
        """Infer vendor (cisco/juniper) from a device identifier string."""
        if not device:
            return None
        d = device.lower()
        if any(ind in d for ind in {"juniper", "junos", "vmx", "r3", "r5"}):
            return "juniper"
        return "cisco"

    def _load_topology_context(
        self, topology_graph: dict[str, Any], device_identifier: str
    ) -> tuple[list[dict[str, Any]], dict[str, str]]:
        """Use the digital twin to find neighbors and load their CLI outputs."""
        try:
            from backend.digital_twin.graph_engine import find_device_id, get_neighbors
            from backend.digital_twin.topology_builder import graph_from_dict

            G = graph_from_dict(topology_graph)
            device_id = find_device_id(G, device_identifier)
            if not device_id:
                return [], {}

            neighbors = get_neighbors(G, device_id)
            neighbor_cli: dict[str, str] = {}
            for nbr in neighbors:
                nbr_outputs = self._load_cli_outputs(nbr["device_id"])
                # Prefix keys so they don't overwrite the primary device's outputs
                for k, v in nbr_outputs.items():
                    neighbor_cli[f"neighbor_{nbr['device_id']}_{k}"] = v

            return neighbors, neighbor_cli
        except Exception as exc:
            log.warning("topology_context_failed", error=str(exc))
            return [], {}

    def _load_cli_outputs(self, device: str | None) -> dict[str, str]:
        """Load CLI outputs via DeviceGateway (simulator or live SSH based on device config)."""
        return _device_gateway.load_all_outputs(device)
