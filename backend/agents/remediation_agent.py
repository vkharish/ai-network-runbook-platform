"""RemediationAgent — proposes specific CLI remediation commands after diagnosis.

The agent reads the ReportOutput and produces a set of concrete, device-targeted
commands that a NOC engineer can review and approve before execution.

Each proposed step has:
  - device: which device to run it on
  - command: the exact CLI command
  - rationale: why this command fixes the issue
  - risk_level: low | medium | high
  - expected_outcome: what should happen after execution

Steps are stored in RemediationPlan (JSONB) and remain PENDING_APPROVAL
until an engineer explicitly approves each one.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.agents.analysis_agent import AnalysisResult
from backend.agents.investigation_agent import InvestigationContext
from backend.agents.llm_client import get_llm_client
from backend.agents.report_agent import ReportOutput
from backend.core.logging import get_logger

log = get_logger(__name__)

_SYSTEM_PROMPT = """You are a senior NOC engineer proposing safe remediation commands for a network incident.

Based on the diagnosis report, propose specific CLI commands to resolve the issue.
Each command must be:
- Read-only diagnostic OR a safe, reversible corrective action
- Targeted to the specific device mentioned
- Accompanied by a clear rationale and expected outcome

Respond ONLY with a valid JSON object — no markdown fences, no extra text:

{
  "steps": [
    {
      "step_number": 1,
      "device": "R1-CORE",
      "command": "show bgp neighbors 10.0.0.2",
      "rationale": "Verify current BGP session state and hold timer values",
      "risk_level": "low",
      "expected_outcome": "Confirms session is in Active/Idle state with expired hold timer"
    },
    {
      "step_number": 2,
      "device": "R1-CORE",
      "command": "clear ip bgp 10.0.0.2 soft",
      "rationale": "Soft reset BGP session to refresh route advertisements without dropping peering",
      "risk_level": "low",
      "expected_outcome": "BGP session refreshes, routes re-advertised within 30 seconds"
    }
  ],
  "notes": "If soft reset does not re-establish session within 2 minutes, proceed to hard reset."
}

Risk level guidelines:
  low    — read-only commands, soft resets, no traffic impact
  medium — may briefly disrupt traffic (interface bounce, hard BGP reset)
  high   — could cause outage (link shutdown, routing table clear)

Limit to 5 steps maximum. Prefer low-risk steps first."""


@dataclass
class RemediationStep:
    step_number: int
    device: str
    command: str
    rationale: str
    risk_level: str          # low | medium | high
    expected_outcome: str
    approval_status: str = "pending"   # pending | approved | rejected
    approved_by: str | None = None
    approved_at: str | None = None
    rejection_reason: str | None = None
    execution_status: str | None = None   # None | executing | completed | failed
    execution_output: str | None = None
    executed_at: str | None = None


@dataclass
class RemediationProposal:
    incident_id: str
    inc_ref: str
    steps: list[RemediationStep]
    notes: str
    proposed_at: str
    llm_provider: str


class RemediationAgent:
    """Proposes human-approved remediation commands for an incident."""

    def run(
        self,
        context: InvestigationContext,
        analysis: AnalysisResult,
        report: ReportOutput,
    ) -> RemediationProposal:
        prompt = self._build_prompt(context, analysis, report)
        llm = get_llm_client()

        log.info("remediation_llm_call", inc_ref=context.inc_ref, incident_id=context.incident_id)
        raw = llm.complete(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=1024,
        )

        parsed = self._parse(raw)
        steps = [RemediationStep(**s) for s in parsed.get("steps", [])]

        log.info(
            "remediation_proposal_complete",
            inc_ref=context.inc_ref,
            incident_id=context.incident_id,
            steps=len(steps),
        )

        from backend.core.config import settings, LLMProvider
        provider = (
            f"ollama/{settings.ollama_model}"
            if settings.llm_provider == LLMProvider.OLLAMA
            else f"{settings.llm_provider.value}/{settings.llm_model}"
        )

        return RemediationProposal(
            incident_id=context.incident_id,
            inc_ref=context.inc_ref,
            steps=steps,
            notes=parsed.get("notes", ""),
            proposed_at=datetime.now(timezone.utc).isoformat(),
            llm_provider=provider,
        )

    def _build_prompt(
        self,
        ctx: InvestigationContext,
        analysis: AnalysisResult,
        report: ReportOutput,
    ) -> str:
        steps_text = "\n".join(f"  {s}" for s in report.steps) or "  No steps generated."
        return (
            f"## Incident: {ctx.title}\n"
            f"**Severity:** {ctx.severity} | "
            f"**Device:** {ctx.affected_device or 'unknown'} | "
            f"**Protocol:** {ctx.affected_protocol or 'unknown'}\n\n"
            f"## Diagnosis\n"
            f"**Root Cause:** {analysis.root_cause}\n"
            f"**Confidence:** {analysis.confidence:.0%}\n"
            f"**Affected Components:** {', '.join(analysis.affected_components)}\n\n"
            f"## Recommended Steps (from report)\n{steps_text}\n\n"
            f"Propose specific CLI commands to implement these steps on {ctx.affected_device or 'the affected device'}."
        )

    def _parse(self, raw: str) -> dict:
        text = raw.strip()
        match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
        if match:
            text = match.group(1).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            log.warning("remediation_json_parse_failed", raw_preview=raw[:300])
            return {"steps": [], "notes": "Automated remediation proposal failed — manual review required."}
