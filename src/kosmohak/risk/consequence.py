from __future__ import annotations

from typing import Any

from kosmohak.domain.result import SimulationResult


def _costs(result: SimulationResult) -> dict[str, float]:
    return {
        "total_cost_mln": float(result.summary["undiscounted_cost_mln"]),
        "discounted_cost_mln": float(result.summary["discounted_cost_mln"]),
        "procurement_mln": sum(float(row["procurement_mln"]) for row in result.annual),
        "reservation_mln": sum(float(row["reservation_mln"]) for row in result.annual),
        "capex_mln": sum(float(row["capex_mln"]) for row in result.annual),
        "fixed_opex_mln": sum(float(row["fixed_opex_mln"]) for row in result.annual),
        "holding_mln": sum(float(row["holding_mln"]) for row in result.annual),
    }


def extract_metrics(result: SimulationResult) -> dict[str, Any]:
    violations = [item.to_dict() for item in result.violations]
    first_violation = violations[0] if violations else None
    annual_total = {str(row["year"]): row["total_service_level"] for row in result.annual}
    annual_critical = {
        str(row["year"]): row["critical_service_level"] for row in result.annual
    }
    reserve_breaches = [
        item for item in violations if item["constraint_id"] == "RESERVE_45D"
    ]
    hard_periods = sorted(
        {item["period"] for item in violations if item["severity"] == "hard"}
    )
    total_demand = sum(float(row["demand_total_t"]) for row in result.annual)
    return {
        "run_id": result.summary["run_id"],
        "total_demand_t": total_demand,
        "total_shortage_t": float(result.summary["total_shortage_t"]),
        "critical_shortage_t": float(result.summary["critical_shortage_t"]),
        "total_service_by_year": annual_total,
        "critical_service_by_year": annual_critical,
        "minimum_inventory_t": float(result.summary["minimum_inventory_t"]),
        "final_inventory_t": float(result.summary["final_inventory_t"]),
        "reserve_breaches": reserve_breaches,
        "storage_overflow_t": float(result.summary["total_overflow_t"]),
        "unavailable_requested_supply_t": float(
            result.summary["unavailable_requested_supply_t"]
        ),
        "hard_violation_count": int(result.summary["hard_violation_count"]),
        "first_violation": first_violation,
        "violation_duration_periods": len(hard_periods),
        "hard_violation_periods": hard_periods,
        "violations": violations,
        "delayed_delivery_count": int(result.summary["delayed_delivery_count"]),
        "delayed_delivery_t": float(result.summary["delayed_delivery_t"]),
        "months_with_shortage": int(result.summary["months_with_shortage"]),
        "costs": _costs(result),
    }


def compare_results(
    baseline: SimulationResult,
    risk_result: SimulationResult,
) -> dict[str, Any]:
    base = extract_metrics(baseline)
    risk = extract_metrics(risk_result)
    annual_total_delta = {
        year: risk["total_service_by_year"][year] - value
        for year, value in base["total_service_by_year"].items()
    }
    annual_critical_delta = {
        year: risk["critical_service_by_year"][year] - value
        for year, value in base["critical_service_by_year"].items()
    }
    numeric = [
        "total_shortage_t",
        "critical_shortage_t",
        "minimum_inventory_t",
        "final_inventory_t",
        "storage_overflow_t",
        "unavailable_requested_supply_t",
        "hard_violation_count",
        "violation_duration_periods",
        "delayed_delivery_count",
        "delayed_delivery_t",
        "months_with_shortage",
    ]
    delta = {key: risk[key] - base[key] for key in numeric}
    delta["total_service_by_year"] = annual_total_delta
    delta["critical_service_by_year"] = annual_critical_delta
    delta["minimum_annual_total_service_delta"] = min(annual_total_delta.values())
    delta["minimum_annual_critical_service_delta"] = min(annual_critical_delta.values())
    delta["costs"] = {
        key: risk["costs"][key] - value for key, value in base["costs"].items()
    }
    return {"baseline": base, "risk": risk, "delta": delta}
