from __future__ import annotations

import json
from pathlib import Path

import pytest

from kosmohak.loading import RiskLoader
from kosmohak.risk import evaluate_risk, evaluate_risk_set
from kosmohak.reporting import export_risk_portfolio
from kosmohak.simulation import simulate
from kosmohak.simulation.environment import SimulationEnvironment


ROOT = Path(__file__).resolve().parents[2]


def _risk(
    risk_id,
    factor,
    value,
    *,
    period_start="2038-01",
    period_end="2038-12",
    likelihood=None,
    **target,
):
    raw = {
        "risk_id": risk_id,
        "name": risk_id,
        "description": "integration test",
        "event": factor,
        "cause": "test",
        "period_start": period_start,
        "period_end": period_end,
        "affected_parameters": [factor],
        "factor_changes": [
            {"factor": factor, "value": value, "status": "TEAM_ASSUMPTION", **target}
        ],
        "dependencies": [],
        "owner": "test",
        "likelihood": likelihood or {"likelihood_type": "unknown"},
        "likelihood_status": "UNKNOWN" if likelihood is None else "TEAM_ASSUMPTION",
        "source_references": [],
        "combination_policy": "apply_after_base",
        "metadata": {"status": "TEAM_ASSUMPTION"},
    }
    return RiskLoader.from_dict(raw)


def test_team_risk_is_isolated_from_official_scenario(
    plan, case_data, assumptions, base_scenario, stress_scenario
):
    risk = _risk("R-DEMAND", "total_demand_multiplier", 1.1)
    base_eval = evaluate_risk(plan, base_scenario, risk, case_data, assumptions)
    stress_eval = evaluate_risk(plan, stress_scenario, risk, case_data, assumptions)
    assert base_eval.base_scenario_id == "BASE"
    assert stress_eval.base_scenario_id == "MANDATORY_STRESS"
    assert base_eval.environment_id == "BASE+R-DEMAND"
    assert stress_eval.environment_id == "MANDATORY_STRESS+R-DEMAND"
    assert base_eval.baseline_result.summary["scenario_id"] == "BASE"


def test_price_only_risk_changes_cost_not_physical_flow(
    plan, case_data, assumptions, base_scenario
):
    risk = _risk(
        "R-PRICE",
        "variable_price_multiplier",
        1.5,
        source_id="A",
    )
    evaluation = evaluate_risk(plan, base_scenario, risk, case_data, assumptions)
    assert evaluation.consequence["delta"]["costs"]["procurement_mln"] > 0
    assert evaluation.consequence["delta"]["total_shortage_t"] == pytest.approx(0)
    assert [row["closing_inventory_t"] for row in evaluation.baseline_result.monthly] == pytest.approx(
        [row["closing_inventory_t"] for row in evaluation.risk_result.monthly]
    )


def test_delivery_share_and_availability_reduce_physical_delivery(
    plan, case_data, assumptions, base_scenario
):
    share = _risk(
        "R-SHARE",
        "actual_delivery_share",
        0.25,
        source_id="D",
    )
    outage = _risk(
        "R-OUT",
        "availability_share",
        0.0,
        source_id="A",
    )
    share_result = simulate(
        plan,
        SimulationEnvironment.with_risks(base_scenario, [share]),
        case_data,
        assumptions,
    )
    outage_result = simulate(
        plan,
        SimulationEnvironment.with_risks(base_scenario, [outage]),
        case_data,
        assumptions,
    )
    base_d = next(row for row in simulate(plan, base_scenario, case_data, assumptions).sources if row["source_id"] == "D" and row["year"] == 2038)
    risk_d = next(row for row in share_result.sources if row["source_id"] == "D" and row["year"] == 2038)
    assert risk_d["gross_delivery_t"] < base_d["gross_delivery_t"]
    assert outage_result.summary["unavailable_requested_supply_t"] > 0


def test_lead_time_risk_delays_deliveries(plan, case_data, assumptions, base_scenario):
    risk = _risk(
        "R-LEAD",
        "additional_lead_time_months",
        3,
        source_id="A",
    )
    result = simulate(
        plan,
        SimulationEnvironment.with_risks(base_scenario, [risk]),
        case_data,
        assumptions,
    )
    assert result.summary["delayed_delivery_count"] > 0
    assert result.summary["delayed_delivery_t"] > 0


def test_capacity_degradation_preserves_request_and_reduces_feasible(
    plan, case_data, assumptions, base_scenario
):
    risk = _risk(
        "R-CAPACITY",
        "source_capacity_multiplier",
        0.5,
        source_id="A",
    )
    result = simulate(
        plan,
        SimulationEnvironment.with_risks(base_scenario, [risk]),
        case_data,
        assumptions,
    )
    row = next(item for item in result.sources if item["source_id"] == "A" and item["year"] == 2038)
    assert row["requested_order_t"] == 170
    assert row["feasible_order_t"] < row["requested_order_t"]
    assert row["unfulfilled_request_t"] > 0


def test_storage_loss_and_capacity_risks_are_applied(
    plan, case_data, assumptions, base_scenario
):
    loss = _risk(
        "R-LOSS",
        "storage_loss_rate_override",
        0.2,
        storage_id="ZBO",
    )
    capacity = _risk(
        "R-STORAGE-CAP",
        "storage_capacity_multiplier",
        0.2,
        storage_id="ZBO",
    )
    loss_result = simulate(
        plan,
        SimulationEnvironment.with_risks(base_scenario, [loss]),
        case_data,
        assumptions,
    )
    capacity_result = simulate(
        plan,
        SimulationEnvironment.with_risks(base_scenario, [capacity]),
        case_data,
        assumptions,
    )
    month = next(row for row in loss_result.monthly if row["month"] == "2038-03")
    assert month["active_loss_rate"] == pytest.approx(0.2)
    assert capacity_result.summary["total_overflow_t"] > 0


