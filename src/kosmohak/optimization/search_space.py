from __future__ import annotations

import copy

from kosmohak.domain.case import CaseData
from kosmohak.domain.plan import OperatorPlan
from kosmohak.domain.result import SimulationResult
from kosmohak.optimization.domain import OptimizerConfig


def _reservation(raw: dict, source_id: str, year: int) -> dict | None:
    return next(
        (
            item for item in raw["decisions"]["capacity_reservations"]
            if str(item["source_id"]) == source_id and int(item["year"]) == year
        ),
        None,
    )


def _set_reservation(raw: dict, source_id: str, year: int, value: float) -> None:
    item = _reservation(raw, source_id, year)
    if item is None:
        raw["decisions"]["capacity_reservations"].append(
            {"source_id": source_id, "year": year, "reserved_capacity_t": value}
        )
    else:
        item["reserved_capacity_t"] = value


def _schedule(raw: dict, source_id: str) -> dict | None:
    return next(
        (
            item for item in raw["decisions"]["supply_orders"]
            if str(item["source_id"]) == source_id
        ),
        None,
    )


def _set_annual_total(raw: dict, source_id: str, year: int, target: float) -> None:
    schedule = _schedule(raw, source_id)
    if schedule is None:
        raw["decisions"]["supply_orders"].append(
            {"source_id": source_id, "mode": "annual_even", "values": {str(year): target}}
        )
        return
    values = schedule.setdefault("values", {})
    if schedule["mode"] == "annual_even":
        values[str(year)] = target
        return
    months = sorted(key for key in values if key.startswith(f"{year:04d}-"))
    if not months:
        months = [f"{year:04d}-{number:02d}" for number in range(1, 13)]
    current = sum(float(values.get(month, 0.0)) for month in months)
    if current > 0:
        factor = target / current
        for month in months:
            values[month] = float(values.get(month, 0.0)) * factor
    else:
        for month in months:
            values[month] = target / len(months)


def _annual_total(raw: dict, source_id: str, year: int) -> float:
    schedule = _schedule(raw, source_id)
    if schedule is None:
        return 0.0
    if schedule["mode"] == "annual_even":
        return float(schedule.get("values", {}).get(str(year), 0.0))
    return sum(
        float(value)
        for period, value in schedule.get("values", {}).items()
        if str(period).startswith(f"{year:04d}-")
    )


def repair_candidates(
    plan: OperatorPlan,
    result: SimulationResult,
    case_data: CaseData,
) -> list[dict]:
    raw = copy.deepcopy(plan.raw)
    changed = False
    for violation in result.violations:
        source_id = violation.source_id
        try:
            year = int(str(violation.period)[:4])
        except ValueError:
            year = case_data.years[0]
        if violation.code == "CAPACITY_EXCEEDED" and source_id:
            _set_reservation(raw, source_id, year, float(violation.limit))
            changed = True
        elif violation.code == "ORDER_CAPACITY_EXCEEDED" and source_id:
            limit = max(0.0, float(violation.limit))
            capacity = case_data.source_capacity(source_id, year)
            ordered = _annual_total(raw, source_id, year)
            if ordered <= capacity:
                _set_reservation(raw, source_id, year, ordered)
            else:
                _set_annual_total(raw, source_id, year, limit)
                _set_reservation(raw, source_id, year, min(limit, capacity))
            changed = True
        elif violation.code == "SOURCE_UNAVAILABLE" and source_id:
            _set_annual_total(raw, source_id, year, 0.0)
            _set_reservation(raw, source_id, year, 0.0)
            changed = True
        elif violation.code == "INITIAL_STOCK_RESERVATION_CAPACITY_EXCEEDED":
            acquisition = raw["decisions"].get("initial_stock_acquisition")
            if acquisition and source_id:
                acquisition["reserved_capacity_t_per_year"] = case_data.sources[
                    source_id
                ].capacity_t_per_year
                changed = True
        elif violation.code == "INITIAL_STOCK_CAPACITY_EXCEEDED":
            acquisition = raw["decisions"].get("initial_stock_acquisition")
            if acquisition:
                acquisition["ordered_volume_t"] = float(violation.limit)
                changed = True
    return [raw] if changed else []


def improvement_candidates(
    plan: OperatorPlan,
    config: OptimizerConfig,
) -> list[dict]:
    output: list[dict] = []
    for schedule in plan.raw["decisions"].get("supply_orders", []):
        source_id = str(schedule["source_id"])
        for period, value in sorted(schedule.get("values", {}).items()):
            amount = float(value)
            if amount <= 0:
                continue
            for fraction in config.reduction_fractions:
                raw = copy.deepcopy(plan.raw)
                candidate_schedule = _schedule(raw, source_id)
                assert candidate_schedule is not None
                candidate_schedule["values"][str(period)] = amount * (1.0 - fraction)
                year = int(str(period)[:4])
                ordered = _annual_total(raw, source_id, year)
                reservation = _reservation(raw, source_id, year)
                if reservation and float(reservation["reserved_capacity_t"]) > ordered:
                    reservation["reserved_capacity_t"] = ordered
                output.append(raw)
                if len(output) >= config.max_candidates:
                    return output
    return output


def resilience_candidates(
    plan: OperatorPlan,
    case_data: CaseData,
    config: OptimizerConfig,
) -> list[dict]:
    output: list[dict] = []
    for source_id in sorted(case_data.sources):
        schedule = _schedule(plan.raw, source_id)
        if schedule is None or schedule.get("mode") != "annual_even":
            continue
        for year in case_data.years:
            current_order = _annual_total(plan.raw, source_id, year)
            current_reservation = plan.reservation(source_id, year)
            capacity = case_data.source_capacity(source_id, year)
            room = max(0.0, capacity - max(current_order, current_reservation))
            if room <= 1e-9:
                continue
            for fraction in config.increase_fractions:
                increment = min(room, max(1.0, capacity * fraction))
                raw = copy.deepcopy(plan.raw)
                _set_annual_total(raw, source_id, year, current_order + increment)
                _set_reservation(raw, source_id, year, max(current_reservation, current_order + increment))
                output.append(raw)
                if len(output) >= config.max_candidates:
                    return output
    return output
