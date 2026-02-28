"""Testing agent for validation scheduling and failure follow-up."""

from __future__ import annotations

from pce_os.agents.base import Agent, AgentInput, AgentOutput
from pce_os.agents.llm import LLMClient, NullLLMClient


class TestsAgent(Agent):
    __test__ = False
    name = "tests"

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or NullLLMClient()

    def process(self, agent_input: AgentInput) -> AgentOutput:
        output = AgentOutput(confidence=0.76, rationale="Test heuristics applied.")
        event = agent_input.event

        if event.event_type in {"purchase.completed", "part.received"}:
            output.proposed_actions.append(
                {
                    "action_type": "os.schedule_test",
                    "priority": 1,
                    "metadata": {
                        "purchase_id": event.payload.get("purchase_id"),
                        "source_agent": self.name,
                    },
                }
            )

        if event.event_type == "test.result.recorded" and not bool(event.payload.get("passed", False)):
            output.risk_flags.append("test_failure_detected")
            output.proposed_actions.append(
                {
                    "action_type": "os.update_project_plan",
                    "priority": 1,
                    "metadata": {"reason": "test_failure", "source_agent": self.name},
                }
            )

        if agent_input.enable_llm:
            completion = self.llm_client.complete(f"Testing rationale for {event.event_type}")
            if completion:
                output.rationale = completion

        return output
