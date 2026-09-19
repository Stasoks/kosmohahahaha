from __future__ import annotations

from kosmohak.domain.plan import OperatorPlan
from kosmohak.optimization.domain import DecisionLocks


def lock_violations(
    original: OperatorPlan,
    candidate: OperatorPlan,
    locks: DecisionLocks,
) -> list[str]:
    errors: list[str] = []
    for investment_id, locked in locks.investments.items():
        if locked and original.investment(investment_id) != candidate.investment(investment_id):
            errors.append(f"investment:{investment_id}")
    for source_id, locked in locks.sources.items():
        if not locked:
            continue
        original_orders = [item for item in original.supply_orders if item.source_id == source_id]
        candidate_orders = [item for item in candidate.supply_orders if item.source_id == source_id]
        original_reservations = [
            item for item in original.capacity_reservations if item.source_id == source_id
        ]
        candidate_reservations = [
            item for item in candidate.capacity_reservations if item.source_id == source_id
        ]
        if original_orders != candidate_orders or original_reservations != candidate_reservations:
            errors.append(f"source:{source_id}")
    if locks.initial_stock and original.initial_stock_acquisition != candidate.initial_stock_acquisition:
        errors.append("initial_stock")
    if locks.emergency_role and original.emergency_role_by_year != candidate.emergency_role_by_year:
        errors.append("emergency_role")
    return errors
