from __future__ import annotations

import json
from pathlib import Path

from kosmohak import compare_plans, evaluate_both_scenarios
from kosmohak.loading import PlanLoader, RiskLoader
from kosmohak.optimization import (
    OptimizerConfig,
    reopen_suggested_plan,
    repair_plan,
    save_optimization_result,
)
from kosmohak.reporting import export_plan_comparison
from kosmohak.simulation import simulate


ROOT = Path(__file__).resolve().parents[2]


def test_three_demonstration_strategies_are_distinct_and_base_valid(
    case_data, assumptions, base_scenario, stress_scenario
):
    paths = [
        ROOT / "plans/cost_focused.json",
        ROOT / "plans/diversified.json",
        ROOT / "plans/resilient.json",
    ]
    plans = [PlanLoader.load(path, case_data, assumptions) for path in paths]
    assert len({json.dumps(plan.raw["decisions"], sort_keys=True) for plan in plans}) == 3
    comparison = compare_plans(
        plans, base_scenario, stress_scenario, case_data, assumptions
    )
    assert comparison["winner_selected"] is False
    assert all(row["base_valid"] for row in comparison["plans"])
    assert all("stress_shortage_t" in row for row in comparison["plans"])
    assert len({row["stress_shortage_t"] for row in comparison["plans"]}) == 3


def test_comparison_and_stable_ui_pair_api_export(
    tmp_path, plan, case_data, assumptions, base_scenario, stress_scenario
):
    pair = evaluate_both_scenarios(
        plan, base_scenario, stress_scenario, case_data, assumptions
    )
    assert pair["BASE"].summary["plan_id"] == plan.plan_id
    comparison = compare_plans(
        [plan],
        base_scenario,
        stress_scenario,
        case_data,
        assumptions,
        risks=RiskLoader.load(ROOT / "configs/risks/team_risks.json"),
    )
    assert len(comparison["plans"][0]["risk_consequences"]) == 8
    directory = export_plan_comparison(comparison, tmp_path)
    assert (directory / "strategy_comparison.json").is_file()
    assert (directory / "strategy_comparison.csv").is_file()


def test_saved_repair_patch_reopens_to_same_result(
    tmp_path, case_data, assumptions, base_scenario, stress_scenario
):
    raw = json.loads((ROOT / "configs/operator_plan_example.json").read_text(encoding="utf-8"))
    raw["plan_id"] = "repair-overcapacity-serialization"
    reservation = next(
        item for item in raw["decisions"]["capacity_reservations"]
        if item["source_id"] == "A" and item["year"] == 2035
    )
    reservation["reserved_capacity_t"] = 200
    path = tmp_path / "overcapacity-serialization.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    plan = PlanLoader.load(path, case_data, assumptions)
    result = repair_plan(
        plan,
        base_scenario,
        stress_scenario,
        case_data,
        assumptions,
        config=OptimizerConfig(seed=33),
    )
    directory = save_optimization_result(result, tmp_path / "optimizer")
    suggestion = result.suggestions[0]
    reopened = reopen_suggested_plan(
        plan,
        directory / "suggestion-01/patch.json",
        plan_id=suggestion.resulting_plan.plan_id,
    )
    reopened_result = simulate(reopened, base_scenario, case_data, assumptions)
    assert reopened.raw == suggestion.resulting_plan.raw
    assert reopened_result.to_dict() == suggestion.suggested_result.to_dict()
