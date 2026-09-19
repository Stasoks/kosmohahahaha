from __future__ import annotations

import json
from typing import Iterable

from kosmohak.domain.assumptions import ModelAssumptions
from kosmohak.domain.case import CaseData
from kosmohak.domain.plan import OperatorPlan
from kosmohak.domain.scenario import Scenario
from kosmohak.loading.plan import PlanLoader, PlanValidationError
from kosmohak.optimization.distance import measure_distance
from kosmohak.optimization.domain import DecisionLocks, OptimizerConfig
from kosmohak.optimization.locks import lock_violations
from kosmohak.optimization.patch import diff_plans
from kosmohak.optimization.result import SuggestedPlan
from kosmohak.simulation.engine import simulate


def cheap_prevalidate(raw: dict, case_data: CaseData) -> bool:
    decisions = raw.get("decisions", {})
    if any(
        float(value) < 0
        for item in decisions.get("supply_orders", [])
        for value in item.get("values", {}).values()
    ):
        return False
    if any(
        item.get("source_id") not in case_data.sources
        for item in decisions.get("supply_orders", [])
    ):
        return False
    return True


def evaluate_candidates(
    *,
    mode: str,
    original: OperatorPlan,
    candidate_raws: Iterable[dict],
    base_scenario: Scenario,
    stress_scenario: Scenario,
    case_data: CaseData,
    assumptions: ModelAssumptions,
    locks: DecisionLocks,
    config: OptimizerConfig,
) -> tuple[list[SuggestedPlan], int]:
    original_base = simulate(original, base_scenario, case_data, assumptions)
    original_stress = simulate(original, stress_scenario, case_data, assumptions)
    suggestions: list[SuggestedPlan] = []
    evaluated = 0
    seen: set[str] = set()
    for index, raw_input in enumerate(candidate_raws, start=1):
        if evaluated >= config.max_candidates:
            break
        raw = json.loads(json.dumps(raw_input))
        raw["plan_id"] = f"{original.plan_id}--{mode.lower()}-{index:03d}"
        canonical = json.dumps(raw["decisions"], sort_keys=True, separators=(",", ":"))
        if canonical in seen or not cheap_prevalidate(raw, case_data):
            continue
        seen.add(canonical)
        evaluated += 1
        try:
            candidate = OperatorPlan.from_dict(raw)
            PlanLoader.validate(candidate, case_data, assumptions)
        except (KeyError, TypeError, ValueError, PlanValidationError):
            continue
        if lock_violations(original, candidate, locks):
            continue
        patch = diff_plans(original, candidate)
        distance = measure_distance(patch)
        if (
            config.allowed_change_budget is not None
            and distance.changed_decision_count > config.allowed_change_budget
        ):
            continue
        candidate_base = simulate(candidate, base_scenario, case_data, assumptions)
        candidate_stress = simulate(candidate, stress_scenario, case_data, assumptions)
        suggestions.append(
            SuggestedPlan(
                base_plan_id=original.plan_id,
                patch=patch,
                resulting_plan=candidate,
                changed_decisions=[item.to_dict() for item in patch.changes],
                distance=distance,
                original_result=original_base,
                suggested_result=candidate_base,
                stress_before=original_stress,
                stress_after=candidate_stress,
            )
        )
    return suggestions, evaluated
