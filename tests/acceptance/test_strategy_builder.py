from __future__ import annotations

import copy

import pytest

from kosmohak.builder import StrategyBuilderConfig, build_strategies
from kosmohak.loading.plan import PlanLoader
from kosmohak.service import (
    OptimizerConfig,
    StrategyBuilderResult,
    repair_strategy,
    synthesize_strategy,
)
from kosmohak.simulation.engine import simulate


def _config(**overrides):
    values = {
        "max_candidates": 40,
        "beam_width": 8,
        "max_iterations": 0,
        "max_results": 3,
        "seed": 17,
    }
    values.update(overrides)
    return StrategyBuilderConfig(**values)


def _build(case_data, assumptions, base_scenario, stress_scenario, **overrides):
    return build_strategies(
        base_scenario=base_scenario,
        stress_scenario=stress_scenario,
        case_data=case_data,
        assumptions=assumptions,
        config=_config(**overrides),
    )


def test_builder_01_builds_base_valid_strategy_from_official_inputs(
    case_data, assumptions, base_scenario, stress_scenario
):
    result = _build(case_data, assumptions, base_scenario, stress_scenario)
    assert result.status == "success"
    assert result.solutions
    assert all(solution.base_result.summary["valid"] for solution in result.solutions)
    assert all(
        solution.base_result.summary["hard_violation_count"] == 0
        for solution in result.solutions
    )


def test_builder_02_returned_plans_pass_normal_plan_validation(
    case_data, assumptions, base_scenario, stress_scenario
):
    result = _build(case_data, assumptions, base_scenario, stress_scenario)
    for solution in result.solutions:
        PlanLoader.validate(solution.plan, case_data, assumptions)


def test_builder_03_saved_results_match_fresh_digital_twin_runs(
    case_data, assumptions, base_scenario, stress_scenario
):
    result = _build(
        case_data,
        assumptions,
        base_scenario,
        stress_scenario,
        max_results=1,
    )
    solution = result.solutions[0]
    base = simulate(solution.plan, base_scenario, case_data, assumptions)
    stress = simulate(solution.plan, stress_scenario, case_data, assumptions)
    assert base.summary == solution.base_result.summary
    assert stress.summary == solution.stress_result.summary
    assert base.annual == solution.base_result.annual
    assert stress.annual == solution.stress_result.annual


def test_builder_04_multistep_beam_search_reaches_target(
    case_data, assumptions, base_scenario, stress_scenario
):
    result = _build(
        case_data,
        assumptions,
        base_scenario,
        stress_scenario,
        objective="MAX_RESILIENCE",
        stress_total_service_target=0.90,
        max_candidates=180,
        beam_width=10,
        max_iterations=4,
        max_results=1,
    )
    assert result.status == "success"
    solution = result.solutions[0]
    assert solution.metrics["minimum_annual_stress_total_service"] >= 0.90 - 1e-12
    assert solution.search_depth >= 2
    assert len(solution.mutation_history) >= 2


def test_builder_05_annual_stress_service_target_is_enforced(
    case_data, assumptions, base_scenario, stress_scenario
):
    target = 0.80
    result = _build(
        case_data,
        assumptions,
        base_scenario,
        stress_scenario,
        objective="MAX_RESILIENCE",
        stress_total_service_target=target,
        max_candidates=100,
        beam_width=8,
        max_iterations=3,
        max_results=2,
    )
    assert result.status == "success"
    assert result.solutions
    for solution in result.solutions:
        annual_minimum = min(
            row["total_service_level"] for row in solution.stress_result.annual
        )
        assert annual_minimum >= target - 1e-12
        assert (
            solution.target_satisfaction["stress_total_service"]["actual"]
            == annual_minimum
        )


def test_builder_06_unreachable_cost_target_returns_no_fabricated_solution(
    case_data, assumptions, base_scenario, stress_scenario
):
    result = _build(
        case_data,
        assumptions,
        base_scenario,
        stress_scenario,
        max_total_cost_mln=0.0,
    )
    assert result.status == "no_target_satisfying_plan_found"
    assert result.solutions == []
    assert "global infeasibility" not in result.failure_reason.lower()
    assert result.search_metadata["global_optimum_claimed"] is False


