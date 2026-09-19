from __future__ import annotations

import copy
import itertools
from collections import defaultdict
from typing import Any

from kosmohak.domain.assumptions import ModelAssumptions
from kosmohak.domain.case import CaseData, SupplySource
from kosmohak.domain.plan import OperatorPlan
from kosmohak.domain.scenario import Scenario
from kosmohak.domain.time import add_months, month_range
from kosmohak.simulation.availability import source_commissioning_dates
from kosmohak.simulation.environment import SimulationEnvironment, ensure_environment


def active_order_months(
    source_id: str,
    year: int,
    commissions: dict[str, str | None],
) -> list[str]:
    commission = commissions[source_id]
    if commission is None:
        return []
    return [
        month
        for month in month_range(f"{year:04d}-01", f"{year:04d}-12")
        if month >= commission
    ]


def investment_decisions(
    case_data: CaseData,
    enabled_ids: set[str],
) -> list[dict[str, Any]]:
    """Create official investment decision shapes without copying a saved plan."""
    decisions: list[dict[str, Any]] = []
    for investment_id in sorted(case_data.investments):
        enabled = investment_id in enabled_ids
        if investment_id == "ZBO":
            item: dict[str, Any] = {
                "investment_id": investment_id,
                "enabled": enabled,
            }
            if enabled:
                item["commissioning_month"] = (
                    f"{case_data.storage['ZBO'].available_from_year:04d}-01"
                )
        elif investment_id == "EARTH_NEW":
            item = {
                "investment_id": investment_id,
                "enabled": enabled,
                "buy_option": enabled,
                "exercise_option": enabled,
            }
            if enabled:
                item.update(
                    {
                        "option_purchase_month": case_data.start_month,
                        "option_exercise_month": add_months(
                            case_data.start_month, 1
                        ),
                    }
                )
        elif investment_id == "LUNAR_ISRU":
            item = {
                "investment_id": investment_id,
                "enabled": enabled,
            }
            if enabled:
                item["funding_month"] = case_data.start_month
        else:
            item = {"investment_id": investment_id, "enabled": enabled}
        decisions.append(item)
    return decisions


def _investment_sets(case_data: CaseData) -> list[set[str]]:
    ids = tuple(sorted(case_data.investments))
    values = [
        {investment_id for investment_id, flag in zip(ids, flags) if flag}
        for flags in itertools.product((False, True), repeat=len(ids))
    ]
    return sorted(
        values,
        key=lambda enabled: (
            -len(enabled),
            sum(case_data.investments[item].total_capex_mln for item in enabled),
            tuple(sorted(enabled)),
        ),
    )


def _plan_shell(
    case_data: CaseData,
    enabled_ids: set[str],
    profile: str,
    planning_scenario: Scenario,
) -> dict[str, Any]:
    return {
        "plan_id": "strategy-builder-seed",
        "scenario_id": planning_scenario.scenario_id,
        "decisions": {
            "supply_orders": [],
            "capacity_reservations": [],
            "investments": investment_decisions(case_data, enabled_ids),
            "inventory_policy": {
                "reserve_strategy_by_year": {
                    str(year): "physical" for year in case_data.years
                }
            },
            "emergency_role_by_year": {
                str(year): "reserve_only" for year in case_data.years
            },
        },
        "metadata": {
            "status": "TEAM_DECISION",
            "generated_by": "STRATEGY_BUILDER",
            "seed_profile": profile,
            "planning_scenario": planning_scenario.scenario_id,
            "provenance": {
                "decisions": "TEAM_DECISION",
                "case": "CASE_INPUT",
            },
        },
    }


def _initial_stock(
    raw: dict[str, Any],
    commissions: dict[str, str | None],
    case_data: CaseData,
    assumptions: ModelAssumptions,
    planning_scenario: Scenario,
) -> None:
    """Create a legal paid opening stock, never a free initial inventory."""
    available = [
        source
        for source in case_data.sources.values()
        if commissions[source.source_id] is not None
        and str(commissions[source.source_id]) <= case_data.start_month
    ]
    if not available:
        return
    source = min(
        available,
        key=lambda item: (
            item.variable_cost_mln_per_t
            + item.reservation_rate_mln_per_t_year_capacity,
            item.source_id,
        ),
    )
    storage = case_data.storage["BASE"]
    environment = ensure_environment(planning_scenario)
    reserve_days = float(case_data.constraints["RESERVE_45D"].value)
    desired_net = max(
        case_data.demand[year].base_total_t
        * environment.demand_multiplier(year)
        * reserve_days
        / 365.0
        for year in case_data.official_years
    )
    first_month_demand = (
        case_data.demand[case_data.official_years[0]].base_total_t
        * environment.demand_multiplier_for_month(case_data.start_month)
        / 12.0
    )
    desired_net = min(
        desired_net,
        max(0.0, storage.capacity_t - first_month_demand),
    )
    ordered = desired_net / (1.0 - storage.loss_rate_on_throughput)
    ordered = min(ordered, source.capacity_t_per_year)
    lead = assumptions.source_delivery_lead_months(source)
    order_month = add_months(case_data.start_month, -lead)
    raw["decisions"]["initial_stock_acquisition"] = {
        "source_id": source.source_id,
        "reserved_capacity_t_per_year": ordered,
        "ordered_volume_t": ordered,
        "order_date": order_month,
        "planned_delivery_date": case_data.start_month,
        "contract_period_start": f"{order_month[:4]}-01",
        "contract_period_end": f"{order_month[:4]}-12",
        "notes": "Constructive opening stock generated from official storage and lead-time data.",
        "status": "TEAM_DECISION",
    }


