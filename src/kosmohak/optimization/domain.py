from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class OptimizerConfig:
    max_candidates: int = 200
    seed: int = 42
    allowed_change_budget: int | None = None
    max_suggestions: int = 3
    reduction_fractions: tuple[float, ...] = (0.02, 0.05, 0.10)
    increase_fractions: tuple[float, ...] = (0.05, 0.10, 0.20)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reduction_fractions"] = list(self.reduction_fractions)
        value["increase_fractions"] = list(self.increase_fractions)
        return value


@dataclass(frozen=True)
class DecisionLocks:
    investments: dict[str, bool] = field(default_factory=dict)
    sources: dict[str, bool] = field(default_factory=dict)
    initial_stock: bool = False
    emergency_role: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
