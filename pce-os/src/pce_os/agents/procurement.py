"""Procurement agent for quote and approval workflows."""

from __future__ import annotations

from pce_os.agents.base import Agent, AgentInput, AgentOutput
from pce_os.agents.llm import LLMClient, NullLLMClient


class ProcurementAgent(Agent):
    name = "procurement"

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or NullLLMClient()

    def process(self, agent_input: AgentInput) -> AgentOutput:
        output = AgentOutput(confidence=0.74, rationale="Procurement heuristics applied.")
        event = agent_input.event
        payload = event.payload

        if event.event_type == "purchase.requested":
            projected_cost = float(payload.get("projected_cost", 0.0))
            risk_level = str(payload.get("risk_level", "MEDIUM"))
            output.proposed_actions.extend(
                [
                    {
                        "action_type": "os.request_quote",
                        "priority": 2,
                        "metadata": {
                            "projected_cost": projected_cost,
                            "risk_level": risk_level,
                            "source_agent": self.name,
                        },
                    },
                    {
                        "action_type": "os.request_purchase_approval",
                        "priority": 1,
                        "metadata": {
                            "projected_cost": projected_cost,
                            "risk_level": risk_level,
                            "purchase_id": payload.get("purchase_id"),
                            "source_agent": self.name,
                        },
                    },
                ]
            )

        if agent_input.enable_llm:
            completion = self.llm_client.complete(
                f"Procurement rationale and mitigation notes for {event.event_type}",
            )
            if completion:
                output.rationale = completion

        return output
