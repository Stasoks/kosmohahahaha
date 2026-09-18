from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class Violation:
    code: str
    constraint_id: str
    severity: str
    scenario: str
    period: str
    source_id: str | None
    actual: float | str | None
    operator: str
    limit: float | str | None
    unit: str
    excess_or_gap: float | None
    reason: str
    human_message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SimulationResult:
    summary: dict[str, Any]
    annual: list[dict[str, Any]]
    monthly: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    violations: list[Violation]
    costs: list[dict[str, Any]]
    assumptions: dict[str, Any]
    pre_horizon: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "annual": self.annual,
            "monthly": self.monthly,
            "sources": self.sources,
            "violations": [item.to_dict() for item in self.violations],
            "costs": self.costs,
            "assumptions": self.assumptions,
            "pre_horizon": self.pre_horizon,
        }

    def to_export_envelope(self) -> dict[str, Any]:
        return {
            "scenario_id": self.summary["scenario_id"],
            "plan_id": self.summary["plan_id"],
            "units": {
                "mass": "t",
                "capacity": "t/year",
                "money": "million constant 2035 units",
                "service": "share",
            },
            "assumptions_reference": self.assumptions,
            "yearly_balance": self.annual,
            "source_schedule": self.sources,
            "inventory_trace": self.monthly,
            "financial_breakdown": self.costs,
            "constraint_checks": [item.to_dict() for item in self.violations],
            "risk_register": [],
            "pre_horizon": self.pre_horizon,
            "summary": self.summary,
        }
