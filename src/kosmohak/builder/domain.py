from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from kosmohak.domain.plan import OperatorPlan
from kosmohak.domain.result import SimulationResult


SUPPORTED_OBJECTIVES = {"MIN_COST", "MAX_RESILIENCE"}


@dataclass(frozen=True)
class StrategyBuilderConfig:
    objective: str = "MIN_COST"
    stress_total_service_target: float | None = None
    stress_critical_service_target: float | None = None
    max_total_cost_mln: float | None = None
    max_candidates: int = 3000
    beam_width: int = 20
    max_iterations: int = 8
    max_results: int = 3
    seed: int = 42
    mutation_fractions: tuple[float, ...] = (0.10, 0.25)
    diversity_threshold: float = 0.08

    def __post_init__(self) -> None:
        objective = str(self.objective).upper()
        object.__setattr__(self, "objective", objective)
        if objective not in SUPPORTED_OBJECTIVES:
            raise ValueError(
                f"Unsupported Strategy Builder objective: {self.objective!r}"
            )
        for name, value in (
            ("stress_total_service_target", self.stress_total_service_target),
            (
                "stress_critical_service_target",
                self.stress_critical_service_target,
            ),
        ):
            if value is not None and not 0.0 <= float(value) <= 1.0:
                raise ValueError(f"{name} must be within 0..1")
        if self.max_total_cost_mln is not None and self.max_total_cost_mln < 0:
            raise ValueError("max_total_cost_mln cannot be negative")
        for name, value in (
            ("max_candidates", self.max_candidates),
            ("beam_width", self.beam_width),
            ("max_results", self.max_results),
        ):
            if int(value) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.max_iterations < 0:
            raise ValueError("max_iterations cannot be negative")
        if not self.mutation_fractions:
            raise ValueError("mutation_fractions cannot be empty")
        if any(not 0.0 < float(value) <= 1.0 for value in self.mutation_fractions):
            raise ValueError("mutation_fractions must be within (0, 1]")
        if not 0.0 <= self.diversity_threshold <= 2.0:
            raise ValueError("diversity_threshold must be within 0..2")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["mutation_fractions"] = list(self.mutation_fractions)
        return value


@dataclass
class StrategyBuilderSolution:
    plan: OperatorPlan
    base_result: SimulationResult
    stress_result: SimulationResult
    metrics: dict[str, Any]
    target_satisfaction: dict[str, Any]
    provenance: dict[str, Any]
    search_depth: int
    mutation_history: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan": self.plan.raw,
            "base_summary": self.base_result.summary,
            "stress_summary": self.stress_result.summary,
            "metrics": self.metrics,
            "target_satisfaction": self.target_satisfaction,
            "provenance": self.provenance,
            "search_depth": self.search_depth,
            "mutation_history": list(self.mutation_history),
        }


@dataclass
class StrategyBuilderResult:
    status: str
    config: dict[str, Any]
    evaluated_candidate_count: int
    iterations: int
    solutions: list[StrategyBuilderSolution]
    search_metadata: dict[str, Any] = field(default_factory=dict)
    failure_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "config": self.config,
            "evaluated_candidate_count": self.evaluated_candidate_count,
            "iterations": self.iterations,
            "solutions": [item.to_dict() for item in self.solutions],
            "search_metadata": self.search_metadata,
            "failure_reason": self.failure_reason,
        }
