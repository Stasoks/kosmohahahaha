from __future__ import annotations

from kosmohak.risk import (
    find_failure_threshold,
    official_demand_sensitivity,
    sensitivity_sweep,
)


def test_sensitivity_sweep_reports_first_failure(
    plan, base_scenario, case_data, assumptions
):
    result = sensitivity_sweep(
        plan,
        "demand_multiplier",
        [1.0, 1.05, 1.1],
        base_scenario,
        case_data,
        assumptions,
    )
    assert len(result.points) == 3
    assert result.first_failing_point is not None
    assert result.first_failing_point["value"] in {1.05, 1.1}
    assert all(point["run_id"] for point in result.points)


def test_official_low_high_demand_points_use_case_input(
    plan, base_scenario, case_data, assumptions
):
    result = official_demand_sensitivity(plan, base_scenario, case_data, assumptions)
    assert len(result.points) == 3
    assert result.provenance["parameter_values"] == "CASE_INPUT"
    assert result.points[0]["total_demand_t"] == sum(row.low_total_t for row in case_data.demand.values())
    assert result.points[-1]["total_demand_t"] == sum(row.high_total_t for row in case_data.demand.values())
    assert result.points[0]["total_service_level"] >= result.points[-1]["total_service_level"]


def test_reverse_stress_finds_last_safe_and_first_failure(
    plan, base_scenario, case_data, assumptions
):
    result = find_failure_threshold(
        plan,
        "demand_multiplier",
        {"start": 1.0, "stop": 1.2, "step": 0.01},
        "BASE_TOTAL_SERVICE",
        base_scenario,
        case_data,
        assumptions,
    )
    assert result.last_safe_value is not None
    assert result.first_failing_value is not None
    assert result.last_safe_value < result.first_failing_value
    assert result.first_violated_constraint["constraint_id"] == "BASE_TOTAL_SERVICE"


def test_reverse_stress_can_search_decreasing_delivery_share(
    plan, base_scenario, case_data, assumptions
):
    result = find_failure_threshold(
        plan,
        {"name": "delivery_share", "source_id": "D", "period_start": "2038-01", "period_end": "2040-12"},
        {"start": 1.0, "stop": 0.0, "step": -0.1},
        "ANY_HARD",
        base_scenario,
        case_data,
        assumptions,
    )
    assert result.evaluated_points[0]["value"] == 1.0
    assert result.first_failing_value is not None
