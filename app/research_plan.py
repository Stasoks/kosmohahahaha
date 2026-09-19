from __future__ import annotations

import copy
from typing import Any, Iterable


_EPS = 1e-9


def annual_order_total(schedule: dict[str, Any], year: int) -> float:
    """Return a schedule's total ordered volume for one calendar year."""

    return sum(
        float(value)
        for period, value in schedule.get("values", {}).items()
        if int(str(period)[:4]) == int(year)
    )


def set_annual_total_preserving_schedule(
    schedule: dict[str, Any],
    year: int,
    target_t: float,
) -> bool:
    """Set one annual total without silently changing the schedule's time semantics.

    Existing monthly schedules keep their month pattern. If the year has no monthly
    entries yet, a new annual total is spread evenly over the twelve months. Existing
    annual_even schedules remain annual_even.
    """

    target = float(target_t)
    values = schedule.setdefault("values", {})
    mode = str(schedule.get("mode", "annual_even"))

    if mode == "annual_even":
        key = str(int(year))
        current = float(values.get(key, 0.0))
        if abs(current - target) <= _EPS:
            return False
        if abs(target) <= _EPS:
            values.pop(key, None)
        else:
            values[key] = target
        return True

    if mode != "monthly":
        raise ValueError(f"Unsupported supply-order mode: {mode}")

    prefix = f"{int(year):04d}-"
    months = sorted(key for key in values if str(key).startswith(prefix))
    current = sum(float(values[key]) for key in months)

    if abs(current - target) <= _EPS:
        return False

    if abs(target) <= _EPS:
        for month in months:
            values[month] = 0.0
        return True

    if current > _EPS:
        factor = target / current
        for month in months:
            values[month] = float(values[month]) * factor
        return True

    monthly = target / 12.0
    for month_number in range(1, 13):
        values[f"{int(year):04d}-{month_number:02d}"] = monthly
    return True


def _set_reservation(
    reservations: list[dict[str, Any]],
    source_id: str,
    year: int,
    target_t: float,
) -> None:
    target = float(target_t)
    index = next(
        (
            idx
            for idx, item in enumerate(reservations)
            if str(item.get("source_id")) == source_id
            and int(item.get("year")) == int(year)
        ),
        None,
    )

    if abs(target) <= _EPS:
        if index is not None:
            reservations.pop(index)
        return

    if index is None:
        reservations.append(
            {
                "source_id": source_id,
                "year": int(year),
                "reserved_capacity_t": target,
            }
        )
        return

    reservations[index]["reserved_capacity_t"] = target


def apply_research_decisions(
    raw: dict[str, Any],
    order_rows: Iterable[dict[str, Any]],
    reserve_rows: Iterable[dict[str, Any]],
    years: Iterable[int],
) -> dict[str, Any]:
    """Patch the research plan while preserving unchanged monthly decisions."""

    updated = copy.deepcopy(raw)
    decisions = updated.setdefault("decisions", {})
    schedules = {
        str(item["source_id"]): item
        for item in decisions.setdefault("supply_orders", [])
    }
    reservations = decisions.setdefault("capacity_reservations", [])

    order_rows = list(order_rows)
    reserve_by_source = {
        str(row["Источник"]): row
        for row in reserve_rows
    }
    years = [int(year) for year in years]

    for row in order_rows:
        source_id = str(row["Источник"])
        active = bool(row.get("Использовать", True))
        schedule = schedules.get(source_id)
        if schedule is None:
            schedule = {
                "source_id": source_id,
                "mode": "annual_even",
                "values": {},
            }
            decisions["supply_orders"].append(schedule)
            schedules[source_id] = schedule

        reserve_row = reserve_by_source.get(source_id, {})
        for year in years:
            target_order = float(row.get(str(year), 0.0)) if active else 0.0
            set_annual_total_preserving_schedule(schedule, year, target_order)

            target_reservation = (
                float(reserve_row.get(str(year), 0.0))
                if active
                else 0.0
            )
            _set_reservation(
                reservations,
                source_id,
                year,
                target_reservation,
            )

    return updated