def test_builder_07_min_cost_solutions_are_cost_ordered(
    case_data, assumptions, base_scenario, stress_scenario
):
    result = _build(
        case_data,
        assumptions,
        base_scenario,
        stress_scenario,
        objective="MIN_COST",
        max_results=3,
    )
    costs = [solution.metrics["total_cost_mln"] for solution in result.solutions]
    assert costs == sorted(costs)


def test_builder_08_is_deterministic_for_identical_inputs_and_seed(
    case_data, assumptions, base_scenario, stress_scenario
):
    first = _build(
        case_data,
        assumptions,
        base_scenario,
        stress_scenario,
        objective="MAX_RESILIENCE",
        max_candidates=70,
        max_iterations=2,
        max_results=2,
    )
    second = _build(
        case_data,
        assumptions,
        base_scenario,
        stress_scenario,
        objective="MAX_RESILIENCE",
        max_candidates=70,
        max_iterations=2,
        max_results=2,
    )
    assert first.to_dict() == second.to_dict()


def test_builder_09_does_not_mutate_case_scenarios_or_assumptions(
    case_data, assumptions, base_scenario, stress_scenario
):
    before_case = copy.deepcopy(case_data)
    before_assumptions = copy.deepcopy(assumptions)
    before_base = copy.deepcopy(base_scenario)
    before_stress = copy.deepcopy(stress_scenario)

    _build(
        case_data,
        assumptions,
        base_scenario,
        stress_scenario,
        max_candidates=70,
        max_iterations=1,
    )

    assert case_data == before_case
    assert assumptions == before_assumptions
    assert base_scenario == before_base
    assert stress_scenario == before_stress


def test_builder_10_service_facade_and_existing_advisor_both_work(
    plan, case_data, assumptions, base_scenario, stress_scenario
):
    built = synthesize_strategy(
        base_scenario,
        stress_scenario,
        case_data,
        assumptions,
        config=_config(max_results=1),
    )
    assert isinstance(built, StrategyBuilderResult)
    assert built.status == "success"
    assert built.solutions[0].base_result.summary["valid"] is True

    advisor = repair_strategy(
        plan,
        base_scenario,
        stress_scenario,
        case_data,
        assumptions,
        config=OptimizerConfig(max_candidates=20, seed=17),
    )
    assert advisor.mode == "REPAIR"
    assert advisor.base_plan_id == plan.plan_id


def test_builder_11_max_resilience_is_not_worse_than_min_cost_on_stress_service(
    case_data, assumptions, base_scenario, stress_scenario
):
    common = {
        "max_candidates": 100,
        "beam_width": 8,
        "max_iterations": 2,
        "max_results": 1,
    }
    cheap = _build(
        case_data,
        assumptions,
        base_scenario,
        stress_scenario,
        objective="MIN_COST",
        **common,
    )
    resilient = _build(
        case_data,
        assumptions,
        base_scenario,
        stress_scenario,
        objective="MAX_RESILIENCE",
        **common,
    )
    assert (
        resilient.solutions[0].metrics["minimum_annual_stress_critical_service"]
        >= cheap.solutions[0].metrics["minimum_annual_stress_critical_service"] - 1e-12
    )
    assert (
        resilient.solutions[0].metrics["minimum_annual_stress_total_service"]
        >= cheap.solutions[0].metrics["minimum_annual_stress_total_service"] - 1e-12
    )


def test_builder_12_config_rejects_invalid_targets_and_limits():
    with pytest.raises(ValueError):
        StrategyBuilderConfig(stress_total_service_target=1.01)
    with pytest.raises(ValueError):
        StrategyBuilderConfig(stress_critical_service_target=-0.01)
    with pytest.raises(ValueError):
        StrategyBuilderConfig(max_total_cost_mln=-1.0)
    with pytest.raises(ValueError):
        StrategyBuilderConfig(max_candidates=0)
