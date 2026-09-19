from pathlib import Path

from kosmohak.builder import StrategyBuilderConfig, build_strategies
from kosmohak.loading import AssumptionsLoader, CaseDataLoader, ScenarioLoader

ROOT = Path(__file__).resolve().parents[2]


def test_builder_finds_97_99_mandatory_stress_strategy():
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
            max_candidates=600,
            beam_width=24,
            max_iterations=8,
            max_results=1,
            seed=17,
        ),
    )

    print("STATUS", result.status)
    print("EVALUATED", result.evaluated_candidate_count)
    print("ITERATIONS", result.iterations)
    print("FAILURE", result.failure_reason)
    print("CLOSEST", result.search_metadata.get("closest_base_valid"))
    if result.solutions:
        solution = result.solutions[0]
        print("METRICS", solution.metrics)
        print("HISTORY", solution.mutation_history)
        print("PLAN", solution.plan.raw)

    assert result.status == "success"
    solution = result.solutions[0]
    assert solution.base_result.summary["valid"] is True
    assert min(row["total_service_level"] for row in solution.stress_result.annual) >= 0.97 - 1e-12
    assert min(row["critical_service_level"] for row in solution.stress_result.annual) >= 0.99 - 1e-12
