"""OrchestratorAgent — state-machine orchestrator for true multi-agent diagnosis.

Replaces the hardcoded Investigation→Analysis→Report pipeline in incident_service.py
with dynamic routing that dispatches to specialist agents based on incident attributes
and analysis confidence.

Routing table (evaluated after each AnalysisAgent run, in priority order):
  1. confidence < 0.6  AND  iteration < 2   → SecondOpinionAgent  (re-investigate)
  2. affected_protocol == bgp               → BGPSpecialistAgent   (once per pipeline)
  3. affected_device is Juniper             → JunosSpecialistAgent (once per pipeline)
  4. default                                → ReportAgent          → done

State is tracked in AgentState, which is carried through each step and stored in
the final report's `orchestration` field for full auditability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import time

from backend.agents.analysis_agent import AnalysisAgent, AnalysisResult
from backend.agents.investigation_agent import InvestigationAgent, InvestigationContext
from backend.agents.report_agent import ReportAgent, ReportOutput
from backend.core.logging import get_logger

if TYPE_CHECKING:
    pass

log = get_logger(__name__)

# Safety cap on the diagnosis loop
MAX_ITERATIONS = 3

# ---------------------------------------------------------------------------
# Prometheus metrics (registered once at import time)
# ---------------------------------------------------------------------------
try:
    from prometheus_client import Counter, Gauge, Histogram

    _DIAGNOSIS_DURATION = Histogram(
        "diagnosis_duration_seconds",
        "End-to-end diagnosis pipeline latency",
        ["route_taken"],
    )
    _AGENT_CONFIDENCE = Gauge(
        "agent_confidence_score",
        "Final confidence score produced by the last analysis agent",
    )
    _DIAGNOSIS_TOTAL = Counter(
        "diagnosis_total",
        "Total diagnosis pipeline runs",
        ["outcome"],          # success | failure
    )
    _ROUTE_COUNTER = Counter(
        "orchestrator_route_total",
        "Routing decisions made by the orchestrator",
        ["route"],
    )
    _PROMETHEUS_AVAILABLE = True
except Exception:  # pragma: no cover
    _PROMETHEUS_AVAILABLE = False

# Device-name substrings that indicate a Juniper platform
_JUNIPER_INDICATORS = {"juniper", "junos", "vmx", "r3", "r5"}


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


@dataclass
class AgentState:
    """Carries all mutable state through the orchestration loop."""

    incident: Any
    topology_graph: dict[str, Any] | None

    context: InvestigationContext | None = None
    analysis: AnalysisResult | None = None
    report: ReportOutput | None = None

    # Current node in the state machine
    route: str = "investigate"

    # How many (re-)investigation passes have been completed
    iteration: int = 0

    # Human-readable audit trail of every routing decision
    decisions: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class OrchestratorAgent:
    """
    Dynamic multi-agent orchestrator.

    Each call to `run()` creates a fresh AgentState and steps through the
    state machine until route == "done".  Routing decisions are recorded in
    `state.decisions` and embedded in the final report's `orchestration` field.
    """

    def run(
        self,
        incident: Any,
        topology_graph: dict[str, Any] | None = None,
    ) -> ReportOutput:
        state = AgentState(incident=incident, topology_graph=topology_graph)
        t_start = time.perf_counter()

        try:
            while state.route != "done":
                log.info(
                    "orchestrator_step",
                    incident_id=str(incident.id),
                    route=state.route,
                    iteration=state.iteration,
                )

                if _PROMETHEUS_AVAILABLE:
                    _ROUTE_COUNTER.labels(route=state.route).inc()

                if state.route == "investigate":
                    state = self._step_investigate(state)
                elif state.route == "analyze":
                    state = self._step_analyze(state)
                elif state.route == "bgp_specialist":
                    state = self._step_bgp_specialist(state)
                elif state.route == "junos_specialist":
                    state = self._step_junos_specialist(state)
                elif state.route == "second_opinion":
                    state = self._step_second_opinion(state)
                elif state.route == "report":
                    state = self._step_report(state)
                else:
                    log.error("orchestrator_unknown_route", route=state.route)
                    state.route = "report"

            assert state.report is not None, "Orchestrator exited without producing a report"

            elapsed = time.perf_counter() - t_start
            final_route = next(
                (d for d in reversed(state.decisions) if any(
                    r in d for r in ["bgp_specialist", "junos_specialist", "second_opinion"]
                )),
                "standard",
            )
            if _PROMETHEUS_AVAILABLE:
                _DIAGNOSIS_DURATION.labels(route_taken=final_route).observe(elapsed)
                _AGENT_CONFIDENCE.set(state.report.confidence)
                _DIAGNOSIS_TOTAL.labels(outcome="success").inc()

            log.info(
                "orchestrator_complete",
                incident_id=str(incident.id),
                elapsed_s=round(elapsed, 2),
                confidence=state.report.confidence,
                agents=state.report.orchestration.get("agents_invoked", []),
            )
            return state.report

        except Exception:
            if _PROMETHEUS_AVAILABLE:
                _DIAGNOSIS_TOTAL.labels(outcome="failure").inc()
            raise

    # ------------------------------------------------------------------
    # Step handlers
    # ------------------------------------------------------------------

    def _step_investigate(self, state: AgentState) -> AgentState:
        state.context = InvestigationAgent().run(
            state.incident, topology_graph=state.topology_graph
        )
        state.decisions.append(
            f"iter{state.iteration}:investigate"
            f" chunks={len(state.context.runbook_chunks)}"
            f" cli_files={len(state.context.cli_outputs)}"
        )
        state.route = "analyze"
        return state

    def _step_analyze(self, state: AgentState) -> AgentState:
        assert state.context is not None
        state.analysis = AnalysisAgent().run(state.context)
        state.decisions.append(
            f"iter{state.iteration}:analyze"
            f" confidence={state.analysis.confidence:.2f}"
            f" urgency={state.analysis.urgency}"
        )
        state.route = self._route_after_analysis(state)
        return state

    def _step_bgp_specialist(self, state: AgentState) -> AgentState:
        from backend.agents.bgp_specialist_agent import BGPSpecialistAgent

        assert state.context is not None
        state.analysis = BGPSpecialistAgent().run(state.context)
        state.decisions.append(
            f"iter{state.iteration}:bgp_specialist"
            f" confidence={state.analysis.confidence:.2f}"
        )
        state.route = "report"
        return state

    def _step_junos_specialist(self, state: AgentState) -> AgentState:
        from backend.agents.junos_specialist_agent import JunosSpecialistAgent

        assert state.context is not None
        state.analysis = JunosSpecialistAgent().run(state.context)
        state.decisions.append(
            f"iter{state.iteration}:junos_specialist"
            f" confidence={state.analysis.confidence:.2f}"
        )
        state.route = "report"
        return state

    def _step_second_opinion(self, state: AgentState) -> AgentState:
        from backend.agents.second_opinion_agent import SecondOpinionAgent

        assert state.context is not None
        assert state.analysis is not None
        state.context = SecondOpinionAgent().run(state.context, state.analysis)
        state.iteration += 1
        state.decisions.append(
            f"iter{state.iteration}:second_opinion"
            f" total_chunks={len(state.context.runbook_chunks)}"
        )
        state.route = "analyze"
        return state

    def _step_report(self, state: AgentState) -> AgentState:
        assert state.context is not None
        assert state.analysis is not None
        report = ReportAgent().run(state.context, state.analysis)
        report.orchestration = {
            "decisions": state.decisions,
            "total_iterations": state.iteration,
            "agents_invoked": self._agents_invoked(state.decisions),
        }
        state.report = report
        state.decisions.append("report_generated")
        state.route = "done"
        return state

    # ------------------------------------------------------------------
    # Routing logic
    # ------------------------------------------------------------------

    def _route_after_analysis(self, state: AgentState) -> str:
        """Determine next route after a base AnalysisAgent pass."""
        analysis = state.analysis
        assert analysis is not None

        incident = state.incident
        protocol = (incident.affected_protocol or "").lower()
        device = (incident.affected_device or "").lower()

        already = set(state.decisions)

        # Priority 1: Low confidence — re-investigate with refined queries
        if analysis.confidence < 0.6 and state.iteration < 2:
            log.info(
                "orchestrator_routing_second_opinion",
                confidence=analysis.confidence,
                iteration=state.iteration,
                incident_id=str(incident.id),
            )
            return "second_opinion"

        # Priority 2: BGP protocol — run BGP specialist (only once)
        if "bgp" in protocol and not any("bgp_specialist" in d for d in already):
            log.info(
                "orchestrator_routing_bgp_specialist",
                protocol=protocol,
                incident_id=str(incident.id),
            )
            return "bgp_specialist"

        # Priority 3: Juniper device — run JunOS specialist (only once)
        if any(ind in device for ind in _JUNIPER_INDICATORS) and not any(
            "junos_specialist" in d for d in already
        ):
            log.info(
                "orchestrator_routing_junos_specialist",
                device=device,
                incident_id=str(incident.id),
            )
            return "junos_specialist"

        return "report"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _agents_invoked(decisions: list[str]) -> list[str]:
        """Extract unique agent names from the decision log."""
        labels = ["investigate", "analyze", "bgp_specialist", "junos_specialist", "second_opinion", "report"]
        return [label for label in labels if any(label in d for d in decisions)]
