"""FastAPI interface for PCE with request-scoped dependency access."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from llm_assistant import (
    AssistantAdaptationPlugin,
    AssistantDecisionPlugin,
    AssistantStorage,
    AssistantValueModelPlugin,
    OpenRouterClient,
)
from llm_assistant.config import load_openrouter_credentials
from pce.afs.feedback import AdaptiveFeedbackSystem
from pce.ao.orchestrator import ActionOrchestrator
from pce.core.cci import CCIMetric
from pce.core.config import Settings
from pce.core.plugins import PluginRegistry
from pce.core.types import ExecutionResult, PCEEvent
from pce.de.engine import DecisionEngine
from pce.epl.processor import EventProcessingLayer
from pce.isi.integrator import InternalStateIntegrator
from pce.sm.manager import StateManager
from pce.vel.evaluator import ValueEvaluationLayer
from pce_os import (
    ApprovalGate,
    OSRoboticsAdaptationPlugin,
    OSRoboticsDecisionPlugin,
    OSRoboticsValueModelPlugin,
    RobotProjectState,
    RobotTwinStore,
)
from pce_os.transcript import append_transcript_item, items_since, read_transcript
from pydantic import BaseModel, Field
from rover_plugins import (
    RoboticsAdaptationPlugin,
    RoboticsDecisionPlugin,
    RoboticsStorage,
    RoboticsValueModelPlugin,
)

from agents.rover import router as rover_router
from agents.rover.app import runtime as rover_runtime

logger = logging.getLogger(__name__)


class EventIn(BaseModel):
    """Raw event API input model."""

    event_type: str
    source: str
    payload: dict[str, object]


class ApprovalDecisionIn(BaseModel):
    """Control-plane payload for approval transitions."""

    actor: str = Field(min_length=1)
    notes: str | None = None
    reason: str | None = None


class TranscriptQueryOut(BaseModel):
    cursor: int
    items: list[dict[str, Any]]


class OSStateOut(BaseModel):
    twin_snapshot: dict[str, Any]
    os_metrics: dict[str, Any]
    policy_state: dict[str, Any]
    last_n_audit_trail: list[dict[str, Any]]


def _sse_format(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _broadcast_sse(app: FastAPI, event: str, payload: dict[str, Any]) -> None:
    queues = getattr(app.state, "os_stream_queues", [])
    for queue in list(queues):
        try:
            queue.put_nowait({"event": event, "data": payload})
        except asyncio.QueueFull:
            logger.warning("sse_queue_full dropping event=%s", event)


def _append_transcript_and_emit(
    request: Request,
    state: dict[str, object],
    *,
    kind: str,
    payload: dict[str, Any],
    correlation_id: str,
    decision_id: str = "",
    agent: str = "",
    event_name: str,
) -> tuple[dict[str, object], dict[str, Any]]:
    next_state, item = append_transcript_item(
        state,
        kind=kind,
        payload=payload,
        correlation_id=correlation_id,
        decision_id=decision_id,
        agent=agent,
    )
    _broadcast_sse(request.app, event_name, item)
    return next_state, item


def load_twin(current_state: dict[str, object]) -> RobotProjectState:
    """Load robotics twin from current request state snapshot."""
    return RobotTwinStore.from_state(current_state)


def apply_os_event_to_twin(
    current_twin: RobotProjectState,
    event: PCEEvent,
    metadata: dict[str, Any] | None = None,
) -> RobotProjectState:
    """Apply one PCE-OS event to twin using deterministic metadata precedence."""
    event_metadata: dict[str, Any] = {
        "event_id": event.event_id,
        "event_at": event.timestamp.isoformat(),
    }
    if metadata:
        event_metadata.update(metadata)
    return RobotTwinStore.apply_event(current_twin, event.event_type, event.payload, event_metadata)


def _budget_remaining(state: dict[str, object]) -> float:
    twin = RobotTwinStore.from_state(state)
    return float(twin.budget_remaining)


def _run_pipeline(
    request: Request,
    event_in: EventIn,
    *,
    initial_state: dict[str, object] | None = None,
) -> dict[str, object]:
    """End-to-end event processing pipeline entrypoint with plugin dispatch."""
    app_state = request.app.state
    try:
        event = app_state.epl.ingest(event_in.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    state = initial_state if initial_state is not None else app_state.sm.load_state()
    correlation_id = str(event.payload.get("correlation_id", event.event_id))

    state, _ = _append_transcript_and_emit(
        request,
        state,
        kind="event_ingested",
        payload={"event_id": event.event_id, "event_type": event.event_type, "source": event.source},
        correlation_id=correlation_id,
        decision_id=event.event_id,
        event_name="os.event_ingested",
    )

    updated_state = app_state.isi.integrate(state, event)
    app_state.sm.remember_event(event)

    value_score = app_state.plugin_registry.evaluate(
        event,
        updated_state,
        fallback=app_state.vel.evaluate_event,
    )

    cci, components = app_state.cci_metric.from_state_manager(app_state.sm)
    cci_payload = {
        "decision_consistency": components.decision_consistency,
        "priority_stability": components.priority_stability,
        "contradiction_rate": components.contradiction_rate,
        "predictive_accuracy": components.predictive_accuracy,
    }
    plan = app_state.plugin_registry.deliberate(
        event,
        updated_state,
        value_score,
        cci,
        fallback=app_state.de.deliberate,
    )

    explain = plan.metadata.get("explain")
    if isinstance(explain, dict):
        explain["cci"] = {"score": cci, "components": cci_payload}
        for item in explain.get("agent_transcript", []):
            if not isinstance(item, dict):
                continue
            event_name = "os.agent_message"
            if item.get("kind") == "actions_proposed":
                event_name = "os.actions_proposed"
            updated_state, _ = _append_transcript_and_emit(
                request,
                updated_state,
                kind=str(item.get("kind", "agent_message")),
                payload=item.get("payload", {}),
                correlation_id=str(item.get("correlation_id", correlation_id)),
                decision_id=str(item.get("decision_id", event.event_id)),
                agent=str(item.get("agent", "")),
                event_name=event_name,
            )

    state_for_adaptation = updated_state
    if event.event_type.startswith("feedback."):
        result = ExecutionResult(
            action_type=event.event_type,
            success=True,
            observed_impact=float(event.payload.get("reward", 0.0)),
            notes="feedback ingestion",
            metadata={"feedback": event.payload},
        )
    else:
        needs_approval, rationale = app_state.approval_gate.decide_if_requires_approval(
            plan,
            updated_state,
        )
        if needs_approval and event.event_type != "purchase.completed":
            pending, state_for_adaptation = app_state.approval_gate.enqueue_pending_approval(
                decision_id=event.event_id,
                plan=plan,
                snapshot_state=updated_state,
                state=updated_state,
                metadata={"event_id": event.event_id, "gate_rationale": rationale},
            )
            state_for_adaptation, _ = _append_transcript_and_emit(
                request,
                state_for_adaptation,
                kind="approval_created",
                payload=pending,
                correlation_id=correlation_id,
                decision_id=str(pending.get("decision_id", event.event_id)),
                event_name="os.approval_created",
            )
            result = ExecutionResult(
                action_type=plan.action_type,
                success=True,
                observed_impact=0.0,
                notes="approval pending",
                metadata={"approval_pending": True, "approval_id": pending["approval_id"]},
            )
        else:
            result = app_state.plugin_registry.execute(plan, fallback=app_state.ao.execute)

    adapted_state = app_state.plugin_registry.adapt(
        state_for_adaptation,
        event,
        result,
        fallback=app_state.afs.adapt,
    )

    if str(event.payload.get("domain")) == "os.robotics":
        twin = load_twin(adapted_state)
        twin_next = apply_os_event_to_twin(twin, event)
        adapted_state = RobotTwinStore.write_into_state_slice(adapted_state, twin_next)

    adapted_state, final_item = _append_transcript_and_emit(
        request,
        adapted_state,
        kind="state_updated",
        payload={"event_id": event.event_id, "action_type": plan.action_type},
        correlation_id=correlation_id,
        decision_id=event.event_id,
        event_name="os.state_updated",
    )

    app_state.sm.save_state(adapted_state)

    violated_values = [] if value_score >= 0.6 else ["long_term_coherence"]
    respected_values = len(violated_values) == 0

    app_state.sm.remember_action(
        action_id=str(uuid4()),
        event_id=event.event_id,
        action_type=plan.action_type,
        priority=plan.priority,
        value_score=value_score,
        expected_impact=float(plan.metadata.get("expected_impact", 0.5)),
        observed_impact=result.observed_impact,
        respected_values=respected_values,
        violated_values=violated_values,
        metadata={"rationale": plan.rationale, "plan_metadata": plan.metadata},
    )

    cci, components = app_state.cci_metric.from_state_manager(app_state.sm)
    cci_payload = {
        "decision_consistency": components.decision_consistency,
        "priority_stability": components.priority_stability,
        "contradiction_rate": components.contradiction_rate,
        "predictive_accuracy": components.predictive_accuracy,
    }
    app_state.sm.save_cci_snapshot(cci_id=str(uuid4()), cci=cci, metrics=cci_payload)

    action_payload = plan.metadata.get("action_payload", plan.action_type)
    response: dict[str, object] = {
        "event_id": event.event_id,
        "correlation_id": correlation_id,
        "value_score": value_score,
        "cci": cci,
        "cci_components": cci_payload,
        "action_type": plan.action_type,
        "action": action_payload,
        "metadata": plan.metadata,
        "success": result.success,
        "cursor": final_item["cursor"],
    }

    if event.event_type.startswith("feedback."):
        q_update = adapted_state.get("robotics_rl")
        response["updated"] = bool(q_update)
        response["epsilon"] = q_update.get("epsilon") if isinstance(q_update, dict) else None
        response["q_update"] = q_update if isinstance(q_update, dict) else {}
        assistant_learning = adapted_state.get("assistant_learning")
        if isinstance(assistant_learning, dict):
            response["assistant_learning"] = assistant_learning

    return response


def _os_metrics(state: dict[str, object], cci: float) -> dict[str, Any]:
    twin = load_twin(state)
    approvals = state.get("pce_os", {}).get("pending_approvals", []) if isinstance(state.get("pce_os"), dict) else []
    total = len([item for item in approvals if isinstance(item, dict)])
    approved = len([item for item in approvals if isinstance(item, dict) and item.get("status") == "approved"])
    return {
        "budget_remaining": float(twin.budget_remaining),
        "risk_level": twin.risk_level,
        "projected_vs_actual": {
            "projected_cost": float(twin.cost_projection.projected_total_cost),
            "actual_purchase_spend": sum(float(i.total_cost) for i in twin.purchase_history),
        },
        "approval_rate": (approved / total) if total > 0 else 0.0,
        "cci": cci,
    }


def build_app(state_manager: StateManager | None = None) -> FastAPI:
    """Build FastAPI app with an explicit dependency container in ``app.state``."""
    settings = Settings()
    sm = state_manager or StateManager(settings.db_url)

    app = FastAPI(title="PCE API", version="0.1.0")

    app.state.sm = sm
    app.state.epl = EventProcessingLayer(settings.event_schema_path)
    app.state.isi = InternalStateIntegrator()
    app.state.vel = ValueEvaluationLayer()
    app.state.de = DecisionEngine()
    app.state.ao = ActionOrchestrator()
    app.state.afs = AdaptiveFeedbackSystem()
    app.state.cci_metric = CCIMetric()
    app.state.os_stream_queues: list[asyncio.Queue[dict[str, Any]]] = []

    app.state.plugin_registry = PluginRegistry()
    app.state.robotics_storage = RoboticsStorage(sm)
    app.state.assistant_storage = AssistantStorage(sm)
    app.state.approval_gate = ApprovalGate()
    app.state.assistant_value_model = AssistantValueModelPlugin()

    openrouter_credentials = load_openrouter_credentials()
    app.state.assistant_client = OpenRouterClient(
        api_key=openrouter_credentials["api_key"],
        model=openrouter_credentials["model"],
        base_url=openrouter_credentials["base_url"],
        timeout_s=float(openrouter_credentials["timeout_s"]),
        referer=openrouter_credentials["referer"],
        title=openrouter_credentials["title"],
    )

    app.state.plugin_registry.register_value_model(RoboticsValueModelPlugin())
    app.state.plugin_registry.register_value_model(app.state.assistant_value_model)
    app.state.plugin_registry.register_value_model(OSRoboticsValueModelPlugin())
    app.state.plugin_registry.register_decision(RoboticsDecisionPlugin(app.state.robotics_storage))
    app.state.plugin_registry.register_decision(OSRoboticsDecisionPlugin())
    app.state.plugin_registry.register_decision(
        AssistantDecisionPlugin(
            app.state.assistant_storage,
            app.state.assistant_value_model,
            app.state.assistant_client,
        )
    )
    app.state.plugin_registry.register_adaptation(RoboticsAdaptationPlugin(app.state.robotics_storage))
    app.state.plugin_registry.register_adaptation(OSRoboticsAdaptationPlugin())
    app.state.plugin_registry.register_adaptation(AssistantAdaptationPlugin(app.state.assistant_storage))

    @app.post("/events")
    @app.post("/v1/events")
    def process_event(request: Request, event_in: EventIn) -> dict[str, object]:
        return _run_pipeline(request, event_in)

    @app.get("/v1/os/state", response_model=OSStateOut)
    def get_v1_os_state(request: Request, limit: int = Query(30, ge=1, le=200)) -> dict[str, Any]:
        state = request.app.state.sm.load_state()
        twin = load_twin(state)
        cci, _ = request.app.state.cci_metric.from_state_manager(request.app.state.sm)
        approvals = request.app.state.approval_gate.list_all(state)
        transcript = read_transcript(state)
        policy_state = {
            "pending_count": len([a for a in approvals if a.get("status") == "pending"]),
            "resolved_count": len([a for a in approvals if a.get("status") != "pending"]),
            "transcript_cursor": transcript["cursor"],
        }
        return {
            "twin_snapshot": twin.model_dump(mode="json"),
            "os_metrics": _os_metrics(state, cci),
            "policy_state": policy_state,
            "last_n_audit_trail": twin.audit_trail[-limit:],
        }

    @app.get("/v1/os/approvals")
    @app.get("/os/approvals")
    def get_os_approvals(request: Request) -> dict[str, object]:
        state = request.app.state.sm.load_state()
        approvals = request.app.state.approval_gate.list_all(state)
        return {"items": approvals, "pending": [item for item in approvals if item.get("status") == "pending"]}

    @app.post("/v1/os/approvals/{approval_id}/approve")
    @app.post("/os/approvals/{approval_id}/approve")
    def approve_os_request(request: Request, approval_id: str, body: ApprovalDecisionIn) -> dict[str, object]:
        current_state = request.app.state.sm.load_state()
        gate = request.app.state.approval_gate

        try:
            approval = gate.get_approval(current_state, approval_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        if approval.get("status") != "pending":
            raise HTTPException(status_code=409, detail="approval_not_pending")

        required_budget = float(approval.get("projected_cost", 0.0))
        available_budget = _budget_remaining(current_state)
        if available_budget < required_budget:
            summary = (
                "insufficient budget for purchase "
                f"(required={required_budget:.2f}, available={available_budget:.2f})"
            )
            record, rejected_state = gate.transition_reject(approval_id, body.actor, summary, current_state)
            rejected_state, _ = _append_transcript_and_emit(
                request,
                rejected_state,
                kind="approval_updated",
                payload=record,
                correlation_id=str(record.get("metadata", {}).get("event_id", record.get("decision_id", ""))),
                decision_id=str(record.get("decision_id", "")),
                event_name="os.approval_updated",
            )
            request.app.state.sm.save_state(rejected_state)
            raise HTTPException(status_code=409, detail="insufficient_budget_for_purchase")

        try:
            record, updated_state = gate.transition_approve(approval_id, body.actor, body.notes or "", current_state)
            updated_state, _ = _append_transcript_and_emit(
                request,
                updated_state,
                kind="approval_updated",
                payload=record,
                correlation_id=str(record.get("metadata", {}).get("event_id", record.get("decision_id", ""))),
                decision_id=str(record.get("decision_id", "")),
                event_name="os.approval_updated",
            )
            event_payload = gate.build_approval_event(record, body.actor, body.notes or "")
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _run_pipeline(request, EventIn.model_validate(event_payload), initial_state=updated_state)

    @app.post("/v1/os/approvals/{approval_id}/reject")
    @app.post("/os/approvals/{approval_id}/reject")
    def reject_os_request(request: Request, approval_id: str, body: ApprovalDecisionIn) -> dict[str, object]:
        reason = body.reason or body.notes or "no reason provided"
        current_state = request.app.state.sm.load_state()
        try:
            record, updated_state = request.app.state.approval_gate.transition_reject(
                approval_id, body.actor, reason, current_state
            )
            updated_state, _ = _append_transcript_and_emit(
                request,
                updated_state,
                kind="approval_updated",
                payload=record,
                correlation_id=str(record.get("metadata", {}).get("event_id", record.get("decision_id", ""))),
                decision_id=str(record.get("decision_id", "")),
                event_name="os.approval_updated",
            )
            request.app.state.sm.save_state(updated_state)
            event_payload = request.app.state.approval_gate.build_rejection_event(record, body.actor, reason)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _run_pipeline(request, EventIn.model_validate(event_payload), initial_state=updated_state)

    @app.post("/v1/os/approvals/{approval_id}/override")
    def override_os_request(request: Request, approval_id: str, body: ApprovalDecisionIn) -> dict[str, object]:
        current_state = request.app.state.sm.load_state()
        notes = body.notes or "override"
        try:
            record, updated_state = request.app.state.approval_gate.transition_override(
                approval_id, body.actor, notes, current_state
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        updated_state, _ = _append_transcript_and_emit(
            request,
            updated_state,
            kind="approval_updated",
            payload=record,
            correlation_id=str(record.get("metadata", {}).get("event_id", record.get("decision_id", ""))),
            decision_id=str(record.get("decision_id", "")),
            event_name="os.approval_updated",
        )
        request.app.state.sm.save_state(updated_state)
        return {"status": "ok", "approval": record}

    @app.get("/v1/os/agents/transcript", response_model=TranscriptQueryOut)
    def get_agents_transcript(request: Request, since: int = Query(0, ge=0)) -> dict[str, Any]:
        state = request.app.state.sm.load_state()
        transcript = read_transcript(state)
        return {"cursor": transcript["cursor"], "items": items_since(state, since)}

    @app.get("/v1/stream/os")
    async def stream_os(request: Request) -> StreamingResponse:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=200)
        request.app.state.os_stream_queues.append(queue)

        async def event_iterator() -> AsyncIterator[str]:
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        msg = await asyncio.wait_for(queue.get(), timeout=15)
                        yield _sse_format(msg["event"], msg["data"])
                    except TimeoutError:
                        yield ": keepalive\n\n"
            finally:
                if queue in request.app.state.os_stream_queues:
                    request.app.state.os_stream_queues.remove(queue)

        return StreamingResponse(event_iterator(), media_type="text/event-stream")

    @app.get("/cci")
    def get_cci(request: Request) -> dict[str, float]:
        cci, _ = request.app.state.cci_metric.from_state_manager(request.app.state.sm)
        return {"cci": cci}

    @app.get("/state")
    def get_state(request: Request) -> dict[str, object]:
        return {"state": request.app.state.sm.load_state()}

    @app.get("/os/robotics/state")
    def get_os_robotics_state(request: Request) -> dict[str, object]:
        twin = load_twin(request.app.state.sm.load_state())
        return {"robotics_twin": twin.model_dump(mode="json")}

    @app.get("/cci/history")
    def get_cci_history(request: Request) -> dict[str, object]:
        return {"history": request.app.state.sm.get_cci_history()}

    @app.post("/agents/rover/control/clear_policy")
    def clear_rover_policy(request: Request) -> dict[str, object]:
        defaults = request.app.state.robotics_storage.clear_policy()
        state = request.app.state.sm.load_state()
        if "robotics" in state:
            state["robotics"] = {}
            request.app.state.sm.save_state(state)
        return {"status": "cleared", "defaults": defaults}

    @app.post("/agents/rover/control/reset_stats")
    async def reset_rover_stats() -> dict[str, object]:
        await rover_runtime.reset_stats()
        await rover_runtime.broadcast(rover_runtime._frame_payload({"type": "robot.stop"}))
        return {"status": "stats_reset"}

    @app.post("/agents/assistant/control/clear_memory")
    def clear_assistant_memory(request: Request) -> dict[str, object]:
        deleted = request.app.state.assistant_storage.clear_all()
        state = request.app.state.sm.load_state()
        if "assistant" in state:
            state["assistant"] = {}
        if "assistant_learning" in state:
            state["assistant_learning"] = {}
        request.app.state.sm.save_state(state)
        return {"status": "cleared", "deleted": deleted, "epsilon": 0.6}

    app.include_router(rover_router)
    return app


app = build_app()

__all__ = ["app", "build_app"]
