from pathlib import Path

from kosmohak.builder.construction import construct_seed
from kosmohak.loading import AssumptionsLoader, CaseDataLoader, ScenarioLoader, PlanLoader
from kosmohak.simulation.engine import simulate
from kosmohak.domain.time import add_months
from kosmohak.builder.search import _commissions, _rebuild_reservations, _schedule

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
    for row in stress_result.monthly:
        shortage = row["shortage_critical_t"] + row["shortage_noncritical_t"]
        if shortage > 1e-9:
            print(
                "SHORTAGE_MONTH",
                row["month"],
                "shortage", shortage,
                "critical", row["shortage_critical_t"],
                "opening", row["opening_inventory_t"],
                "gross", row["gross_delivery_t"],
                "closing", row["closing_inventory_t"],
            )
    for row in base_result.monthly:
        if int(row["month"][:4]) >= 2039:
            print(
                "BASE_MONTH",
                row["month"],
                "opening", row["opening_inventory_t"],
                "gross", row["gross_delivery_t"],
                "overflow", row["overflow_t"],
                "closing", row["closing_inventory_t"],
            )
    print("ORDERS", raw["decisions"]["supply_orders"])
    print("RESERVATIONS", raw["decisions"]["capacity_reservations"])

    # Construct a direct 97% feasibility witness from the actual stress deficit.
    repaired = raw
    loss_factor = 1.0 - case_data.storage["ZBO"].loss_rate_on_throughput
    stress_by_year = {int(row["year"]): row for row in stress_result.annual}
    monthly_by_year = {}
    for row in stress_result.monthly:
        monthly_by_year.setdefault(int(row["month"][:4]), []).append(row)

    for year, source_id in ((2039, "B"), (2040, "C")):
        annual = stress_by_year[year]
        remaining_net = max(
            0.0,
            0.97 * annual["demand_total_t"] - annual["served_total_t"],
        )
        lead = assumptions.source_delivery_lead_months(case_data.sources[source_id])
        schedule = _schedule(repaired, source_id)
        for row in sorted(monthly_by_year[year], key=lambda item: item["month"]):
            if remaining_net <= 1e-10:
                break
            shortage = row["shortage_critical_t"] + row["shortage_noncritical_t"]
            if shortage <= 1e-10:
                continue
            net_add = min(remaining_net, shortage)
            gross_add = net_add / loss_factor
            order_month = add_months(row["month"], -lead)
            schedule["values"][order_month] = schedule["values"].get(order_month, 0.0) + gross_add
            remaining_net -= net_add

    provisional = PlanLoader.from_dict(repaired, case_data, assumptions)
    commissions = _commissions(repaired, base, case_data, assumptions)
    _rebuild_reservations(repaired, commissions, case_data)
    repaired_plan = PlanLoader.from_dict(repaired, case_data, assumptions)
    repaired_base = simulate(repaired_plan, base, case_data, assumptions)
    repaired_stress = simulate(repaired_plan, stress, case_data, assumptions)
    print("REPAIRED_BASE_VALID", repaired_base.summary["valid"])
    print("REPAIRED_BASE_FINAL_INV", repaired_base.summary["final_inventory_t"])
    print("REPAIRED_BASE_OVERFLOW", repaired_base.summary["total_overflow_t"])
    for row in repaired_base.annual:
        print("REPAIRED_BASE", row["year"], row["total_service_level"], row["critical_service_level"], row["reserve_actual_days"], row["closing_inventory_t"])
    for row in repaired_stress.annual:
        print("REPAIRED_STRESS", row["year"], row["total_service_level"], row["critical_service_level"], row["shortage_t"], row["closing_inventory_t"])
    print("REPAIRED_VIOLATIONS", [v.to_dict() for v in repaired_base.violations])
    print("REPAIRED_STRESS_VIOLATIONS", [v.to_dict() for v in repaired_stress.violations])
    assert repaired_base.summary["valid"] is True
    assert min(row["total_service_level"] for row in repaired_stress.annual) >= 0.97 - 1e-10
    assert min(row["critical_service_level"] for row in repaired_stress.annual) >= 0.99 - 1e-10
    assert True
