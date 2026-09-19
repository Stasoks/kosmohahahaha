from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from kosmohak.loading import PlanLoader, RiskLoader
from kosmohak.risk import evaluate_risk


ROOT = Path(__file__).resolve().parents[2]


def _plan(tmp_path, case_data, assumptions, mutate):
    raw = json.loads((ROOT / "configs/operator_plan_example.json").read_text(encoding="utf-8"))
    mutate(raw)
    path = tmp_path / "acceptance-plan.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return PlanLoader.load(path, case_data, assumptions)


def _risk(risk_id, factor, value, start, end, source_id):
    return RiskLoader.from_dict(
        {
            "risk_id": risk_id,
            "name": risk_id,
            "event": factor,
            "cause": "independent acceptance fixture",
            "period_start": start,
            "period_end": end,
            "factor_changes": [
                {
                    "factor": factor,
                    "source_id": source_id,
                    "value": value,
                    "status": "TEAM_ASSUMPTION",
                }
            ],
            "owner": "test",
            "likelihood": {"likelihood_type": "unknown"},
            "likelihood_status": "UNKNOWN",
            "metadata": {"status": "TEAM_ASSUMPTION"},
        }
    )


def _physical_projection(result):
    ignored = {"holding_cost_mln", "fixed_opex_mln", "violations"}
    return [
        {key: copy.deepcopy(value) for key, value in row.items() if key not in ignored}
        for row in result.monthly
    ]


def test_nonuniform_monthly_orders_use_order_volume_weighted_prices(
    tmp_path, case_data, assumptions, base_scenario
):
    def mutate(raw):
        schedule = next(
            item for item in raw["decisions"]["supply_orders"] if item["source_id"] == "B"
        )
        schedule["mode"] = "monthly"
        schedule["values"] = {"2038-01": 10, "2038-06": 30}
        raw["decisions"]["capacity_reservations"].append(
            {"source_id": "B", "year": 2038, "reserved_capacity_t": 40}
        )

    plan = _plan(tmp_path, case_data, assumptions, mutate)
    risk = _risk(
        "PRICE-B-APR-SEP",
        "variable_price_multiplier",
        2,
        "2038-04",
        "2038-09",
        "B",
    )
    evaluation = evaluate_risk(plan, base_scenario, risk, case_data, assumptions)
    baseline = next(
        row for row in evaluation.baseline_result.sources
        if row["source_id"] == "B" and row["year"] == 2038
    )
    shocked = next(
        row for row in evaluation.risk_result.sources
        if row["source_id"] == "B" and row["year"] == 2038
    )
    assert baseline["procurement_cost_mln"] == pytest.approx(40 * 8.9)
    assert shocked["procurement_cost_mln"] == pytest.approx(10 * 8.9 + 30 * 17.8)
    assert evaluation.baseline_result.violations == evaluation.risk_result.violations
    assert _physical_projection(evaluation.baseline_result) == _physical_projection(
        evaluation.risk_result
    )


def test_outage_applies_only_to_actual_delivery_months(
    plan, case_data, assumptions, base_scenario
):
    risk = _risk(
        "A-OUTAGE-APR-SEP",
        "availability_share",
        0,
        "2038-04",
        "2038-09",
        "A",
    )
    evaluation = evaluate_risk(plan, base_scenario, risk, case_data, assumptions)
    base = {row["month"]: row for row in evaluation.baseline_result.monthly}
    outage = {row["month"]: row for row in evaluation.risk_result.monthly}
    for number in range(1, 13):
        month = f"2038-{number:02d}"
        actual = outage[month]["gross_delivery_by_source"].get("A", 0)
        expected = base[month]["gross_delivery_by_source"].get("A", 0)
        if 4 <= number <= 9:
            assert actual == 0
        else:
            assert actual == pytest.approx(expected)
    assert outage["2038-10"]["opening_inventory_t"] <= base["2038-10"]["opening_inventory_t"]


def test_cost_per_served_ton_is_exported_in_summary(base_result):
    served = sum(row["served_total_t"] for row in base_result.annual)
    assert base_result.summary["cost_per_served_ton_mln"] == pytest.approx(
        base_result.summary["undiscounted_cost_mln"] / served
    )
    assert base_result.summary["discounted_cost_per_served_ton_mln"] == pytest.approx(
        base_result.summary["discounted_cost_mln"] / served
    )
