from pathlib import Path

from kosmohak.loading import AssumptionsLoader, CaseDataLoader, ScenarioLoader
from kosmohak.builder import StrategyBuilderConfig, build_strategies

ROOT = Path(__file__).resolve().parents[2]


def test_builder_reaches_official_stress_benchmarks_with_bounded_budget():
    case_data = CaseDataLoader.load(ROOT)
    assumptions = AssumptionsLoader.load(ROOT / "configs/model_assumptions.json")
    base = ScenarioLoader.load("BASE", ROOT)
    stress = ScenarioLoader.load("MANDATORY_STRESS", ROOT)
    result = build_strategies(
        base_scenario=base,
        stress_scenario=stress,
        case_data=case_data,
        assumptions=assumptions,
        config=StrategyBuilderConfig(
            objective="MIN_COST",
            stress_total_service_target=0.97,
            stress_critical_service_target=0.99,
            max_candidates=800,
            beam_width=20,
            max_iterations=8,
            max_results=1,
            seed=17,
        ),
    )
    print("STATUS", result.status, "EVALUATED", result.evaluated_candidate_count)
    if result.solutions:
        s = result.solutions[0]
        print("COST", s.metrics["total_cost_mln"])
        print("STRESS_TOTAL_MIN", s.metrics["minimum_annual_stress_total_service"])
        print("STRESS_CRITICAL_MIN", s.metrics["minimum_annual_stress_critical_service"])
        print("DEPTH", s.search_depth)
        print("HISTORY", s.mutation_history)
    else:
        print("FAILURE", result.failure_reason)
    assert result.status == "success"
    assert result.solutions[0].base_result.summary["valid"] is True
    assert result.solutions[0].metrics["minimum_annual_stress_total_service"] >= 0.97 - 1e-12
    assert result.solutions[0].metrics["minimum_annual_stress_critical_service"] >= 0.99 - 1e-12
