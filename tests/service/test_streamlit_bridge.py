from __future__ import annotations

import copy

from app.kernel_bridge import (
    abc_results,
    build_stress_specific,
    case_metadata,
    default_plan_path,
    default_plan_raw,
    mitigation_detail,
    official_demand_sensitivity,
    research_plan_template,
    result_csv_bytes,
    validate,
    workspace_add_source,
    workspace_bytes,
    workspace_extend_year,
    workspace_from_bytes,
    new_workspace,
)
from app.view_models import abc_comparison, source_colors


def _workspace_with_source() -> dict:
    return workspace_add_source(
        new_workspace(),
        {
            "source_id": "F",
            "name": "Research-F",
            "capacity_t_per_year": 24,
            "variable_cost_mln_per_t": 4.25,
            "reservation_rate_mln_per_t_year_capacity": 0.2,
            "take_or_pay_share": 0.5,
            "lead_time_min_value": 4,
            "lead_time_max_value": 4,
            "lead_time_unit": "month",
            "availability_rule": {"type": "calendar", "available_from": "2040-07"},
            "reliability_metadata": {"semantics": "metadata_only"},
            "notes": "Test research source.",
            "provenance": {"basis": "test", "source": "TEAM:test-source-F"},
            "selected_lead_time_months": None,
        },
    )


def _extend_2041(workspace: dict) -> dict:
    source_ids = list(case_metadata(workspace)["sources"])
    return workspace_extend_year(
        workspace,
        {
            "year": 2041,
            "base_total_demand_t": 410,
            "base_critical_demand_t": 260,
            "low_total_t": 328,
            "high_total_t": 512.5,
            "source_price_assumptions": {item: 8 for item in source_ids},
            "source_capacity_assumptions": {item: 100 for item in source_ids},
            "source_availability_assumptions": {item: 1 for item in source_ids},
            "reliability_assumptions": {item: "metadata_only" for item in source_ids},
            "applicable_constraints": [
                "BASE_TOTAL_SERVICE",
                "BASE_CRITICAL_SERVICE",
                "RESERVE_45D",
            ],
            "notes": "Explicit test year.",
            "provenance": {"basis": "test", "source": "TEAM:test-2041"},
        },
    )


def test_default_final_plan_is_loaded_and_axes_are_dynamic():
    raw = default_plan_raw()
    metadata = case_metadata()
    assert default_plan_path().name == "final_base.json"
    assert raw["plan_id"] == "final-base-plan"
    assert metadata["years"] == [2035, 2036, 2037, 2038, 2039, 2040]
    assert set(metadata["sources"]) == {"A", "B", "C", "D", "E"}
    assert source_colors(["A", "B", "F"])["F"] != source_colors(["A", "B", "F"])["A"]


def test_validation_errors_are_structured():
    raw = copy.deepcopy(default_plan_raw())
    raw["decisions"]["supply_orders"][0]["source_id"] = "UNKNOWN"
    result = validate(raw)
    assert result["valid"] is False
    assert result["errors"][0]["code"] == "PLAN_VALIDATION_ERROR"
    assert "Unknown source_id" in result["errors"][0]["message"]


def test_official_demand_sensitivity_wrapper_uses_three_case_points():
    result = official_demand_sensitivity(default_plan_raw())
    assert [point["value"] for point in result["points"]] == ["LOW", "BASE", "HIGH"]
    assert result["parameter"]["status"] == "CASE_INPUT"


def test_strategy_builder_wrapper_returns_stress_valid_candidate():
    result = build_stress_specific(
        max_candidates=40, beam_width=8, max_iterations=0, seed=17
    )
    assert result["status"] == "success"
    assert result["solutions"][0]["plan"]["scenario_id"] == "MANDATORY_STRESS"
    assert result["solutions"][0]["stress_summary"]["valid"] is True
    assert result["search_metadata"]["global_optimum_claimed"] is False


def test_research_source_2041_extension_and_workspace_roundtrip():
    workspace = _extend_2041(_workspace_with_source())
    metadata = case_metadata(workspace)
    assert metadata["research_source_ids"] == ["F"]
    assert metadata["research_years"] == [2041]
    assert metadata["years"][-1] == 2041
    reopened = workspace_from_bytes(workspace_bytes(workspace))
    assert reopened == workspace
    plan = research_plan_template(default_plan_raw(), workspace)
    assert validate(plan, workspace)["valid"] is True
    assert any(item["source_id"] == "F" for item in plan["decisions"]["supply_orders"])


def test_core_outage_mitigation_is_quantitatively_evaluated():
    result = mitigation_detail(default_plan_raw(), "R-CORE-OUTAGE")
    assert result["mitigation_id"] == "M-FLEX-2038"
    assert result["mitigation_cost_mln"] > 0
    assert result["original_risk_metrics"]["total_shortage_t"] > 0
    assert result["residual_consequence"]["risk"]["total_shortage_t"] == 0
    assert result["risk_result"]["summary"]["valid"] is True


def test_abc_view_model_uses_minimum_annual_service():
    payload = abc_results(default_plan_raw())
    view = abc_comparison(payload)
    assert [row["case"] for row in view["rows"]] == ["A", "B", "C"]
    assert view["metrics"]["A"]["valid"] is True
    assert view["metrics"]["B"]["minimum_annual_total_service"] < 0.8
    assert view["metrics"]["C"]["minimum_annual_total_service"] >= 0.97
    assert view["adaptation_effect"]["total_service_pp"] > 0


def test_backend_csv_exports_are_created_for_both_scenarios():
    files = result_csv_bytes(default_plan_raw())
    expected = {
        "BASE/annual.csv",
        "BASE/monthly.csv",
        "BASE/channels.csv",
        "BASE/costs.csv",
        "MANDATORY_STRESS/annual.csv",
        "comparison/comparison.csv",
    }
    assert expected <= set(files)
    assert all(files[name] for name in expected)
