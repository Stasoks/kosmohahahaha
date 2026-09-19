from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ResearchSourceSpec:
    source_id: str
    name: str
    capacity_t_per_year: float
    variable_cost_mln_per_t: float
    reservation_rate_mln_per_t_year_capacity: float
    take_or_pay_share: float
    lead_time_min_value: float
    lead_time_max_value: float
    lead_time_unit: str
    availability_rule: dict[str, Any]
    reliability_metadata: dict[str, Any]
    notes: str
    provenance: dict[str, Any]
    status: str = "TEAM_ASSUMPTION"
    selected_lead_time_months: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ResearchSourceSpec":
        return cls(**value)


@dataclass(frozen=True)
class FutureYearSpec:
    year: int
    base_total_demand_t: float
    base_critical_demand_t: float
    low_total_t: float
    high_total_t: float
    source_price_assumptions: dict[str, Any]
    source_capacity_assumptions: dict[str, Any]
    source_availability_assumptions: dict[str, Any]
    reliability_assumptions: dict[str, Any]
    applicable_constraints: tuple[str, ...]
    notes: str
    provenance: dict[str, Any]
    status: str = "TEAM_ASSUMPTION"
    scope: str = "RESEARCH_EXTENSION"
    scenario_assumptions: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["applicable_constraints"] = list(self.applicable_constraints)
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "FutureYearSpec":
        normalized = dict(value)
        normalized["applicable_constraints"] = tuple(
            normalized.get("applicable_constraints", [])
        )
        return cls(**normalized)
