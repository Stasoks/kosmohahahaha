from pathlib import Path

from kosmohak.loading import AssumptionsLoader, CaseDataLoader, ScenarioLoader
from kosmohak.builder import StrategyBuilderConfig, build_strategies

ROOT = Path(__file__).resolve().parents[2]


def test_official_builder_reaches_97_total_99_critical_stress():
    case_data = CaseDataLoader.load(ROOT)
    assumptions = AssumptionsLoader.load(ROOT / "configs" / "model_assumptions.json")
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
            max_candidates=3000,
            beam_width=20,
            max_iterations=8,
            max_results=3,
            seed=17,
        ),
    )

    print("STATUS", result.status)
    print("EVALUATED", result.evaluated_candidate_count)
    print("ITERATIONS", result.iterations)
    print("FAILURE", result.failure_reason)
    for i, solution in enumerate(result.solutions, 1):
        print(
            "SOLUTION",
            i,
            "COST", solution.metrics["total_cost_mln"],
            "STRESS_TOTAL_MIN", solution.metrics["minimum_annual_stress_total_service"],
            "STRESS_CRITICAL_MIN", solution.metrics["minimum_annual_stress_critical_service"],
            "DEPTH", solution.search_depth,
            "HISTORY", solution.mutation_history,
        )

    assert result.status == "success"
    assert result.solutions
    best = result.solutions[0]
    assert best.base_result.summary["valid"] is True
    assert best.metrics["minimum_annual_stress_total_service"] >= 0.97 - 1e-12
    assert best.metrics["minimum_annual_stress_critical_service"] >= 0.99 - 1e-12
