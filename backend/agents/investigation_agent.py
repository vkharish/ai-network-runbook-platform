"""InvestigationAgent — gathers all context needed for diagnosis.

Responsibilities:
  1. Build multiple RAG queries from incident fields.
  2. Retrieve and deduplicate runbook chunks from ChromaDB.
  3. Load simulated CLI outputs for the affected device.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.rag.embedding_engine import get_embedding_engine
from backend.rag.vector_store import query_collection

log = get_logger(__name__)

# Resolved at import time — works regardless of working directory.
SIMULATOR_DIR = Path(__file__).resolve().parent.parent.parent / "simulator"


@dataclass
class InvestigationContext:
    incident_id: str
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

        log.info(
            "investigation_complete",
            incident_id=str(incident.id),
            queries=len(queries),
            chunks=len(chunks),
            cli_files=len(cli),
            topology_neighbors=len(topology_neighbors),
        )
        return InvestigationContext(
            incident_id=str(incident.id),
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
                                "tags": meta.get("tags", ""),
                            }
                        )
            except Exception as exc:
                log.warning("rag_query_failed", query_preview=query[:60], error=str(exc))

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

        # Vendor-aware filtering: prefer chunks tagged for the affected vendor.
        # Falls back to all chunks if fewer than 2 vendor-specific chunks are found.
        if vendor_hint:
            vendor_chunks = [
                c for c in merged
                if vendor_hint in c.get("tags", "").lower()
                or vendor_hint in c.get("source", "").lower()
            ]
            if len(vendor_chunks) >= 2:
                log.info(
                    "vendor_filter_applied",
                    vendor=vendor_hint,
                    before=len(merged),
                    after=len(vendor_chunks),
                )
                return vendor_chunks[:8]
            log.info(
                "vendor_filter_fallback",
                vendor=vendor_hint,
                vendor_chunks_found=len(vendor_chunks),
            )

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
        """Load *.txt simulator files for the affected device (or all if unknown)."""
        if not SIMULATOR_DIR.exists():
            log.warning("simulator_dir_missing", path=str(SIMULATOR_DIR))
            return {}

        if device:
            # "R1-CORE" → "r1",  "R2-DIST" → "r2",  "r1" → "r1"
            normalized = device.lower().split("-")[0].split("_")[0]
            device_dir = SIMULATOR_DIR / normalized
            dirs = [device_dir] if device_dir.exists() else list(SIMULATOR_DIR.iterdir())
        else:
            dirs = list(SIMULATOR_DIR.iterdir())

        outputs: dict[str, str] = {}
        for d in dirs:
            if not d.is_dir():
                continue
            for txt in sorted(d.glob("*.txt")):
                key = f"{d.name}_{txt.stem}"
                outputs[key] = txt.read_text(encoding="utf-8", errors="replace")

        log.info("cli_outputs_loaded", device=device, files=list(outputs.keys()))
        return outputs
