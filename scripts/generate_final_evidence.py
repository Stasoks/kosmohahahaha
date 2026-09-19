#!/usr/bin/env python3
from __future__ import annotations

import copy
import csv
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from kosmohak.loading import (
    AssumptionsLoader,
    CaseDataLoader,
    PlanLoader,
    RiskLoader,
    ScenarioLoader,
)
from kosmohak.reporting import export_analysis_result, export_plan_comparison
from kosmohak.service import (
    StrategyBuilderConfig,
    compare_plans,
    evaluate_both_scenarios,
    evaluate_risks,
    export_plan_results,
    export_risk_results,
    export_scenario_comparison,
    run_official_demand_sensitivity,
    run_sensitivity,
    run_reverse_stress,
    save_plan,
    synthesize_strategy,
)


OUTPUT = PROJECT_ROOT / "results" / "final-evidence"
PLAN_DIR = PROJECT_ROOT / "plans"


def _json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _renamed_plan(solution, plan_id: str, case_data, assumptions):
    raw = copy.deepcopy(solution.plan.raw)
    raw["plan_id"] = plan_id
    raw.setdefault("metadata", {})
    raw["metadata"].update(
        {
            "status": "TEAM_DECISION",
            "final_evidence": True,
            "generated_by": "StrategyBuilder",
            "builder_search_depth": solution.search_depth,
            "builder_mutation_history": list(solution.mutation_history),
        }
    )
    return PlanLoader.from_dict(raw, case_data, assumptions)


def _min_annual(result, field: str) -> float:
    return min(float(row[field]) for row in result.annual)


def _source_mix(result, source_ids) -> dict[str, float]:
    return {
        source_id: sum(
            float(row["gross_delivery_t"])
            for row in result.sources
            if row["source_id"] == source_id
        )
        for source_id in source_ids
    }


def _comparison_row(label: str, plan, result, case_data) -> dict[str, Any]:
    return {
        "case": label,
        "plan_id": plan.plan_id,
        "scenario_id": result.summary["scenario_id"],
        "valid": result.summary["valid"],
        "hard_violation_count": result.summary["hard_violation_count"],
        "min_annual_total_service": _min_annual(result, "total_service_level"),
        "min_annual_critical_service": _min_annual(result, "critical_service_level"),
        "aggregate_total_service": result.summary["total_service_level"],
        "aggregate_critical_service": result.summary["critical_service_level"],
        "total_shortage_t": result.summary["total_shortage_t"],
        "critical_shortage_t": result.summary["critical_shortage_t"],
        "minimum_inventory_t": result.summary["minimum_inventory_t"],
        "final_inventory_t": result.summary["final_inventory_t"],
        "undiscounted_cost_mln": result.summary["undiscounted_cost_mln"],
        "discounted_cost_mln": result.summary["discounted_cost_mln"],
        "cost_per_served_ton_mln": result.summary["cost_per_served_ton_mln"],
        "source_mix_t": _source_mix(result, case_data.sources),
        "run_id": result.summary["run_id"],
    }


def _decision_snapshot(plan) -> dict[str, Any]:
    decisions = plan.raw["decisions"]
    return {
        "investments": copy.deepcopy(decisions.get("investments", [])),
        "capacity_reservations": copy.deepcopy(
            decisions.get("capacity_reservations", [])
        ),
        "supply_orders": copy.deepcopy(decisions.get("supply_orders", [])),
        "inventory_policy": copy.deepcopy(decisions.get("inventory_policy", {})),
        "emergency_role_by_year": copy.deepcopy(
            decisions.get("emergency_role_by_year", {})
        ),
        "initial_stock_acquisition": copy.deepcopy(
            decisions.get("initial_stock_acquisition")
        ),
    }


