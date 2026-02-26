"""State Manager backed by SQLite via SQLAlchemy."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import DateTime, Engine, String, Text, create_engine, desc, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from pce.core.types import PCEEvent


class Base(DeclarativeBase):
    """Declarative base for SQLite models."""


class CognitiveState(Base):
    """Persisted single-record state snapshot."""

    __tablename__ = "cognitive_state"

    key: Mapped[str] = mapped_column(String(32), primary_key=True, default="global")
    state_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class EventMemory(Base):
    """Append-only event memory for audit and adaptive feedback."""

    __tablename__ = "event_memory"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class ActionMemory(Base):
    """Append-only action registry for decision traceability and CCI metrics."""

    __tablename__ = "action_memory"

    action_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    priority: Mapped[int] = mapped_column(nullable=False)
    value_score: Mapped[float] = mapped_column(nullable=False)
    expected_impact: Mapped[float] = mapped_column(nullable=False)
    observed_impact: Mapped[float] = mapped_column(nullable=False)
    respected_values: Mapped[bool] = mapped_column(nullable=False, default=True)
    violated_values_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class CCIHistory(Base):
    """Persisted CCI evolution snapshots used by API and worker diagnostics."""

    __tablename__ = "cci_history"

    cci_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    cci: Mapped[float] = mapped_column(nullable=False)
    metrics_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class StateManager:
    """CRUD gateway for persistent state and event storage."""

    def __init__(self, db_url: str) -> None:
        self._engine: Engine = create_engine(db_url, future=True)
        Base.metadata.create_all(self._engine)

    def load_state(self) -> dict[str, Any]:
        """Load global cognitive state snapshot."""
        with Session(self._engine) as session:
            record = session.get(CognitiveState, "global")
            if record is None:
                return {}
            loaded = json.loads(record.state_json)
            return cast(dict[str, Any], loaded)

    def save_state(self, state: Mapping[str, Any]) -> None:
        """Persist global state snapshot atomically."""
        with Session(self._engine) as session:
            record = session.get(CognitiveState, "global")
            serialized = json.dumps(dict(state), ensure_ascii=False)
            if record is None:
                record = CognitiveState(key="global", state_json=serialized)
                session.add(record)
            else:
                record.state_json = serialized
                record.updated_at = datetime.now(UTC)
            session.commit()

    def remember_event(self, event: PCEEvent) -> None:
        """Append event into event memory table."""
        with Session(self._engine) as session:
            session.add(
                EventMemory(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    source=event.source,
                    payload_json=json.dumps(event.payload, ensure_ascii=False),
                )
            )
            session.commit()

    def recent_event_count(self) -> int:
        """Get event count for coherence/feedback metrics."""
        with Session(self._engine) as session:
            result = session.execute(select(EventMemory.event_id))
            return len(result.scalars().all())

    def remember_action(
        self,
        *,
        action_id: str,
        event_id: str,
        action_type: str,
        priority: int,
        value_score: float,
        expected_impact: float,
        observed_impact: float,
        respected_values: bool,
        violated_values: list[str] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        """Append action decision and execution outcome for CCI traceability."""
        with Session(self._engine) as session:
            session.add(
                ActionMemory(
                    action_id=action_id,
                    event_id=event_id,
                    action_type=action_type,
                    priority=priority,
                    value_score=value_score,
                    expected_impact=expected_impact,
                    observed_impact=observed_impact,
                    respected_values=respected_values,
                    violated_values_json=json.dumps(violated_values or []),
                    metadata_json=json.dumps(dict(metadata or {}), ensure_ascii=False),
                )
            )
            session.commit()

    def get_recent_actions(self, n: int) -> list[dict[str, Any]]:
        """Return most recent action traces ordered from oldest to newest."""
        with Session(self._engine) as session:
            rows = session.execute(
                select(ActionMemory).order_by(desc(ActionMemory.created_at)).limit(max(0, n))
            ).scalars()
            recent = list(rows)

        recent.reverse()
        return [
            {
                "action_id": row.action_id,
                "event_id": row.event_id,
                "action_type": row.action_type,
                "priority": row.priority,
                "value_score": row.value_score,
                "expected_impact": row.expected_impact,
                "observed_impact": row.observed_impact,
                "respected_values": row.respected_values,
                "violated_values": json.loads(row.violated_values_json),
                "metadata": json.loads(row.metadata_json),
                "created_at": row.created_at.isoformat(),
            }
            for row in recent
        ]

    def save_cci_snapshot(self, cci_id: str, cci: float, metrics: Mapping[str, Any]) -> None:
        """Persist CCI and its components for historical analysis."""
        with Session(self._engine) as session:
            session.add(
                CCIHistory(
                    cci_id=cci_id,
                    cci=cci,
                    metrics_json=json.dumps(dict(metrics), ensure_ascii=False),
                )
            )
            session.commit()

    def get_cci_history(self) -> list[dict[str, Any]]:
        """Load full CCI history ordered by creation time."""
        with Session(self._engine) as session:
            rows = session.execute(select(CCIHistory).order_by(CCIHistory.created_at)).scalars()
            return [
                {
                    "cci_id": row.cci_id,
                    "cci": row.cci,
                    "metrics": json.loads(row.metrics_json),
                    "created_at": row.created_at.isoformat(),
                }
                for row in rows
            ]

    def calculate_contradictions(self) -> dict[str, Any]:
        """Aggregate contradiction indicators from explicit value violations."""
        actions = self.get_recent_actions(500)
        if not actions:
            return {"contradiction_rate": 0.0, "violation_count": 0, "total_actions": 0}

        violation_count = 0
        violations_by_value: dict[str, int] = {}
        for action in actions:
            violated = action["violated_values"]
            if violated:
                violation_count += 1
            for value in violated:
                violations_by_value[value] = violations_by_value.get(value, 0) + 1

        contradiction_rate = violation_count / len(actions)
        return {
            "contradiction_rate": contradiction_rate,
            "violation_count": violation_count,
            "total_actions": len(actions),
            "violations_by_value": violations_by_value,
        }
