"""PCE-OS robotics digital twin models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Supplier(BaseModel):
    """Supplier profile with lead-time and reliability signals."""

    supplier_id: str
    name: str
    reliability_score: float = Field(default=0.7, ge=0.0, le=1.0)
    avg_lead_time_days: int = Field(default=14, ge=0)


class Component(BaseModel):
    """BOM component candidate or acquired part."""

    component_id: str
    name: str
    category: str = "general"
    quantity: int = Field(default=1, ge=1)
    estimated_unit_cost: float = Field(default=0.0, ge=0.0)
    selected_supplier_id: str | None = None
    status: str = "planned"
    risk_level: str = Field(default="LOW", pattern="^(LOW|MEDIUM|HIGH)$")


class DependencyGraph(BaseModel):
    """Simple adjacency representation for build dependencies."""

    edges: dict[str, list[str]] = Field(default_factory=dict)


class CostProjection(BaseModel):
    """Current aggregate projection for cost and procurement risk."""

    projected_total_cost: float = Field(default=0.0, ge=0.0)
    projected_risk_buffer: float = Field(default=0.0, ge=0.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class SimulationResult(BaseModel):
    """Result of one simulation pass used to steer planning."""

    simulation_id: str
    scenario: str
    projected_cost: float = Field(default=0.0, ge=0.0)
    projected_risk_level: str = Field(default="LOW", pattern="^(LOW|MEDIUM|HIGH)$")
    notes: str = ""


class TestResult(BaseModel):
    """Structured test execution outcome."""

    test_id: str
    component_id: str
    passed: bool
    measured_metrics: dict[str, float] = Field(default_factory=dict)
    notes: str = ""


class RobotProjectState(BaseModel):
    """Root digital twin state persisted in PCE global state slice."""

    schema_version: str = "v0"
    project_id: str = "robotics-v0"
    phase: str = "planning"
    budget_total: float = Field(default=0.0, ge=0.0)
    budget_remaining: float = Field(default=0.0)
    risks: list[str] = Field(default_factory=list)
    risk_level: str = Field(default="LOW", pattern="^(LOW|MEDIUM|HIGH)$")
    components: list[Component] = Field(default_factory=list)
    suppliers: list[Supplier] = Field(default_factory=list)
    dependency_graph: DependencyGraph = Field(default_factory=DependencyGraph)
    cost_projection: CostProjection = Field(default_factory=CostProjection)
    simulations: list[SimulationResult] = Field(default_factory=list)
    tests: list[TestResult] = Field(default_factory=list)
    purchase_history: list[dict[str, object]] = Field(default_factory=list)
    audit_trail: list[dict[str, object]] = Field(default_factory=list)
