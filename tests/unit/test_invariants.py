"""Cross-cutting identities that must hold for every simulation result.

They complement the balance test in ``test_material_and_pipeline`` by checking
the arithmetic links *between* monthly rows, annual rows and the summary.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.kernel

MONTHLY_NON_NEGATIVE = (
    "opening_inventory_t",
    "gross_delivery_t",
    "losses_t",
    "net_delivery_t",
    "accepted_delivery_t",
    "overflow_t",
    "available_inventory_t",
    "served_critical_t",
    "served_noncritical_t",
    "shortage_critical_t",
    "shortage_noncritical_t",
    "closing_inventory_t",
)


def test_inventory_conservation_each_month(base_result):
    for row in base_result.monthly:
        available = row["opening_inventory_t"] + row["accepted_delivery_t"]
        assert row["available_inventory_t"] == pytest.approx(available, abs=1e-6)
        served = row["served_critical_t"] + row["served_noncritical_t"]
        assert row["closing_inventory_t"] == pytest.approx(max(0.0, available - served), abs=1e-6)


def test_throughput_splits_gross_into_net_and_overflow(base_result):
    for row in base_result.monthly:
        assert row["net_delivery_t"] == pytest.approx(row["gross_delivery_t"] - row["losses_t"], abs=1e-6)
        assert row["accepted_delivery_t"] + row["overflow_t"] == pytest.approx(row["net_delivery_t"], abs=1e-6)


def test_demand_is_served_within_bounds(base_result):
    for row in base_result.monthly:
        noncritical = row["demand_total_t"] - row["demand_critical_t"]
        assert row["served_critical_t"] <= row["demand_critical_t"] + 1e-6
        assert row["served_noncritical_t"] <= noncritical + 1e-6
        assert row["shortage_critical_t"] == pytest.approx(row["demand_critical_t"] - row["served_critical_t"], abs=1e-6)
        assert row["shortage_noncritical_t"] == pytest.approx(noncritical - row["served_noncritical_t"], abs=1e-6)


def test_all_monthly_flows_are_non_negative(base_result):
    for row in base_result.monthly:
        for key in MONTHLY_NON_NEGATIVE:
            assert row[key] >= -1e-6, (row["month"], key, row[key])


def test_pipeline_request_split_is_exact(base_result):
    for row in base_result.monthly:
        for shipment in row["pipeline"]:
            assert shipment["requested_t"] == pytest.approx(
                shipment["feasible_t"] + shipment["unfulfilled_request_t"], abs=1e-6
            )


def test_source_orders_split_is_exact(base_result):
    for row in base_result.sources:
        assert row["requested_order_t"] == pytest.approx(
            row["feasible_order_t"] + row["unfulfilled_request_t"], abs=1e-6
        )


def test_timeline_is_contiguous_and_ordered(base_result):
    months = [row["month"] for row in base_result.monthly]
    assert months == sorted(months)
    assert len(months) == len(set(months))
    assert len(months) % 12 == 0
    years = sorted({int(month[:4]) for month in months})
    assert years == list(range(years[0], years[0] + len(years)))


def test_summary_reconciles_with_annual_and_monthly(base_result):
    summary = base_result.summary
    annual = base_result.annual
    monthly = base_result.monthly

    assert summary["undiscounted_cost_mln"] == pytest.approx(sum(r["total_cost_mln"] for r in annual), abs=1e-6)
    assert summary["discounted_cost_mln"] == pytest.approx(sum(r["discounted_cost_mln"] for r in annual), abs=1e-6)
    assert summary["total_shortage_t"] == pytest.approx(sum(r["shortage_t"] for r in annual), abs=1e-6)
    assert summary["critical_shortage_t"] == pytest.approx(sum(r["critical_shortage_t"] for r in annual), abs=1e-6)
    assert summary["total_losses_t"] == pytest.approx(sum(r["losses_t"] for r in annual), abs=1e-6)
    assert summary["total_overflow_t"] == pytest.approx(sum(r["overflow_t"] for r in annual), abs=1e-6)
    assert summary["opening_inventory_t"] == pytest.approx(monthly[0]["opening_inventory_t"], abs=1e-6)
    assert summary["final_inventory_t"] == pytest.approx(monthly[-1]["closing_inventory_t"], abs=1e-6)
    assert summary["minimum_inventory_t"] == pytest.approx(
        min(r["closing_inventory_t"] for r in monthly), abs=1e-6
    )


def test_service_levels_match_annual_totals(base_result):
    summary = base_result.summary
    annual = base_result.annual

    served = sum(r["served_total_t"] for r in annual)
    demand = sum(r["demand_total_t"] for r in annual)
    assert summary["total_service_level"] == pytest.approx(served / demand, abs=1e-9)

    served_critical = sum(r["served_critical_t"] for r in annual)
    demand_critical = sum(r["demand_critical_t"] for r in annual)
    assert summary["critical_service_level"] == pytest.approx(served_critical / demand_critical, abs=1e-9)


def test_invariants_hold_under_mandatory_stress(stress_result):
    assert stress_result.summary["scenario_id"] == "MANDATORY_STRESS"
    for row in stress_result.monthly:
        available = row["opening_inventory_t"] + row["accepted_delivery_t"]
        served = row["served_critical_t"] + row["served_noncritical_t"]
        assert row["closing_inventory_t"] == pytest.approx(max(0.0, available - served), abs=1e-6)
        assert row["net_delivery_t"] == pytest.approx(row["gross_delivery_t"] - row["losses_t"], abs=1e-6)
