"""Plugin contracts and registry for domain-specific PCE behaviors."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from pce.core.types import ActionPlan, ExecutionResult, PCEEvent


class ValueModelPlugin(Protocol):
    name: str

    def match(self, event: PCEEvent, state: dict[str, object]) -> bool: ...

    def evaluate(self, event: PCEEvent, state: dict[str, object]) -> float: ...


class DecisionPlugin(Protocol):
    name: str

    def match(self, event: PCEEvent, state: dict[str, object]) -> bool: ...

    def deliberate(
        self,
        event: PCEEvent,
        state: dict[str, object],
        value_score: float,
        cci: float,
    ) -> ActionPlan: ...


class AdaptationPlugin(Protocol):
    name: str

    def match(self, event: PCEEvent, state: dict[str, object], result: ExecutionResult) -> bool: ...

    def adapt(
        self,
        state: dict[str, object],
        event: PCEEvent,
        result: ExecutionResult,
    ) -> dict[str, object]: ...


class ExecutorPlugin(Protocol):
    name: str

    def match(self, plan: ActionPlan) -> bool: ...

    def execute(self, plan: ActionPlan) -> ExecutionResult: ...


EvaluateFallback = Callable[[PCEEvent, dict[str, float] | None], float]
DeliberateFallback = Callable[[dict[str, object], float, float], ActionPlan]
AdaptFallback = Callable[[dict[str, object], ExecutionResult], dict[str, object]]
ExecuteFallback = Callable[[ActionPlan], ExecutionResult]


@dataclass(slots=True)
class PluginRegistry:
    """Registry that dispatches plugins by first successful match."""

    _value_plugins: list[ValueModelPlugin] = field(default_factory=list)
    _decision_plugins: list[DecisionPlugin] = field(default_factory=list)
    _adaptation_plugins: list[AdaptationPlugin] = field(default_factory=list)
    _executor_plugins: list[ExecutorPlugin] = field(default_factory=list)

    def register_value_model(self, plugin: ValueModelPlugin) -> None:
        self._value_plugins.append(plugin)

    def register_decision(self, plugin: DecisionPlugin) -> None:
        self._decision_plugins.append(plugin)

    def register_adaptation(self, plugin: AdaptationPlugin) -> None:
        self._adaptation_plugins.append(plugin)

    def register_executor(self, plugin: ExecutorPlugin) -> None:
        self._executor_plugins.append(plugin)

    def evaluate(
        self,
        event: PCEEvent,
        state: dict[str, object],
        fallback: EvaluateFallback,
    ) -> float:
        plugin = self._first_value_plugin(event, state)
        if plugin is None:
            return float(fallback(event, self._strategic_values(state)))
        try:
            return float(plugin.evaluate(event, state))
        except Exception as exc:  # pragma: no cover
            self._log_plugin_error(plugin.name, "evaluate", exc)
            return float(fallback(event, self._strategic_values(state)))

    def deliberate(
        self,
        event: PCEEvent,
        state: dict[str, object],
        value_score: float,
        cci: float,
        fallback: DeliberateFallback,
    ) -> ActionPlan:
        plugin = self._first_decision_plugin(event, state)
        if plugin is None:
            return fallback(state, value_score, cci)
        try:
            return plugin.deliberate(event, state, value_score, cci)
        except Exception as exc:  # pragma: no cover
            self._log_plugin_error(plugin.name, "deliberate", exc)
            return fallback(state, value_score, cci)

    def adapt(
        self,
        state: dict[str, object],
        event: PCEEvent,
        result: ExecutionResult,
        fallback: AdaptFallback,
    ) -> dict[str, object]:
        plugin = self._first_adaptation_plugin(event, state, result)
        if plugin is None:
            return fallback(state, result)
        try:
            return plugin.adapt(state, event, result)
        except Exception as exc:  # pragma: no cover
            self._log_plugin_error(plugin.name, "adapt", exc)
            return fallback(state, result)

    def execute(self, plan: ActionPlan, fallback: ExecuteFallback) -> ExecutionResult:
        plugin = self._first_executor_plugin(plan)
        if plugin is None:
            return fallback(plan)
        try:
            return plugin.execute(plan)
        except Exception as exc:  # pragma: no cover
            self._log_plugin_error(plugin.name, "execute", exc)
            return fallback(plan)

    def _first_value_plugin(
        self,
        event: PCEEvent,
        state: dict[str, object],
    ) -> ValueModelPlugin | None:
        for plugin in self._value_plugins:
            if plugin.match(event, state):
                return plugin
        return None

    def _first_decision_plugin(
        self,
        event: PCEEvent,
        state: dict[str, object],
    ) -> DecisionPlugin | None:
        for plugin in self._decision_plugins:
            if plugin.match(event, state):
                return plugin
        return None

    def _first_adaptation_plugin(
        self,
        event: PCEEvent,
        state: dict[str, object],
        result: ExecutionResult,
    ) -> AdaptationPlugin | None:
        for plugin in self._adaptation_plugins:
            if plugin.match(event, state, result):
                return plugin
        return None

    def _first_executor_plugin(self, plan: ActionPlan) -> ExecutorPlugin | None:
        for plugin in self._executor_plugins:
            if plugin.match(plan):
                return plugin
        return None

    @staticmethod
    def _strategic_values(state: dict[str, object]) -> dict[str, float] | None:
        strategic_values = state.get("strategic_values")
        if not isinstance(strategic_values, dict):
            return None
        return {key: float(value) for key, value in strategic_values.items()}

    @staticmethod
    def _log_plugin_error(plugin_name: str, operation: str, exc: Exception) -> None:
        print(
            json.dumps(
                {
                    "event": "plugin_fallback",
                    "plugin": plugin_name,
                    "operation": operation,
                    "error": str(exc),
                },
                ensure_ascii=False,
            )
        )
