from __future__ import annotations

import json
from pathlib import Path

import pytest

from kosmohak.loading import PlanLoader, PlanValidationError
from kosmohak.simulation import simulate


ROOT = Path(__file__).resolve().parents[2]


def _plan(tmp_path, case_data, assumptions, mutate):
    raw = json.loads((ROOT / "configs/operator_plan_example.json").read_text(encoding="utf-8"))
    mutate(raw)
    path = tmp_path / "initial-plan.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return PlanLoader.load(path, case_data, assumptions)


def test_initial_stock_is_created_by_preparatory_shipment(base_result):
    pre = base_result.pre_horizon
    assert pre["source_id"] == "A"
    assert pre["requested_order_t"] == pytest.approx(62.8272251309)
    assert pre["losses_t"] == pytest.approx(pre["gross_delivery_t"] * 0.045)
    assert pre["opening_inventory_t"] == pytest.approx(60.0)
    assert base_result.monthly[0]["opening_inventory_t"] == pytest.approx(60.0)


def test_initial_stock_source_is_validated(tmp_path, case_data, assumptions):
    def mutate(raw):
        raw["decisions"]["initial_stock_acquisition"]["source_id"] = "UNKNOWN"

    with pytest.raises(PlanValidationError, match="valid source_id"):
        _plan(tmp_path, case_data, assumptions, mutate)


def test_magic_positive_initial_inventory_is_rejected(tmp_path, case_data, assumptions):
    def mutate(raw):
        raw["decisions"]["inventory_policy"]["initial_inventory"] = {"tons": 10}

    with pytest.raises(PlanValidationError, match="initial_stock_acquisition"):
        _plan(tmp_path, case_data, assumptions, mutate)


def test_infeasible_initial_lead_time_creates_violation_not_stock(
    tmp_path, case_data, assumptions, base_scenario
):
    def mutate(raw):
        acquisition = raw["decisions"]["initial_stock_acquisition"]
        acquisition["order_date"] = "2034-12"
        acquisition["contract_period_start"] = "2034-01"
        acquisition["contract_period_end"] = "2034-12"

    plan = _plan(tmp_path, case_data, assumptions, mutate)
    result = simulate(plan, base_scenario, case_data, assumptions)
    assert result.pre_horizon["opening_inventory_t"] == 0
    assert any(item.code == "INITIAL_STOCK_LEAD_TIME_VIOLATION" for item in result.violations)


def test_initial_stock_uses_contract_top_and_reservation_fee(
    tmp_path, case_data, assumptions, base_scenario
):
    def mutate(raw):
        acquisition = raw["decisions"]["initial_stock_acquisition"]
        acquisition["ordered_volume_t"] = 10
        acquisition["reserved_capacity_t_per_year"] = 100

    plan = _plan(tmp_path, case_data, assumptions, mutate)
    result = simulate(plan, base_scenario, case_data, assumptions)
    pre = result.pre_horizon
    assert pre["payable_volume_t"] == pytest.approx(70)
    assert pre["procurement_cost_mln"] == pytest.approx(70 * 6.2)
    assert pre["reservation_cost_mln"] == pytest.approx(100 * 0.45)
    assert pre["take_or_pay_effect_mln"] == pytest.approx((70 - 10) * 6.2)
    assert result.annual[0]["initial_stock_cost_mln"] == pytest.approx(70 * 6.2 + 45)


def test_initial_shipment_does_not_reappear_as_january_arrival(base_result):
    january = base_result.monthly[0]
    assert january["month"] == "2035-01"
    assert january["gross_delivery_by_source"].get("A", 0) == 0
    assert base_result.pre_horizon["opening_inventory_t"] > 0


def test_requested_feasible_and_unfulfilled_are_separate(
    tmp_path, case_data, assumptions, base_scenario
):
    def mutate(raw):
        acquisition = raw["decisions"]["initial_stock_acquisition"]
        acquisition["ordered_volume_t"] = 220
        acquisition["reserved_capacity_t_per_year"] = 190

    plan = _plan(tmp_path, case_data, assumptions, mutate)
    result = simulate(plan, base_scenario, case_data, assumptions)
    pre = result.pre_horizon
    assert pre["requested_order_t"] == 220
    assert pre["feasible_order_t"] == 190
    assert pre["unfulfilled_request_t"] == 30
    assert plan.initial_stock_acquisition.ordered_volume_t == 220


def test_initial_stock_obeys_source_investment_prerequisites(
    tmp_path, case_data, assumptions, base_scenario
):
    def mutate(raw):
        acquisition = raw["decisions"]["initial_stock_acquisition"]
        acquisition["source_id"] = "C"
        acquisition["ordered_volume_t"] = 10
        acquisition["reserved_capacity_t_per_year"] = 10

    plan = _plan(tmp_path, case_data, assumptions, mutate)
    result = simulate(plan, base_scenario, case_data, assumptions)
    assert result.pre_horizon["opening_inventory_t"] == 0
    assert any(item.code == "INITIAL_STOCK_SOURCE_UNAVAILABLE" for item in result.violations)


def test_initial_stock_obeys_storage_capacity(
    tmp_path, case_data, assumptions, base_scenario
):
    def mutate(raw):
        acquisition = raw["decisions"]["initial_stock_acquisition"]
        acquisition["ordered_volume_t"] = 100
        acquisition["reserved_capacity_t_per_year"] = 100

    plan = _plan(tmp_path, case_data, assumptions, mutate)
    result = simulate(plan, base_scenario, case_data, assumptions)
    assert result.pre_horizon["opening_inventory_t"] == pytest.approx(70)
    assert result.pre_horizon["overflow_t"] == pytest.approx(25.5)
    assert any(item.code == "INITIAL_STORAGE_CAPACITY_EXCEEDED" for item in result.violations)
