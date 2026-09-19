from __future__ import annotations

import hashlib
import json
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
from kosmohak.economics.contracts import priced_contract_cost
from kosmohak.economics.finance import discount_end_of_year, holding_cost
from kosmohak.economics.investments import investment_events
from kosmohak.simulation.environment import SimulationEnvironment, ensure_environment
from kosmohak.simulation.physics import accept_throughput, reserve_tons, serve_demand
from kosmohak.simulation.pipeline import build_shipments, expand_orders
from kosmohak.simulation.pre_horizon import evaluate_preparatory_acquisition
from kosmohak.workspace.serialization import effective_case_to_dict


def _run_id(
    plan: OperatorPlan,
    environment: SimulationEnvironment,
    case_data: CaseData,
    assumptions: ModelAssumptions,
) -> str:
    payload = {
        "plan": plan.raw,
        "base_scenario": environment.base_scenario.config,
        "environment_id": environment.environment_id,
        "overrides": environment.applied_overrides(),
        "assumptions": assumptions.raw,
        "effective_case": effective_case_to_dict(case_data),
    }
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"run-{digest[:16]}"


def simulate(
    plan: OperatorPlan,
    environment: Scenario | SimulationEnvironment,
    case_data: CaseData,
    assumptions: ModelAssumptions,
) -> SimulationResult:
    """Evaluate one immutable participant plan in one deterministic environment."""
    env = ensure_environment(environment)
    run_id = _run_id(plan, env, case_data, assumptions)
    months = month_range(case_data.start_month, case_data.end_month)
    orders = expand_orders(plan, case_data)
    investment_commissions = commissioning_dates(plan, case_data, assumptions, env)
    shipments, eligibility = build_shipments(plan, case_data, assumptions, env, orders)
    actual_arrivals_by_month: dict[str, list] = defaultdict(list)
    planned_arrivals_by_month: dict[str, list] = defaultdict(list)
    for shipment in shipments:
        actual_arrivals_by_month[shipment.actual_arrival_month].append(shipment)
        planned_arrivals_by_month[shipment.planned_arrival_month].append(shipment)

    checker = ConstraintChecker(case_data, env)
    preparatory = evaluate_preparatory_acquisition(plan, env, case_data, assumptions)
    checker.extend(preparatory.violations)
    inventory = preparatory.opening_inventory_t
    monthly_rows: list[dict[str, Any]] = []

    for month in months:
        year = int(month[:4])
        zbo_active = (
            investment_commissions["ZBO"] is not None
            and month >= str(investment_commissions["ZBO"])
        )
        storage = case_data.storage["ZBO" if zbo_active else "BASE"]
        storage_capacity = env.storage_capacity(storage.storage_id, month, storage.capacity_t)
        loss_rate = env.storage_loss_rate(storage.storage_id, month, storage.loss_rate_on_throughput)
        opening = inventory

        planned_arrival: dict[str, float] = defaultdict(float)
        for shipment in planned_arrivals_by_month.get(month, []):
            planned_arrival[shipment.source_id] += shipment.feasible_t
        gross_delivery_by_source: dict[str, float] = defaultdict(float)
        arriving = actual_arrivals_by_month.get(month, [])
        for shipment in arriving:
            gross_delivery_by_source[shipment.source_id] += shipment.gross_delivery_t
        gross_delivery = sum(gross_delivery_by_source.values())
        flow = accept_throughput(opening, gross_delivery, loss_rate, storage_capacity)
        checker.storage_overflow(
            month,
            opening + flow.net_delivery_t,
            storage_capacity,
            flow.overflow_t,
        )
        available = opening + flow.accepted_delivery_t

        demand_row = case_data.demand[year]
        demand_total = demand_row.base_total_t * env.demand_multiplier_for_month(month) / 12.0
        demand_critical = (
            demand_row.base_critical_t
            * env.demand_multiplier_for_month(month, critical=True)
            / 12.0
        )
        service = serve_demand(available, demand_total, demand_critical)
        served_total = service.served_critical_t + service.served_noncritical_t
        calculated_closing = available - served_total
        if abs(calculated_closing - service.closing_inventory_t) > 1e-8:
            raise RuntimeError(f"Internal material-balance error in {month}")
        inventory = max(0.0, service.closing_inventory_t)

        active_investments: list[str] = []
        fixed_opex = 0.0
        if zbo_active:
            active_investments.append("ZBO")
            fixed_opex += env.fixed_opex(
                "ZBO",
                month,
                case_data.investments["ZBO"].fixed_opex_mln_per_year,
            ) / 12.0
        if (
            investment_commissions["EARTH_NEW"] is not None
            and month >= str(investment_commissions["EARTH_NEW"])
        ):
            active_investments.append("EARTH_NEW")
        if (
            investment_commissions["LUNAR_ISRU"] is not None
            and month >= str(investment_commissions["LUNAR_ISRU"])
        ):
            active_investments.append("LUNAR_ISRU")
            fixed_opex += env.fixed_opex(
                "LUNAR_ISRU",
                month,
                case_data.investments["LUNAR_ISRU"].fixed_opex_mln_per_year,
            ) / 12.0

        month_orders = {
            source_id: values.get(month, 0.0)
            for source_id, values in orders.items()
            if values.get(month, 0.0) != 0
        }
        reservations = {
            source_id: plan.reservation(source_id, year) for source_id in case_data.sources
        }
        pipeline = [
            shipment.to_dict()
            for shipment in shipments
            if shipment.feasible_t > 0
            and shipment.order_month <= month < shipment.actual_arrival_month
        ]
        monthly_rows.append(
            {
                "month": month,
                "opening_inventory_t": opening,
                "demand_total_t": demand_total,
                "demand_critical_t": demand_critical,
                "reserved_by_source": reservations,
                "requested_order_by_source": month_orders,
                "pipeline": pipeline,
                "planned_arrival_by_source": dict(sorted(planned_arrival.items())),
                "gross_delivery_by_source": dict(sorted(gross_delivery_by_source.items())),
                "gross_delivery_t": flow.gross_delivery_t,
                "losses_t": flow.losses_t,
                "net_delivery_t": flow.net_delivery_t,
                "accepted_delivery_t": flow.accepted_delivery_t,
                "overflow_t": flow.overflow_t,
                "available_inventory_t": available,
                "served_critical_t": service.served_critical_t,
                "served_noncritical_t": service.served_noncritical_t,
                "shortage_critical_t": service.shortage_critical_t,
                "shortage_noncritical_t": service.shortage_noncritical_t,
                "closing_inventory_t": inventory,
                "active_storage_id": storage.storage_id,
                "active_storage_capacity_t": storage_capacity,
                "active_loss_rate": loss_rate,
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

    events = investment_events(plan, case_data, env)
    source_rows: list[dict[str, Any]] = []
    for source_id, source in case_data.sources.items():
        for year in case_data.years:
            info = eligibility[(source_id, year)]
            ordered = info["ordered_t"]
            active_fraction = info["active_fraction"]
            reserved = plan.reservation(source_id, year)
            year_months = [f"{year:04d}-{number:02d}" for number in range(1, 13)]
            ordered_by_month = {
                month: orders.get(source_id, {}).get(month, 0.0)
                for month in year_months
                if orders.get(source_id, {}).get(month, 0.0) != 0
            }
            prices = {
                month: env.variable_price_for_month(
                    source_id,
                    source.name,
                    month,
                    case_data.source_price(source_id, month),
                )
                for month in year_months
            }
            reservation_rates = {
                month: env.reservation_price_for_month(
                    source_id,
                    month,
                    source.reservation_rate_mln_per_t_year_capacity,
                )
                for month in year_months
            }
            contract = priced_contract_cost(
                ordered_by_month_t=ordered_by_month,
                variable_price_by_month_mln_per_t=prices,
                active_months=info["active_months"],
                reserved_capacity_period_t=reserved * active_fraction,
                take_or_pay_share=source.take_or_pay_share,
                annual_reserved_capacity_t=reserved,
                reservation_rate_by_month_mln_per_t_year_capacity=reservation_rates,
            )
            price = contract.effective_variable_price_mln_per_t
            planned_delivery = sum(
                shipment.feasible_t
                for shipment in shipments
                if shipment.source_id == source_id
                and int(shipment.planned_arrival_month[:4]) == year
                and case_data.start_month <= shipment.planned_arrival_month <= case_data.end_month
            )
            gross_delivery = sum(
                shipment.gross_delivery_t
                for shipment in shipments
                if shipment.source_id == source_id
                and int(shipment.actual_arrival_month[:4]) == year
                and case_data.start_month <= shipment.actual_arrival_month <= case_data.end_month
            )
            delayed_delivery = sum(
                shipment.gross_delivery_t
                for shipment in shipments
                if shipment.source_id == source_id
                and shipment.actual_arrival_month > shipment.planned_arrival_month
                and int(shipment.actual_arrival_month[:4]) == year
            )
            risk_underdelivery = sum(
                shipment.feasible_t - shipment.gross_delivery_t
                for shipment in shipments
                if shipment.source_id == source_id
                and int(shipment.order_month[:4]) == year
            )
            physical_capacity = info["physical_limit_t"]
            is_preparatory_row = year == case_data.years[0] and preparatory.source_id == source_id
            prep_procurement = preparatory.procurement_cost_mln if is_preparatory_row else 0.0
            prep_reservation = preparatory.reservation_cost_mln if is_preparatory_row else 0.0
            prep_top = preparatory.take_or_pay_effect_mln if is_preparatory_row else 0.0
            source_rows.append(
                {
                    "source_id": source_id,
                    "source_name": source.name,
                    "source_status": source.status,
                    "source_provenance": source.provenance,
                    "year": year,
                    "reserved_capacity_t_per_year": reserved,
                    "active_fraction": active_fraction,
                    "requested_order_t": ordered,
                    "feasible_order_t": info["eligible_t"],
                    "unfulfilled_request_t": ordered - info["eligible_t"],
                    "planned_delivery_t": planned_delivery,
                    "gross_delivery_t": gross_delivery,
                    "risk_underdelivery_t": risk_underdelivery,
                    "delayed_delivery_t": delayed_delivery,
                    "initial_stock_requested_t": preparatory.requested_order_t if is_preparatory_row else 0.0,
                    "initial_stock_feasible_t": preparatory.feasible_order_t if is_preparatory_row else 0.0,
                    "initial_stock_gross_delivery_t": preparatory.gross_delivery_t if is_preparatory_row else 0.0,
                    "initial_stock_losses_t": preparatory.losses_t if is_preparatory_row else 0.0,
                    "initial_stock_opening_inventory_t": preparatory.opening_inventory_t if is_preparatory_row else 0.0,
                    "payable_volume_t": contract.payable_volume_t + (preparatory.payable_volume_t if is_preparatory_row else 0.0),
                    "utilization": gross_delivery / physical_capacity if physical_capacity else 0.0,
                    "active_variable_price_mln_per_t": price,
                    "ordered_payment_mln": contract.ordered_payment_mln,
                    "take_or_pay_extra_volume_t": contract.take_or_pay_extra_volume_t,
                    "take_or_pay_price_mln_per_t": contract.take_or_pay_price_mln_per_t,
                    "procurement_cost_mln": contract.variable_payment_mln + prep_procurement,
                    "reservation_cost_mln": contract.reservation_payment_mln + prep_reservation,
                    "take_or_pay_effect_mln": contract.take_or_pay_effect_mln + prep_top,
                    "initial_stock_procurement_cost_mln": prep_procurement,
                    "initial_stock_reservation_cost_mln": prep_reservation,
                    "reliability_profile": source.reliability_profile,
                    "reliability_semantics": "METADATA_ONLY",
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
        gross = sum(row["gross_delivery_t"] for row in states)
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
                "horizon_scope": case_data.horizon_provenance.get(year, {}).get(
                    "scope", "OFFICIAL_CASE_HORIZON"
                ),
                "provenance_status": case_data.demand[year].status,
                "year_provenance": case_data.horizon_provenance.get(year, {}),
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
                "shortage_t": sum(
                    row["shortage_critical_t"] + row["shortage_noncritical_t"] for row in states
                ),
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
                "initial_stock_cost_mln": preparatory.total_cost_mln if year == base_year else 0.0,
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
                "initial_stock_procurement_mln": preparatory.procurement_cost_mln if year == base_year else 0.0,
                "initial_stock_reservation_mln": preparatory.reservation_cost_mln if year == base_year else 0.0,
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
    delayed_shipments = [item for item in shipments if item.actual_arrival_month > item.planned_arrival_month]
    unavailable_requested = (
        preparatory.unfulfilled_request_t
        + preparatory.scenario_underdelivery_t
        + sum(item.unfulfilled_request_t for item in shipments)
        + sum(item.feasible_t - item.gross_delivery_t for item in shipments)
    )
    summary = {
        "run_id": run_id,
        "scenario_id": env.scenario_id,
        "base_scenario_id": env.base_scenario_id,
        "environment_id": env.environment_id,
        "risk_ids": list(env.risk_ids),
        "applied_overrides": env.applied_overrides(),
        "plan_id": plan.plan_id,
        "valid": hard_count == 0,
        "undiscounted_cost_mln": sum(row["total_cost_mln"] for row in annual_rows),
        "discounted_cost_mln": sum(row["discounted_cost_mln"] for row in annual_rows),
        "cost_per_served_ton_mln": (
            sum(row["total_cost_mln"] for row in annual_rows) / total_served
            if total_served
            else None
        ),
        "discounted_cost_per_served_ton_mln": (
            sum(row["discounted_cost_mln"] for row in annual_rows) / total_served
            if total_served
            else None
        ),
        "total_service_level": total_served / total_demand if total_demand else 1.0,
        "critical_service_level": critical_served / critical_demand if critical_demand else 1.0,
        "total_shortage_t": sum(row["shortage_t"] for row in annual_rows),
        "critical_shortage_t": sum(row["critical_shortage_t"] for row in annual_rows),
        "total_losses_t": sum(row["losses_t"] for row in annual_rows),
        "emergency_usage_t": sum(row["gross_delivery_t"] for row in source_rows if row["source_id"] == "E"),
        "final_inventory_t": monthly_rows[-1]["closing_inventory_t"],
        "minimum_inventory_t": min(row["closing_inventory_t"] for row in monthly_rows),
        "total_overflow_t": sum(row["overflow_t"] for row in monthly_rows),
        "unavailable_requested_supply_t": unavailable_requested,
        "delayed_delivery_count": len(delayed_shipments),
        "delayed_delivery_t": sum(item.gross_delivery_t for item in delayed_shipments),
        "months_with_shortage": sum(
            row["shortage_critical_t"] + row["shortage_noncritical_t"] > 1e-12
            for row in monthly_rows
        ),
        "opening_inventory_t": preparatory.opening_inventory_t,
        "initial_stock_total_cost_mln": preparatory.total_cost_mln,
        "violation_count": len(violations),
        "hard_violation_count": hard_count,
        "case_input_root": str(case_data.root),
        "scenario_source": str(env.source_path),
        "official_horizon_years": list(case_data.official_years),
        "research_extension_years": list(case_data.research_years),
        "research_source_ids": list(case_data.research_source_ids),
    }
    return SimulationResult(
        summary=summary,
        annual=annual_rows,
        monthly=monthly_rows,
        sources=source_rows,
        violations=violations,
        costs=cost_rows,
        assumptions={
            **assumptions.raw,
            "environment": {
                "base_scenario_id": env.base_scenario_id,
                "environment_id": env.environment_id,
                "risk_ids": list(env.risk_ids),
                "applied_overrides": env.applied_overrides(),
            },
            "effective_case_provenance": {
                "status": case_data.status,
                "workspace": case_data.workspace_provenance,
                "horizon": {
                    str(year): value
                    for year, value in sorted(case_data.horizon_provenance.items())
                },
                "research_sources": {
                    source_id: case_data.sources[source_id].provenance
                    for source_id in case_data.research_source_ids
                },
                "future_year_assumptions": {
                    str(year): value
                    for year, value in sorted(case_data.future_year_assumptions.items())
                },
            },
        },
        pre_horizon=preparatory.to_dict(),
    )
