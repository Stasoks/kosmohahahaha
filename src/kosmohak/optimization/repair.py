from __future__ import annotations

from kosmohak.domain.assumptions import ModelAssumptions
from kosmohak.domain.case import CaseData
from kosmohak.domain.plan import OperatorPlan
from kosmohak.domain.scenario import Scenario
from kosmohak.optimization.domain import DecisionLocks, OptimizerConfig
from kosmohak.optimization.evaluator import evaluate_candidates
from kosmohak.optimization.objectives import repair_rank
from kosmohak.optimization.result import OptimizationResult
from kosmohak.optimization.search_space import repair_candidates
from kosmohak.simulation.engine import simulate


def repair_plan(
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
    if original.summary["valid"]:
        return OptimizationResult(
            "REPAIR", plan.plan_id, "already_feasible", [], 0, 0,
            config.to_dict(), config.seed, locks.to_dict(), "Original BASE plan is already valid."
        )
    raws = repair_candidates(plan, original, case_data)
    evaluated, count = evaluate_candidates(
        mode="REPAIR",
        original=plan,
        candidate_raws=raws,
        base_scenario=base_scenario,
        stress_scenario=stress_scenario,
        case_data=case_data,
        assumptions=assumptions,
        locks=locks,
        config=config,
    )
    feasible = [item for item in evaluated if item.suggested_result.summary["valid"]]
    feasible.sort(key=repair_rank)
    selected = feasible[: config.max_suggestions]
    return OptimizationResult(
        "REPAIR",
        plan.plan_id,
        "success" if selected else "no_feasible_repair_found",
        selected,
        count,
        len(feasible),
        config.to_dict(),
        config.seed,
        locks.to_dict(),
        "" if selected else "No candidate in the declared deterministic search space passed the full digital twin.",
    )
