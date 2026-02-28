"""Finance agent for budget guardrails and risk signaling."""

from __future__ import annotations

from pce_os.agents.base import Agent, AgentInput, AgentMessage, AgentOutput
from pce_os.agents.llm import LLMClient, NullLLMClient


class FinanceAgent(Agent):
    name = "finance"

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or NullLLMClient()

    def process(self, agent_input: AgentInput) -> AgentOutput:
        output = AgentOutput(confidence=0.8, rationale="Finance heuristics applied.")
        event = agent_input.event
        payload = event.payload

        if event.event_type in {"budget.updated", "purchase.requested"}:
            budget_remaining = float(
                payload.get("budget_remaining", agent_input.twin_snapshot.get("budget_remaining", 0.0))
            )
            projected_cost = float(payload.get("projected_cost", 0.0))
            if projected_cost > budget_remaining:
                output.risk_flags.append("insufficient_budget")
                output.proposed_actions.append(
                    {
                        "action_type": "os.update_project_plan",
                        "priority": 1,
                        "metadata": {
                            "reason": "budget_gap",
                            "budget_remaining": budget_remaining,
                            "projected_cost": projected_cost,
                            "source_agent": self.name,
                        },
                    }
                )
                output.messages.append(
                    AgentMessage(
                        from_agent=self.name,
                        to_agent="engineering",
                        kind="plan.adjustment.requested",
                        content={"budget_gap": projected_cost - budget_remaining},
                    )
                )

        if agent_input.enable_llm:
            completion = self.llm_client.complete(f"Finance rationale for {event.event_type}")
            if completion:
                output.rationale = completion

        return output
