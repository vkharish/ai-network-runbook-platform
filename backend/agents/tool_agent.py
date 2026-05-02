"""ToolCallingAgent — ReAct agent loop for dynamic incident investigation.

Replaces the static CLI file loading of InvestigationAgent with a true
think → act → observe loop where the LLM decides which commands to run.

Loop:
  1. LLM receives incident description + available tools
  2. LLM responds with {"thought": "...", "action": "...", "args": {...}}
  3. System executes the tool and appends result to conversation
  4. Repeat until LLM calls "conclude" OR MAX_STEPS reached

Tools available to the LLM:
  run_cli_command  — SSH to device (or simulator) and run a show command
  query_rag        — Search runbook knowledge base for relevant procedures
  conclude         — Exit loop with root cause + confidence

Returns InvestigationContext — same interface as InvestigationAgent.
"""

from __future__ import annotations

import json
import re
from typing import Any

from backend.agents.investigation_agent import InvestigationContext
from backend.agents.llm_client import get_llm_client
from backend.automation.device_gateway import DeviceGateway
from backend.core.logging import get_logger

log = get_logger(__name__)

MAX_STEPS = 8  # Safety cap on tool calls per investigation

_SYSTEM_PROMPT = """You are a senior NOC engineer diagnosing a network incident.
Use the available tools to gather evidence, then conclude with your root cause analysis.

Respond ONLY with a single valid JSON object — no markdown fences, no extra text:
{"thought": "<your reasoning>", "action": "<tool_name>", "args": {<tool arguments>}}

Available tools:

  run_cli_command
    args: {"device": "<hostname>", "command": "<IOS-XR or JunOS show command>"}
    Use for: checking BGP state, interface status, routing table, logs, OSPF neighbors

  query_rag
    args: {"query": "<search terms>"}
    Use for: finding relevant troubleshooting steps and runbook procedures

  conclude
    args: {
      "root_cause": "<concise root cause statement>",
      "confidence": <0.0 to 1.0>,
      "hypothesis": "<detailed explanation of what happened and why>",
      "affected_components": ["<component1>", "<component2>"]
    }
    Use when: you have sufficient evidence to identify the root cause

Rules:
- Always start with a read-only show command to understand current state
- Query RAG early to find relevant troubleshooting procedures
- Never repeat the same device+command pair twice
- Conclude when confidence >= 0.7 or after 6 tool calls
- If evidence is limited, conclude with lower confidence rather than looping
- Only use commands safe for production (show/display commands, no writes)
"""


