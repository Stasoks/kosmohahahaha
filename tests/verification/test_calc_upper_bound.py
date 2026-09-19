from pathlib import Path

from kosmohak.builder.construction import construct_seed
from kosmohak.loading import AssumptionsLoader, CaseDataLoader, ScenarioLoader, PlanLoader
from kosmohak.simulation.engine import simulate

ROOT = Path(__file__).resolve().parents[2]


def test_print_aggressive_seed():
    case_data = CaseDataLoader.load(ROOT)
    assumptions = AssumptionsLoader.load(ROOT / "configs/model_assumptions.json")
    base = ScenarioLoader.load("BASE", ROOT)
    stress = ScenarioLoader.load("MANDATORY_STRESS", ROOT)

    raw = construct_seed(
        case_data,
        assumptions,
        base,
        stress,
        set(case_data.investments),
        "MAX_RESILIENCE",
    )
    plan = PlanLoader.from_dict(raw, case_data, assumptions)
    base_result = simulate(plan, base, case_data, assumptions)
    stress_result = simulate(plan, stress, case_data, assumptions)

    print("BASE_VALID", base_result.summary["valid"])
    print("BASE_COST", base_result.summary["undiscounted_cost_mln"])
    for row in stress_result.annual:
        print(
            "STRESS",
            row["year"],
            "demand", row["demand_total_t"],
            "served", row["served_total_t"],
            "SL", row["total_service_level"],
            "crit", row["critical_service_level"],
            "shortage", row["shortage_t"],
            "opening", row["opening_inventory_t"],
            "gross", row["gross_supply_t"],
            "closing", row["closing_inventory_t"],
        )
    print("ORDERS", raw["decisions"]["supply_orders"])
    print("RESERVATIONS", raw["decisions"]["capacity_reservations"])
    assert True
