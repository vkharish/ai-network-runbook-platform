"""Tests for the multi-agent pipeline (InvestigationAgent, AnalysisAgent, OrchestratorAgent)."""

from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, patch
import uuid

import pytest

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fake incident fixture
# ---------------------------------------------------------------------------

@dataclass
class FakeIncident:
    id: uuid.UUID = uuid.UUID("12345678-1234-5678-1234-567812345678")
    title: str = "BGP session down on R1-CORE"
    description: str = "R1-CORE BGP peer 10.0.0.2 stuck in Active state"
    severity: str = "P2"
    affected_device: str = "R1-CORE"
    affected_protocol: str = "bgp"
    incident_number: int = 1


# ---------------------------------------------------------------------------
# InvestigationAgent
# ---------------------------------------------------------------------------

def test_detect_vendor_cisco():
    from backend.agents.investigation_agent import InvestigationAgent
    assert InvestigationAgent._detect_vendor("R1-CORE") == "cisco"
    assert InvestigationAgent._detect_vendor("R2-DIST") == "cisco"


def test_detect_vendor_juniper():
    from backend.agents.investigation_agent import InvestigationAgent
    assert InvestigationAgent._detect_vendor("R3-vmx") == "juniper"
    assert InvestigationAgent._detect_vendor("R5-juniper") == "juniper"
    assert InvestigationAgent._detect_vendor("junos-pe1") == "juniper"


def test_detect_vendor_none():
    from backend.agents.investigation_agent import InvestigationAgent
    assert InvestigationAgent._detect_vendor(None) is None


def test_investigation_agent_no_chromadb(monkeypatch):
    """InvestigationAgent should return context even when ChromaDB is unavailable."""
    from backend.agents.investigation_agent import InvestigationAgent

    monkeypatch.setattr(
        "backend.agents.investigation_agent.query_collection",
        lambda *a, **kw: {"documents": [[]], "metadatas": [[]], "distances": [[]]},
    )

    class FakeEngine:
        def embed_one(self, text):
            return [0.0] * 384

    monkeypatch.setattr(
        "backend.agents.investigation_agent.get_embedding_engine",
        lambda: FakeEngine(),
    )

    ctx = InvestigationAgent().run(FakeIncident(), topology_graph=None)
    assert ctx.incident_id == "12345678-1234-5678-1234-567812345678"
    assert ctx.affected_device == "R1-CORE"
    assert isinstance(ctx.runbook_chunks, list)
    assert isinstance(ctx.cli_outputs, dict)


# ---------------------------------------------------------------------------
# AnalysisAgent
# ---------------------------------------------------------------------------

def test_analysis_agent_parses_valid_json(mock_llm):
    from backend.agents.investigation_agent import InvestigationContext
    from backend.agents.analysis_agent import AnalysisAgent

    ctx = InvestigationContext(
        incident_id="test-id",
        inc_ref="INC-0001",
        title="BGP down",
        description="Peer inactive",
        severity="P2",
        affected_device="R1-CORE",
        affected_protocol="bgp",
        runbook_chunks=[],
        cli_outputs={},
    )
    result = AnalysisAgent().run(ctx)
    assert isinstance(result.confidence, float)
    assert 0.0 <= result.confidence <= 1.0
    assert isinstance(result.root_cause, str)
    assert len(result.root_cause) > 0


def test_analysis_agent_graceful_fallback(monkeypatch):
    """AnalysisAgent should not raise when LLM returns unparseable text."""
    from backend.agents.investigation_agent import InvestigationContext
    from backend.agents.analysis_agent import AnalysisAgent
    from backend.agents.llm_client import BaseLLMClient

    class BrokenLLM(BaseLLMClient):
        def complete(self, messages, **kw):
            return "This is not JSON at all ¯\\_(ツ)_/¯"

    monkeypatch.setattr("backend.agents.analysis_agent.get_llm_client", lambda: BrokenLLM())

    ctx = InvestigationContext(
        incident_id="test",
        inc_ref="INC-0000",
        title="Test",
        description="desc",
        severity="P3",
        affected_device=None,
        affected_protocol=None,
        runbook_chunks=[],
        cli_outputs={},
    )
    result = AnalysisAgent().run(ctx)
    assert result.confidence == 0.4   # fallback confidence
    assert "Unable to parse" in result.root_cause


