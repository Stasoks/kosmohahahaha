from __future__ import annotations

from collections.abc import Iterable

from kosmohak.domain.assumptions import ModelAssumptions
from kosmohak.domain.case import CaseData
from kosmohak.domain.plan import OperatorPlan
from kosmohak.domain.scenario import Scenario
from kosmohak.domain.risk import RiskDefinition
from kosmohak.reporting.export import build_comparison
from kosmohak.risk.engine import evaluate_risk_set
from kosmohak.simulation.engine import simulate


def evaluate_plan(
    plan: OperatorPlan,
    environment: Scenario,
    case_data: CaseData,
    assumptions: ModelAssumptions,
):
    return simulate(plan, environment, case_data, assumptions)


def evaluate_both_scenarios(
    plan: OperatorPlan,
    base_scenario: Scenario,
    stress_scenario: Scenario,
    case_data: CaseData,
    assumptions: ModelAssumptions,
) -> dict:
    base = simulate(plan, base_scenario, case_data, assumptions)
    stress = simulate(plan, stress_scenario, case_data, assumptions)
    return {
        "BASE": base,
        "MANDATORY_STRESS": stress,
        "comparison": build_comparison(base, stress),
    }


def compare_plans(
    plans: Iterable[OperatorPlan],
    base_scenario: Scenario,
    stress_scenario: Scenario,
    case_data: CaseData,
    assumptions: ModelAssumptions,
    risks: Iterable[RiskDefinition] | None = None,
) -> dict:
    rows = []
    results = {}
    for plan in plans:
        pair = evaluate_both_scenarios(
            plan, base_scenario, stress_scenario, case_data, assumptions
        )
        results[plan.plan_id] = pair
        base, stress = pair["BASE"], pair["MANDATORY_STRESS"]
        source_mix = {
            source_id: sum(
                row["gross_delivery_t"]
                for row in base.sources
                if row["source_id"] == source_id
            )
            for source_id in case_data.sources
        }
        risk_consequences = []
        if risks:
            portfolio = evaluate_risk_set(
                plan, base_scenario, risks, case_data, assumptions
            )
            risk_consequences = [
                {
                    "risk_id": item.risk.risk_id,
                    "impact_score": item.impact["impact_score"],
                    "likelihood_score": item.likelihood_score,
                    "cost_delta_mln": item.consequence["delta"]["costs"]["total_cost_mln"],
                    "shortage_delta_t": item.consequence["delta"]["total_shortage_t"],
                    "critical_shortage_delta_t": item.consequence["delta"]["critical_shortage_t"],
                }
                for item in portfolio.evaluations
            ]
        rows.append(
            {
                "plan_id": plan.plan_id,
                "base_valid": base.summary["valid"],
                "base_cost_mln": base.summary["undiscounted_cost_mln"],
                "base_cost_per_served_ton_mln": base.summary[
                    "cost_per_served_ton_mln"
                ],
                "base_service": base.summary["total_service_level"],
                "base_shortage_t": base.summary["total_shortage_t"],
                "base_minimum_inventory_t": base.summary["minimum_inventory_t"],
                "base_capex_mln": sum(row["capex_mln"] for row in base.annual),
                "stress_service": stress.summary["total_service_level"],
                "stress_shortage_t": stress.summary["total_shortage_t"],
                "stress_critical_shortage_t": stress.summary["critical_shortage_t"],
                "stress_minimum_inventory_t": stress.summary["minimum_inventory_t"],
                "source_mix_t": source_mix,
                "risk_consequences": risk_consequences,
            }
        )
    return {
        "status": "DIGITAL_TWIN_RESULT",
        "winner_selected": False,
        "plans": rows,
        "results": results,
    }