class ToolCallingAgent:
    """
    ReAct loop agent. Drop-in replacement for InvestigationAgent.

    Each call to run() creates a fresh conversation and steps through the
    think→act→observe loop until the LLM concludes or MAX_STEPS is hit.
    """

    def __init__(self) -> None:
        self._gateway = DeviceGateway()

    def run(self, incident: Any, topology_graph: dict[str, Any] | None = None) -> InvestigationContext:
        inc_ref = f"INC-{str(incident.incident_number or 0).zfill(4)}"
        incident_id = str(incident.id)

        log.info("tool_agent_start", inc_ref=inc_ref, incident_id=incident_id)

        messages: list[dict] = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": self._build_incident_prompt(incident)},
        ]

        # Accumulated evidence
        cli_outputs: dict[str, str] = {}
        runbook_chunks: list[dict] = []
        seen_commands: set[tuple[str, str]] = set()

        # Final conclusion (populated when LLM calls conclude)
        conclusion: dict = {}

        llm = get_llm_client()

        for step in range(MAX_STEPS):
            log.info("tool_agent_step", inc_ref=inc_ref, step=step + 1, max=MAX_STEPS)

            raw = llm.complete(messages=messages, temperature=0.1, max_tokens=512)

            parsed = self._parse_response(raw)
            if not parsed:
                log.warning("tool_agent_bad_json", inc_ref=inc_ref, step=step, raw=raw[:200])
                # Force conclusion with what we have
                break

            action = parsed.get("action", "")
            args = parsed.get("args", {})
            thought = parsed.get("thought", "")

            log.info("tool_agent_action", inc_ref=inc_ref, step=step + 1, action=action, thought=thought[:80])

            # Append LLM turn to conversation
            messages.append({"role": "assistant", "content": raw})

            # Nudge toward conclusion on penultimate step
            if step == MAX_STEPS - 2 and action != "conclude":
                messages.append({
                    "role": "user",
                    "content": "[System] This is your last tool call. After receiving the result, you MUST call conclude with your findings."
                })

            if action == "conclude":
                conclusion = args
                log.info(
                    "tool_agent_concluded",
                    inc_ref=inc_ref,
                    steps_used=step + 1,
                    confidence=args.get("confidence", 0),
                )
                break

            elif action == "run_cli_command":
                result = self._tool_run_cli(args, seen_commands, cli_outputs, inc_ref)
                messages.append({"role": "user", "content": f"[Tool result - run_cli_command]\n{result}"})

            elif action == "query_rag":
                result = self._tool_query_rag(args, runbook_chunks, inc_ref)
                messages.append({"role": "user", "content": f"[Tool result - query_rag]\n{result}"})

            else:
                messages.append({"role": "user", "content": f"[Error] Unknown action '{action}'. Use: run_cli_command, query_rag, or conclude."})

        # If loop ended without a conclusion, extract best effort from conversation
        if not conclusion:
            conclusion = self._fallback_conclusion(cli_outputs)

        return InvestigationContext(
            incident_id=incident_id,
            inc_ref=inc_ref,
            title=incident.title,
            description=incident.description or "",
            severity=incident.severity or "P3",
            affected_device=incident.affected_device,
            affected_protocol=incident.affected_protocol,
            runbook_chunks=runbook_chunks,
            cli_outputs=cli_outputs,
            citations=list({c.get("source", "") for c in runbook_chunks if c.get("source")}),
            topology_neighbors=[],
        )

    # ------------------------------------------------------------------
    # Tool implementations
    # ------------------------------------------------------------------

    def _tool_run_cli(
        self,
        args: dict,
        seen: set[tuple[str, str]],
        cli_outputs: dict[str, str],
        inc_ref: str,
    ) -> str:
        device = args.get("device", "").strip()
        command = args.get("command", "").strip()

        if not device or not command:
            return "[Error] 'device' and 'command' are required."

        key = (device.lower(), command.lower())
        if key in seen:
            return f"[Skipped] Already ran '{command}' on {device}. Use a different command."
        seen.add(key)

        try:
            output = self._gateway.run_command(device, command)
            # Store with a sanitised key
            store_key = f"{device}_{command[:40].replace(' ', '_').replace('|', '')}"
            cli_outputs[store_key] = output
            log.info("tool_agent_cli_ok", inc_ref=inc_ref, device=device, command=command[:60])
            return output[:2000]  # Cap individual result to 2k chars
        except Exception as exc:
            log.warning("tool_agent_cli_failed", inc_ref=inc_ref, device=device, command=command, error=str(exc))
            return f"[Error] Command failed: {exc}"

    def _tool_query_rag(
        self,
        args: dict,
        runbook_chunks: list[dict],
        inc_ref: str,
    ) -> str:
        query = args.get("query", "").strip()
        if not query:
            return "[Error] 'query' is required."

        try:
            from backend.rag.embedding_engine import get_embedding_engine
            from backend.rag.vector_store import query_collection

            engine = get_embedding_engine()
            raw_emb = engine.embed(query)
            # embed() may return [[floats]] or [[[floats]]] depending on provider — unwrap to [floats]
            while isinstance(raw_emb, list) and raw_emb and isinstance(raw_emb[0], list):
                raw_emb = raw_emb[0]
            results = query_collection(
                query_embedding=raw_emb,
                top_k=4,
            )

            new_chunks = [
                c for c in results
                if c.get("score", 0) >= 0.6 and c not in runbook_chunks
            ]
            runbook_chunks.extend(new_chunks)

            if not new_chunks:
                return "[No relevant runbook content found for this query.]"

            lines = []
            for c in new_chunks:
                lines.append(f"[Source: {c.get('source','?')} | Score: {c.get('score',0):.2f}]")
                lines.append(c.get("text", "")[:400])
                lines.append("")
            log.info("tool_agent_rag_ok", inc_ref=inc_ref, query=query[:60], chunks=len(new_chunks))
            return "\n".join(lines)
        except Exception as exc:
            log.warning("tool_agent_rag_failed", inc_ref=inc_ref, query=query, error=str(exc))
            return f"[Error] RAG query failed: {exc}"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_incident_prompt(incident: Any) -> str:
        return (
            f"## Incident to Diagnose\n"
            f"**Title:** {incident.title}\n"
            f"**Description:** {incident.description or 'No description provided.'}\n"
            f"**Severity:** {incident.severity or 'unknown'}\n"
            f"**Affected Device:** {incident.affected_device or 'unknown'}\n"
            f"**Affected Protocol:** {incident.affected_protocol or 'unknown'}\n\n"
            f"Begin investigation. Start with a show command to check current device state."
        )

    @staticmethod
    def _parse_response(raw: str) -> dict | None:
        text = raw.strip()
        # Strip markdown code fences if present
        match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
        if match:
            text = match.group(1).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to extract JSON object from mixed text
            match = re.search(r"\{[\s\S]+\}", text)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
        return None

    @staticmethod
    def _fallback_conclusion(cli_outputs: dict) -> dict:
        """Best-effort conclusion when loop exits without LLM concluding."""
        return {
            "root_cause": "Investigation incomplete — insufficient evidence collected.",
            "confidence": 0.3,
            "hypothesis": f"Gathered {len(cli_outputs)} CLI outputs but could not determine root cause. Manual review required.",
            "affected_components": [],
        }
