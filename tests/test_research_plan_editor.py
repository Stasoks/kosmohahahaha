from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from app.research_plan import annual_order_total, apply_research_decisions


ROOT = Path(__file__).resolve().parents[1]


def _base_plan() -> dict:
    return {
        "decisions": {
            "supply_orders": [
                {
                    "source_id": "B",
                    "mode": "monthly",
                    "values": {
                        "2040-06": 10.0,
                        "2040-07": 20.0,
                        "2040-08": 30.0,
                    },
                }
            ],
            "capacity_reservations": [
                {
                    "source_id": "B",
                    "year": 2040,
                    "reserved_capacity_t": 60.0,
                }
            ],
        }
    }


def test_research_apply_without_changes_preserves_monthly_schedule() -> None:
    raw = _base_plan()
    before = copy.deepcopy(raw["decisions"]["supply_orders"])

    updated = apply_research_decisions(
        raw,
        [
            {
                "Использовать": True,
                "Источник": "B",
                "2040": 60.0,
                "2041": 0.0,
            }
        ],
        [
            {
                "Источник": "B",
                "2040": 60.0,
                "2041": 0.0,
            }
        ],
        [2040, 2041],
    )

    assert updated["decisions"]["supply_orders"] == before


def test_research_apply_scales_existing_monthly_profile() -> None:
    raw = _base_plan()

    updated = apply_research_decisions(
        raw,
        [
            {
                "Использовать": True,
                "Источник": "B",
                "2040": 120.0,
            }
        ],
        [{"Источник": "B", "2040": 60.0}],
        [2040],
    )

    values = updated["decisions"]["supply_orders"][0]["values"]
    assert values["2040-06"] == pytest.approx(20.0)
    assert values["2040-07"] == pytest.approx(40.0)
    assert values["2040-08"] == pytest.approx(60.0)


def test_research_apply_new_year_keeps_monthly_mode_and_spreads_new_total() -> None:
    raw = _base_plan()

    updated = apply_research_decisions(
        raw,
        [
            {
                "Использовать": True,
                "Источник": "B",
                "2040": 60.0,
                "2041": 120.0,
            }
        ],
        [
            {
                "Источник": "B",
                "2040": 60.0,
                "2041": 0.0,
            }
        ],
        [2040, 2041],
    )

    schedule = updated["decisions"]["supply_orders"][0]
    assert schedule["mode"] == "monthly"
    assert sum(
        value
        for period, value in schedule["values"].items()
        if period.startswith("2041-")
    ) == pytest.approx(120.0)
    assert schedule["values"]["2040-06"] == pytest.approx(10.0)


def test_research_apply_updates_reservations_without_rebuilding_unrelated_rows() -> None:
    raw = _base_plan()
    raw["decisions"]["capacity_reservations"].append(
        {"source_id": "A", "year": 2040, "reserved_capacity_t": 50.0}
    )

    updated = apply_research_decisions(
        raw,
        [{"Использовать": True, "Источник": "B", "2040": 60.0}],
        [{"Источник": "B", "2040": 75.0}],
        [2040],
    )

    reservations = {
        (item["source_id"], item["year"]): item["reserved_capacity_t"]
        for item in updated["decisions"]["capacity_reservations"]
    }
    assert reservations[("B", 2040)] == pytest.approx(75.0)
    assert reservations[("A", 2040)] == pytest.approx(50.0)

def test_final_base_extension_with_zero_2041_keeps_official_schedule_exact() -> None:
    raw = json.loads((ROOT / "plans" / "final_base.json").read_text(encoding="utf-8"))
    schedules = raw["decisions"]["supply_orders"]
    before = copy.deepcopy(schedules)
    reservations = raw["decisions"]["capacity_reservations"]

    order_rows = []
    reserve_rows = []
    for schedule in schedules:
        source_id = str(schedule["source_id"])
        order_rows.append(
            {
                "Использовать": True,
                "Источник": source_id,
                **{
                    str(year): annual_order_total(schedule, year)
                    for year in range(2035, 2041)
                },
                "2041": 0.0,
            }
        )
        reserve_rows.append(
            {
                "Источник": source_id,
                **{
                    str(year): next(
                        (
                            float(item["reserved_capacity_t"])
                            for item in reservations
                            if str(item["source_id"]) == source_id
                            and int(item["year"]) == year
                        ),
                        0.0,
                    )
                    for year in range(2035, 2041)
                },
                "2041": 0.0,
            }
        )

    updated = apply_research_decisions(
        raw,
        order_rows,
        reserve_rows,
        range(2035, 2042),
    )

    assert updated["decisions"]["supply_orders"] == before
