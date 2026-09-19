from __future__ import annotations

import copy
import json
from pathlib import Path

from kosmohak.loading import PlanLoader
from kosmohak.optimization import (
    DecisionLocks,
    OptimizerConfig,
    improve_plan,
    improve_resilience,
    repair_plan,
)


ROOT = Path(__file__).resolve().parents[2]


def _overcapacity_plan(tmp_path, case_data, assumptions):
    raw = json.loads((ROOT / "configs/operator_plan_example.json").read_text(encoding="utf-8"))
    raw["plan_id"] = "repair-overcapacity"
    reservation = next(
        item for item in raw["decisions"]["capacity_reservations"]
        if item["source_id"] == "A" and item["year"] == 2035
    )
    reservation["reserved_capacity_t"] = 200
    path = tmp_path / "overcapacity.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return PlanLoader.load(path, case_data, assumptions)


def test_repair_is_real_reproducible_and_original_is_immutable(
    tmp_path, case_data, assumptions, base_scenario, stress_scenario
):
    plan = _overcapacity_plan(tmp_path, case_data, assumptions)
    before = copy.deepcopy(plan.raw)
    config = OptimizerConfig(max_candidates=50, seed=17)
    first = repair_plan(plan, base_scenario, stress_scenario, case_data, assumptions, config=config)
    second = repair_plan(plan, base_scenario, stress_scenario, case_data, assumptions, config=config)
    assert plan.raw == before
    assert first.status == "success"
    assert first.suggestions
    suggestion = first.suggestions[0]
    assert suggestion.original_result.summary["valid"] is False
    assert suggestion.suggested_result.summary["valid"] is True
    assert suggestion.patch.changes
    assert suggestion.distance.changed_decision_count > 0
    assert first.to_dict() == second.to_dict()


def test_locks_are_strict_and_impossible_search_reports_no_repair(
    tmp_path, case_data, assumptions, base_scenario, stress_scenario
):
    plan = _overcapacity_plan(tmp_path, case_data, assumptions)
    result = repair_plan(
        plan,
        base_scenario,
        stress_scenario,
        case_data,
        assumptions,
        locks=DecisionLocks(sources={"A": True}),
        config=OptimizerConfig(max_candidates=20, seed=9),
    )
    assert result.status == "no_feasible_repair_found"
    assert result.suggestions == []


def test_improve_and_resilience_return_only_property_safe_suggestions(
    plan, case_data, assumptions, base_scenario, stress_scenario
):
    improve = improve_plan(
        plan,
        base_scenario,
        stress_scenario,
        case_data,
        assumptions,
        config=OptimizerConfig(max_candidates=60, seed=4, allowed_change_budget=2),
    )
    for suggestion in improve.suggestions:
        assert suggestion.suggested_result.summary["valid"] is True
        assert suggestion.cost_delta_mln <= 1e-9
    resilience = improve_resilience(
        plan,
        base_scenario,
        stress_scenario,
        case_data,
        assumptions,
        config=OptimizerConfig(max_candidates=60, seed=4, allowed_change_budget=2),
    )
    for suggestion in resilience.suggestions:
        assert suggestion.suggested_result.summary["valid"] is True
        assert suggestion.stress_after.summary["total_shortage_t"] <= suggestion.stress_before.summary["total_shortage_t"] + 1e-9
