from pce.core.plugins import PluginRegistry
from pce.core.types import ActionPlan, ExecutionResult, PCEEvent


class BoomValuePlugin:
    name = "boom.value"

    def match(self, event: PCEEvent, state: dict[str, object]) -> bool:
        _ = (event, state)
        return True

    def evaluate(self, event: PCEEvent, state: dict[str, object]) -> float:
        _ = (event, state)
        raise RuntimeError("boom")


class PassDecisionPlugin:
    name = "pass.decision"

    def match(self, event: PCEEvent, state: dict[str, object]) -> bool:
        _ = (event, state)
        return True

    def deliberate(
        self,
        event: PCEEvent,
        state: dict[str, object],
        value_score: float,
        cci: float,
    ) -> ActionPlan:
        _ = (event, state, value_score, cci)
        return ActionPlan(action_type="plugin", rationale="ok", priority=1)


def test_registry_fallback_and_priority() -> None:
    event = PCEEvent(event_type="x", source="test", payload={"domain": "general", "tags": []})
    state: dict[str, object] = {}

    registry = PluginRegistry()
    registry.register_value_model(BoomValuePlugin())
    registry.register_decision(PassDecisionPlugin())

    score = registry.evaluate(event, state, fallback=lambda e, o: 0.42)
    assert score == 0.42

    plan = registry.deliberate(
        event,
        state,
        value_score=0.5,
        cci=0.5,
        fallback=lambda _s, _v, _c: ActionPlan(action_type="fallback", rationale="fb", priority=3),
    )
    assert plan.action_type == "plugin"

    adapted = registry.adapt(
        state,
        event,
        ExecutionResult(action_type="x", success=True, observed_impact=1.0),
        fallback=lambda st, _r: dict(st, adapted=True),
    )
    assert adapted["adapted"] is True
