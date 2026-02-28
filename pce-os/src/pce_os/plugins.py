"""PCE-OS domain plugins for robotics orchestration."""

from __future__ import annotations

from pce.core.plugins import AdaptationPlugin, DecisionPlugin, ValueModelPlugin
from pce.core.types import ActionPlan, ExecutionResult, PCEEvent

from pce_os.models import RobotProjectState


class OSRoboticsValueModelPlugin(ValueModelPlugin):
    """Budget-first value model with risk and project-phase adjustments."""

    name = "os.robotics.value"

    def match(self, event: PCEEvent, state: dict[str, object]) -> bool:
        _ = state
        return str(event.payload.get("domain")) == "os.robotics"

    def evaluate(self, event: PCEEvent, state: dict[str, object]) -> float:
        _ = event
        twin = self._twin(state)
        budget_total = float(twin.budget_total or 1.0)
        budget_remaining = float(twin.budget_remaining)
        budget_score = max(0.0, min(1.0, budget_remaining / budget_total))

        risk_penalty = {"LOW": 0.0, "MEDIUM": 0.15, "HIGH": 0.35}.get(twin.risk_level, 0.1)
        phase_weights = {
            "planning": 0.1,
            "procurement": 0.05,
            "integration": 0.0,
            "testing": 0.05,
        }
        phase_bonus = phase_weights.get(twin.phase, 0.0)
        return max(0.0, min(1.0, 0.65 * budget_score + phase_bonus - risk_penalty + 0.25))

    @staticmethod
    def _twin(state: dict[str, object]) -> RobotProjectState:
        os_state = state.get("pce_os")
        if isinstance(os_state, dict) and isinstance(os_state.get("robotics_twin"), dict):
            return RobotProjectState.model_validate(os_state["robotics_twin"])
        return RobotProjectState()


class OSRoboticsDecisionPlugin(DecisionPlugin):
    """Domain workflow planner for PCE-OS robotics lifecycle."""

    name = "os.robotics.decision"

    def match(self, event: PCEEvent, state: dict[str, object]) -> bool:
        _ = state
        return str(event.payload.get("domain")) == "os.robotics"

    def deliberate(
        self,
        event: PCEEvent,
        state: dict[str, object],
        value_score: float,
        cci: float,
    ) -> ActionPlan:
        twin_state = self._twin(state)
        projected_cost = self._projected_cost(event, twin_state)
        projected_risk = str(event.payload.get("risk_level", twin_state.risk_level))

        explain = {
            "value_dimensions": {
                "value_score": value_score,
                "cci": cci,
                "budget_remaining": twin_state.budget_remaining,
            },
            "risk_level": twin_state.risk_level,
            "budget_snapshot": {
                "total": twin_state.budget_total,
                "remaining": twin_state.budget_remaining,
            },
            "event_snapshot": {
                "event_type": event.event_type,
                "payload": event.payload,
            },
            "twin_snapshot": twin_state.model_dump(mode="json"),
            "gate_required": event.event_type in {"purchase.requested"},
        }

        if event.event_type == "project.goal.defined":
            return ActionPlan(
                action_type="os.generate_bom",
                rationale="Projeto definido; gerar BOM inicial e baseline de custo/risco.",
                priority=2,
                metadata={
                    "projected_cost": projected_cost,
                    "risk_level": twin_state.risk_level,
                    "explain": explain,
                },
            )
        if event.event_type == "part.candidate.added":
            return ActionPlan(
                action_type="os.update_project_plan",
                rationale="Componente candidato adicionado; recalcular projeções.",
                priority=3,
                metadata={
                    "projected_cost": projected_cost,
                    "risk_level": twin_state.risk_level,
                    "explain": explain,
                },
            )
        if event.event_type == "purchase.requested":
            return ActionPlan(
                action_type="os.request_purchase_approval",
                rationale="Compra solicitada; aguardando gate humano obrigatório.",
                priority=1,
                metadata={
                    "projected_cost": projected_cost,
                    "risk_level": projected_risk,
                    "purchase_id": event.payload.get("purchase_id"),
                    "explain": explain,
                },
            )
        if event.event_type == "purchase.completed":
            return ActionPlan(
                action_type="os.record_purchase",
                rationale="Compra concluída; registrar execução e atualizar saldo.",
                priority=1,
                metadata={
                    "projected_cost": projected_cost,
                    "risk_level": twin_state.risk_level,
                    "explain": explain,
                },
            )
        if event.event_type == "test.result.recorded":
            return ActionPlan(
                action_type="os.update_project_plan",
                rationale="Resultado de teste recebido; atualizar risco e custo projetado.",
                priority=2,
                metadata={
                    "projected_cost": projected_cost,
                    "risk_level": twin_state.risk_level,
                    "explain": explain,
                },
            )

        return ActionPlan(
            action_type="os.update_project_plan",
            rationale="Evento OS processado com atualização incremental do plano.",
            priority=4,
            metadata={
                "projected_cost": projected_cost,
                "risk_level": twin_state.risk_level,
                "explain": explain,
            },
        )

    @staticmethod
    def _twin(state: dict[str, object]) -> RobotProjectState:
        os_state = state.get("pce_os")
        if isinstance(os_state, dict) and isinstance(os_state.get("robotics_twin"), dict):
            return RobotProjectState.model_validate(os_state["robotics_twin"])
        return RobotProjectState()

    @staticmethod
    def _projected_cost(event: PCEEvent, twin: RobotProjectState) -> float:
        if "projected_cost" in event.payload:
            return float(event.payload.get("projected_cost", 0.0))
        return float(twin.cost_projection.projected_total_cost)


class OSRoboticsAdaptationPlugin(AdaptationPlugin):
    """Feedback adaptation with bounded changes on risk/cost projections."""

    name = "os.robotics.adaptation"

    def match(self, event: PCEEvent, state: dict[str, object], result: ExecutionResult) -> bool:
        _ = (state, result)
        return str(event.payload.get("domain")) == "os.robotics"

    def adapt(
        self,
        state: dict[str, object],
        event: PCEEvent,
        result: ExecutionResult,
    ) -> dict[str, object]:
        _ = result
        os_state = state.get("pce_os")
        if not isinstance(os_state, dict):
            os_state = {}

        twin_payload = os_state.get("robotics_twin")
        if isinstance(twin_payload, dict):
            twin = RobotProjectState.model_validate(twin_payload)
        else:
            twin = RobotProjectState()

        if event.event_type == "test.result.recorded":
            outcome = bool(event.payload.get("passed", False))
            risk_shift = -0.05 if outcome else 0.08
            cost_shift = -0.02 if outcome else 0.04
            current_conf = twin.cost_projection.confidence
            next_conf = max(0.1, min(0.95, current_conf + risk_shift))
            next_cost = max(0.0, twin.cost_projection.projected_total_cost * (1 + cost_shift))
            twin.cost_projection = twin.cost_projection.model_copy(
                update={
                    "projected_total_cost": round(next_cost, 2),
                    "confidence": round(next_conf, 2),
                }
            )
            twin.risk_level = "LOW" if outcome else "MEDIUM"

        os_state["robotics_twin"] = twin.model_dump(mode="json")
        state["pce_os"] = os_state
        return state
