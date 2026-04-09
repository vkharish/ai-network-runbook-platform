"""ReportAgent — generates the final structured diagnosis report.

Takes the root cause analysis + investigation context and produces
a ReportOutput that gets stored in incident.ai_report (JSONB).
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.agents.analysis_agent import AnalysisResult
from backend.agents.investigation_agent import InvestigationContext
from backend.agents.llm_client import get_llm_client
from backend.core.config import LLMProvider, settings
from backend.core.logging import get_logger

log = get_logger(__name__)

_SYSTEM_PROMPT = """You are a technical writer for a NOC team producing an incident diagnosis report.

Given the root cause analysis, generate actionable remediation steps and a clear executive summary.
Respond ONLY with a valid JSON object — no extra text, no markdown fences:

{
  "summary": "1–2 sentence executive summary for management",
  "steps": [
    "1. Verify BGP peer connectivity: ping 10.0.0.2 source Loopback0",
    "2. Check hold timer: show bgp neighbors 10.0.0.2 | i Hold",
    "3. ..."
  ],
  "commands": ["show bgp summary", "show bgp neighbors", "show interface"],
  "escalation": "If BGP does not re-establish within 10 minutes, escalate to Tier 3 NOC."
}

Steps must be numbered, specific, and reference actual device commands.
Commands must be valid Cisco IOS-XE or Juniper JunOS CLI commands."""


@dataclass
class ReportOutput:
    summary: str
    root_cause: str
    hypothesis: str
    confidence: float
    urgency: str
    steps: list[str]
    commands: list[str]
    citations: list[dict]
    cli_evidence: dict[str, str]
    affected_components: list[str]
    escalation: str
    generated_at: str
    llm_provider: str
    orchestration: dict = field(default_factory=dict)


class ReportAgent:
    """Structures the analysis into the final report stored in incident.ai_report."""

    def run(self, context: InvestigationContext, analysis: AnalysisResult) -> ReportOutput:
        prompt = self._build_prompt(context, analysis)
        llm = get_llm_client()

        log.info("report_llm_call", inc_ref=context.inc_ref, incident_id=context.incident_id)
        raw = llm.complete(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=1024,
        )

        structured = self._parse(raw)

        citations = [
            {
                "source": c.get("source", ""),
                "chunk_index": c.get("chunk_index", 0),
                "score": c.get("score", 0.0),
            }
            for c in context.runbook_chunks
        ]

        provider_label = _llm_label()

        report = ReportOutput(
            summary=structured.get("summary", analysis.root_cause),
            root_cause=analysis.root_cause,
            hypothesis=analysis.hypothesis,
            confidence=analysis.confidence,
            urgency=analysis.urgency,
            steps=structured.get("steps", []),
            commands=structured.get("commands", []),
            citations=citations,
            cli_evidence=context.cli_outputs,
            affected_components=analysis.affected_components,
            escalation=structured.get(
                "escalation",
                "Escalate to Tier 3 NOC if issue is not resolved within 30 minutes.",
            ),
            generated_at=datetime.now(timezone.utc).isoformat(),
            llm_provider=provider_label,
        )

        log.info(
            "report_complete",
            inc_ref=context.inc_ref,
            incident_id=context.incident_id,
            steps=len(report.steps),
            citations=len(report.citations),
        )
        return report

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_prompt(self, ctx: InvestigationContext, analysis: AnalysisResult) -> str:
        evidence_lines = "\n".join(f"- {e}" for e in analysis.evidence) or "- No specific evidence listed."
        components = ", ".join(analysis.affected_components) or "unknown"

        return (
            f"## Incident: {ctx.title}\n"
            f"**Severity:** {ctx.severity} | "
            f"**Device:** {ctx.affected_device or 'unknown'} | "
            f"**Protocol:** {ctx.affected_protocol or 'unknown'}\n\n"
            f"## Root Cause Analysis\n"
            f"**Root Cause:** {analysis.root_cause}\n"
            f"**Hypothesis:** {analysis.hypothesis}\n"
            f"**Confidence:** {analysis.confidence:.0%}\n"
            f"**Urgency:** {analysis.urgency}\n"
            f"**Affected Components:** {components}\n\n"
            f"**Evidence:**\n{evidence_lines}\n\n"
            f"Generate the structured remediation report now."
        )

    def _parse(self, raw: str) -> dict:
        text = raw.strip()
        match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
        if match:
            text = match.group(1).strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            log.warning("report_json_parse_failed", raw_preview=raw[:300])
            return {
                "summary": raw[:400],
                "steps": [],
                "commands": [],
                "escalation": "Manual review required. Automated report generation failed.",
            }


def _llm_label() -> str:
    if settings.llm_provider == LLMProvider.OLLAMA:
        return f"ollama/{settings.ollama_model}"
    return f"{settings.llm_provider.value}/{settings.llm_model}"