def _delivery_share(
    source: SupplySource,
    delivery_month: str,
    environment: SimulationEnvironment,
    case_data: CaseData,
) -> float:
    return (
        environment.actual_delivery_share(
            source.name,
            delivery_month,
            source_id=source.source_id,
        )
        * environment.availability_share(source.source_id, delivery_month)
        * case_data.source_availability_share(source.source_id, delivery_month)
    )


def _allocation_order(
    choices: list[dict[str, Any]],
    profile: str,
    delivery_month: str,
    resilience_scenario: Scenario,
    case_data: CaseData,
) -> list[dict[str, Any]]:
    resilience_env = ensure_environment(resilience_scenario)
    if profile == "MAX_RESILIENCE":
        return sorted(
            choices,
            key=lambda item: (
                -_delivery_share(
                    item["source"],
                    delivery_month,
                    resilience_env,
                    case_data,
                ),
                item["effective_cost"],
                item["source"].source_id,
            ),
        )
    if profile == "DIVERSIFIED":
        return sorted(
            choices,
            key=lambda item: (
                item["used_fraction"],
                item["effective_cost"],
                item["source"].source_id,
            ),
        )
    return sorted(
        choices,
        key=lambda item: (
            item["effective_cost"],
            item["source"].source_id,
        ),
    )


def _storage_for_month(
    raw: dict[str, Any],
    month: str,
    case_data: CaseData,
):
    zbo = next(
        (
            item
            for item in raw["decisions"]["investments"]
            if item["investment_id"] == "ZBO"
        ),
        {"enabled": False},
    )
    if zbo.get("enabled") and month >= str(zbo["commissioning_month"]):
        return case_data.storage["ZBO"]
    return case_data.storage["BASE"]


def _order_month_for_delivery(
    source: SupplySource,
    delivery_month: str,
    environment: SimulationEnvironment,
    assumptions: ModelAssumptions,
) -> str:
    base_lead = assumptions.source_delivery_lead_months(source)
    tentative = add_months(delivery_month, -base_lead)
    actual_lead = environment.lead_time_months(
        source.source_id,
        tentative,
        base_lead,
    )
    return add_months(delivery_month, -actual_lead)


