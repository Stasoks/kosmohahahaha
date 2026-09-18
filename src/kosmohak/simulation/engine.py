from __future__ import annotations

from collections import defaultdict
from typing import Any

from kosmohak.constraints.checker import ConstraintChecker
from kosmohak.domain.assumptions import ModelAssumptions
from kosmohak.domain.case import CaseData
from kosmohak.domain.investment import commissioning_dates
from kosmohak.domain.plan import OperatorPlan
from kosmohak.domain.result import SimulationResult
from kosmohak.domain.scenario import Scenario
from kosmohak.domain.time import month_range
from kosmohak.economics.contracts import contract_cost
from kosmohak.economics.finance import discount_end_of_year, holding_cost
from kosmohak.economics.investments import investment_events
from kosmohak.simulation.physics import accept_throughput, material_balance, reserve_tons, serve_demand
from kosmohak.simulation.pipeline import (
    build_shipments,
    expand_orders,
    source_commissioning_dates,
)


def simulate(
    plan: OperatorPlan,
    scenario: Scenario,
    case_data: CaseData,
    assumptions: ModelAssumptions,
) -> SimulationResult:
    """Execute one immutable participant plan in one official scenario."""
    months = month_range(case_data.start_month, case_data.end_month)
    orders = expand_orders(plan, case_data)
    source_commissions = source_commissioning_dates(plan, case_data, assumptions)
    investment_commissions = commissioning_dates(plan, case_data, assumptions)
    shipments, eligibility = build_shipments(plan, case_data, assumptions, scenario, orders)
    arrivals_by_month: dict[str, list] = defaultdict(list)
    for shipment in shipments:
        arrivals_by_month[shipment.actual_arrival_month].append(shipment)

    checker = ConstraintChecker(case_data, scenario)
    initial_planned = float(plan.initial_inventory.get("tons", 0.0))
    base_storage = case_data.storage["BASE"]
    inventory = min(initial_planned, base_storage.capacity_t)
    checker.initial_storage(initial_planned, inventory, base_storage.capacity_t)
    monthly_rows: list[dict[str, Any]] = []

    for month in months:
        year = int(month[:4])
        zbo_active = investment_commissions["ZBO"] is not None and month >= str(investment_commissions["ZBO"])
        storage = case_data.storage["ZBO" if zbo_active else "BASE"]
        opening = inventory

        arriving = arrivals_by_month.get(month, [])
        planned_arrival: dict[str, float] = defaultdict(float)
        actual_delivered: dict[str, float] = defaultdict(float)
        for shipment in arriving:
            planned_arrival[shipment.source_id] += shipment.eligible_t
            actual_delivered[shipment.source_id] += shipment.actual_delivered_t
        gross = sum(actual_delivered.values())
        flow = accept_throughput(opening, gross, storage.loss_rate_on_throughput, storage.capacity_t)
        checker.storage_overflow(
            month,
            opening + gross - flow.losses_t,
            storage.capacity_t,
            flow.overflow_t,
        )
        available = opening + flow.net_accepted_t

        demand_row = case_data.demand[year]
        demand_total = demand_row.base_total_t * scenario.demand_multiplier(year) / 12.0
        demand_critical = demand_row.base_critical_t * scenario.demand_multiplier(year, critical=True) / 12.0
        service = serve_demand(available, demand_total, demand_critical)
        served_total = service.served_critical_t + service.served_noncritical_t
        calculated_closing = material_balance(
            opening,
            flow.delivered_for_balance_t,
            flow.losses_t,
            served_total,
        )
        if abs(calculated_closing - service.closing_inventory_t) > 1e-8:
            raise RuntimeError(f"Internal material-balance error in {month}")
        inventory = max(0.0, service.closing_inventory_t)

        active_investments: list[str] = []
        fixed_opex = 0.0
        if zbo_active:
            active_investments.append("ZBO")
            fixed_opex += case_data.investments["ZBO"].fixed_opex_mln_per_year / 12.0
        if investment_commissions["EARTH_NEW"] is not None and month >= str(investment_commissions["EARTH_NEW"]):
            active_investments.append("EARTH_NEW")
        if investment_commissions["LUNAR_ISRU"] is not None and month >= str(investment_commissions["LUNAR_ISRU"]):
            active_investments.append("LUNAR_ISRU")
            fixed_opex += case_data.investments["LUNAR_ISRU"].fixed_opex_mln_per_year / 12.0

        month_orders = {
            source_id: values.get(month, 0.0)
            for source_id, values in orders.items()
            if values.get(month, 0.0) != 0
        }
        reservations = {
            source_id: plan.reservation(source_id, year)
            for source_id in case_data.sources
        }
        pipeline = [
            shipment.to_dict()
            for shipment in shipments
            if shipment.eligible_t > 0
            and shipment.order_month <= month < shipment.actual_arrival_month
        ]
        monthly_rows.append(
            {
                "month": month,
                "opening_inventory_t": opening,
                "demand_total_t": demand_total,
                "demand_critical_t": demand_critical,
                "reserved_by_source": reservations,
                "ordered_by_source": month_orders,
                "pipeline": pipeline,
                "planned_arrival_by_source": dict(sorted(planned_arrival.items())),
                "actual_delivered_by_source": dict(sorted(actual_delivered.items())),
                "gross_throughput_t": flow.gross_throughput_t,
                "delivered_for_balance_t": flow.delivered_for_balance_t,
                "losses_t": flow.losses_t,
                "net_accepted_t": flow.net_accepted_t,
                "overflow_t": flow.overflow_t,
                "served_critical_t": service.served_critical_t,
                "served_noncritical_t": service.served_noncritical_t,
                "shortage_critical_t": service.shortage_critical_t,
                "shortage_noncritical_t": service.shortage_noncritical_t,
                "closing_inventory_t": inventory,
                "active_storage_id": storage.storage_id,
                "active_storage_capacity_t": storage.capacity_t,
                "active_loss_rate": storage.loss_rate_on_throughput,
                "active_investments": active_investments,
                "holding_cost_mln": holding_cost(
                    opening,
                    inventory,
                    storage.holding_cost_mln_per_t_year,
                    assumptions.storage_average_method,
                ),
                "fixed_opex_mln": fixed_opex,
                "violations": [],
            }
        )

    events = investment_events(plan, case_data)
    initial_source_id = plan.initial_inventory.get("source_id")
    initial_tons = float(plan.initial_inventory.get("tons", 0.0))
    source_rows: list[dict[str, Any]] = []
    for source_id, source in case_data.sources.items():
        for year in case_data.years:
            info = eligibility[(source_id, year)]
            ordered = info["ordered_t"]
            active_fraction = info["active_fraction"]
            reserved = plan.reservation(source_id, year)
            price = source.variable_cost_mln_per_t * scenario.variable_price_multiplier(source.name, year)
            contract = contract_cost(
                ordered_volume_t=ordered,
                reserved_capacity_period_t=reserved * active_fraction,
                take_or_pay_share=source.take_or_pay_share,
                variable_price_mln_per_t=price,
                annual_reserved_capacity_t=reserved,
                reservation_rate_mln_per_t_year_capacity=source.reservation_rate_mln_per_t_year_capacity,
                period_fraction=active_fraction,
            )
            initial_for_row = initial_tons if source_id == initial_source_id and year == case_data.years[0] else 0.0
            planned_delivery = sum(
                shipment.eligible_t
                for shipment in shipments
                if shipment.source_id == source_id
                and int(shipment.planned_arrival_month[:4]) == year
                and case_data.start_month <= shipment.planned_arrival_month <= case_data.end_month
            )
            actual_delivery = sum(
                shipment.actual_delivered_t
                for shipment in shipments
                if shipment.source_id == source_id
                and int(shipment.actual_arrival_month[:4]) == year
                and case_data.start_month <= shipment.actual_arrival_month <= case_data.end_month
            )
            physical_capacity = source.capacity_t_per_year * active_fraction
            source_rows.append(
                {
                    "source_id": source_id,
                    "source_name": source.name,
                    "year": year,
                    "reserved_capacity_t_per_year": reserved,
                    "active_fraction": active_fraction,
                    "ordered_t": ordered,
                    "eligible_ordered_t": info["eligible_t"],
                    "rejected_ordered_t": ordered - info["eligible_t"],
                    "planned_delivered_t": planned_delivery,
                    "actual_delivered_t": actual_delivery,
                    "initial_inventory_procured_t": initial_for_row,
                    "payable_volume_t": contract.payable_volume_t + initial_for_row,
                    "utilization": actual_delivery / physical_capacity if physical_capacity else 0.0,
                    "active_variable_price_mln_per_t": price,
                    "procurement_cost_mln": contract.variable_payment_mln + initial_for_row * price,
                    "reservation_cost_mln": contract.reservation_payment_mln,
                    "take_or_pay_effect_mln": contract.take_or_pay_effect_mln,
                    "reliability_profile": source.reliability_profile,
                    "violations": [],
                }
            )

    annual_rows: list[dict[str, Any]] = []
    cost_rows: list[dict[str, Any]] = []
    base_year = case_data.years[0]
    reserve_days = case_data.constraints["RESERVE_45D"].value
    for year in case_data.years:
        states = [row for row in monthly_rows if int(row["month"][:4]) == year]
        source_year = [row for row in source_rows if row["year"] == year]
        demand_total = sum(row["demand_total_t"] for row in states)
        demand_critical = sum(row["demand_critical_t"] for row in states)
        served_critical = sum(row["served_critical_t"] for row in states)
        served_noncritical = sum(row["served_noncritical_t"] for row in states)
        served_total = served_critical + served_noncritical
        gross = sum(row["gross_throughput_t"] for row in states)
        losses = sum(row["losses_t"] for row in states)
        capex = sum(event.capex_mln for event in events if int(event.month[:4]) == year)
        fixed_opex = sum(row["fixed_opex_mln"] for row in states)
        procurement = sum(row["procurement_cost_mln"] for row in source_year)
        reservation = sum(row["reservation_cost_mln"] for row in source_year)
        top_effect = sum(row["take_or_pay_effect_mln"] for row in source_year)
        holding = sum(row["holding_cost_mln"] for row in states)
        total_cost = capex + fixed_opex + procurement + reservation + holding
        discounted = discount_end_of_year(total_cost, year, base_year, assumptions.real_discount_rate)
        requirement = reserve_tons(demand_total, reserve_days)
        opening = states[0]["opening_inventory_t"]
        reserve_actual_days = opening / demand_total * 365.0 if demand_total else reserve_days
        annual_rows.append(
            {
                "year": year,
                "demand_total_t": demand_total,
                "demand_critical_t": demand_critical,
                "served_total_t": served_total,
                "served_critical_t": served_critical,
                "total_service_level": served_total / demand_total if demand_total else 1.0,
                "critical_service_level": served_critical / demand_critical if demand_critical else 1.0,
                "opening_inventory_t": opening,
                "gross_supply_t": gross,
                "losses_t": losses,
                "losses_divided_by_throughput": losses / gross if gross else 0.0,
                "overflow_t": sum(row["overflow_t"] for row in states),
                "closing_inventory_t": states[-1]["closing_inventory_t"],
                "shortage_t": sum(row["shortage_critical_t"] + row["shortage_noncritical_t"] for row in states),
                "critical_shortage_t": sum(row["shortage_critical_t"] for row in states),
                "reserve_requirement_t": requirement,
                "reserve_actual_t": opening,
                "reserve_actual_days": reserve_actual_days,
                "capex_mln": capex,
                "fixed_opex_mln": fixed_opex,
                "procurement_mln": procurement,
                "reservation_mln": reservation,
                "take_or_pay_effect_mln": top_effect,
                "holding_mln": holding,
                "total_cost_mln": total_cost,
                "discounted_cost_mln": discounted,
                "violations": [],
            }
        )
        cost_rows.append(
            {
                "year": year,
                "capex_mln": capex,
                "fixed_opex_mln": fixed_opex,
                "procurement_mln": procurement,
                "reservation_mln": reservation,
                "take_or_pay_effect_in_procurement_mln": top_effect,
                "holding_mln": holding,
                "total_cost_mln": total_cost,
                "discounted_cost_mln": discounted,
            }
        )

    violations = checker.complete(
        plan=plan,
        assumptions=assumptions,
        annual=annual_rows,
        monthly=monthly_rows,
        eligibility=eligibility,
        investment_events=events,
    )
    for row in monthly_rows:
        row["violations"] = [item.code for item in violations if item.period == row["month"]]
    for row in annual_rows:
        row["violations"] = [item.code for item in violations if item.period == str(row["year"])]
    for row in source_rows:
        row["violations"] = [
            item.code
            for item in violations
            if item.period == str(row["year"]) and item.source_id == row["source_id"]
        ]

    total_demand = sum(row["demand_total_t"] for row in annual_rows)
    critical_demand = sum(row["demand_critical_t"] for row in annual_rows)
    total_served = sum(row["served_total_t"] for row in annual_rows)
    critical_served = sum(row["served_critical_t"] for row in annual_rows)
    hard_count = sum(item.severity == "hard" for item in violations)
    summary = {
        "scenario_id": scenario.scenario_id,
        "plan_id": plan.plan_id,
        "valid": hard_count == 0,
        "undiscounted_cost_mln": sum(row["total_cost_mln"] for row in annual_rows),
        "discounted_cost_mln": sum(row["discounted_cost_mln"] for row in annual_rows),
        "total_service_level": total_served / total_demand if total_demand else 1.0,
        "critical_service_level": critical_served / critical_demand if critical_demand else 1.0,
        "total_shortage_t": sum(row["shortage_t"] for row in annual_rows),
        "critical_shortage_t": sum(row["critical_shortage_t"] for row in annual_rows),
        "total_losses_t": sum(row["losses_t"] for row in annual_rows),
        "emergency_usage_t": sum(row["actual_delivered_t"] for row in source_rows if row["source_id"] == "E"),
        "final_inventory_t": monthly_rows[-1]["closing_inventory_t"],
        "violation_count": len(violations),
        "hard_violation_count": hard_count,
        "case_input_root": str(case_data.root),
        "scenario_source": str(scenario.source_path),
    }
    return SimulationResult(
        summary=summary,
        annual=annual_rows,
        monthly=monthly_rows,
        sources=source_rows,
        violations=violations,
        costs=cost_rows,
        assumptions=assumptions.raw,
    )

