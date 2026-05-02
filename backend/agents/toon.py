"""TOON — Token Optimization Object Notation

A compact inter-agent serialization format that reduces LLM input tokens by
40-60% through four mechanisms:

  1. Abbreviated field keys       — "root_cause" → "rc", "hypothesis" → "hyp"
  2. CLI signal-line extraction   — strips decorative/empty lines, keeps anomalies
  3. RAG chunk truncation         — keeps first 250 chars of each chunk text
  4. Compact JSON output          — no pretty-printing, no whitespace between fields

TOON is used when passing context TO specialist agents and the ReportAgent.
The InvestigationAgent still builds full context; TOON is applied only at the
boundary where full context would be sent redundantly to a second LLM call.

Token estimation: 1 token ≈ 4 characters (conservative GPT-4 approximation).

Usage:
    from backend.agents.toon import TOON

    # Compress InvestigationContext for a specialist agent
    compact = TOON.compress_context(ctx)
    savings = TOON.savings(original_str, compact)
    # → {"saved_tokens": 1240, "saved_pct": 58.3}

    # Compact AnalysisResult for ReportAgent
    compact_analysis = TOON.compress_analysis(analysis)
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from typing import Any

from backend.core.logging import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Signal patterns — lines matching these are KEPT in CLI output
# Everything else is stripped.
# ---------------------------------------------------------------------------
_SIGNAL_RES = [re.compile(p, re.IGNORECASE) for p in [
    r"\d{1,3}(?:\.\d{1,3}){3}",                          # any IP address
    r"Established|Active|Idle|Connect|OpenSent|OpenConfirm",  # BGP states
    r"\bup\b|\bdown\b|FULL|LOADING|Init|2WAY|EXSTART|EXCHANGE",  # interface / OSPF states
    r"error|fail|drop|exceed|threshold|limit|reset|flap",  # anomaly keywords
    r"State/PfxRcd|MsgRcvd|MsgSent|Up/Down|PfxRcd",      # BGP summary columns
    r"input errors|output errors|CRC|runts|giants",        # interface error counters
    r"BGP-\d|OSPF-\d|ISIS-\d|LINK-\d|SYS-\d",           # Cisco syslog events
    r"rpd\[\d+\]|chassisd|mgd",                           # Juniper daemon logs
    r"neighbor\s+\S+\s+state|adjchange|nbrdown|nbrup",    # neighbour state changes
    r"hold.?time|keepalive|timer",                         # BGP timer fields
    r"prefix.?limit|maximum.?prefix",                      # prefix limit events
    r"AS\s*\d+|local AS|remote AS",                       # AS number lines
]]

# Lines that are purely decorative — always stripped
_NOISE_RES = [re.compile(p) for p in [
    r"^\s*[-=*#!~]{3,}\s*$",   # horizontal rules
    r"^\s*$",                   # blank lines
    r"^\s*!\s*$",               # standalone !
]]

# Maximum chars kept per CLI block after signal filtering
_CLI_BLOCK_MAX = 800

# Maximum chars kept per RAG chunk text
_CHUNK_TEXT_MAX = 250

# Abbreviated key map for InvestigationContext → TOON
_CTX_KEY_MAP = {
    "incident_id": "id",
    "inc_ref": "ref",
    "title": "ttl",
    "description": "desc",
    "severity": "sev",
    "affected_device": "dev",
    "affected_protocol": "proto",
    "runbook_chunks": "kb",
    "cli_outputs": "cli",
    "citations": "cit",
    "topology_neighbors": "nbr",
}

# Abbreviated key map for AnalysisResult → TOON
_ANALYSIS_KEY_MAP = {
    "root_cause": "rc",
    "hypothesis": "hyp",
    "confidence": "conf",
    "evidence": "ev",
    "affected_components": "comp",
    "urgency": "urg",
}


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def _is_signal_line(line: str) -> bool:
    if any(n.search(line) for n in _NOISE_RES):
        return False
    return any(s.search(line) for s in _SIGNAL_RES)


def extract_cli_signals(raw: str, max_chars: int = _CLI_BLOCK_MAX) -> str:
    """Extract only signal-bearing lines from CLI output.

    Falls back to first N chars of raw if no signal lines found
    (prevents completely empty output for unknown command formats).
    """
    lines = raw.splitlines()
    signal_lines = [l for l in lines if _is_signal_line(l)]

    if not signal_lines:
        # Fallback: keep first 200 chars — better than nothing
        return raw[:200].strip()

    result = "\n".join(signal_lines)
    if len(result) > max_chars:
        result = result[:max_chars] + "…"
    return result


def compress_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Truncate chunk text, keep only score+source+text."""
    compressed = []
    for c in chunks:
        text = c.get("text", "")
        compressed.append({
            "s": round(c.get("score", 0.0), 3),
            "src": c.get("source", ""),
            "t": text[:_CHUNK_TEXT_MAX] + ("…" if len(text) > _CHUNK_TEXT_MAX else ""),
        })
    return compressed


