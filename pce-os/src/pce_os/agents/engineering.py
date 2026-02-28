"""Engineering agent focused on planning and technical feasibility."""

from __future__ import annotations

from typing import Any

from pce_os.agents.base import Agent, AgentInput, AgentMessage, AgentOutput
from pce_os.agents.llm import LLMClient, NullLLMClient


class EngineeringAgent(Agent):
    name = "engineering"

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or NullLLMClient()

    def process(self, agent_input: AgentInput) -> AgentOutput:
        event = agent_input.event
        output = AgentOutput(confidence=0.78, rationale="Engineering heuristics applied.")

        if event.event_type in {"project.goal.defined", "budget.updated"}:
            output.proposed_actions.extend(
                [
                    {
                        "action_type": "os.generate_bom",
                        "priority": 2,
                        "metadata": {"source_agent": self.name},
                    },
                    {
                        "action_type": "os.update_project_plan",
                        "priority": 3,
                        "metadata": {"source_agent": self.name},
                    },
                ]
            )

        if event.event_type == "part.candidate.added":
            graph = agent_input.twin_snapshot.get("dependency_graph", {})
            edges = graph.get("edges", {}) if isinstance(graph, dict) else {}
            if self._has_cycle(edges):
                output.risk_flags.append("dependency_cycle_detected")
                output.messages.append(
                    AgentMessage(
                        from_agent=self.name,
                        to_agent="tests",
                        kind="simulation.requested",
                        content={"reason": "cycle_detected"},
                    )
                )
            missing = self._missing_dependencies(edges)
            if missing:
                output.risk_flags.append("missing_dependencies")
                output.questions.append(f"Missing dependencies for nodes: {','.join(sorted(missing))}")
                output.messages.append(
                    AgentMessage(
                        from_agent=self.name,
                        to_agent="procurement",
                        kind="mitigation.requested",
                        content={"missing_dependencies": sorted(missing)},
                    )
                )
            output.proposed_actions.append(
                {
                    "action_type": "os.update_project_plan",
                    "priority": 2,
                    "metadata": {"source_agent": self.name, "dependency_issues": len(output.risk_flags)},
                }
            )

        self._maybe_enrich_with_llm(agent_input, output)
        return output

    def _maybe_enrich_with_llm(self, agent_input: AgentInput, output: AgentOutput) -> None:
        if not agent_input.enable_llm:
            return
        prompt = (
            f"Agent engineering summarize rationale and missing data questions for event={agent_input.event.event_type}. "
            f"Risk flags={output.risk_flags}."
        )
        completion = self.llm_client.complete(prompt)
        if completion:
            output.rationale = completion

    @staticmethod
    def _missing_dependencies(edges: dict[str, list[str]]) -> set[str]:
        known_nodes = set(edges.keys())
        missing: set[str] = set()
        for dependencies in edges.values():
            for dep in dependencies:
                if dep not in known_nodes:
                    missing.add(dep)
        return missing

    @staticmethod
    def _has_cycle(edges: dict[str, list[str]]) -> bool:
        visiting: set[str] = set()
        visited: set[str] = set()

        def dfs(node: str) -> bool:
            if node in visiting:
                return True
            if node in visited:
                return False
            visiting.add(node)
            for neighbor in edges.get(node, []):
                if dfs(neighbor):
                    return True
            visiting.remove(node)
            visited.add(node)
            return False

        for node in edges:
            if dfs(node):
                return True
        return False
