"""AnalysisAgent — uses the LLM to reason over incident + runbook chunks + CLI output.

Returns a structured AnalysisResult with root cause, hypothesis, confidence, and evidence.
"""

import json
import re
from dataclasses import dataclass

from backend.agents.investigation_agent import InvestigationContext
from backend.agents.llm_client import get_llm_client
from backend.core.logging import get_logger

log = get_logger(__name__)

_SYSTEM_PROMPT = """You are a senior NOC (Network Operations Center) engineer with 15+ years of \
experience diagnosing network incidents across Cisco IOS-XE and Juniper JunOS environments.

Analyze the provided incident using the runbook knowledge and CLI outputs.
Respond ONLY with a valid JSON object — no extra text, no markdown fences:

{
  "root_cause": "concise 1-sentence root cause",
  "hypothesis": "detailed technical explanation referencing CLI evidence",
  "confidence": 0.85,
  "evidence": ["evidence item referencing actual CLI values", "..."],
  "affected_components": ["R1-CORE GigabitEthernet1", "BGP session 10.0.0.2"],
  "urgency": "immediate"
}

urgency values: immediate | high | medium | low
confidence: float 0.0–1.0"""


@dataclass
class AnalysisResult:
    root_cause: str
    hypothesis: str
    confidence: float
    evidence: list[str]
    affected_components: list[str]
    urgency: str


class AnalysisAgent:
    """Sends investigation context to the LLM and extracts structured root cause analysis."""

    system_prompt: str = _SYSTEM_PROMPT

    def run_toon(self, toon_ctx: str, prior_analysis: "AnalysisResult | None" = None) -> "AnalysisResult":
        """Run analysis using a TOON-compressed context string.

        Used by specialist agents (BGP, JunOS) receiving compressed context
        from the Orchestrator instead of the full InvestigationContext.
        Saves 40-60% input tokens compared to run().
        """
        prior_block = ""
        if prior_analysis:
            prior_block = (
                f"\n## Prior Analysis (confidence={prior_analysis.confidence:.0%})\n"
                f"Root cause: {prior_analysis.root_cause}\n"
                f"Refine or confirm this analysis using the TOON context below.\n"
            )

        prompt = (
            f"{prior_block}"
            f"\n## Incident Context (TOON format)\n"
            f"```json\n{toon_ctx}\n```\n"
            f"\nKeys: ref=incident_ref, ttl=title, sev=severity, dev=device, "
            f"proto=protocol, kb=runbook_chunks(s=score,src=source,t=text), "
            f"cli=CLI_outputs, nbr=topology_neighbors\n"
            f"\nAnalyze and respond with the JSON object."
        )

        llm = get_llm_client()
        raw = llm.complete(
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=1024,
        )
        return self._parse(raw)

    def run(self, context: InvestigationContext) -> AnalysisResult:
        prompt = self._build_prompt(context)
        llm = get_llm_client()

        log.info("analysis_llm_call", inc_ref=context.inc_ref, incident_id=context.incident_id)
        raw = llm.complete(
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=1024,
        )

        result = self._parse(raw)
        log.info(
            "analysis_complete",
            inc_ref=context.inc_ref,
            incident_id=context.incident_id,
            root_cause=result.root_cause[:80],
            confidence=result.confidence,
        )
        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_prompt(self, ctx: InvestigationContext) -> str:
        lines: list[str] = [
            "## Incident",
            f"**Title:** {ctx.title}",
            f"**Severity:** {ctx.severity}",
            f"**Description:** {ctx.description}",
        ]
        if ctx.affected_device:
            lines.append(f"**Affected Device:** {ctx.affected_device}")
        if ctx.affected_protocol:
            lines.append(f"**Affected Protocol:** {ctx.affected_protocol}")

        if ctx.runbook_chunks:
            lines.append("\n## Relevant Runbook Knowledge")
            for i, chunk in enumerate(ctx.runbook_chunks[:5], 1):
                score = chunk.get("score", 0.0)
                source = chunk.get("source", "unknown")
                lines.append(f"\n[{i}] **{source}** (relevance: {score:.2f})\n{chunk.get('text', '')}")

        if ctx.cli_outputs:
            lines.append("\n## Device CLI Outputs")
            for cmd_key, output in ctx.cli_outputs.items():
                truncated = output.strip()
                if len(truncated) > 3000:
                    truncated = truncated[:3000] + "\n…[truncated]"
                lines.append(f"\n### {cmd_key}\n```\n{truncated}\n```")

        lines.append("\nAnalyze the incident and respond with the JSON object.")
        return "\n".join(lines)

    def _parse(self, raw: str) -> AnalysisResult:
        text = raw.strip()
        # Strip markdown code fences if present
        match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
        if match:
            text = match.group(1).strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            log.warning("analysis_json_parse_failed", raw_preview=raw[:300])
            # Graceful fallback — treat raw text as hypothesis
            return AnalysisResult(
                root_cause="Unable to parse structured analysis. See hypothesis for details.",
                hypothesis=raw[:1000],
                confidence=0.4,
                evidence=[],
                affected_components=[],
                urgency="medium",
            )

        return AnalysisResult(
            root_cause=data.get("root_cause", "Root cause undetermined."),
            hypothesis=data.get("hypothesis", ""),
            confidence=float(data.get("confidence", 0.5)),
            evidence=data.get("evidence", []),
            affected_components=data.get("affected_components", []),
            urgency=data.get("urgency", "medium"),
        )