def _write_master_comparison(rows: list[dict[str, Any]]) -> None:
    json_rows = copy.deepcopy(rows)
    for row in json_rows:
        row["source_mix_t"] = dict(row["source_mix_t"])
    _json(OUTPUT / "master_comparison.json", {"rows": json_rows})

    scalar_fields = [
        "case",
        "plan_id",
        "scenario_id",
        "valid",
        "hard_violation_count",
        "min_annual_total_service",
        "min_annual_critical_service",
        "aggregate_total_service",
        "aggregate_critical_service",
        "total_shortage_t",
        "critical_shortage_t",
        "minimum_inventory_t",
        "final_inventory_t",
        "undiscounted_cost_mln",
        "discounted_cost_mln",
        "cost_per_served_ton_mln",
        "run_id",
    ]
    source_ids = sorted(
        {source_id for row in rows for source_id in row["source_mix_t"]}
    )
    with (OUTPUT / "master_comparison.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[*scalar_fields, *[f"source_{sid}_gross_t" for sid in source_ids]],
        )
        writer.writeheader()
        for row in rows:
            flat = {key: row[key] for key in scalar_fields}
            for sid in source_ids:
                flat[f"source_{sid}_gross_t"] = row["source_mix_t"].get(sid, 0.0)
            writer.writerow(flat)


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    PLAN_DIR.mkdir(parents=True, exist_ok=True)

    case_data = CaseDataLoader.load(PROJECT_ROOT)
    assumptions = AssumptionsLoader.load(
        PROJECT_ROOT / "configs" / "model_assumptions.json"
    )
    base = ScenarioLoader.load("BASE", PROJECT_ROOT)
    stress = ScenarioLoader.load("MANDATORY_STRESS", PROJECT_ROOT)

    builder_common = dict(
        max_candidates=1200,
        beam_width=24,
        max_iterations=8,
        max_results=3,
        seed=17,
    )
    base_build = synthesize_strategy(
        base,
        stress,
        case_data,
        assumptions,
        config=StrategyBuilderConfig(
            planning_mode="BASE_PLAN",
            objective="MIN_COST",
            **builder_common,
        ),
    )
    stress_build = synthesize_strategy(
        base,
        stress,
        case_data,
        assumptions,
        config=StrategyBuilderConfig(
            planning_mode="STRESS_ADAPTATION",
            objective="MIN_COST",
            **builder_common,
        ),
    )
    if base_build.status != "success" or not base_build.solutions:
        raise RuntimeError(
            f"BASE Builder failed: {base_build.status}: {base_build.failure_reason}"
        )
    if stress_build.status != "success" or not stress_build.solutions:
        raise RuntimeError(
            "STRESS Builder failed: "
            f"{stress_build.status}: {stress_build.failure_reason}"
        )

    final_base = _renamed_plan(
        base_build.solutions[0], "final-base-plan", case_data, assumptions
    )
    final_stress = _renamed_plan(
        stress_build.solutions[0],
        "final-stress-adaptation",
        case_data,
        assumptions,
    )
    save_plan(final_base, PLAN_DIR / "final_base.json")
    save_plan(final_stress, PLAN_DIR / "final_stress_adaptation.json")

    base_pair = evaluate_both_scenarios(
        final_base, base, stress, case_data, assumptions
    )
    stress_pair = evaluate_both_scenarios(
        final_stress, base, stress, case_data, assumptions
    )

    final_base_result = base_pair["BASE"]
    base_replayed_in_stress = base_pair["MANDATORY_STRESS"]
    adapted_stress_result = stress_pair["MANDATORY_STRESS"]

    if not final_base_result.summary["valid"]:
        raise RuntimeError("Selected FINAL BASE plan is not BASE-valid")
    if not adapted_stress_result.summary["valid"]:
        raise RuntimeError("Selected FINAL STRESS plan is not stress-valid")

    export_plan_results(
        final_base_result, OUTPUT / "A_BASE_PLAN_IN_BASE", PROJECT_ROOT
    )
    export_plan_results(
        base_replayed_in_stress,
        OUTPUT / "B_BASE_PLAN_REPLAYED_IN_STRESS",
        PROJECT_ROOT,
    )
    export_plan_results(
        adapted_stress_result,
        OUTPUT / "C_STRESS_ADAPTATION_IN_STRESS",
        PROJECT_ROOT,
    )
    export_scenario_comparison(
        final_base_result,
        base_replayed_in_stress,
        OUTPUT / "base_plan_scenario_comparison",
    )

    rows = [
        _comparison_row(
            "A_BASE_PLAN_IN_BASE", final_base, final_base_result, case_data
        ),
        _comparison_row(
            "B_BASE_PLAN_REPLAYED_IN_STRESS",
            final_base,
            base_replayed_in_stress,
            case_data,
        ),
        _comparison_row(
            "C_STRESS_ADAPTATION_IN_STRESS",
            final_stress,
            adapted_stress_result,
            case_data,
        ),
    ]
    _write_master_comparison(rows)

    a, b, c = rows
    deltas = {
        "stress_effect_B_minus_A": {
            "cost_delta_mln": b["undiscounted_cost_mln"]
            - a["undiscounted_cost_mln"],
            "shortage_delta_t": b["total_shortage_t"] - a["total_shortage_t"],
            "min_total_service_delta_pp": 100.0
            * (
                b["min_annual_total_service"]
                - a["min_annual_total_service"]
            ),
            "min_critical_service_delta_pp": 100.0
            * (
                b["min_annual_critical_service"]
                - a["min_annual_critical_service"]
            ),
        },
        "adaptation_effect_C_minus_B": {
            "cost_delta_mln": c["undiscounted_cost_mln"]
            - b["undiscounted_cost_mln"],
            "shortage_delta_t": c["total_shortage_t"] - b["total_shortage_t"],
            "min_total_service_delta_pp": 100.0
            * (
                c["min_annual_total_service"]
                - b["min_annual_total_service"]
            ),
            "min_critical_service_delta_pp": 100.0
            * (
                c["min_annual_critical_service"]
                - b["min_annual_critical_service"]
            ),
        },
    }
    _json(OUTPUT / "master_deltas.json", deltas)
    _json(
        OUTPUT / "decision_comparison.json",
        {
            "BASE_PLAN": _decision_snapshot(final_base),
            "STRESS_ADAPTATION": _decision_snapshot(final_stress),
        },
    )
    _json(
        OUTPUT / "builder_runs.json",
        {
            "BASE_PLAN": base_build.to_dict(),
            "STRESS_ADAPTATION": stress_build.to_dict(),
        },
    )

    alternative_plans = [
        PlanLoader.load(PLAN_DIR / "cost_focused.json", case_data, assumptions),
        PlanLoader.load(PLAN_DIR / "diversified.json", case_data, assumptions),
        PlanLoader.load(PLAN_DIR / "resilient.json", case_data, assumptions),
        final_base,
    ]
    alternative_comparison = compare_plans(
        alternative_plans, base, stress, case_data, assumptions
    )
    export_plan_comparison(
        alternative_comparison, OUTPUT / "alternatives"
    )

    demand_sensitivity = run_official_demand_sensitivity(
        final_base, base, case_data, assumptions
    )
    export_analysis_result(
        demand_sensitivity, OUTPUT / "sensitivity" / "official_low_base_high"
    )

    flex_lead_time_sensitivity = run_sensitivity(
        final_base,
        {
            "name": "lead_time_delay",
            "source_id": "B",
            "status": "TEAM_ASSUMPTION",
        },
        [0, 1, 2, 3, 4, 6],
        base,
        case_data,
        assumptions,
    )
    export_analysis_result(
        flex_lead_time_sensitivity,
        OUTPUT / "sensitivity" / "earth_flex_lead_time_delay_months",
    )

    zbo_loss_sensitivity = run_sensitivity(
        final_base,
        {
            "name": "storage_loss_multiplier",
            "storage_id": "ZBO",
            "status": "TEAM_ASSUMPTION",
        },
        [0.5, 1.0, 1.25, 1.5, 2.0],
        base,
        case_data,
        assumptions,
    )
    export_analysis_result(
        zbo_loss_sensitivity,
        OUTPUT / "sensitivity" / "zbo_loss_multiplier",
    )

    reverse_demand = run_reverse_stress(
        final_base,
        "demand_multiplier",
        {"start": 1.0, "stop": 1.5, "step": 0.01},
        "BASE_TOTAL_SERVICE",
        base,
        case_data,
        assumptions,
    )
    export_analysis_result(
        reverse_demand, OUTPUT / "reverse_stress" / "demand_multiplier"
    )

    reverse_flex_delay = run_reverse_stress(
        final_base,
        {
            "name": "lead_time_delay",
            "source_id": "B",
            "status": "TEAM_ASSUMPTION",
        },
        {"start": 0, "stop": 12, "step": 1},
        "ANY_HARD",
        base,
        case_data,
        assumptions,
    )
    export_analysis_result(
        reverse_flex_delay,
        OUTPUT / "reverse_stress" / "earth_flex_lead_time_delay_months",
    )

    risks = RiskLoader.load(PROJECT_ROOT / "configs" / "risks" / "team_risks.json")
    portfolio = evaluate_risks(
        final_base, base, risks, case_data, assumptions
    )
    export_risk_results(portfolio, OUTPUT / "risks", PROJECT_ROOT)

    manifest = {
        "status": "DIGITAL_TWIN_RESULT",
        "purpose": "Final reproducible evidence pack for competition deliverables",
        "case_input_root": ".",
        "plans": {
            "BASE_PLAN": "plans/final_base.json",
            "STRESS_ADAPTATION": "plans/final_stress_adaptation.json",
        },
        "three_way_comparison": {
            "A": "FINAL_BASE_PLAN simulated in BASE",
            "B": "the exact same FINAL_BASE_PLAN replayed in MANDATORY_STRESS",
            "C": "FINAL_STRESS_ADAPTATION simulated in MANDATORY_STRESS",
        },
        "builder_config": {
            "seed": 17,
            "max_candidates": 1200,
            "beam_width": 24,
            "max_iterations": 8,
            "max_results": 3,
        },
        "run_ids": {
            "A": final_base_result.summary["run_id"],
            "B": base_replayed_in_stress.summary["run_id"],
            "C": adapted_stress_result.summary["run_id"],
        },
        "additional_evidence": {
            "alternative_comparison": "results/final-evidence/alternatives/",
            "official_low_base_high": "results/final-evidence/sensitivity/official_low_base_high.json",
            "earth_flex_lead_time_sensitivity": "results/final-evidence/sensitivity/earth_flex_lead_time_delay_months.json",
            "zbo_loss_sensitivity": "results/final-evidence/sensitivity/zbo_loss_multiplier.json",
            "reverse_demand": "results/final-evidence/reverse_stress/demand_multiplier.json",
            "reverse_flex_delay": "results/final-evidence/reverse_stress/earth_flex_lead_time_delay_months.json",
            "risk_portfolio": "results/final-evidence/risks/risk_portfolio.json"
        },
        "provenance": {
            "official_inputs": "CASE_INPUT",
            "generated_plans": "TEAM_DECISION",
            "outputs": "DIGITAL_TWIN_RESULT",
            "stress_97_99": "RESILIENCE_BENCHMARK",
        },
    }
    _json(OUTPUT / "manifest.json", manifest)

    print(json.dumps(
        {
            "A": a,
            "B": b,
            "C": c,
            "deltas": deltas,
            "official_demand_first_failing_point": demand_sensitivity.first_failing_point,
            "flex_lead_time_first_failing_point": flex_lead_time_sensitivity.first_failing_point,
            "zbo_loss_first_failing_point": zbo_loss_sensitivity.first_failing_point,
            "reverse_demand": reverse_demand.to_dict(),
            "reverse_flex_delay": reverse_flex_delay.to_dict(),
        },
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
