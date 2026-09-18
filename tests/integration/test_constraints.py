import json
from pathlib import Path

from kosmohak.loading import PlanLoader
from kosmohak.simulation import simulate


ROOT = Path(__file__).resolve().parents[2]


def _load_mutated(tmp_path, case_data, assumptions, mutate):
    raw = json.loads((ROOT / "configs/operator_plan_example.json").read_text(encoding="utf-8"))
    mutate(raw)
    path = tmp_path / "mutated-plan.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return PlanLoader.load(path, case_data, assumptions)


def test_over_capacity_plan_is_not_hidden_or_auto_repaired(tmp_path, case_data, assumptions, base_scenario):
    def mutate(raw):
        reservation = next(item for item in raw["decisions"]["capacity_reservations"] if item["source_id"] == "A" and item["year"] == 2035)
        reservation["reserved_capacity_t"] = 200
    plan = _load_mutated(tmp_path, case_data, assumptions, mutate)
    result = simulate(plan, base_scenario, case_data, assumptions)
    violation = next(item for item in result.violations if item.code == "CAPACITY_EXCEEDED")
    assert violation.actual == 200
    assert violation.limit == 190
    assert violation.excess_or_gap == 10


def test_emergency_base_role_over_two_years_is_violation(tmp_path, case_data, assumptions, base_scenario):
    def mutate(raw):
        raw["decisions"]["emergency_role_by_year"].update(
            {"2035": "planned_supply", "2036": "planned_supply", "2037": "planned_supply"}
        )
    plan = _load_mutated(tmp_path, case_data, assumptions, mutate)
    result = simulate(plan, base_scenario, case_data, assumptions)
    assert any(item.constraint_id == "EMERGENCY_BASE_STREAK" and item.period == "2037" for item in result.violations)


def test_order_from_unavailable_isru_is_rejected_physically(tmp_path, case_data, assumptions, base_scenario):
    def mutate(raw):
        schedule = next(item for item in raw["decisions"]["supply_orders"] if item["source_id"] == "D")
        schedule["values"]["2037"] = 12
        raw["decisions"]["capacity_reservations"].append({"source_id": "D", "year": 2037, "reserved_capacity_t": 12})
    plan = _load_mutated(tmp_path, case_data, assumptions, mutate)
    result = simulate(plan, base_scenario, case_data, assumptions)
    assert any(item.code == "SOURCE_UNAVAILABLE" and item.source_id == "D" for item in result.violations)
    assert all(row["gross_delivery_by_source"].get("D", 0) == 0 for row in result.monthly if row["month"].startswith("2037"))