# ---------------------------------------------------------------------------
# OrchestratorAgent — routing logic
# ---------------------------------------------------------------------------

def test_orchestrator_routes_to_bgp_specialist(mock_llm, monkeypatch):
    """BGP incident with confidence >= 0.6 should route to BGPSpecialistAgent."""
    monkeypatch.setattr(
        "backend.agents.investigation_agent.query_collection",
        lambda *a, **kw: {"documents": [[]], "metadatas": [[]], "distances": [[]]},
    )
    monkeypatch.setattr(
        "backend.agents.investigation_agent.get_embedding_engine",
        lambda: MagicMock(embed_one=lambda t: [0.0] * 384),
    )

    from backend.agents.orchestrator_agent import OrchestratorAgent

    incident = FakeIncident()   # affected_protocol="bgp", confidence=0.85 from mock
    report = OrchestratorAgent().run(incident, topology_graph=None)

    assert report is not None
    assert isinstance(report.orchestration, dict)
    agents = report.orchestration.get("agents_invoked", [])
    assert "bgp_specialist" in agents


def test_orchestrator_full_pipeline_completes(mock_llm, monkeypatch):
    """Full pipeline should return a ReportOutput with required fields."""
    monkeypatch.setattr(
        "backend.agents.investigation_agent.query_collection",
        lambda *a, **kw: {"documents": [[]], "metadatas": [[]], "distances": [[]]},
    )
    monkeypatch.setattr(
        "backend.agents.investigation_agent.get_embedding_engine",
        lambda: MagicMock(embed_one=lambda t: [0.0] * 384),
    )

    from backend.agents.orchestrator_agent import OrchestratorAgent

    report = OrchestratorAgent().run(FakeIncident(), topology_graph=None)

    assert report.summary
    assert report.root_cause
    assert isinstance(report.steps, list)
    assert isinstance(report.confidence, float)
    assert "agents_invoked" in report.orchestration
    assert "decisions" in report.orchestration


def test_orchestrator_second_opinion_on_low_confidence(mock_llm, monkeypatch):
    """Low-confidence analysis should trigger SecondOpinionAgent loop."""
    import json

    low_conf_json = json.dumps({
        "root_cause": "Undetermined root cause",
        "hypothesis": "Need more context",
        "confidence": 0.4,
        "evidence": [],
        "affected_components": [],
        "urgency": "medium",
    })

    call_count = {"n": 0}

    from backend.agents.llm_client import BaseLLMClient

    class LowConfLLM(BaseLLMClient):
        def complete(self, messages, **kw):
            call_count["n"] += 1
            from tests.conftest import MOCK_REPORT_JSON
            prompt = " ".join(m.get("content", "") for m in messages)
            if "urgency" in prompt:
                # First analysis: low confidence; subsequent: high confidence
                if call_count["n"] <= 2:
                    return low_conf_json
                return json.dumps({
                    "root_cause": "BGP hold timer expired",
                    "hypothesis": "Timer expired",
                    "confidence": 0.85,
                    "evidence": ["BGP state Active"],
                    "affected_components": ["R1"],
                    "urgency": "high",
                })
            return MOCK_REPORT_JSON

    monkeypatch.setattr("backend.agents.analysis_agent.get_llm_client", lambda: LowConfLLM())
    monkeypatch.setattr("backend.agents.report_agent.get_llm_client", lambda: LowConfLLM())
    fake_embed = MagicMock(embed_one=lambda t: [0.0] * 384)
    monkeypatch.setattr(
        "backend.agents.investigation_agent.query_collection",
        lambda *a, **kw: {"documents": [[]], "metadatas": [[]], "distances": [[]]},
    )
    monkeypatch.setattr("backend.agents.investigation_agent.get_embedding_engine", lambda: fake_embed)
    monkeypatch.setattr(
        "backend.agents.second_opinion_agent.query_collection",
        lambda *a, **kw: {"documents": [[]], "metadatas": [[]], "distances": [[]]},
    )
    monkeypatch.setattr("backend.agents.second_opinion_agent.get_embedding_engine", lambda: fake_embed)

    incident = FakeIncident()
    incident.affected_protocol = "ospf"   # avoid BGP specialist route

    from backend.agents.orchestrator_agent import OrchestratorAgent
    report = OrchestratorAgent().run(incident, topology_graph=None)

    agents = report.orchestration.get("agents_invoked", [])
    assert "second_opinion" in agents
