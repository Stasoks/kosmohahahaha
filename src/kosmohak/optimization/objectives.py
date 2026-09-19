from __future__ import annotations

from kosmohak.optimization.result import SuggestedPlan


def repair_rank(item: SuggestedPlan) -> tuple:
    return (
        item.suggested_result.summary["hard_violation_count"],
        item.distance.changed_decision_count,
        item.distance.investment_change_count,
        item.distance.normalized_volume_distance,
        item.distance.date_change_distance,
        item.cost_delta_mln,
        item.resulting_plan.plan_id,
    )


def improve_rank(item: SuggestedPlan) -> tuple:
    return (
        item.suggested_result.summary["hard_violation_count"],
        item.suggested_result.summary["undiscounted_cost_mln"],
        item.distance.changed_decision_count,
        item.distance.normalized_volume_distance,
        item.resulting_plan.plan_id,
    )


def resilience_rank(item: SuggestedPlan) -> tuple:
    return (
        item.suggested_result.summary["hard_violation_count"],
        item.stress_after.summary["critical_shortage_t"],
        item.stress_after.summary["total_shortage_t"],
        -item.stress_after.summary["minimum_inventory_t"],
        item.distance.changed_decision_count,
        item.distance.normalized_volume_distance,
        item.cost_delta_mln,
        item.resulting_plan.plan_id,
    )
