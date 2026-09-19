from pathlib import Path
import copy

from kosmohak.builder.construction import construct_seed
from kosmohak.loading import AssumptionsLoader, CaseDataLoader, ScenarioLoader, PlanLoader
from kosmohak.simulation.engine import simulate

ROOT = Path(__file__).resolve().parents[2]

ORDERS = {
  "A": {
    "2035-01": 11.808367071524966,
    "2035-03": 11.808367071524966,
    "2035-05": 11.808367071524966,
    "2035-08": 11.808367071524966,
    "2035-09": 11.808367071524971,
    "2035-10": 11.808367071524966,
    "2036-01": 16.025641025641026,
    "2036-05": 16.025641025641026,
    "2036-07": 16.025641025641026,
    "2036-08": 16.025641025641026,
    "2036-10": 16.025641025641026,
    "2037-02": 42.17273954116059,
    "2037-04": 21.086369770580294,
    "2037-07": 12.332995951416985,
    "2038-02": 31.039136302294192,
    "2038-05": 31.0391363022942,
    "2038-07": 31.0391363022942,
    "2038-08": 31.0391363022942,
    "2038-09": 31.0391363022942,
    "2038-10": 3.765182186234828,
    "2038-12": 31.0391363022942,
    "2039-04": 17.45656207827254,
    "2039-06": 37.828947368421076,
    "2039-07": 37.82894736842105,
    "2039-11": 32.89473684210526
  },
  "B": {
    "2035-01": 8.726003490401395,
    "2035-02": 8.726003490401398,
    "2035-03": 8.726003490401395,
    "2035-04": 8.726003490401396,
    "2035-05": 8.726003490401396,
    "2035-06": 8.726003490401398,
    "2035-07": 8.726003490401396,
    "2035-08": 8.726003490401396,
    "2035-10": 11.808367071524966,
    "2035-12": 11.808367071524966,
    "2036-02": 11.808367071524966,
    "2036-03": 11.808367071524966,
    "2036-07": 11.808367071524966,
    "2036-08": 11.808367071524966,
    "2036-10": 16.025641025641026,
    "2036-12": 16.025641025641026,
    "2037-07": 16.025641025641026,
    "2038-01": 22.008898448043176,
    "2038-04": 24.24932523616734,
    "2038-05": 24.24932523616734,
    "2038-11": 27.51539304993252,
    "2038-12": 11.977058029689626,
    "2039-02": 31.0391363022942,
    "2039-07": 31.0391363022942,
    "2039-09": 47.92172739541161
  },
  "C": {
    "2037-03": 16.025641025641026,
    "2037-06": 16.025641025641022,
    "2037-09": 16.025641025641026,
    "2037-12": 16.025641025641026,
    "2038-01": 21.086369770580294,
    "2038-06": 36.1656545209177,
    "2038-10": 24.24932523616734,
    "2038-11": 24.24932523616734,
    "2038-12": 24.24932523616734,
    "2039-01": 31.039136302294196,
    "2039-03": 3.523743252361685,
    "2039-10": 27.27395411605937,
    "2040-01": 20.951627867746296,
    "2040-03": 37.82894736842105,
    "2040-05": 24.46546052631578,
    "2040-08": 37.82894736842105,
    "2040-12": 8.925016869095835
  },
  "D": {
    "2039-12": 6.784539473684189,
    "2040-02": 20.372385290148507,
    "2040-07": 42.7631578947368,
    "2040-08": 32.89473684210526,
    "2040-10": 23.96971997300943
  },
  "E": {}
}

def test_verify_exact_upper_bound_plan():
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
    raw["plan_id"] = "exact-stress-upper-bound"
    raw["decisions"]["supply_orders"] = [
        {"source_id": source_id, "mode": "monthly", "values": values}
        for source_id, values in ORDERS.items()
    ]

    opening_inventory = 33.333333333333336
    initial = raw["decisions"]["initial_stock_acquisition"]
    initial["ordered_volume_t"] = opening_inventory / (1.0 - case_data.storage["BASE"].loss_rate_on_throughput)
    initial["reserved_capacity_t_per_year"] = initial["ordered_volume_t"]

    reservations = []
    for source_id in ("A", "B", "C", "D"):
        years = sorted({int(month[:4]) for month in ORDERS[source_id]})
        for year in years:
            reservations.append({
                "source_id": source_id,
                "year": year,
                "reserved_capacity_t": case_data.source_capacity(source_id, year),
            })

    for year in case_data.official_years:
        stress_demand = case_data.demand[year].base_total_t * stress.demand_multiplier(year)
        reserve_t = stress_demand * 45.0 / 365.0
        reservations.append({
            "source_id": "E",
            "year": year,
            "reserved_capacity_t": reserve_t,
        })
        raw["decisions"]["inventory_policy"]["reserve_strategy_by_year"][str(year)] = "emergency_contract"
        raw["decisions"]["emergency_role_by_year"][str(year)] = "reserve_only"

    raw["decisions"]["capacity_reservations"] = sorted(
        reservations, key=lambda item: (item["source_id"], item["year"])
    )

    plan = PlanLoader.from_dict(copy.deepcopy(raw), case_data, assumptions)
    base_result = simulate(plan, base, case_data, assumptions)
    stress_result = simulate(plan, stress, case_data, assumptions)

    print("EXACT_BASE_VALID", base_result.summary["valid"])
    print("EXACT_STRESS_VALID", stress_result.summary["valid"])
    print("EXACT_BASE_VIOLATIONS", [v.to_dict() for v in base_result.violations])
    print("EXACT_STRESS_VIOLATIONS", [v.to_dict() for v in stress_result.violations])
    for row in stress_result.annual:
        print(
            "EXACT_STRESS_YEAR",
            row["year"],
            "service", row["total_service_level"],
            "critical", row["critical_service_level"],
            "shortage", row["shortage_t"],
            "opening", row["opening_inventory_t"],
            "closing", row["closing_inventory_t"],
        )
    print("EXACT_MIN_STRESS", min(row["total_service_level"] for row in stress_result.annual))
    print("EXACT_COST", base_result.summary["undiscounted_cost_mln"])

    assert base_result.summary["valid"] is True
    assert stress_result.summary["valid"] is True
