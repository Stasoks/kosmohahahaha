from __future__ import annotations

import copy
import hashlib
import json
import random
from dataclasses import dataclass
from typing import Any

from kosmohak.builder.construction import active_order_months, constructive_seeds
from kosmohak.builder.domain import (
    StrategyBuilderConfig,
    StrategyBuilderResult,
    StrategyBuilderSolution,
)
from kosmohak.domain.assumptions import ModelAssumptions
from kosmohak.domain.case import CaseData
from kosmohak.domain.plan import OperatorPlan
from kosmohak.domain.result import SimulationResult
from kosmohak.domain.scenario import Scenario
from kosmohak.domain.time import add_months
from kosmohak.loading.plan import PlanLoader, PlanValidationError
from kosmohak.simulation.availability import source_commissioning_dates
from kosmohak.simulation.engine import simulate
from kosmohak.simulation.environment import ensure_environment


@dataclass
class _Candidate:
    canonical_key: str
    plan: OperatorPlan
    base_result: SimulationResult
    stress_result: SimulationResult
    metrics: dict[str, Any]
    target_satisfaction: dict[str, Any]
    depth: int
    history: tuple[str, ...]


def _canonical_decisions(raw: dict[str, Any]) -> str:
    return json.dumps(
        raw["decisions"],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _plan_id(canonical: str, seed: int) -> str:
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
    return f"strategy-builder-{seed}-{digest}"


def _cheap_prevalidate(raw: dict[str, Any], case_data: CaseData) -> bool:
    decisions = raw.get("decisions")
    if not isinstance(decisions, dict):
        return False
    official_sources = set(case_data.sources)
    official_years = set(case_data.official_years)
    for schedule in decisions.get("supply_orders", []):
        if schedule.get("source_id") not in official_sources:
            return False
        for period, value in schedule.get("values", {}).items():
            if float(value) < 0 or int(str(period)[:4]) not in official_years:
                return False
    for reservation in decisions.get("capacity_reservations", []):
        source_id = reservation.get("source_id")
        year = int(reservation.get("year", -1))
        value = float(reservation.get("reserved_capacity_t", -1))
        if (
            source_id not in official_sources
            or year not in official_years
            or value < 0
            or value > case_data.source_capacity(source_id, year) + 1e-8
        ):
            return False
    return all(
        item.get("investment_id") in case_data.investments
        for item in decisions.get("investments", [])
    )


def _source_mix(result: SimulationResult, case_data: CaseData) -> dict[str, float]:
    return {
        source_id: sum(
            row["gross_delivery_t"]
            for row in result.sources
            if row["source_id"] == source_id
        )
        for source_id in sorted(case_data.sources)
    }


def _metrics(
    plan: OperatorPlan,
    base: SimulationResult,
    stress: SimulationResult,
    case_data: CaseData,
) -> dict[str, Any]:
    enabled = sorted(
        str(item["investment_id"])
        for item in plan.investments
        if item.get("enabled")
    )
    return {
        "minimum_annual_base_total_service": min(
            row["total_service_level"] for row in base.annual
        ),
        "minimum_annual_base_critical_service": min(
            row["critical_service_level"] for row in base.annual
        ),
        "minimum_annual_stress_total_service": min(
            row["total_service_level"] for row in stress.annual
        ),
        "minimum_annual_stress_critical_service": min(
            row["critical_service_level"] for row in stress.annual
        ),
        "total_cost_mln": base.summary["undiscounted_cost_mln"],
        "stress_total_shortage_t": stress.summary["total_shortage_t"],
        "stress_critical_shortage_t": stress.summary["critical_shortage_t"],
        "minimum_stress_inventory_t": stress.summary["minimum_inventory_t"],
        "minimum_annual_stress_reserve_days": min(
            row["reserve_actual_days"] for row in stress.annual
        ),
        "base_hard_violation_count": base.summary["hard_violation_count"],
        "base_total_shortage_t": base.summary["total_shortage_t"],
        "source_mix_t": _source_mix(base, case_data),
        "enabled_investments": enabled,
    }


def _target_satisfaction(
    metrics: dict[str, Any],
    config: StrategyBuilderConfig,
) -> dict[str, Any]:
    definitions = {
        "stress_total_service": (
            config.stress_total_service_target,
            metrics["minimum_annual_stress_total_service"],
            ">=",
        ),
        "stress_critical_service": (
            config.stress_critical_service_target,
            metrics["minimum_annual_stress_critical_service"],
            ">=",
        ),
        "maximum_total_cost_mln": (
            config.max_total_cost_mln,
            metrics["total_cost_mln"],
            "<=",
        ),
    }
    values: dict[str, Any] = {}
    for name, (target, actual, operator) in definitions.items():
        if target is None:
            satisfied = True
        elif operator == ">=":
            satisfied = actual >= target - 1e-12
        else:
            satisfied = actual <= target + 1e-12
        values[name] = {
            "target": target,
            "actual": actual,
            "operator": operator,
            "satisfied": satisfied,
            "provenance": "OPERATOR_PREFERENCE",
        }
    values["all_satisfied"] = all(
        item["satisfied"] for item in values.values() if isinstance(item, dict)
    )
    return values


def _target_deficit(candidate: _Candidate) -> float:
    total = 0.0
    for item in candidate.target_satisfaction.values():
        if not isinstance(item, dict) or item["target"] is None:
            continue
        if item["operator"] == ">=":
            total += max(0.0, float(item["target"]) - float(item["actual"]))
        else:
            scale = max(1.0, float(item["target"]))
            total += max(0.0, float(item["actual"]) - float(item["target"])) / scale
    return total


def _annual_target_deficit(candidate: _Candidate) -> float:
    """Measure annual service-target gap, with critical service weighted higher."""
    total_target = candidate.target_satisfaction["stress_total_service"]["target"]
    critical_target = candidate.target_satisfaction["stress_critical_service"]["target"]
    total = 0.0
    for row in candidate.stress_result.annual:
        if total_target is not None:
            required = float(total_target) * float(row["demand_total_t"])
            total += max(0.0, required - float(row["served_total_t"])) / max(
                1.0, float(row["demand_total_t"])
            )
        if critical_target is not None:
            required = float(critical_target) * float(row["demand_critical_t"])
            total += 4.0 * max(
                0.0, required - float(row["served_critical_t"])
            ) / max(1.0, float(row["demand_critical_t"]))
    return total


def _rank(candidate: _Candidate, objective: str) -> tuple:
    metrics = candidate.metrics
    has_targets = any(
        value is not None
        for value in (
            candidate.target_satisfaction["stress_total_service"]["target"],
            candidate.target_satisfaction["stress_critical_service"]["target"],
            candidate.target_satisfaction["maximum_total_cost_mln"]["target"],
        )
    )
    feasibility = (
        metrics["base_hard_violation_count"],
        _annual_target_deficit(candidate) if has_targets else 0.0,
        _target_deficit(candidate),
        metrics["base_total_shortage_t"],
    )
    resilience = (
        -metrics["minimum_annual_stress_critical_service"],
        -metrics["minimum_annual_stress_total_service"],
        metrics["stress_critical_shortage_t"],
        metrics["stress_total_shortage_t"],
        -metrics["minimum_annual_stress_reserve_days"],
        -metrics["minimum_stress_inventory_t"],
        metrics["total_cost_mln"],
    )
    if objective == "MAX_RESILIENCE":
        return (*feasibility, *resilience, candidate.canonical_key)
    return (
        *feasibility,
        metrics["total_cost_mln"],
        *resilience,
        candidate.canonical_key,
    )


def _solution_rank(candidate: _Candidate, objective: str) -> tuple:
    metrics = candidate.metrics
    if objective == "MAX_RESILIENCE":
        return (
            -metrics["minimum_annual_stress_critical_service"],
            -metrics["minimum_annual_stress_total_service"],
            metrics["stress_critical_shortage_t"],
            metrics["stress_total_shortage_t"],
            -metrics["minimum_annual_stress_reserve_days"],
            -metrics["minimum_stress_inventory_t"],
            metrics["total_cost_mln"],
            candidate.canonical_key,
        )
    return (
        metrics["total_cost_mln"],
        -metrics["minimum_annual_stress_critical_service"],
        -metrics["minimum_annual_stress_total_service"],
        metrics["stress_critical_shortage_t"],
        metrics["stress_total_shortage_t"],
        candidate.canonical_key,
    )


def _schedule(raw: dict[str, Any], source_id: str) -> dict[str, Any]:
    return next(
        item
        for item in raw["decisions"]["supply_orders"]
        if str(item["source_id"]) == source_id
    )


def _commissions(
    raw: dict[str, Any],
    base_scenario: Scenario,
    case_data: CaseData,
    assumptions: ModelAssumptions,
) -> dict[str, str | None]:
    return source_commissioning_dates(
        OperatorPlan.from_dict(copy.deepcopy(raw)),
        case_data,
        assumptions,
        ensure_environment(base_scenario),
    )


def _year_total(schedule: dict[str, Any], year: int) -> float:
    return sum(
        float(value)
        for period, value in schedule.get("values", {}).items()
        if int(str(period)[:4]) == year
    )


def _rebuild_reservations(
    raw: dict[str, Any],
    commissions: dict[str, str | None],
    case_data: CaseData,
) -> None:
    reservations: list[dict[str, Any]] = []
    for schedule in raw["decisions"]["supply_orders"]:
        source_id = str(schedule["source_id"])
        for year in case_data.official_years:
            total = _year_total(schedule, year)
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
    raw["decisions"]["capacity_reservations"] = sorted(
        reservations, key=lambda item: (item["source_id"], item["year"])
    )


def _volume_mutations(
    candidate: _Candidate,
    config: StrategyBuilderConfig,
    base_scenario: Scenario,
    case_data: CaseData,
    assumptions: ModelAssumptions,
) -> list[tuple[dict[str, Any], str]]:
    raw = candidate.plan.raw
    commissions = _commissions(raw, base_scenario, case_data, assumptions)
    output: list[tuple[dict[str, Any], str]] = []
    for source_id in sorted(case_data.sources):
        source = case_data.sources[source_id]
        schedule = _schedule(raw, source_id)
        lead = assumptions.source_delivery_lead_months(source)
        for year in case_data.official_years:
            active = active_order_months(source_id, year, commissions)
            useful = [
                month
                for month in active
                if add_months(month, lead) <= case_data.end_month
            ]
            current = _year_total(schedule, year)
            physical_limit = case_data.source_capacity(source_id, year) * len(
                active
            ) / 12.0
            room = max(0.0, physical_limit - current)
            for fraction in config.mutation_fractions:
                if room > 1e-9 and useful:
                    value = copy.deepcopy(raw)
                    target = _schedule(value, source_id)
                    increment = min(room, case_data.source_capacity(source_id, year) * fraction)
                    for month in useful:
                        target["values"][month] = float(
                            target["values"].get(month, 0.0)
                        ) + increment / len(useful)
                    _rebuild_reservations(value, commissions, case_data)
                    output.append(
                        (
                            value,
                            f"increase:{source_id}:{year}:{fraction:.4f}",
                        )
                    )
                if current > 1e-9:
                    value = copy.deepcopy(raw)
                    target = _schedule(value, source_id)
                    for period in list(target["values"]):
                        if int(str(period)[:4]) == year:
                            target["values"][period] = float(
                                target["values"][period]
                            ) * (1.0 - fraction)
                    _rebuild_reservations(value, commissions, case_data)
                    output.append(
                        (
                            value,
                            f"decrease:{source_id}:{year}:{fraction:.4f}",
                        )
                    )
    acquisition = raw["decisions"].get("initial_stock_acquisition")
    if acquisition:
        for fraction in config.mutation_fractions:
            value = copy.deepcopy(raw)
            target = value["decisions"]["initial_stock_acquisition"]
            target["ordered_volume_t"] *= 1.0 - fraction
            target["reserved_capacity_t_per_year"] = target["ordered_volume_t"]
            output.append((value, f"decrease:initial_stock:{fraction:.4f}"))
    return output


def _transfer_mutations(
    candidate: _Candidate,
    config: StrategyBuilderConfig,
    base_scenario: Scenario,
    stress_scenario: Scenario,
    case_data: CaseData,
    assumptions: ModelAssumptions,
) -> list[tuple[dict[str, Any], str]]:
    raw = candidate.plan.raw
    commissions = _commissions(raw, base_scenario, case_data, assumptions)
    environment = ensure_environment(stress_scenario)
    output: list[tuple[dict[str, Any], str]] = []
    largest_fraction = max(config.mutation_fractions)
    for delivery_year in case_data.official_years:
        for source_from in sorted(case_data.sources):
            from_source = case_data.sources[source_from]
            from_schedule = _schedule(raw, source_from)
            from_lead = assumptions.source_delivery_lead_months(from_source)
            periods = [
                period
                for period, amount in from_schedule["values"].items()
                if float(amount) > 1e-10
                and int(add_months(str(period), from_lead)[:4]) == delivery_year
            ]
            if not periods:
                continue
            reference_month = add_months(str(periods[0]), from_lead)
            from_share = environment.actual_delivery_share(
                from_source.name,
                reference_month,
                source_id=source_from,
            )
            total_from = sum(float(from_schedule["values"][item]) for item in periods)
            for source_to in sorted(case_data.sources):
                if source_to == source_from:
                    continue
                to_source = case_data.sources[source_to]
                to_share = environment.actual_delivery_share(
                    to_source.name,
                    reference_month,
                    source_id=source_to,
                )
                if to_share <= from_share + 1e-12:
                    continue
                to_lead = assumptions.source_delivery_lead_months(to_source)
                value = copy.deepcopy(raw)
                from_target = _schedule(value, source_from)
                to_target = _schedule(value, source_to)
                remaining = total_from * largest_fraction
                moved = 0.0
                for from_period in sorted(periods):
                    arrival = add_months(from_period, from_lead)
                    to_period = add_months(arrival, -to_lead)
                    if (
                        to_period < case_data.start_month
                        or to_period > case_data.end_month
                        or commissions[source_to] is None
                        or to_period < str(commissions[source_to])
                    ):
                        continue
                    to_year = int(to_period[:4])
                    active = active_order_months(source_to, to_year, commissions)
                    physical_limit = case_data.source_capacity(
                        source_to, to_year
                    ) * len(active) / 12.0
                    room = physical_limit - _year_total(to_target, to_year)
                    available = float(from_target["values"][from_period])
                    amount = min(remaining, available, max(0.0, room))
                    if amount <= 1e-10:
                        continue
                    from_target["values"][from_period] = available - amount
                    to_target["values"][to_period] = float(
                        to_target["values"].get(to_period, 0.0)
                    ) + amount
                    remaining -= amount
                    moved += amount
                    if remaining <= 1e-10:
                        break
                if moved > 1e-9:
                    _rebuild_reservations(value, commissions, case_data)
                    output.append(
                        (
                            value,
                            f"transfer:{delivery_year}:{source_from}->{source_to}:{moved:.6f}",
                        )
                    )
    return output


def _stress_repair_requirements(
    candidate: _Candidate,
    config: StrategyBuilderConfig,
) -> dict[str, float]:
    """Return net tons that must be recovered in shortage months to hit annual targets."""
    total_target = config.stress_total_service_target
    critical_target = config.stress_critical_service_target
    if total_target is None and critical_target is None:
        return {}

    monthly_by_year: dict[int, list[dict[str, Any]]] = {}
    for row in candidate.stress_result.monthly:
        monthly_by_year.setdefault(int(str(row["month"])[:4]), []).append(row)

    requirements: dict[str, float] = {}
    for annual in candidate.stress_result.annual:
        year = int(annual["year"])
        rows = sorted(monthly_by_year.get(year, []), key=lambda item: item["month"])
        total_need = 0.0
        critical_need = 0.0
        if total_target is not None:
            total_need = max(
                0.0,
                float(total_target) * float(annual["demand_total_t"])
                - float(annual["served_total_t"]),
            )
        if critical_target is not None:
            critical_need = max(
                0.0,
                float(critical_target) * float(annual["demand_critical_t"])
                - float(annual["served_critical_t"]),
            )
        if total_need <= 1e-10 and critical_need <= 1e-10:
            continue

        used_by_month: dict[str, float] = {}
        remaining_critical = critical_need
        for row in sorted(
            rows,
            key=lambda item: (
                -float(item["shortage_critical_t"]),
                item["month"],
            ),
        ):
            if remaining_critical <= 1e-10:
                break
            available = float(row["shortage_critical_t"])
            if available <= 1e-10:
                continue
            amount = min(remaining_critical, available)
            month = str(row["month"])
            requirements[month] = requirements.get(month, 0.0) + amount
            used_by_month[month] = used_by_month.get(month, 0.0) + amount
            remaining_critical -= amount

        remaining_total = max(0.0, total_need - (critical_need - remaining_critical))
        for row in sorted(
            rows,
            key=lambda item: (
                -(
                    float(item["shortage_critical_t"])
                    + float(item["shortage_noncritical_t"])
                ),
                item["month"],
            ),
        ):
            if remaining_total <= 1e-10:
                break
            month = str(row["month"])
            shortage = (
                float(row["shortage_critical_t"])
                + float(row["shortage_noncritical_t"])
            )
            available = max(0.0, shortage - used_by_month.get(month, 0.0))
            if available <= 1e-10:
                continue
            amount = min(remaining_total, available)
            requirements[month] = requirements.get(month, 0.0) + amount
            used_by_month[month] = used_by_month.get(month, 0.0) + amount
            remaining_total -= amount

    return {month: amount for month, amount in requirements.items() if amount > 1e-10}


def _target_repair_candidate(
    candidate: _Candidate,
    config: StrategyBuilderConfig,
    profile: str,
    base_scenario: Scenario,
    stress_scenario: Scenario,
    case_data: CaseData,
    assumptions: ModelAssumptions,
) -> tuple[dict[str, Any], str] | None:
    requirements = _stress_repair_requirements(candidate, config)
    if not requirements:
        return None

    value = copy.deepcopy(candidate.plan.raw)
    commissions = _commissions(value, base_scenario, case_data, assumptions)
    stress_env = ensure_environment(stress_scenario)
    stress_rows = {
        str(row["month"]): row for row in candidate.stress_result.monthly
    }

    for delivery_month, required_net in sorted(requirements.items()):
        remaining = required_net
        while remaining > 1e-8:
            choices: list[dict[str, Any]] = []
            for source_id in sorted(case_data.sources):
                source = case_data.sources[source_id]
                delivery_year = int(delivery_month[:4])
                if (
                    source_id == "E"
                    and candidate.plan.emergency_role_by_year.get(delivery_year)
                    == "reserve_only"
                ):
                    continue
                lead = stress_env.lead_time_months(
                    source_id,
                    delivery_month,
                    assumptions.source_delivery_lead_months(source),
                )
                order_month = add_months(delivery_month, -lead)
                commission = commissions.get(source_id)
                if (
                    commission is None
                    or order_month < case_data.start_month
                    or order_month > case_data.end_month
                    or order_month < str(commission)
                ):
                    continue
                order_year = int(order_month[:4])
                active = active_order_months(source_id, order_year, commissions)
                if not active:
                    continue
                schedule = _schedule(value, source_id)
                physical_limit = (
                    case_data.source_capacity(source_id, order_year)
                    * len(active)
                    / 12.0
                )
                current = _year_total(schedule, order_year)
                room = max(0.0, physical_limit - current)
                if room <= 1e-10:
                    continue
                delivery_share = stress_env.actual_delivery_share(
                    source.name,
                    delivery_month,
                    source_id=source_id,
                )
                delivery_share *= stress_env.availability_share(
                    source_id, delivery_month
                )
                loss_rate = float(stress_rows[delivery_month]["active_loss_rate"])
                net_per_order = delivery_share * max(0.0, 1.0 - loss_rate)
                if net_per_order <= 1e-10:
                    continue
                variable_cost = stress_env.variable_price_for_month(
                    source_id,
                    source.name,
                    order_month,
                    source.variable_cost_mln_per_t,
                )
                effective_cost = (
                    variable_cost + source.reservation_rate_mln_per_t_year_capacity
                ) / net_per_order
                choices.append(
                    {
                        "source_id": source_id,
                        "order_month": order_month,
                        "room": room,
                        "net_per_order": net_per_order,
                        "effective_cost": effective_cost,
                        "delivery_share": delivery_share,
                        "used_fraction": current / physical_limit if physical_limit else 1.0,
                    }
                )
            if not choices:
                break
            if profile == "RELIABILITY":
                choices.sort(
                    key=lambda item: (
                        -item["delivery_share"],
                        item["effective_cost"],
                        item["used_fraction"],
                        item["source_id"],
                    )
                )
            elif profile == "DIVERSIFIED":
                choices.sort(
                    key=lambda item: (
                        item["used_fraction"],
                        item["effective_cost"],
                        -item["delivery_share"],
                        item["source_id"],
                    )
                )
            else:
                choices.sort(
                    key=lambda item: (
                        item["effective_cost"],
                        -item["delivery_share"],
                        item["used_fraction"],
                        item["source_id"],
                    )
                )
            choice = choices[0]
            requested = min(
                float(choice["room"]),
                remaining / float(choice["net_per_order"]),
            )
            if requested <= 1e-10:
                break
            schedule = _schedule(value, str(choice["source_id"]))
            order_month = str(choice["order_month"])
            schedule["values"][order_month] = float(
                schedule["values"].get(order_month, 0.0)
            ) + requested
            remaining -= requested * float(choice["net_per_order"])

    _rebuild_reservations(value, commissions, case_data)
    canonical_before = _canonical_decisions(candidate.plan.raw)
    canonical_after = _canonical_decisions(value)
    if canonical_before == canonical_after:
        return None
    return (
        value,
        "target_repair:"
        f"{profile.lower()}:"
        f"{sum(requirements.values()):.6f}net_t",
    )


def _target_repair_mutations(
    candidate: _Candidate,
    config: StrategyBuilderConfig,
    base_scenario: Scenario,
    stress_scenario: Scenario,
    case_data: CaseData,
    assumptions: ModelAssumptions,
) -> list[tuple[dict[str, Any], str]]:
    values: list[tuple[dict[str, Any], str]] = []
    for profile in ("COST", "RELIABILITY", "DIVERSIFIED"):
        item = _target_repair_candidate(
            candidate,
            config,
            profile,
            base_scenario,
            stress_scenario,
            case_data,
            assumptions,
        )
        if item is not None:
            values.append(item)
    return values


def _investment_timing_mutations(
    candidate: _Candidate,
    case_data: CaseData,
) -> list[tuple[dict[str, Any], str]]:
    """Explore operator-controlled investment timing without changing CASE_INPUT."""
    raw = candidate.plan.raw
    output: list[tuple[dict[str, Any], str]] = []

    for item in raw["decisions"].get("investments", []):
        if not item.get("enabled"):
            continue
        investment_id = str(item.get("investment_id"))

        if investment_id == "ZBO" and item.get("commissioning_month"):
            current = str(item["commissioning_month"])
            earliest = max(
                case_data.start_month,
                f"{case_data.storage['ZBO'].available_from_year:04d}-01",
            )
            for delta in (-12, 12):
                target_month = add_months(current, delta)
                if not earliest <= target_month <= case_data.end_month:
                    continue
                value = copy.deepcopy(raw)
                target = next(
                    investment
                    for investment in value["decisions"]["investments"]
                    if investment["investment_id"] == investment_id
                )
                target["commissioning_month"] = target_month
                output.append(
                    (
                        value,
                        f"investment_timing:{investment_id}:{current}->{target_month}",
                    )
                )

        elif (
            investment_id == "EARTH_NEW"
            and item.get("buy_option")
            and item.get("exercise_option")
            and item.get("option_purchase_month")
            and item.get("option_exercise_month")
        ):
            purchase = str(item["option_purchase_month"])
            exercise = str(item["option_exercise_month"])
            for delta in (-12, 12):
                target_purchase = add_months(purchase, delta)
                target_exercise = add_months(exercise, delta)
                if not (
                    case_data.start_month
                    <= target_purchase
                    < target_exercise
                    <= case_data.end_month
                ):
                    continue
                value = copy.deepcopy(raw)
                target = next(
                    investment
                    for investment in value["decisions"]["investments"]
                    if investment["investment_id"] == investment_id
                )
                target["option_purchase_month"] = target_purchase
                target["option_exercise_month"] = target_exercise
                output.append(
                    (
                        value,
                        "investment_timing:"
                        f"{investment_id}:{purchase}/{exercise}->"
                        f"{target_purchase}/{target_exercise}",
                    )
                )

        elif investment_id == "LUNAR_ISRU" and item.get("funding_month"):
            current = str(item["funding_month"])
            linked_sources = [
                source
                for source in case_data.sources.values()
                if str(source.availability_rule.get("investment_id", ""))
                == investment_id
                and source.available_from_year is not None
            ]
            if not linked_sources:
                continue
            latest_available_year = min(
                int(source.available_from_year) for source in linked_sources
            )
            latest = f"{latest_available_year - 1:04d}-12"
            for delta in (-12, 12):
                target_month = add_months(current, delta)
                if not case_data.start_month <= target_month <= latest:
                    continue
                value = copy.deepcopy(raw)
                target = next(
                    investment
                    for investment in value["decisions"]["investments"]
                    if investment["investment_id"] == investment_id
                )
                target["funding_month"] = target_month
                output.append(
                    (
                        value,
                        f"investment_timing:{investment_id}:{current}->{target_month}",
                    )
                )

    return output


def _policy_mutations(
    candidate: _Candidate,
    case_data: CaseData,
) -> list[tuple[dict[str, Any], str]]:
    """Explore reserve and Emergency policy choices that belong to TEAM_DECISION."""
    raw = candidate.plan.raw
    output: list[tuple[dict[str, Any], str]] = []

    strategies = raw["decisions"].setdefault("inventory_policy", {}).setdefault(
        "reserve_strategy_by_year", {}
    )
    emergency_roles = raw["decisions"].setdefault("emergency_role_by_year", {})

    for year in case_data.official_years:
        year_key = str(year)

        current_strategy = str(
            strategies.get(year_key, strategies.get(year, "physical"))
        )
        target_strategy = (
            "emergency_contract"
            if current_strategy == "physical"
            else "physical"
        )
        value = copy.deepcopy(raw)
        value["decisions"]["inventory_policy"]["reserve_strategy_by_year"][
            year_key
        ] = target_strategy
        output.append(
            (
                value,
                f"reserve_policy:{year}:{current_strategy}->{target_strategy}",
            )
        )

        current_role = str(
            emergency_roles.get(year_key, emergency_roles.get(year, "reserve_only"))
        )
        target_role = (
            "planned_supply"
            if current_role == "reserve_only"
            else "reserve_only"
        )
        value = copy.deepcopy(raw)
        value["decisions"].setdefault("emergency_role_by_year", {})[
            year_key
        ] = target_role
        output.append(
            (
                value,
                f"emergency_role:{year}:{current_role}->{target_role}",
            )
        )

    return output


def _mutations(
    candidate: _Candidate,
    config: StrategyBuilderConfig,
    base_scenario: Scenario,
    stress_scenario: Scenario,
    case_data: CaseData,
    assumptions: ModelAssumptions,
) -> list[tuple[dict[str, Any], str]]:
    values = _volume_mutations(
        candidate, config, base_scenario, case_data, assumptions
    )
    values.extend(
        _transfer_mutations(
            candidate,
            config,
            base_scenario,
            stress_scenario,
            case_data,
            assumptions,
        )
    )
    values.extend(_investment_timing_mutations(candidate, case_data))
    values.extend(_policy_mutations(candidate, case_data))
    return values


def _dominates(first: _Candidate, second: _Candidate) -> bool:
    a, b = first.metrics, second.metrics
    first_vector = (
        a["base_hard_violation_count"],
        _annual_target_deficit(first),
        _target_deficit(first),
        a["base_total_shortage_t"],
        a["total_cost_mln"],
        a["stress_critical_shortage_t"],
        a["stress_total_shortage_t"],
        -a["minimum_stress_inventory_t"],
    )
    second_vector = (
        b["base_hard_violation_count"],
        _annual_target_deficit(second),
        _target_deficit(second),
        b["base_total_shortage_t"],
        b["total_cost_mln"],
        b["stress_critical_shortage_t"],
        b["stress_total_shortage_t"],
        -b["minimum_stress_inventory_t"],
    )
    return all(x <= y + 1e-12 for x, y in zip(first_vector, second_vector)) and any(
        x < y - 1e-12 for x, y in zip(first_vector, second_vector)
    )


def _structural_signature(candidate: _Candidate) -> tuple:
    mix = candidate.metrics["source_mix_t"]
    return (
        tuple(candidate.metrics["enabled_investments"]),
        tuple(source_id for source_id, value in mix.items() if value > 1e-8),
    )


def _dominance_prune(candidates: list[_Candidate]) -> tuple[list[_Candidate], int]:
    kept: list[_Candidate] = []
    pruned = 0
    for candidate in candidates:
        signature = _structural_signature(candidate)
        if any(
            _structural_signature(other) == signature
            and _dominates(other, candidate)
            for other in kept
        ):
            pruned += 1
            continue
        kept = [
            other
            for other in kept
            if not (
                _structural_signature(other) == signature
                and _dominates(candidate, other)
            )
        ]
        kept.append(candidate)
    return kept, pruned


def _is_diverse(
    candidate: _Candidate,
    selected: list[_Candidate],
    threshold: float,
) -> bool:
    if not selected:
        return True
    mix = candidate.metrics["source_mix_t"]
    total = sum(mix.values()) or 1.0
    shares = {key: value / total for key, value in mix.items()}
    investments = tuple(candidate.metrics["enabled_investments"])
    for other in selected:
        if tuple(other.metrics["enabled_investments"]) != investments:
            continue
        other_mix = other.metrics["source_mix_t"]
        other_total = sum(other_mix.values()) or 1.0
        distance = sum(
            abs(shares.get(key, 0.0) - other_mix.get(key, 0.0) / other_total)
            for key in set(shares) | set(other_mix)
        )
        if distance < threshold:
            return False
    return True


def _solution(candidate: _Candidate, config: StrategyBuilderConfig) -> StrategyBuilderSolution:
    return StrategyBuilderSolution(
        plan=candidate.plan,
        base_result=candidate.base_result,
        stress_result=candidate.stress_result,
        metrics=copy.deepcopy(candidate.metrics),
        target_satisfaction=copy.deepcopy(candidate.target_satisfaction),
        provenance={
            "official_inputs": "CASE_INPUT",
            "plan_decisions": "TEAM_DECISION",
            "search_targets": "OPERATOR_PREFERENCE",
            "simulation_outputs": "DIGITAL_TWIN_RESULT",
            "objective": config.objective,
            "global_optimum_claimed": False,
        },
        search_depth=candidate.depth,
        mutation_history=candidate.history,
    )


def build_strategies(
    *,
    base_scenario: Scenario,
    stress_scenario: Scenario,
    case_data: CaseData,
    assumptions: ModelAssumptions,
    config: StrategyBuilderConfig | None = None,
) -> StrategyBuilderResult:
    """Run deterministic bounded construction and beam search on official inputs."""
    config = config or StrategyBuilderConfig()
    if case_data.research_source_ids or case_data.research_years:
        raise ValueError(
            "Competition Strategy Builder accepts only CASE_INPUT sources and the official horizon"
        )
    if base_scenario.scenario_id != "BASE":
        raise ValueError("Strategy Builder requires the official BASE scenario")
    if stress_scenario.scenario_id != "MANDATORY_STRESS":
        raise ValueError(
            "Strategy Builder requires the official MANDATORY_STRESS scenario"
        )

    rng = random.Random(config.seed)
    cache: dict[str, _Candidate] = {}
    seen: set[str] = set()
    all_candidates: list[_Candidate] = []
    duplicate_count = 0
    structural_rejections = 0
    cache_hits = 0
    generated_count = 0
    dominance_pruned = 0
    budget_exhausted = False

    def evaluate(
        raw_input: dict[str, Any],
        depth: int,
        history: tuple[str, ...],
    ) -> _Candidate | None:
        nonlocal duplicate_count, structural_rejections, cache_hits
        nonlocal generated_count, budget_exhausted
        generated_count += 1
        raw = copy.deepcopy(raw_input)
        canonical = _canonical_decisions(raw)
        if canonical in seen:
            duplicate_count += 1
            if canonical in cache:
                cache_hits += 1
            return None
        seen.add(canonical)
        if not _cheap_prevalidate(raw, case_data):
            structural_rejections += 1
            return None
        if len(cache) >= config.max_candidates:
            budget_exhausted = True
            return None
        raw["plan_id"] = _plan_id(canonical, config.seed)
        try:
            plan = PlanLoader.from_dict(raw, case_data, assumptions)
        except (KeyError, TypeError, ValueError, PlanValidationError):
            structural_rejections += 1
            return None
        base_result = simulate(plan, base_scenario, case_data, assumptions)
        stress_result = simulate(plan, stress_scenario, case_data, assumptions)
        metrics = _metrics(plan, base_result, stress_result, case_data)
        candidate = _Candidate(
            canonical_key=canonical,
            plan=plan,
            base_result=base_result,
            stress_result=stress_result,
            metrics=metrics,
            target_satisfaction=_target_satisfaction(metrics, config),
            depth=depth,
            history=history,
        )
        cache[canonical] = candidate
        all_candidates.append(candidate)
        return candidate

    seed_candidates: list[_Candidate] = []
    for raw in constructive_seeds(
        case_data, assumptions, base_scenario, stress_scenario
    ):
        candidate = evaluate(raw, 0, ())
        if candidate is not None:
            seed_candidates.append(candidate)
        if budget_exhausted:
            break
    seed_candidates.sort(key=lambda item: _rank(item, config.objective))
    beam = seed_candidates[: config.beam_width]

    completed_iterations = 0
    for iteration in range(1, config.max_iterations + 1):
        if budget_exhausted or not beam:
            break
        targeted: list[tuple[dict[str, Any], int, tuple[str, ...]]] = []
        exploratory: list[tuple[dict[str, Any], int, tuple[str, ...]]] = []
        for parent in beam:
            for raw, description in _target_repair_mutations(
                parent,
                config,
                base_scenario,
                stress_scenario,
                case_data,
                assumptions,
            ):
                targeted.append(
                    (raw, parent.depth + 1, (*parent.history, description))
                )
            for raw, description in _mutations(
                parent,
                config,
                base_scenario,
                stress_scenario,
                case_data,
                assumptions,
            ):
                exploratory.append(
                    (raw, parent.depth + 1, (*parent.history, description))
                )
        targeted.sort(
            key=lambda item: (item[2][-1], _canonical_decisions(item[0]))
        )
        exploratory.sort(
            key=lambda item: (item[2][-1], _canonical_decisions(item[0]))
        )
        rng.shuffle(exploratory)
        generated = [*targeted, *exploratory]
        evaluated_this_round: list[_Candidate] = []
        remaining_iterations = config.max_iterations - iteration + 1
        remaining_budget = config.max_candidates - len(cache)
        round_budget = max(1, remaining_budget // remaining_iterations)
        cache_size_before_round = len(cache)
        for raw, depth, history in generated:
            candidate = evaluate(raw, depth, history)
            if candidate is not None:
                evaluated_this_round.append(candidate)
            if budget_exhausted:
                break
            if len(cache) - cache_size_before_round >= round_budget:
                break
        pool = sorted(
            {item.canonical_key: item for item in [*beam, *evaluated_this_round]}.values(),
            key=lambda item: _rank(item, config.objective),
        )
        pool, pruned = _dominance_prune(pool)
        dominance_pruned += pruned
        pool.sort(key=lambda item: _rank(item, config.objective))
        beam = pool[: config.beam_width]
        completed_iterations = iteration

    eligible = [
        candidate
        for candidate in all_candidates
        if candidate.base_result.summary["valid"]
        and candidate.target_satisfaction["all_satisfied"]
    ]
    eligible.sort(key=lambda item: _solution_rank(item, config.objective))
    selected: list[_Candidate] = []
    for candidate in eligible:
        if _is_diverse(candidate, selected, config.diversity_threshold):
            selected.append(candidate)
        if len(selected) >= config.max_results:
            break

    if selected:
        status = "success"
        failure_reason = ""
    elif not any(item.base_result.summary["valid"] for item in all_candidates):
        status = "no_base_feasible_plan_found"
        failure_reason = (
            "No BASE-valid strategy was found in the explored bounded search space. "
            "This is not a proof of global infeasibility."
        )
    elif budget_exhausted:
        status = "search_budget_exhausted"
        failure_reason = (
            "The candidate budget was exhausted before a target-satisfying strategy "
            "was found; global infeasibility is not claimed."
        )
    else:
        status = "no_target_satisfying_plan_found"
        failure_reason = (
            "BASE-valid strategies were found, but none met every operator target "
            "inside the explored bounded search space."
        )

    return StrategyBuilderResult(
        status=status,
        config=config.to_dict(),
        evaluated_candidate_count=len(cache),
        iterations=completed_iterations,
        solutions=[_solution(item, config) for item in selected],
        search_metadata={
            "algorithm": "DETERMINISTIC_BOUNDED_BEAM_SEARCH",
            "constructive_seed_count": len(seed_candidates),
            "generated_candidate_count": generated_count,
            "duplicate_decision_sets_pruned": duplicate_count,
            "simulation_cache_entries": len(cache),
            "simulation_cache_hits": cache_hits,
            "structural_rejections": structural_rejections,
            "dominance_pruned": dominance_pruned,
            "beam_width": config.beam_width,
            "candidate_budget": config.max_candidates,
            "budget_exhausted": budget_exhausted,
            "global_optimum_claimed": False,
        },
        failure_reason=failure_reason,
    )
