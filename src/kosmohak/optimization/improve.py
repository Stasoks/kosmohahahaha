from __future__ import annotations

from kosmohak.domain.assumptions import ModelAssumptions
from kosmohak.domain.case import CaseData
from kosmohak.domain.plan import OperatorPlan
from kosmohak.domain.scenario import Scenario
from kosmohak.optimization.domain import DecisionLocks, OptimizerConfig
from kosmohak.optimization.evaluator import evaluate_candidates
from kosmohak.optimization.objectives import improve_rank
from kosmohak.optimization.result import OptimizationResult
from kosmohak.optimization.search_space import improvement_candidates
from kosmohak.simulation.engine import simulate


def improve_plan(
    plan: OperatorPlan,
    base_scenario: Scenario,
    stress_scenario: Scenario,
    case_data: CaseData,
    assumptions: ModelAssumptions,
    *,
    locks: DecisionLocks | None = None,
    config: OptimizerConfig | None = None,
) -> OptimizationResult:
    locks = locks or DecisionLocks()
    config = config or OptimizerConfig()
    original = simulate(plan, base_scenario, case_data, assumptions)
    if not original.summary["valid"]:
        return OptimizationResult(
            "IMPROVE", plan.plan_id, "original_infeasible", [], 0, 0,
            config.to_dict(), config.seed, locks.to_dict(), "IMPROVE requires a BASE-valid original plan."
        )
    values, count = evaluate_candidates(
        mode="IMPROVE", original=plan,
        candidate_raws=improvement_candidates(plan, config),
        base_scenario=base_scenario, stress_scenario=stress_scenario,
        case_data=case_data, assumptions=assumptions, locks=locks, config=config,
    )
    feasible = [
        item for item in values
        if item.suggested_result.summary["valid"] and item.cost_delta_mln <= 1e-9
    ]
    feasible.sort(key=improve_rank)
    selected = feasible[: config.max_suggestions]
    return OptimizationResult(
        "IMPROVE", plan.plan_id, "success" if selected else "no_improvement_found",
        selected, count, len(feasible), config.to_dict(), config.seed, locks.to_dict()
    )
