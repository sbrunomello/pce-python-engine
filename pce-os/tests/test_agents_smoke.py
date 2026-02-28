from pce.core.types import PCEEvent
from pce_os.agents import EngineeringAgent, FinanceAgent, NullLLMClient, ProcurementAgent, TestsAgent
from pce_os.agents.base import AgentInput


def test_agents_smoke_outputs_shape() -> None:
    event = PCEEvent(
        event_type="purchase.requested",
        source="test",
        payload={"domain": "os.robotics", "projected_cost": 120.0, "risk_level": "MEDIUM"},
    )
    twin = {"budget_remaining": 100.0, "dependency_graph": {"edges": {"a": ["b"], "b": []}}}
    agents = [
        EngineeringAgent(NullLLMClient()),
        ProcurementAgent(NullLLMClient()),
        FinanceAgent(NullLLMClient()),
        TestsAgent(NullLLMClient()),
    ]

    for agent in agents:
        output = agent.process(
            AgentInput(
                event=event,
                twin_snapshot=twin,
                incoming_messages=[],
                correlation_id="corr-1",
                decision_id="dec-1",
            )
        )
        assert isinstance(output.proposed_actions, list)
        assert isinstance(output.messages, list)
        assert isinstance(output.risk_flags, list)
        assert isinstance(output.questions, list)
        assert isinstance(output.confidence, float)
        assert isinstance(output.rationale, str)
