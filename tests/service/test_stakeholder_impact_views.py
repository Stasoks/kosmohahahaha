from __future__ import annotations

from app.view_models import (
    annual_stress_impact_rows,
    risk_stakeholder_impact_rows,
    stakeholder_detail_rows,
)


def _result(*, year: int, demand: float, critical_demand: float, shortage: float, critical_shortage: float, cost: float) -> dict:
    served = demand - shortage
    critical_served = critical_demand - critical_shortage
    return {
        "summary": {
            "valid": shortage == 0,
            "total_shortage_t": shortage,
            "critical_shortage_t": critical_shortage,
            "undiscounted_cost_mln": cost,
            "discounted_cost_mln": cost,
            "cost_per_served_ton_mln": cost / served if served else 0.0,
            "minimum_inventory_t": 10.0,
            "hard_violation_count": 0,
            "scenario_id": "TEST",
        },
        "annual": [
            {
                "year": year,
                "demand_total_t": demand,
                "demand_critical_t": critical_demand,
                "served_total_t": served,
                "served_critical_t": critical_served,
                "total_service_level": served / demand,
                "critical_service_level": critical_served / critical_demand,
                "shortage_t": shortage,
                "critical_shortage_t": critical_shortage,
                "reserve_actual_days": 45.0,
                "capex_mln": 100.0,
                "total_cost_mln": cost,
            }
        ],
        "sources": [],
    }


def _stakeholders() -> dict:
    return {
        "participants": [
            {
                "stakeholder_id": "operator",
                "name": "Operator",
                "interests": ["service"],
                "kpis": ["total_service_level"],
                "obligations": ["respect constraints"],
                "cost_bearer": ["procurement"],
                "risk_bearer": ["service shortage"],
                "relevant_risks": ["R-TEST"],
            },
            {
                "stakeholder_id": "commercial_consumers",
                "name": "Commercial",
                "interests": ["fuel"],
                "kpis": ["total_shortage_t"],
                "obligations": [],
                "cost_bearer": [],
                "risk_bearer": ["noncritical curtailment"],
                "relevant_risks": ["R-TEST"],
            },
        ]
    }


def test_annual_stress_impact_separates_commercial_and_critical_shortage():
    payload = {
        "A": _result(
            year=2038,
            demand=250,
            critical_demand=170,
            shortage=0,
            critical_shortage=0,
            cost=1000,
        ),
        "B": _result(
            year=2038,
            demand=287.5,
            critical_demand=195.5,
            shortage=41.25,
            critical_shortage=6.75,
            cost=1270,
        ),
        "C": _result(
            year=2038,
            demand=287.5,
            critical_demand=195.5,
            shortage=10,
            critical_shortage=0,
            cost=1400,
        ),
    }

    row = annual_stress_impact_rows(payload)[0]
    assert row["stress_commercial_shortage_t"] == 34.5
    assert row["stress_critical_shortage_t"] == 6.75
    assert row["stress_cost_delta_mln"] == 270
    assert row["adapted_commercial_shortage_t"] == 10
    assert row["adapted_critical_shortage_t"] == 0


def test_stakeholder_detail_exposes_cost_risk_and_obligations():
    result = _result(
        year=2038,
        demand=250,
        critical_demand=170,
        shortage=0,
        critical_shortage=0,
        cost=1000,
    )
    rows = stakeholder_detail_rows(
        _stakeholders(),
        {"A": result, "B": result, "C": result},
    )

    operator = rows[0]
    assert operator["Кто несёт затраты"] == "procurement"
    assert operator["Какой риск несёт"] == "service shortage"
    assert operator["Обязательства"] == "respect constraints"
    assert "KPI: total_service_level" in operator["Интересы / KPI"]


def test_risk_stakeholder_impact_uses_noncritical_shortage_not_total_shortage():
    baseline = _result(
        year=2038,
        demand=250,
        critical_demand=170,
        shortage=0,
        critical_shortage=0,
        cost=1000,
    )
    stressed = _result(
        year=2038,
        demand=250,
        critical_demand=170,
        shortage=12,
        critical_shortage=2,
        cost=1100,
    )
    rows = risk_stakeholder_impact_rows(
        _stakeholders(),
        "R-TEST",
        baseline,
        stressed,
    )
    commercial = next(row for row in rows if row["Сторона"] == "Commercial")
    assert "0.0 → 10.0 т" in commercial["До риска → в риске"]
