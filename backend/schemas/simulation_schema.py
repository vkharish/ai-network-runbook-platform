from typing import Any
from pydantic import BaseModel, Field


class CommandRequest(BaseModel):
    device: str = Field(..., description="Device ID or hostname, e.g. 'r1' or 'R1-CORE'")
    command: str = Field(..., description="CLI command to execute, e.g. 'show bgp summary'")
    failure_scenario: str | None = Field(None, description="Named failure scenario to apply")


class CommandResponse(BaseModel):
    output: str
    device: str
    command: str
    simulated: bool
    success: bool
    allowed: bool
    failure_applied: bool = False


class FailureSimulationRequest(BaseModel):
    scenario_name: str = Field(..., description="Named scenario from topology, e.g. 'bgp_peer_down'")


class FailureSimulationResponse(BaseModel):
    failure_report: dict[str, Any]
    impact_analysis: dict[str, Any]
    available_scenarios: list[str]
    post_failure_graph: dict[str, Any]