def construct_seed(
    case_data: CaseData,
    assumptions: ModelAssumptions,
    base_scenario: Scenario,
    stress_scenario: Scenario,
    enabled_ids: set[str],
    profile: str,
    *,
    planning_scenario: Scenario | None = None,
) -> dict[str, Any]:
    """Construct a data-driven plan for BASE or for the provided stress scenario.

    BASE_PLAN seeds plan against BASE demand. STRESS_ADAPTATION seeds plan directly
    against MANDATORY_STRESS demand and compensates scenario delivery shares before
    the normal simulator performs the authoritative validation.
    """
    planning_scenario = planning_scenario or base_scenario
    planning_env = ensure_environment(planning_scenario)
    raw = _plan_shell(case_data, enabled_ids, profile, planning_scenario)
    provisional = OperatorPlan.from_dict(copy.deepcopy(raw))
    commissions = source_commissioning_dates(
        provisional,
        case_data,
        assumptions,
        planning_env,
    )
    _initial_stock(
        raw,
        commissions,
        case_data,
        assumptions,
        planning_scenario,
    )
    provisional = OperatorPlan.from_dict(copy.deepcopy(raw))
    commissions = source_commissioning_dates(
        provisional,
        case_data,
        assumptions,
        planning_env,
    )

    orders: dict[str, dict[str, float]] = defaultdict(dict)
    used: dict[tuple[str, int], float] = defaultdict(float)

    carry_net = 0.0
    for delivery_month in month_range(case_data.start_month, case_data.end_month):
        year = int(delivery_month[:4])
        storage = _storage_for_month(raw, delivery_month, case_data)
        loss_rate = planning_env.storage_loss_rate(
            storage.storage_id,
            delivery_month,
            storage.loss_rate_on_throughput,
        )
        needed_net = (
            case_data.demand[year].base_total_t
            * planning_env.demand_multiplier_for_month(delivery_month)
            / 12.0
        ) + carry_net
        carry_net = 0.0

        while needed_net > 1e-10:
            choices: list[dict[str, Any]] = []
            for source in case_data.sources.values():
                order_month = _order_month_for_delivery(
                    source,
                    delivery_month,
                    planning_env,
                    assumptions,
                )
                commission = commissions[source.source_id]
                if (
                    order_month < case_data.start_month
                    or order_month > case_data.end_month
                    or commission is None
                    or order_month < commission
                ):
                    continue

                order_year = int(order_month[:4])
                active = active_order_months(
                    source.source_id,
                    order_year,
                    commissions,
                )
                physical_limit = sum(
                    planning_env.source_capacity(
                        source.source_id,
                        month,
                        case_data.source_capacity(source.source_id, month),
                    )
                    / 12.0
                    for month in active
                )
                room = physical_limit - used[(source.source_id, order_year)]
                if room <= 1e-10:
                    continue

                delivery_share = _delivery_share(
                    source,
                    delivery_month,
                    planning_env,
                    case_data,
                )
                net_per_order = delivery_share * max(0.0, 1.0 - loss_rate)
                if net_per_order <= 1e-10:
                    continue
                price = planning_env.variable_price_for_month(
                    source.source_id,
                    source.name,
                    order_month,
                    source.variable_cost_mln_per_t,
                )
                effective_cost = (
                    price + source.reservation_rate_mln_per_t_year_capacity
                ) / net_per_order
                choices.append(
                    {
                        "source": source,
                        "order_month": order_month,
                        "order_year": order_year,
                        "room": room,
                        "net_per_order": net_per_order,
                        "effective_cost": effective_cost,
                        "used_fraction": (
                            used[(source.source_id, order_year)] / physical_limit
                            if physical_limit
                            else 1.0
                        ),
                    }
                )

            if not choices:
                break

            ranked = _allocation_order(
                choices,
                profile,
                delivery_month,
                stress_scenario,
                case_data,
            )
            choice = ranked[0]
            if profile == "DIVERSIFIED":
                requested = min(
                    choice["room"],
                    (needed_net / len(ranked)) / choice["net_per_order"],
                )
            else:
                requested = min(
                    choice["room"],
                    needed_net / choice["net_per_order"],
                )
            if requested <= 1e-10:
                break

            source_id = choice["source"].source_id
            order_month = choice["order_month"]
            orders[source_id][order_month] = (
                orders[source_id].get(order_month, 0.0) + requested
            )
            used[(source_id, choice["order_year"])] += requested
            needed_net -= requested * choice["net_per_order"]

        if needed_net > 1e-10:
            carry_net = needed_net

    raw["decisions"]["supply_orders"] = [
        {
            "source_id": source_id,
            "mode": "monthly",
            "values": dict(sorted(orders.get(source_id, {}).items())),
        }
        for source_id in sorted(case_data.sources)
    ]

    reservations = []
    for (source_id, year), total in sorted(used.items()):
        if total <= 1e-10:
            continue
        active_fraction = len(
            active_order_months(source_id, year, commissions)
        ) / 12.0
        if active_fraction <= 0:
            continue
        reservations.append(
            {
                "source_id": source_id,
                "year": year,
                "reserved_capacity_t": min(
                    case_data.source_capacity(source_id, year),
                    total / active_fraction + 1e-10,
                ),
            }
        )
    raw["decisions"]["capacity_reservations"] = reservations
    return raw


def constructive_seeds(
    case_data: CaseData,
    assumptions: ModelAssumptions,
    base_scenario: Scenario,
    stress_scenario: Scenario,
    *,
    planning_mode: str = "BASE_PLAN",
) -> list[dict[str, Any]]:
    planning_scenario = (
        base_scenario if planning_mode == "BASE_PLAN" else stress_scenario
    )
    seeds: list[dict[str, Any]] = []
    for enabled_ids in _investment_sets(case_data):
        for profile in ("MIN_COST", "MAX_RESILIENCE", "DIVERSIFIED"):
            seeds.append(
                construct_seed(
                    case_data,
                    assumptions,
                    base_scenario,
                    stress_scenario,
                    enabled_ids,
                    profile,
                    planning_scenario=planning_scenario,
                )
            )
    return seeds
