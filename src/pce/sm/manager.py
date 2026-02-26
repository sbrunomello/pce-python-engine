"""State Manager backed by SQLite via SQLAlchemy."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import DateTime, Engine, Float, Integer, String, Text, create_engine, desc, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from pce.core.types import PCEEvent
from pce.robotics.rl import DEFAULT_HYPERPARAMS


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


class RoboticsQValue(Base):
    """Q-table storage for robotics domain."""

    __tablename__ = "robotics_q_values"

    state_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    action: Mapped[str] = mapped_column(String(8), primary_key=True)
    q_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class RoboticsParam(Base):
    """Hyperparameter key-value store for robotics RL."""

    __tablename__ = "robotics_params"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class RoboticsTransition(Base):
    """Most recent transition memory for episode-level Q updates."""

    __tablename__ = "robotics_transitions"

    episode_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tick: Mapped[int] = mapped_column(Integer, nullable=False)
    state_key: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(8), nullable=False)
    reward: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    next_state_key: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    done: Mapped[bool] = mapped_column(nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class RoboticsStats(Base):
    """Aggregated robotics learning stats per episode."""

    __tablename__ = "robotics_stats"

    episode_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    total_reward: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    steps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    collisions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    successes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
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

    def get_q(self, state_key: str) -> dict[str, float]:
        """Get Q-values for all actions in a given state."""
        with Session(self._engine) as session:
            rows = session.execute(
                select(RoboticsQValue).where(RoboticsQValue.state_key == state_key)
            ).scalars()
            return {row.action: row.q_value for row in rows}

    def set_q(self, state_key: str, action: str, q_value: float) -> None:
        """Persist one Q-value entry."""
        with Session(self._engine) as session:
            row = session.get(RoboticsQValue, {"state_key": state_key, "action": action})
            if row is None:
                row = RoboticsQValue(state_key=state_key, action=action, q_value=q_value)
                session.add(row)
            else:
                row.q_value = q_value
                row.updated_at = datetime.now(UTC)
            session.commit()

    def get_robotics_params(self) -> dict[str, float]:
        """Load robotics RL hyperparameters, creating defaults if absent."""
        with Session(self._engine) as session:
            rows = session.execute(select(RoboticsParam)).scalars().all()
            if not rows:
                for key, value in DEFAULT_HYPERPARAMS.items():
                    session.add(RoboticsParam(key=key, value=value))
                session.commit()
                return dict(DEFAULT_HYPERPARAMS)
            params = {row.key: row.value for row in rows}

        merged = dict(DEFAULT_HYPERPARAMS)
        merged.update(params)
        return merged

    def update_robotics_params(self, **params: float) -> None:
        """Update robotics hyperparameters selectively."""
        with Session(self._engine) as session:
            for key, value in params.items():
                row = session.get(RoboticsParam, key)
                if row is None:
                    row = RoboticsParam(key=key, value=value)
                    session.add(row)
                else:
                    row.value = value
                    row.updated_at = datetime.now(UTC)
            session.commit()

    def remember_transition(
        self,
        episode_id: str,
        tick: int,
        state_key: str,
        action: str,
        reward: float,
        next_state_key: str,
        done: bool,
    ) -> None:
        """Persist latest transition data for episode."""
        with Session(self._engine) as session:
            row = session.get(RoboticsTransition, episode_id)
            if row is None:
                row = RoboticsTransition(
                    episode_id=episode_id,
                    tick=tick,
                    state_key=state_key,
                    action=action,
                    reward=reward,
                    next_state_key=next_state_key,
                    done=done,
                )
                session.add(row)
            else:
                row.tick = tick
                row.state_key = state_key
                row.action = action
                row.reward = reward
                row.next_state_key = next_state_key
                row.done = done
                row.updated_at = datetime.now(UTC)
            session.commit()

    def get_transition(self, episode_id: str) -> dict[str, Any] | None:
        """Get latest transition for an episode."""
        with Session(self._engine) as session:
            row = session.get(RoboticsTransition, episode_id)
            if row is None:
                return None
            return {
                "episode_id": row.episode_id,
                "tick": row.tick,
                "state_key": row.state_key,
                "action": row.action,
                "reward": row.reward,
                "next_state_key": row.next_state_key,
                "done": row.done,
            }


    def clear_robotics_policy(self) -> None:
        """Reset robotics Q-table and epsilon to defaults."""
        with Session(self._engine) as session:
            session.query(RoboticsQValue).delete()
            session.query(RoboticsTransition).delete()
            session.query(RoboticsStats).delete()
            session.query(RoboticsParam).delete()
            for key, value in DEFAULT_HYPERPARAMS.items():
                session.add(RoboticsParam(key=key, value=value))
            session.commit()
    def update_robotics_stats(
        self,
        episode_id: str,
        reward: float,
        collisions: int,
        success: bool,
    ) -> None:
        """Aggregate per-episode robotics statistics."""
        with Session(self._engine) as session:
            row = session.get(RoboticsStats, episode_id)
            if row is None:
                row = RoboticsStats(
                    episode_id=episode_id,
                    total_reward=reward,
                    steps=1,
                    collisions=collisions,
                    successes=1 if success else 0,
                )
                session.add(row)
            else:
                row.total_reward += reward
                row.steps += 1
                row.collisions = collisions
                if success:
                    row.successes += 1
                row.updated_at = datetime.now(UTC)
            session.commit()
