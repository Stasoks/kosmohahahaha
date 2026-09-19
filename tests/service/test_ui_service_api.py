from __future__ import annotations

import copy
import json
import zipfile

import pytest
from pathlib import Path

from kosmohak.service import (
    UI_BACKEND_API_VERSION,
    OptimizerConfig,
    add_workspace_source,
    apply_strategy_suggestion,
    build_case_with_source_overrides,
    build_custom_environment,
    build_download_bundle,
    build_effective_case,
    build_future_year_spec,
    build_plan,
    build_research_source_spec,
    create_workspace,
    evaluate_both_scenarios,
    evaluate_plan,
    evaluate_risks,
    extend_workspace_horizon,
    load_application_context,
    load_case_workspace,
    load_plan,
    repair_strategy,
    run_sensitivity,
    save_case_workspace,
    save_plan,
    validate_plan,
)


ROOT = Path(__file__).resolve().parents[2]


def _raw_plan() -> dict:
    return json.loads(
        (ROOT / "configs/operator_plan_example.json").read_text(encoding="utf-8")
    )


def _research_workspace(case_data):
    raw = json.loads(
        (ROOT / "configs/research_workspace_example.json").read_text(
            encoding="utf-8"
        )
    )
    workspace = create_workspace(case_data)
    add_workspace_source(workspace, build_research_source_spec(raw["sources"][0]))
    extend_workspace_horizon(
        workspace, build_future_year_spec(raw["future_years"][0])
    )
    return workspace


def _extended_plan(effective_case, assumptions):
    raw = _raw_plan()
    raw["plan_id"] = "ui-api-extended"
    raw["decisions"]["inventory_policy"]["reserve_strategy_by_year"][
        "2041"
    ] = "physical"
    raw["decisions"]["emergency_role_by_year"]["2041"] = "reserve_only"
    return build_plan(raw, effective_case, assumptions)


def test_ui_api_01_context_loads_standard_application_inputs():
    context = load_application_context(ROOT)
    assert UI_BACKEND_API_VERSION == "1.0"
    assert context.case_data.status == "CASE_INPUT"
    assert context.base_scenario.scenario_id == "BASE"
    assert context.stress_scenario.scenario_id == "MANDATORY_STRESS"
    assert len(context.risks) == 8
    assert context.stakeholders is not None
    assert context.optional_config_errors == ()


def test_ui_api_02_build_and_validate_plan_without_mutating_raw(case_data, assumptions):
    raw = _raw_plan()
    original = copy.deepcopy(raw)
    plan = build_plan(raw, case_data, assumptions)
    assert plan.plan_id == raw["plan_id"]
    assert raw == original
    assert validate_plan(plan, case_data, assumptions).valid is True

    invalid = copy.deepcopy(raw)
    del invalid["decisions"]
    validation = validate_plan(invalid, case_data, assumptions)
    assert validation.valid is False
    assert validation.errors[0].code == "PLAN_VALIDATION_ERROR"
    assert validation.errors[0].field == "$"


def test_ui_api_03_plan_round_trip(tmp_path, case_data, assumptions):
    plan = build_plan(_raw_plan(), case_data, assumptions)
    path = save_plan(plan, tmp_path / "nested" / "plan.json")
    reopened = load_plan(path, case_data, assumptions)
    assert reopened.raw == plan.raw
    assert reopened == plan


def test_ui_api_04_evaluates_both_real_scenarios(
    plan, case_data, assumptions, base_scenario, stress_scenario
):
    pair = evaluate_both_scenarios(
        plan, base_scenario, stress_scenario, case_data, assumptions
    )
    assert set(pair) == {"BASE", "MANDATORY_STRESS", "comparison"}
    assert pair["BASE"].summary["scenario_id"] == "BASE"
    assert pair["MANDATORY_STRESS"].summary["scenario_id"] == "MANDATORY_STRESS"
    assert pair["comparison"]["plan_id"] == plan.plan_id


def test_ui_api_05_evaluates_risk_portfolio_through_facade(
    plan, case_data, assumptions, base_scenario
):
    context = load_application_context(ROOT)
    portfolio = evaluate_risks(
        plan,
        base_scenario,
        context.risks[:1],
        case_data,
        assumptions,
    )
    assert portfolio.plan_id == plan.plan_id
    assert len(portfolio.evaluations) == 1
    assert portfolio.evaluations[0].baseline_result.summary["run_id"]


def test_ui_api_06_runs_real_sensitivity(
    plan, case_data, assumptions, base_scenario
):
    result = run_sensitivity(
        plan,
        "demand_multiplier",
        [1.0, 1.05],
        base_scenario,
        case_data,
        assumptions,
    )
    assert [point["value"] for point in result.points] == [1.0, 1.05]
    assert all(point["run_id"] for point in result.points)