def test_investment_delay_changes_commissioning(plan, case_data, assumptions, base_scenario):
    risk = _risk(
        "R-ZBO-DELAY",
        "investment_commissioning_delay_months",
        6,
        period_start="2036-01",
        period_end="2036-12",
        investment_id="ZBO",
    )
    result = simulate(
        plan,
        SimulationEnvironment.with_risks(base_scenario, [risk]),
        case_data,
        assumptions,
    )
    january = next(row for row in result.monthly if row["month"] == "2036-01")
    july = next(row for row in result.monthly if row["month"] == "2036-07")
    assert january["active_storage_id"] == "BASE"
    assert july["active_storage_id"] == "ZBO"


@pytest.mark.parametrize(
    ("factor", "target", "field"),
    [
        ("reservation_price_multiplier", {"source_id": "A"}, "reservation_mln"),
        ("fixed_opex_multiplier", {"investment_id": "ZBO"}, "fixed_opex_mln"),
        ("capex_multiplier", {"investment_id": "ZBO"}, "capex_mln"),
    ],
)
def test_economic_research_shocks_change_only_declared_component(
    factor, target, field, plan, case_data, assumptions, base_scenario
):
    period = ("2036-01", "2036-12") if factor != "reservation_price_multiplier" else ("2038-01", "2038-12")
    risk = _risk(
        f"R-{factor}",
        factor,
        2.0,
        period_start=period[0],
        period_end=period[1],
        **target,
    )
    evaluation = evaluate_risk(plan, base_scenario, risk, case_data, assumptions)
    assert evaluation.consequence["delta"]["costs"][field] > 0
    assert evaluation.consequence["delta"]["total_shortage_t"] == pytest.approx(0)


def test_risk_consequence_scoring_matrix_and_unknown_likelihood(
    plan, case_data, assumptions, base_scenario
):
    unknown = _risk("R-UNKNOWN", "total_demand_multiplier", 1.2)
    known = _risk(
        "R-KNOWN",
        "variable_price_multiplier",
        1.2,
        source_id="A",
        likelihood={
            "likelihood_type": "qualitative",
            "score": 3,
            "label": "possible",
            "basis": "test basis",
            "source": "TEST:source",
        },
    )
    portfolio = evaluate_risk_set(
        plan,
        base_scenario,
        [unknown, known],
        case_data,
        assumptions,
    )
    assert portfolio.evaluations[0].consequence["risk"]["run_id"]
    assert 1 <= portfolio.evaluations[0].impact["impact_score"] <= 5
    assert "R-UNKNOWN" in portfolio.unknown_likelihood_risks
    assert portfolio.evaluations[0].ordinal_risk_score is None
    assert portfolio.evaluations[1].ordinal_risk_score == 3 * portfolio.evaluations[1].impact["impact_score"]
    assert any(item["risk_id"] == "R-UNKNOWN" for item in portfolio.risk_matrix["unknown_likelihood"])


def test_mitigation_is_rerun_and_has_cost_and_residual_risk(
    plan, case_data, assumptions, base_scenario
):
    risks = RiskLoader.load(ROOT / "configs/risks/team_risks.json")
    risk = next(item for item in risks if item.risk_id == "R-CORE-OUTAGE")
    evaluation = evaluate_risk(plan, base_scenario, risk, case_data, assumptions)
    assert evaluation.mitigation is not None
    assert evaluation.mitigation.mitigation_cost_mln != 0
    assert evaluation.mitigation.risk_result.summary["run_id"] != evaluation.risk_run_id
    assert evaluation.mitigation.residual_impact["impact_score"] >= 1


def test_risk_evaluation_is_reproducible_and_does_not_mutate_plan(
    plan, case_data, assumptions, base_scenario
):
    risk = _risk("R-REPRO", "availability_share", 0.5, source_id="B")
    original = json.dumps(plan.raw, sort_keys=True)
    first = evaluate_risk(plan, base_scenario, risk, case_data, assumptions)
    second = evaluate_risk(plan, base_scenario, risk, case_data, assumptions)
    assert first.risk_result.to_dict() == second.risk_result.to_dict()
    assert json.dumps(plan.raw, sort_keys=True) == original


def test_risk_register_matrix_and_runs_are_exported(
    tmp_path, plan, case_data, assumptions, base_scenario
):
    risks = [
        _risk("R-EXPORT-1", "availability_share", 0.5, source_id="A"),
        _risk(
            "R-EXPORT-2",
            "variable_price_multiplier",
            1.1,
            source_id="B",
            likelihood={
                "likelihood_type": "qualitative",
                "score": 2,
                "label": "unlikely",
                "basis": "test",
                "source": "TEST",
            },
        ),
    ]
    portfolio = evaluate_risk_set(plan, base_scenario, risks, case_data, assumptions)
    directory = export_risk_portfolio(portfolio, tmp_path / "risks", case_data.root)
    assert {
        "risk_register.json",
        "risk_register.csv",
        "risk_matrix.json",
        "risk_matrix.csv",
        "risk_portfolio.json",
        "risk_scoring.json",
    } <= {
        item.name for item in directory.iterdir()
    }
    assert (directory / "runs" / "R-EXPORT-1" / "monthly.csv").is_file()
