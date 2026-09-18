import pytest
import json
from pathlib import Path

from kosmohak.loading import PlanLoader
from kosmohak.simulation import simulate


ROOT = Path(__file__).resolve().parents[2]


def test_base_does_not_apply_reliability(base_result):
    january = next(row for row in base_result.monthly if row["month"] == "2036-01")
    assert january["planned_arrival_by_source"]["A"] == pytest.approx(january["gross_delivery_by_source"]["A"])


def test_mandatory_stress_uses_yaml_demand_price_and_delivery(base_result, stress_result):
    base_2038 = next(row for row in base_result.annual if row["year"] == 2038)
    stress_2038 = next(row for row in stress_result.annual if row["year"] == 2038)
    assert stress_2038["demand_total_t"] == pytest.approx(base_2038["demand_total_t"] * 1.15)
    source_a = next(row for row in stress_result.sources if row["source_id"] == "A" and row["year"] == 2038)
    source_a_2040 = next(row for row in stress_result.sources if row["source_id"] == "A" and row["year"] == 2040)
    assert source_a["active_variable_price_mln_per_t"] == pytest.approx(6.2 * 1.25)
    assert source_a_2040["active_variable_price_mln_per_t"] == pytest.approx(6.2)
    march = next(row for row in stress_result.monthly if row["month"] == "2038-03")
    assert march["gross_delivery_by_source"]["D"] == pytest.approx(march["planned_arrival_by_source"]["D"] * 0.55)


def test_stress_share_is_not_multiplied_by_reliability(stress_result):
    march = next(row for row in stress_result.monthly if row["month"] == "2038-03")
    planned = march["planned_arrival_by_source"]["D"]
    assert march["gross_delivery_by_source"]["D"] == pytest.approx(planned * 0.55)
    assert march["gross_delivery_by_source"]["D"] != pytest.approx(planned * 0.55 * 0.78)


def test_example_base_valid_and_stress_reports_resilience(base_result, stress_result):
    assert base_result.summary["valid"] is True
    assert base_result.summary["total_shortage_t"] == pytest.approx(0)
    assert stress_result.summary["valid"] is False
    assert stress_result.summary["total_shortage_t"] > 0
    assert any(item.code == "STRESS_TOTAL_SERVICE_BENCHMARK" for item in stress_result.violations)


def test_base_storage_violates_mandatory_stress_loss_ceiling(
    tmp_path, case_data, assumptions, stress_scenario
):
    raw = json.loads((ROOT / "configs/operator_plan_example.json").read_text(encoding="utf-8"))
    zbo = next(item for item in raw["decisions"]["investments"] if item["investment_id"] == "ZBO")
    zbo["enabled"] = False
    zbo["commissioning_month"] = None
    path = tmp_path / "no-zbo.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    plan = PlanLoader.load(path, case_data, assumptions)
    result = simulate(plan, stress_scenario, case_data, assumptions)
    assert any(item.constraint_id == "STRESS_LOSS_LIMIT" and item.period == "2038" for item in result.violations)