def test_ui_api_07_advisor_preview_is_immutable_and_apply_is_explicit(
    case_data, assumptions, base_scenario, stress_scenario
):
    raw = _raw_plan()
    raw["plan_id"] = "ui-api-repair"
    reservation = next(
        item
        for item in raw["decisions"]["capacity_reservations"]
        if item["source_id"] == "A" and item["year"] == 2035
    )
    reservation["reserved_capacity_t"] = 200
    plan = build_plan(raw, case_data, assumptions)
    original = copy.deepcopy(plan.raw)
    answer = repair_strategy(
        plan,
        base_scenario,
        stress_scenario,
        case_data,
        assumptions,
        config=OptimizerConfig(max_candidates=50, seed=17),
    )
    assert answer.suggestions
    assert plan.raw == original
    applied = apply_strategy_suggestion(
        plan, answer.suggestions[0], new_plan_id="ui-api-approved"
    )
    assert plan.raw == original
    assert applied.plan_id == "ui-api-approved"
    assert applied.raw["decisions"] == answer.suggestions[0].resulting_plan.raw[
        "decisions"
    ]


def test_ui_api_08_workspace_adds_source_f_and_year_2041(case_data):
    workspace = _research_workspace(case_data)
    effective = build_effective_case(workspace)
    assert "F" in effective.sources
    assert 2041 in effective.demand
    assert "F" not in case_data.sources
    assert 2041 not in case_data.demand


def test_ui_api_09_workspace_round_trip_preserves_case_and_run_id(
    tmp_path, case_data, assumptions, base_scenario
):
    workspace = _research_workspace(case_data)
    path = save_case_workspace(workspace, tmp_path / "case" / "workspace.json")
    reopened = load_case_workspace(path, case_data)
    first_case = build_effective_case(workspace)
    second_case = build_effective_case(reopened)
    assert first_case == second_case
    plan = _extended_plan(first_case, assumptions)
    first = evaluate_plan(plan, base_scenario, first_case, assumptions)
    second = evaluate_plan(plan, base_scenario, second_case, assumptions)
    assert first.summary["run_id"] == second.summary["run_id"]


def test_ui_api_10_download_bundle_contains_observable_contract(
    tmp_path, plan, case_data, assumptions, base_scenario, stress_scenario
):
    pair = evaluate_both_scenarios(
        plan, base_scenario, stress_scenario, case_data, assumptions
    )
    path = build_download_bundle(
        plan=plan,
        case_data=case_data,
        base_result=pair["BASE"],
        stress_result=pair["MANDATORY_STRESS"],
        comparison=pair["comparison"],
        output_path=tmp_path / "downloads" / "run.zip",
    )
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        assert {
            "plan.json",
            "manifest.json",
            "BASE/result.json",
            "BASE/summary.json",
            "MANDATORY_STRESS/result.json",
            "comparison/comparison.json",
            "comparison/comparison.csv",
        } <= names
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["plan_id"] == plan.plan_id
    assert manifest["run_ids"]["BASE"] == pair["BASE"].summary["run_id"]
    assert "export_timestamp" in manifest


def test_ui_api_11_source_overrides_are_non_destructive(
    case_data, assumptions, plan, base_scenario
):
    original_capacity = case_data.sources["B"].capacity_t_per_year
    edited = build_case_with_source_overrides(
        case_data,
        {
            "B": {
                "capacity_t_per_year": 95,
                "variable_cost_mln_per_t": 9.4,
                "selected_lead_time_months": 6,
            }
        },
    )
    assert case_data.sources["B"].capacity_t_per_year == original_capacity
    assert edited.sources["B"].capacity_t_per_year == 95
    assert edited.sources["B"].variable_cost_mln_per_t == 9.4
    assert assumptions.source_delivery_lead_months(edited.sources["B"]) == 6
    assert edited.sources["B"].status == "TEAM_ASSUMPTION"
    result = evaluate_plan(plan, base_scenario, edited, assumptions)
    assert result.summary["run_id"]


def test_ui_api_12_custom_scenario_composes_over_official_base(
    case_data, assumptions, plan, base_scenario
):
    environment = build_custom_environment(
        base_scenario,
        {
            "name": "Demand and price what-if",
            "period_start": "2038-01",
            "period_end": "2040-12",
            "factor_changes": [
                {
                    "factor": "total_demand_multiplier",
                    "value": 1.1,
                    "status": "TEAM_ASSUMPTION",
                },
                {
                    "factor": "critical_demand_multiplier",
                    "value": 1.1,
                    "status": "TEAM_ASSUMPTION",
                },
                {
                    "factor": "variable_price_multiplier",
                    "source_id": "A",
                    "value": 1.2,
                    "status": "TEAM_ASSUMPTION",
                },
            ],
        },
    )
    result = evaluate_plan(plan, environment, case_data, assumptions)
    row_2038 = next(row for row in result.annual if row["year"] == 2038)
    assert environment.base_scenario_id == "BASE"
    assert environment.environment_id == "BASE+CUSTOM-SCENARIO"
    assert row_2038["demand_total_t"] == pytest.approx(
        case_data.demand[2038].base_total_t * 1.1
    )
