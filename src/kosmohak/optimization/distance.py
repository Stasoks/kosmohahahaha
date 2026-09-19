from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from kosmohak.domain.time import parse_month
from kosmohak.optimization.patch import PlanPatch


@dataclass(frozen=True)
class PlanDistance:
    changed_decision_count: int
    normalized_volume_distance: float
    date_change_distance: int
    investment_change_count: int
    contract_role_changes: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _is_volume(path: str) -> bool:
    return path.startswith(("orders.", "reservations.", "initial_stock.ordered", "initial_stock.reserved"))


def _month_index(value: Any) -> int | None:
    if not isinstance(value, str):
        return None
    try:
        year, month = parse_month(value)
    except ValueError:
        return None
    return year * 12 + month


def measure_distance(patch: PlanPatch) -> PlanDistance:
    absolute_volume = 0.0
    volume_basis = 0.0
    date_distance = 0
    investment_changes = 0
    role_changes = 0
    for change in patch.changes:
        if _is_volume(change.path) and isinstance(change.new, (int, float)):
            old = float(change.old or 0.0)
            absolute_volume += abs(float(change.new) - old)
            volume_basis += max(abs(old), 1.0)
        old_month, new_month = _month_index(change.old), _month_index(change.new)
        if old_month is not None and new_month is not None:
            date_distance += abs(new_month - old_month)
        if change.path.startswith("investments."):
            investment_changes += 1
        if change.path.startswith("emergency_role."):
            role_changes += 1
    return PlanDistance(
        changed_decision_count=len(patch.changes),
        normalized_volume_distance=(absolute_volume / volume_basis if volume_basis else 0.0),
        date_change_distance=date_distance,
        investment_change_count=investment_changes,
        contract_role_changes=role_changes,
    )
