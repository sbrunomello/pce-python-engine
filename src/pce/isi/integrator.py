"""Internal State Integrator implementation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pce.core.types import PCEEvent


class InternalStateIntegrator:
    """Pure function-like state integrator for deterministic updates."""

    def integrate(self, state: Mapping[str, Any], event: PCEEvent) -> dict[str, Any]:
        """Merge event payload into current state with event metadata."""
        next_state = dict(state)
        domain = str(event.payload.get("domain", "general"))
        state_slice = dict(next_state.get(domain, {}))
        state_slice.update(event.payload)
        state_slice["last_event_id"] = event.event_id
        state_slice["last_event_type"] = event.event_type
        next_state[domain] = state_slice
        return next_state
