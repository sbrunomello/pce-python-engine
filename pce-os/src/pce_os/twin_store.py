"""Persistence and deterministic event application for robotics digital twin."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from pce.sm.manager import StateManager

from pce_os.models import (
    Component,
    CostProjection,
    RobotProjectState,
    SimulationResult,
    TestResult,
)

_OS_SLICE = "pce_os"
_TWIN_SLICE = "robotics_twin"


class RobotTwinStore:
    """Read/write helper for the robotics twin state slice."""

    def __init__(self, state: RobotProjectState | None = None) -> None:
        self._state = state or RobotProjectState()

    def current_state(self) -> RobotProjectState:
        """Return in-memory twin state."""
        return self._state

    @staticmethod
    def load(sm: StateManager) -> RobotProjectState:
        """Load twin state from the global state store, creating defaults when missing."""
        state = sm.load_state()
        os_payload = state.get(_OS_SLICE)
        if not isinstance(os_payload, dict):
            return RobotProjectState()
        twin_payload = os_payload.get(_TWIN_SLICE)
        if not isinstance(twin_payload, dict):
            return RobotProjectState()
        return RobotProjectState.model_validate(twin_payload)

    @staticmethod
    def save(sm: StateManager, state: RobotProjectState) -> None:
        """Persist twin state in the fixed PCE-OS state slice."""
        global_state = sm.load_state()
        os_payload = global_state.get(_OS_SLICE)
        if not isinstance(os_payload, dict):
            os_payload = {}
        os_payload[_TWIN_SLICE] = state.model_dump(mode="json")
        global_state[_OS_SLICE] = os_payload
        sm.save_state(global_state)

    def apply_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> RobotProjectState:
        """Apply one domain event deterministically and return updated state."""
        metadata = metadata or {}
        next_state = self._state.model_copy(deep=True)
        event_record: dict[str, object] = {
            "event_type": event_type,
            "payload": deepcopy(payload),
            "metadata": deepcopy(metadata),
            "at": str(metadata.get("at", datetime.now(UTC).isoformat())),
        }

        if event_type == "project.goal.defined":
            next_state.phase = str(payload.get("phase", "planning"))
        elif event_type == "budget.updated":
            budget_total = float(payload.get("budget_total", next_state.budget_total))
            next_state.budget_total = budget_total
            next_state.budget_remaining = float(payload.get("budget_remaining", budget_total))
        elif event_type == "part.candidate.added":
            component = Component.model_validate(payload)
            next_state.components = [
                comp
                for comp in next_state.components
                if comp.component_id != component.component_id
            ] + [component]
            next_state.cost_projection = self._project_cost(next_state)
        elif event_type == "purchase.completed":
            spent = float(payload.get("total_cost", 0.0))
            next_state.budget_remaining -= spent
            next_state.purchase_history.append({"status": "completed", **deepcopy(payload)})
            next_state.cost_projection = self._project_cost(next_state)
        elif event_type == "part.received":
            component_id = str(payload.get("component_id", ""))
            next_state.components = [
                (
                    comp.model_copy(update={"status": "received"})
                    if comp.component_id == component_id
                    else comp
                )
                for comp in next_state.components
            ]
        elif event_type == "test.result.recorded":
            test_result = TestResult.model_validate(payload)
            next_state.tests.append(test_result)
        elif event_type == "test.executed":
            simulation = SimulationResult.model_validate(payload)
            next_state.simulations.append(simulation)
            next_state.risk_level = simulation.projected_risk_level
        elif event_type == "risk.detected":
            risk = str(payload.get("description", "unknown risk"))
            next_state.risks.append(risk)
            next_state.risk_level = str(payload.get("risk_level", "HIGH"))

        next_state.audit_trail.append(event_record)
        self._state = next_state
        return next_state

    @staticmethod
    def _project_cost(state: RobotProjectState) -> CostProjection:
        total = sum(comp.estimated_unit_cost * comp.quantity for comp in state.components)
        high_risk_parts = sum(1 for comp in state.components if comp.risk_level == "HIGH")
        return CostProjection(
            projected_total_cost=round(total, 2),
            projected_risk_buffer=round(total * 0.1 + high_risk_parts * 50, 2),
            confidence=0.55 if state.components else 0.5,
        )
