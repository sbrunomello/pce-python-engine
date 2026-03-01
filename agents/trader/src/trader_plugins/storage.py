"""State persistence wrapper using pce-core StateManager plugin KV."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pce.sm.manager import StateManager


class TraderStorage:
    """Namespace-scoped persistence abstraction for trader runtime state."""

    namespace = "trader"

    def __init__(self, db_url: str) -> None:
        self._manager = StateManager(db_url)

    def load_runtime_state(self) -> dict[str, Any]:
        saved = self._manager.plugin_get_json(self.namespace, "runtime")
        if isinstance(saved, dict):
            return saved
        state = {
            "portfolio": {
                "cash": 100_000.0,
                "equity": 100_000.0,
                "positions": {},
                "realized_pnl": 0.0,
                "unrealized_pnl": 0.0,
            },
            "limits": {
                "trades_total_day": 0,
                "trades_by_asset_day": {},
                "day_start_equity": 100_000.0,
                "month_start_equity": 100_000.0,
                "last_day": "",
                "last_month": "",
                "cooldowns": {},
            },
            "market": {},
            "models": {"active": None, "registry": []},
            "metrics": {
                "decisions_total": 0,
                "trades_executed": 0,
                "cci_f": 0.8,
                "p_win_avg": 0.0,
                "drift_flags": [],
                "mode": "cautious",
            },
        }
        self.save_runtime_state(state)
        return state

    def save_runtime_state(self, state: dict[str, Any]) -> None:
        state["updated_at"] = datetime.now(UTC).isoformat()
        self._manager.plugin_set_json(self.namespace, "runtime", state)

    def save_model_registry(self, registry: list[dict[str, Any]]) -> None:
        self._manager.plugin_set_json(self.namespace, "model_registry", registry)

    def load_model_registry(self) -> list[dict[str, Any]]:
        stored = self._manager.plugin_get_json(self.namespace, "model_registry")
        if isinstance(stored, list):
            return [item for item in stored if isinstance(item, dict)]
        return []
