from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kosmohak.domain.plan import OperatorPlan
from kosmohak.domain.result import SimulationResult
from kosmohak.optimization.distance import PlanDistance
from kosmohak.optimization.patch import PlanPatch


@dataclass
class SuggestedPlan:
    base_plan_id: str
    patch: PlanPatch
    resulting_plan: OperatorPlan
    changed_decisions: list[dict[str, Any]]
    distance: PlanDistance
    original_result: SimulationResult
    suggested_result: SimulationResult
    stress_before: SimulationResult
    stress_after: SimulationResult
    archetype: str | None = None

    @property
    def cost_delta_mln(self) -> float:
        return (
            self.suggested_result.summary["undiscounted_cost_mln"]
            - self.original_result.summary["undiscounted_cost_mln"]
        )

    def to_dict(self) -> dict[str, Any]:
        before_codes = [item.code for item in self.original_result.violations]
        after_codes = [item.code for item in self.suggested_result.violations]
        return {
            "base_plan_id": self.base_plan_id,
            "suggested_plan_id": self.resulting_plan.plan_id,
            "archetype": self.archetype,
            "patch": self.patch.to_dict(),
            "changed_decisions": self.changed_decisions,
            "distance": self.distance.to_dict(),
            "base_before": self.original_result.summary,
            "base_after": self.suggested_result.summary,
            "stress_before": self.stress_before.summary,
            "stress_after": self.stress_after.summary,
            "cost_delta_mln": self.cost_delta_mln,
            "service_delta": self.suggested_result.summary["total_service_level"] - self.original_result.summary["total_service_level"],
            "shortage_delta_t": self.suggested_result.summary["total_shortage_t"] - self.original_result.summary["total_shortage_t"],
            "violations_removed": sorted(set(before_codes) - set(after_codes)),
            "violations_introduced": sorted(set(after_codes) - set(before_codes)),
        }


@dataclass
class OptimizationResult:
    mode: str
    original_plan_id: str
    status: str
    suggestions: list[SuggestedPlan]
    evaluated_candidates: int
    feasible_candidates: int
    search_config: dict[str, Any]
    seed: int
    locks: dict[str, Any]
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "original_plan_id": self.original_plan_id,
            "status": self.status,
            "suggestions": [item.to_dict() for item in self.suggestions],
            "evaluated_candidates": self.evaluated_candidates,
            "feasible_candidates": self.feasible_candidates,
            "search_config": self.search_config,
            "seed": self.seed,
            "locks": self.locks,
            "message": self.message,
        }
