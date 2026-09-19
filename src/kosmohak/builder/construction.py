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
from kosmohak.simulation.environment import ensure_environment


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
    """Create official investment decision shapes without copying a plan."""
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
    scenario_id: str,
) -> dict[str, Any]:
    return {
        "plan_id": "strategy-builder-seed",
        "scenario_id": scenario_id,
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
) -> None:
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
    desired_net = storage.capacity_t * 0.95
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


def _stress_share(
    source: SupplySource,
    delivery_month: str,
    stress_scenario: Scenario,
) -> float:
    environment = ensure_environment(stress_scenario)
    return environment.actual_delivery_share(
        source.name,
        delivery_month,
        source_id=source.source_id,
    )


def _allocation_order(
    choices: list[dict[str, Any]],
    profile: str,
    delivery_month: str,
    stress_scenario: Scenario,
) -> list[dict[str, Any]]:
    if profile == "MAX_RESILIENCE":
        return sorted(
            choices,
            key=lambda item: (
                -_stress_share(item["source"], delivery_month, stress_scenario),
                item["source"].variable_cost_mln_per_t,
                item["source"].source_id,
            ),
        )
    if profile == "DIVERSIFIED":
        return sorted(
            choices,
            key=lambda item: (
                item["used_fraction"],
                item["source"].variable_cost_mln_per_t,
                item["source"].source_id,
            ),
        )
    return sorted(
        choices,
        key=lambda item: (
            item["source"].variable_cost_mln_per_t
            + item["source"].reservation_rate_mln_per_t_year_capacity,
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


def construct_seed(
    case_data: CaseData,
    assumptions: ModelAssumptions,
    base_scenario: Scenario,
    stress_scenario: Scenario,
    enabled_ids: set[str],
    profile: str,
    planning_scenario: Scenario | None = None,
) -> dict[str, Any]:
    planning_scenario = planning_scenario or base_scenario
    raw = _plan_shell(
        case_data, enabled_ids, profile, planning_scenario.scenario_id
    )
    provisional = OperatorPlan.from_dict(copy.deepcopy(raw))
    commissions = source_commissioning_dates(
        provisional,
        case_data,
        assumptions,
        ensure_environment(planning_scenario),
    )
    _initial_stock(raw, commissions, case_data, assumptions)
    provisional = OperatorPlan.from_dict(copy.deepcopy(raw))
    commissions = source_commissioning_dates(
        provisional,
        case_data,
        assumptions,
        ensure_environment(base_scenario),
    )

    orders: dict[str, dict[str, float]] = defaultdict(dict)
    used: dict[tuple[str, int], float] = defaultdict(float)
    for delivery_month in month_range(case_data.start_month, case_data.end_month):
        year = int(delivery_month[:4])
        storage = _storage_for_month(raw, delivery_month, case_data)
        demand_multiplier = ensure_environment(
            planning_scenario
        ).demand_multiplier_for_month(delivery_month)
        needed = (
            case_data.demand[year].base_total_t
            * demand_multiplier
            / 12.0
            / (1.0 - storage.loss_rate_on_throughput)
        )
        while needed > 1e-10:
            choices: list[dict[str, Any]] = []
            for source in case_data.sources.values():
                lead = assumptions.source_delivery_lead_months(source)
                order_month = add_months(delivery_month, -lead)
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
                    source.source_id, order_year, commissions
                )
                physical_limit = (
                    case_data.source_capacity(source.source_id, order_year)
                    * len(active)
                    / 12.0
                )
                room = physical_limit - used[(source.source_id, order_year)]
                if room <= 1e-10:
                    continue
                choices.append(
                    {
                        "source": source,
                        "order_month": order_month,
                        "order_year": order_year,
                        "room": room,
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
                choices, profile, delivery_month, stress_scenario
            )
            choice = ranked[0]
            if profile == "DIVERSIFIED":
                amount = min(choice["room"], needed / len(ranked))
            else:
                amount = min(choice["room"], needed)
            if amount <= 1e-10:
                break
            source_id = choice["source"].source_id
            order_month = choice["order_month"]
            orders[source_id][order_month] = (
                orders[source_id].get(order_month, 0.0) + amount
            )
            used[(source_id, choice["order_year"])] += amount
            needed -= amount

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
    planning_scenario: Scenario | None = None,
) -> list[dict[str, Any]]:
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
