"""State Manager backed by SQLite via SQLAlchemy."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import DateTime, Engine, String, Text, create_engine, select
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
