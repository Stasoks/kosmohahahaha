from __future__ import annotations

from collections import defaultdict

from kosmohak.domain.assumptions import ModelAssumptions
from kosmohak.domain.case import CaseData
from kosmohak.domain.investment import active_months_in_year, commissioning_dates
from kosmohak.domain.plan import OperatorPlan
from kosmohak.domain.scenario import Scenario
from kosmohak.domain.shipment import Shipment
from kosmohak.domain.time import add_months, month_range
from kosmohak.simulation.physics import apply_delivery_share


def expand_orders(plan: OperatorPlan, case_data: CaseData) -> dict[str, dict[str, float]]:
    valid_months = set(month_range(case_data.start_month, case_data.end_month))
    output: dict[str, dict[str, float]] = defaultdict(dict)
    for schedule in plan.supply_orders:
        if schedule.mode == "monthly":
            for month, tons in schedule.values.items():
                if month in valid_months:
                    output[schedule.source_id][month] = tons
        else:
            for year, tons in schedule.values.items():
                for month_number in range(1, 13):
                    month = f"{int(year):04d}-{month_number:02d}"
                    if month in valid_months:
                        output[schedule.source_id][month] = tons / 12.0
    return {source_id: dict(values) for source_id, values in output.items()}


def source_commissioning_dates(
    plan: OperatorPlan, case_data: CaseData, assumptions: ModelAssumptions
) -> dict[str, str | None]:
    investments = commissioning_dates(plan, case_data, assumptions)
    return {
        "A": f"{case_data.sources['A'].available_from_year}-01",
        "B": f"{case_data.sources['B'].available_from_year}-01",
        "C": investments["EARTH_NEW"],
        "D": investments["LUNAR_ISRU"],
        "E": f"{case_data.sources['E'].available_from_year}-01",
    }


def source_active_fraction(commissioning_month: str | None, year: int) -> float:
    return active_months_in_year(commissioning_month, year) / 12.0


def build_shipments(
    plan: OperatorPlan,
    case_data: CaseData,
    assumptions: ModelAssumptions,
    scenario: Scenario,
    orders: dict[str, dict[str, float]],
) -> tuple[list[Shipment], dict[tuple[str, int], dict[str, float]]]:
    commissions = source_commissioning_dates(plan, case_data, assumptions)
    eligibility: dict[tuple[str, int], dict[str, float]] = {}
    for source_id, source in case_data.sources.items():
        for year in case_data.years:
            available_orders = {
                month: tons
                for month, tons in orders.get(source_id, {}).items()
                if int(month[:4]) == year
                and commissions[source_id] is not None
                and month >= str(commissions[source_id])
            }
            total_available = sum(available_orders.values())
            total_ordered = sum(
                tons for month, tons in orders.get(source_id, {}).items() if int(month[:4]) == year
            )
            active_fraction = source_active_fraction(commissions[source_id], year)
            reserved_period = plan.reservation(source_id, year) * active_fraction
            physical_period = source.capacity_t_per_year * active_fraction
            contract_limit = min(reserved_period, physical_period)
            factor = min(1.0, contract_limit / total_available) if total_available else 0.0
            eligibility[(source_id, year)] = {
                "ordered_t": total_ordered,
                "available_ordered_t": total_available,
                "eligible_t": total_available * factor,
                "contract_limit_t": contract_limit,
                "active_fraction": active_fraction,
                "factor": factor,
            }

    shipments: list[Shipment] = []
    sequence = 0
    for source_id in sorted(orders):
        source = case_data.sources[source_id]
        lead = assumptions.source_delivery_lead_months(source)
        commission = commissions[source_id]
        for order_month, ordered_t in sorted(orders[source_id].items()):
            if ordered_t <= 0:
                continue
            sequence += 1
            year = int(order_month[:4])
            available = commission is not None and order_month >= commission
            factor = eligibility[(source_id, year)]["factor"] if available else 0.0
            eligible_t = ordered_t * factor
            arrival = add_months(order_month, lead)
            share = scenario.actual_delivery_share(source.name, int(arrival[:4]))
            actual = apply_delivery_share(eligible_t, share, source.reliability_profile)
            shipments.append(
                Shipment(
                    shipment_id=f"S{sequence:04d}",
                    source_id=source_id,
                    source_name=source.name,
                    order_month=order_month,
                    ordered_t=ordered_t,
                    eligible_t=eligible_t,
                    rejected_t=ordered_t - eligible_t,
                    planned_arrival_month=arrival,
                    actual_arrival_month=arrival,
                    actual_delivery_share=share,
                    actual_delivered_t=actual,
                )
            )
    return shipments, eligibility

