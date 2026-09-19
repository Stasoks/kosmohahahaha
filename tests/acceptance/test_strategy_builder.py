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
        "planning_mode": "BASE_PLAN",
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


def test_builder_01_base_mode_returns_standard_plan_valid_under_all_hard_constraints(
    case_data, assumptions, base_scenario, stress_scenario
):
    result = _build(case_data, assumptions, base_scenario, stress_scenario)
    assert result.status == "success"
    assert result.solutions
    for solution in result.solutions:
        assert solution.plan.scenario_id == "BASE"
        assert solution.base_result.summary["valid"] is True
        assert solution.base_result.summary["hard_violation_count"] == 0
        assert solution.provenance["planning_mode"] == "BASE_PLAN"


def test_builder_02_base_mode_enforces_official_97_total_and_99_critical_each_year(
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
    total_limit = case_data.constraints["BASE_TOTAL_SERVICE"].value
    critical_limit = case_data.constraints["BASE_CRITICAL_SERVICE"].value
    for row in solution.base_result.annual:
        assert row["total_service_level"] >= total_limit - 1e-12
        assert row["critical_service_level"] >= critical_limit - 1e-12


def test_builder_03_base_plan_may_miss_stress_benchmarks_without_becoming_invalid_base_plan(
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
    assert solution.base_result.summary["valid"] is True
    assert solution.benchmark_status["stress_total_service"]["severity"] == "benchmark"
    assert solution.benchmark_status["stress_critical_service"]["severity"] == "benchmark"
    assert (
        solution.benchmark_status["stress_total_service"]["benchmark"]
        == case_data.constraints["BASE_TOTAL_SERVICE"].value
    )
    assert (
        solution.benchmark_status["stress_critical_service"]["benchmark"]
        == case_data.constraints["BASE_CRITICAL_SERVICE"].value
    )
    assert solution.benchmark_status["stress_total_service"]["met"] is False


def test_builder_04_stress_adaptation_builds_separate_stress_valid_plan(
    case_data, assumptions, base_scenario, stress_scenario
):
    result = _build(
        case_data,
        assumptions,
        base_scenario,
        stress_scenario,
        planning_mode="STRESS_ADAPTATION",
        max_results=3,
    )
    assert result.status == "success"
    assert result.solutions
    for solution in result.solutions:
        assert solution.plan.scenario_id == "MANDATORY_STRESS"
        assert solution.stress_result.summary["valid"] is True
        assert solution.stress_result.summary["hard_violation_count"] == 0
        assert solution.provenance["planning_mode"] == "STRESS_ADAPTATION"


def test_builder_05_official_case_stress_adaptation_can_reach_both_resilience_benchmarks(
    case_data, assumptions, base_scenario, stress_scenario
):
    result = _build(
        case_data,
        assumptions,
        base_scenario,
        stress_scenario,
        planning_mode="STRESS_ADAPTATION",
        max_results=1,
    )
    solution = result.solutions[0]
    total_benchmark = case_data.constraints["BASE_TOTAL_SERVICE"].value
    critical_benchmark = case_data.constraints["BASE_CRITICAL_SERVICE"].value
    assert solution.metrics["minimum_annual_stress_total_service"] >= total_benchmark - 1e-12
    assert solution.metrics["minimum_annual_stress_critical_service"] >= critical_benchmark - 1e-12
    assert solution.benchmark_status["stress_total_service"]["met"] is True
    assert solution.benchmark_status["stress_critical_service"]["met"] is True


def test_builder_06_stress_adaptation_is_not_rejected_only_because_same_plan_fails_base(
    case_data, assumptions, base_scenario, stress_scenario
):
    result = _build(
        case_data,
        assumptions,
        base_scenario,
        stress_scenario,
        planning_mode="STRESS_ADAPTATION",
        max_results=1,
    )
    solution = result.solutions[0]
    assert solution.stress_result.summary["valid"] is True
    assert solution.base_result.summary["valid"] is False
    assert result.status == "success"


def test_builder_07_every_returned_plan_passes_normal_plan_validation(
    case_data, assumptions, base_scenario, stress_scenario
):
    for mode in ("BASE_PLAN", "STRESS_ADAPTATION"):
        result = _build(
            case_data,
            assumptions,
            base_scenario,
            stress_scenario,
            planning_mode=mode,
            max_results=2,
        )
        for solution in result.solutions:
            PlanLoader.validate(solution.plan, case_data, assumptions)


def test_builder_08_results_match_fresh_authoritative_digital_twin_runs(
    case_data, assumptions, base_scenario, stress_scenario
):
    for mode in ("BASE_PLAN", "STRESS_ADAPTATION"):
        result = _build(
            case_data,
            assumptions,
            base_scenario,
            stress_scenario,
            planning_mode=mode,
            max_results=1,
        )
        solution = result.solutions[0]
        base = simulate(solution.plan, base_scenario, case_data, assumptions)
        stress = simulate(solution.plan, stress_scenario, case_data, assumptions)
        assert base.summary == solution.base_result.summary
        assert stress.summary == solution.stress_result.summary
        assert base.annual == solution.base_result.annual
        assert stress.annual == solution.stress_result.annual


def test_builder_09_stress_planning_cost_comes_from_stress_not_base(
    case_data, assumptions, base_scenario, stress_scenario
):
    result = _build(
        case_data,
        assumptions,
        base_scenario,
        stress_scenario,
        planning_mode="STRESS_ADAPTATION",
        max_results=1,
    )
    solution = result.solutions[0]
    assert (
        solution.metrics["total_cost_mln"]
        == solution.stress_result.summary["undiscounted_cost_mln"]
    )
    assert (
        solution.metrics["stress_total_cost_mln"]
        == solution.stress_result.summary["undiscounted_cost_mln"]
    )


def test_builder_10_min_cost_orders_solutions_by_planning_scenario_cost(
    case_data, assumptions, base_scenario, stress_scenario
):
    for mode in ("BASE_PLAN", "STRESS_ADAPTATION"):
        result = _build(
            case_data,
            assumptions,
            base_scenario,
            stress_scenario,
            planning_mode=mode,
            objective="MIN_COST",
            max_results=3,
        )
        costs = [solution.metrics["total_cost_mln"] for solution in result.solutions]
        assert costs == sorted(costs)


def test_builder_11_hard_cost_cap_is_enforced_without_fabricating_solution(
    case_data, assumptions, base_scenario, stress_scenario
):
    for mode in ("BASE_PLAN", "STRESS_ADAPTATION"):
        result = _build(
            case_data,
            assumptions,
            base_scenario,
            stress_scenario,
            planning_mode=mode,
            max_total_cost_mln=0.0,
        )
        assert result.status == "no_target_satisfying_plan_found"
        assert result.solutions == []
        assert "global infeasibility" not in result.failure_reason.lower()
        assert result.search_metadata["global_optimum_claimed"] is False


def test_builder_12_soft_stress_targets_are_preferences_not_official_hard_constraints(
    case_data, assumptions, base_scenario, stress_scenario
):
    result = _build(
        case_data,
        assumptions,
        base_scenario,
        stress_scenario,
        planning_mode="BASE_PLAN",
        stress_total_service_target=0.99,
        stress_critical_service_target=1.0,
        stress_target_policy="SOFT",
        max_results=1,
    )
    solution = result.solutions[0]
    assert result.status == "success"
    assert solution.target_satisfaction["stress_total_service"]["policy"] == "SOFT"
    assert solution.target_satisfaction["stress_critical_service"]["policy"] == "SOFT"
    assert solution.target_satisfaction["all_hard_satisfied"] is True


def test_builder_13_hard_operator_stress_target_is_explicitly_supported(
    case_data, assumptions, base_scenario, stress_scenario
):
    result = _build(
        case_data,
        assumptions,
        base_scenario,
        stress_scenario,
        planning_mode="STRESS_ADAPTATION",
        stress_total_service_target=0.97,
        stress_critical_service_target=0.99,
        stress_target_policy="HARD",
        max_results=1,
    )
    assert result.status == "success"
    solution = result.solutions[0]
    assert solution.target_satisfaction["all_hard_satisfied"] is True
    assert solution.target_satisfaction["stress_total_service"]["satisfied"] is True
    assert solution.target_satisfaction["stress_critical_service"]["satisfied"] is True


def test_builder_14_multistep_search_still_supports_robust_single_plan_target(
    case_data, assumptions, base_scenario, stress_scenario
):
    result = _build(
        case_data,
        assumptions,
        base_scenario,
        stress_scenario,
        planning_mode="BASE_PLAN",
        objective="MAX_RESILIENCE",
        stress_total_service_target=0.90,
        stress_target_policy="HARD",
        max_candidates=220,
        beam_width=10,
        max_iterations=4,
        max_results=1,
    )
    assert result.status == "success"
    solution = result.solutions[0]
    assert solution.metrics["minimum_annual_stress_total_service"] >= 0.90 - 1e-12
    assert solution.search_depth >= 2
    assert len(solution.mutation_history) >= 2


def test_builder_15_is_deterministic_in_both_planning_modes(
    case_data, assumptions, base_scenario, stress_scenario
):
    for mode in ("BASE_PLAN", "STRESS_ADAPTATION"):
        config = dict(
            planning_mode=mode,
            objective="MIN_COST",
            max_candidates=60,
            max_iterations=1,
            max_results=2,
        )
        first = _build(
            case_data,
            assumptions,
            base_scenario,
            stress_scenario,
            **config,
        )
        second = _build(
            case_data,
            assumptions,
            base_scenario,
            stress_scenario,
            **config,
        )
        assert first.to_dict() == second.to_dict()


def test_builder_16_does_not_mutate_case_scenarios_or_assumptions(
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
        planning_mode="STRESS_ADAPTATION",
        max_candidates=60,
        max_iterations=1,
    )

    assert case_data == before_case
    assert assumptions == before_assumptions
    assert base_scenario == before_base
    assert stress_scenario == before_stress


def test_builder_17_service_facade_supports_both_modes_and_advisor_regression(
    plan, case_data, assumptions, base_scenario, stress_scenario
):
    for mode in ("BASE_PLAN", "STRESS_ADAPTATION"):
        built = synthesize_strategy(
            base_scenario,
            stress_scenario,
            case_data,
            assumptions,
            config=_config(planning_mode=mode, max_results=1),
        )
        assert isinstance(built, StrategyBuilderResult)
        assert built.status == "success"
        assert built.search_metadata["planning_mode"] == mode

    advisor = repair_strategy(
        plan,
        base_scenario,
        stress_scenario,
        case_data,
        assumptions,
        config=OptimizerConfig(max_candidates=20, seed=17),
    )
    assert advisor.mode == "REPAIR"
    assert advisor.original_plan_id == plan.plan_id


def test_builder_18_metadata_matches_official_service_rule_interpretation(
    case_data, assumptions, base_scenario, stress_scenario
):
    result = _build(case_data, assumptions, base_scenario, stress_scenario)
    rules = result.search_metadata["official_service_interpretation"]
    assert rules["BASE"]["severity"] == "hard"
    assert rules["MANDATORY_STRESS"]["severity"] == "benchmark"
    assert (
        rules["BASE"]["total_service_minimum"]
        == case_data.constraints["BASE_TOTAL_SERVICE"].value
    )
    assert (
        rules["BASE"]["critical_service_minimum"]
        == case_data.constraints["BASE_CRITICAL_SERVICE"].value
    )
    assert (
        rules["MANDATORY_STRESS"]["total_service_benchmark"]
        == case_data.constraints["BASE_TOTAL_SERVICE"].value
    )
    assert (
        rules["MANDATORY_STRESS"]["critical_service_benchmark"]
        == case_data.constraints["BASE_CRITICAL_SERVICE"].value
    )


def test_builder_19_config_rejects_invalid_modes_targets_and_limits():
    with pytest.raises(ValueError):
        StrategyBuilderConfig(planning_mode="MAGIC")
    with pytest.raises(ValueError):
        StrategyBuilderConfig(stress_target_policy="MAYBE")
    with pytest.raises(ValueError):
        StrategyBuilderConfig(stress_total_service_target=1.01)
    with pytest.raises(ValueError):
        StrategyBuilderConfig(stress_critical_service_target=-0.01)
    with pytest.raises(ValueError):
        StrategyBuilderConfig(max_total_cost_mln=-1.0)
    with pytest.raises(ValueError):
        StrategyBuilderConfig(max_candidates=0)