# ---------------------------------------------------------------------------
# TOON class — public API
# ---------------------------------------------------------------------------

class TOON:
    """Token Optimization Object Notation — compact inter-agent context format."""

    @staticmethod
    def compress_context(ctx: Any) -> str:
        """Serialize InvestigationContext to compact TOON JSON string."""
        # CLI: extract signal lines only
        compressed_cli: dict[str, str] = {}
        for key, raw in (ctx.cli_outputs or {}).items():
            compressed_cli[key] = extract_cli_signals(raw)

        # RAG chunks: truncate text, drop low-relevance fields
        compressed_chunks = compress_chunks(ctx.runbook_chunks or [])

        # Neighbor list: just device IDs
        nbr_ids = [n.get("device_id", str(n)) for n in (ctx.topology_neighbors or [])]

        doc = {
            _CTX_KEY_MAP["inc_ref"]: ctx.inc_ref,
            _CTX_KEY_MAP["title"]: ctx.title,
            _CTX_KEY_MAP["severity"]: ctx.severity,
            _CTX_KEY_MAP["affected_device"]: ctx.affected_device,
            _CTX_KEY_MAP["affected_protocol"]: ctx.affected_protocol,
            _CTX_KEY_MAP["description"]: ctx.description[:300] if ctx.description else "",
            _CTX_KEY_MAP["runbook_chunks"]: compressed_chunks,
            _CTX_KEY_MAP["cli_outputs"]: compressed_cli,
            _CTX_KEY_MAP["topology_neighbors"]: nbr_ids,
        }
        # Drop None and empty values
        doc = {k: v for k, v in doc.items() if v not in (None, [], {}, "")}
        return json.dumps(doc, separators=(",", ":"))

    @staticmethod
    def compress_analysis(analysis: Any) -> str:
        """Serialize AnalysisResult to compact TOON JSON string."""
        doc = {
            _ANALYSIS_KEY_MAP["root_cause"]: analysis.root_cause,
            _ANALYSIS_KEY_MAP["hypothesis"]: analysis.hypothesis[:600] if analysis.hypothesis else "",
            _ANALYSIS_KEY_MAP["confidence"]: round(analysis.confidence, 3),
            _ANALYSIS_KEY_MAP["evidence"]: analysis.evidence[:5],  # cap at 5 items
            _ANALYSIS_KEY_MAP["affected_components"]: analysis.affected_components,
            _ANALYSIS_KEY_MAP["urgency"]: analysis.urgency,
        }
        doc = {k: v for k, v in doc.items() if v not in (None, [], "")}
        return json.dumps(doc, separators=(",", ":"))

    @staticmethod
    def savings(original: str, compressed: str) -> dict[str, Any]:
        """Calculate token savings between original and TOON-compressed strings.

        Returns dict with original_tokens, compressed_tokens, saved_tokens, saved_pct.
        Token estimate: 1 token ≈ 4 chars (conservative).
        """
        orig_tokens = max(1, len(original) // 4)
        comp_tokens = max(1, len(compressed) // 4)
        saved = orig_tokens - comp_tokens
        pct = round((saved / orig_tokens) * 100, 1)
        return {
            "original_tokens": orig_tokens,
            "compressed_tokens": comp_tokens,
            "saved_tokens": saved,
            "saved_pct": pct,
        }

    @staticmethod
    def log_savings(label: str, original: str, compressed: str, inc_ref: str = "") -> None:
        """Log token savings for observability."""
        s = TOON.savings(original, compressed)
        log.info(
            "toon_compression",
            label=label,
            inc_ref=inc_ref,
            original_tokens=s["original_tokens"],
            compressed_tokens=s["compressed_tokens"],
            saved_tokens=s["saved_tokens"],
            saved_pct=s["saved_pct"],
        )
