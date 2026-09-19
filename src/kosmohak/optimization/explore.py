from __future__ import annotations

from kosmohak.domain.assumptions import ModelAssumptions
from kosmohak.domain.case import CaseData
from kosmohak.domain.plan import OperatorPlan
from kosmohak.domain.scenario import Scenario
from kosmohak.optimization.domain import DecisionLocks, OptimizerConfig
from kosmohak.optimization.evaluator import evaluate_candidates
from kosmohak.optimization.objectives import resilience_rank
from kosmohak.optimization.result import OptimizationResult
from kosmohak.optimization.search_space import improvement_candidates, resilience_candidates


def _archetype(item, case_data: CaseData) -> str:
    delivered = {}
    for row in item.suggested_result.sources:
        delivered[row["source_id"]] = delivered.get(row["source_id"], 0.0) + row["gross_delivery_t"]
    active = [(source_id, value) for source_id, value in delivered.items() if value > 1e-9]
    total = sum(value for _, value in active) or 1.0
    earth = sum(
        value for source_id, value in active
        if "Earth" in case_data.sources[source_id].name
    ) / total
    lunar = sum(
        value for source_id, value in active
        if "Lunar" in case_data.sources[source_id].name
    ) / total
    earth_new = sum(
        value for source_id, value in active
        if case_data.sources[source_id].name == "Earth-New"
    ) / total
    concentration = max((value / total for _, value in active), default=1.0)
    if earth_new >= 0.2:
        return "Earth-New-oriented"
    if lunar >= 0.2:
        return "ISRU-oriented"
    if concentration <= 0.5:
        return "Flex/diversified"
    if earth >= 0.7:
        return "Earth-heavy"
    return "Flex/diversified"


def explore_alternatives(
    plan: OperatorPlan,
    base_scenario: Scenario,
    stress_scenario: Scenario,
    case_data: CaseData,
    assumptions: ModelAssumptions,
    *,
    locks: DecisionLocks | None = None,
    config: OptimizerConfig | None = None,
) -> OptimizationResult:
    locks = locks or DecisionLocks()
    config = config or OptimizerConfig(max_candidates=300, max_suggestions=4)
    raws = improvement_candidates(plan, config) + resilience_candidates(plan, case_data, config)
    values, count = evaluate_candidates(
        mode="EXPLORE", original=plan, candidate_raws=raws,
        base_scenario=base_scenario, stress_scenario=stress_scenario,
        case_data=case_data, assumptions=assumptions, locks=locks, config=config,
    )
    values = [item for item in values if item.suggested_result.summary["valid"]]
    values.sort(key=resilience_rank)
    selected = []
    seen = set()
    for item in values:
        label = _archetype(item, case_data)
        if label in seen:
            continue
        item.archetype = label
        selected.append(item)
        seen.add(label)
        if len(selected) >= config.max_suggestions:
            break
    return OptimizationResult(
        "EXPLORE", plan.plan_id, "success" if selected else "no_alternatives_found",
        selected, count, len(values), config.to_dict(), config.seed, locks.to_dict(),
        "Archetypes classify simulated source mixes; no plan is selected as a winner.",
    )
