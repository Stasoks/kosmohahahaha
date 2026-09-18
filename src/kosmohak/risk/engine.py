from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Iterable

from kosmohak.domain.assumptions import ModelAssumptions
from kosmohak.domain.case import CaseData
from kosmohak.domain.plan import OperatorPlan
from kosmohak.domain.risk import (
    MitigationEvaluation,
    RiskDefinition,
    RiskEvaluation,
    RiskPortfolioResult,
)
from kosmohak.domain.scenario import Scenario
from kosmohak.loading.plan import PlanLoader
from kosmohak.loading.risk import RiskLoader
from kosmohak.risk.consequence import compare_results
from kosmohak.risk.scoring import (
    build_risk_matrix,
    load_scoring_config,
    score_impact,
    score_likelihood,
)
from kosmohak.simulation.engine import simulate
from kosmohak.simulation.environment import SimulationEnvironment


def _default_scoring_path(case_data: CaseData) -> Path:
    return case_data.root / "configs" / "risk_scoring.json"


def _canonical_plan(plan: OperatorPlan) -> str:
    return json.dumps(plan.raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load_scoring(scoring: dict[str, Any] | str | Path | None, case_data: CaseData) -> dict[str, Any]:
    if isinstance(scoring, dict):
        return scoring
    return load_scoring_config(scoring or _default_scoring_path(case_data))


def _evaluate_with_baseline(
    plan: OperatorPlan,
    base_scenario: Scenario,
    risk: RiskDefinition,
    case_data: CaseData,
    assumptions: ModelAssumptions,
    scoring: dict[str, Any],
    baseline_result=None,
) -> RiskEvaluation:
    before = _canonical_plan(plan)
    baseline = baseline_result or simulate(plan, base_scenario, case_data, assumptions)
    environment = SimulationEnvironment.with_risks(base_scenario, [risk])
    risk_result = simulate(plan, environment, case_data, assumptions)
    if _canonical_plan(plan) != before:
        raise RuntimeError("Risk evaluation mutated OperatorPlan")
    consequence = compare_results(baseline, risk_result)
    impact = score_impact(consequence, scoring)
    likelihood_score = score_likelihood(risk.likelihood, scoring)
    ordinal_score = (
        likelihood_score * impact["impact_score"] if likelihood_score is not None else None
    )
    evaluation = RiskEvaluation(
        risk=risk,
        baseline_run_id=baseline.summary["run_id"],
        risk_run_id=risk_result.summary["run_id"],
        base_scenario_id=base_scenario.scenario_id,
        environment_id=environment.environment_id,
        applied_overrides=environment.applied_overrides(),
        consequence=consequence,
        impact=impact,
        likelihood=risk.likelihood,
        likelihood_score=likelihood_score,
        ordinal_risk_score=ordinal_score,
        baseline_result=baseline,
        risk_result=risk_result,
    )
    if risk.mitigation and risk.mitigation.get("plan_patch"):
        evaluation.mitigation = evaluate_mitigation(
            plan,
            base_scenario,
            risk,
            risk.mitigation,
            case_data,
            assumptions,
            scoring,
            original_evaluation=evaluation,
        )
    return evaluation


def evaluate_risk(
    plan: OperatorPlan,
    base_scenario: Scenario,
    risk_definition: RiskDefinition,
    case_data: CaseData,
    assumptions: ModelAssumptions,
    scoring: dict[str, Any] | str | Path | None = None,
) -> RiskEvaluation:
    """Compare the same immutable plan in an official base and one TEAM risk."""
    config = _load_scoring(scoring, case_data)
    return _evaluate_with_baseline(
        plan,
        base_scenario,
        risk_definition,
        case_data,
        assumptions,
        config,
    )


def evaluate_risk_set(
    plan: OperatorPlan,
    base_scenario: Scenario,
    risks: Iterable[RiskDefinition],
    case_data: CaseData,
    assumptions: ModelAssumptions,
    scoring: dict[str, Any] | str | Path | None = None,
) -> RiskPortfolioResult:
    config = _load_scoring(scoring, case_data)
    baseline = simulate(plan, base_scenario, case_data, assumptions)
    evaluations = [
        _evaluate_with_baseline(
            plan,
            base_scenario,
            risk,
            case_data,
            assumptions,
            config,
            baseline_result=baseline,
        )
        for risk in risks
    ]
    register = [item.to_register_entry() for item in evaluations]
    matrix = build_risk_matrix(evaluations)
    unknown = [item.risk.risk_id for item in evaluations if item.likelihood_score is None]
    return RiskPortfolioResult(
        plan_id=plan.plan_id,
        base_scenario_id=base_scenario.scenario_id,
        evaluations=evaluations,
        risk_register=register,
        risk_matrix=matrix,
        unknown_likelihood_risks=unknown,
        scoring_config=config,
    )


def _merge_mapping(target: dict[str, Any], patch: dict[str, Any]) -> None:
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge_mapping(target[key], value)
        else:
            target[key] = copy.deepcopy(value)


def _upsert(items: list[dict[str, Any]], patches: list[dict[str, Any]], keys: tuple[str, ...]) -> None:
    for patch in patches:
        identity = tuple(patch.get(key) for key in keys)
        existing = next(
            (item for item in items if tuple(item.get(key) for key in keys) == identity),
            None,
        )
        if existing is None:
            items.append(copy.deepcopy(patch))
        else:
            _merge_mapping(existing, patch)


def apply_plan_patch(
    plan: OperatorPlan,
    patch: dict[str, Any],
    case_data: CaseData,
    assumptions: ModelAssumptions,
    *,
    mitigation_id: str,
) -> OperatorPlan:
    raw = copy.deepcopy(plan.raw)
    decisions_patch = patch.get("decisions", patch)
    decisions = raw["decisions"]
    for name, keys in (
        ("supply_orders", ("source_id",)),
        ("capacity_reservations", ("source_id", "year")),
        ("investments", ("investment_id",)),
    ):
        if name in decisions_patch:
            _upsert(decisions.setdefault(name, []), decisions_patch[name], keys)
    for name in ("inventory_policy", "emergency_role_by_year", "initial_stock_acquisition"):
        if name not in decisions_patch:
            continue
        if isinstance(decisions_patch[name], dict) and isinstance(decisions.get(name), dict):
            _merge_mapping(decisions[name], decisions_patch[name])
        else:
            decisions[name] = copy.deepcopy(decisions_patch[name])
    if "metadata" in patch:
        _merge_mapping(raw.setdefault("metadata", {}), patch["metadata"])
    raw["plan_id"] = f"{plan.plan_id}--mitigation-{mitigation_id}"
    raw.setdefault("metadata", {})["mitigation_of"] = plan.plan_id
    raw["metadata"]["status"] = "TEAM_DECISION"
    mitigated = OperatorPlan.from_dict(raw)
    PlanLoader.validate(mitigated, case_data, assumptions)
    return mitigated


def evaluate_mitigation(
    original_plan: OperatorPlan,
    base_scenario: Scenario,
    risk: RiskDefinition,
    mitigation: dict[str, Any],
    case_data: CaseData,
    assumptions: ModelAssumptions,
    scoring: dict[str, Any] | str | Path | None = None,
    *,
    original_evaluation: RiskEvaluation | None = None,
) -> MitigationEvaluation:
    config = _load_scoring(scoring, case_data)
    mitigation_id = str(mitigation.get("mitigation_id", f"{risk.risk_id}-M1"))
    mitigated_plan = apply_plan_patch(
        original_plan,
        dict(mitigation["plan_patch"]),
        case_data,
        assumptions,
        mitigation_id=mitigation_id,
    )
    base_original = (
        original_evaluation.baseline_result
        if original_evaluation is not None
        else simulate(original_plan, base_scenario, case_data, assumptions)
    )
    original_risk = (
        original_evaluation.risk_result
        if original_evaluation is not None
        else simulate(
            original_plan,
            SimulationEnvironment.with_risks(base_scenario, [risk]),
            case_data,
            assumptions,
        )
    )
    base_mitigated = simulate(mitigated_plan, base_scenario, case_data, assumptions)
    risk_mitigated = simulate(
        mitigated_plan,
        SimulationEnvironment.with_risks(base_scenario, [risk]),
        case_data,
        assumptions,
    )
    residual = compare_results(base_mitigated, risk_mitigated)
    residual_impact = score_impact(residual, config)
    residual_likelihood = risk.likelihood
    if mitigation.get("residual_likelihood") is not None:
        temporary_raw = copy.deepcopy(risk.raw)
        temporary_raw["risk_id"] = f"{risk.risk_id}--residual-likelihood"
        temporary_raw["likelihood"] = copy.deepcopy(mitigation["residual_likelihood"])
        temporary_raw["likelihood_basis"] = mitigation["residual_likelihood"].get("basis")
        temporary_raw["likelihood_status"] = mitigation["residual_likelihood"].get(
            "status",
            "TEAM_ASSUMPTION",
        )
        residual_risk = RiskLoader.from_dict(temporary_raw)
        if residual_risk.likelihood.get("likelihood_type") == "unknown":
            raise ValueError(
                "Mitigation residual_likelihood requires explicit basis and source"
            )
        residual_likelihood = residual_risk.likelihood
    likelihood_score = score_likelihood(residual_likelihood, config)
    residual_score = (
        likelihood_score * residual_impact["impact_score"]
        if likelihood_score is not None
        else None
    )
    original_metrics = compare_results(base_original, original_risk)["risk"]
    return MitigationEvaluation(
        mitigation_id=mitigation_id,
        mitigation_cost_mln=(
            base_mitigated.summary["undiscounted_cost_mln"]
            - base_original.summary["undiscounted_cost_mln"]
        ),
        base_original_cost_mln=base_original.summary["undiscounted_cost_mln"],
        base_mitigated_cost_mln=base_mitigated.summary["undiscounted_cost_mln"],
        original_risk_metrics=original_metrics,
        residual_consequence=residual,
        residual_impact=residual_impact,
        residual_likelihood=residual_likelihood,
        residual_likelihood_score=likelihood_score,
        residual_risk_score=residual_score,
        mitigated_plan_id=mitigated_plan.plan_id,
        mitigated_plan=mitigated_plan.raw,
        risk_result=risk_mitigated,
    )
