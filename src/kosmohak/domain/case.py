from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DemandRow:
    year: int
    base_total_t: float
    base_critical_t: float
    low_total_t: float
    high_total_t: float
    status: str


@dataclass(frozen=True)
class SupplySource:
    source_id: str
    name: str
    capacity_t_per_year: float
    variable_cost_mln_per_t: float
    reservation_rate_mln_per_t_year_capacity: float
    take_or_pay_share: float
    lead_time_min_value: float
    lead_time_max_value: float
    lead_time_unit: str
    reliability_profile: str
    available_from_year: int | None
    status: str
    notes: str


@dataclass(frozen=True)
class StorageOption:
    storage_id: str
    name: str
    capacity_t: float
    loss_rate_on_throughput: float
    holding_cost_mln_per_t_year: float
    capex_mln: float
    fixed_opex_mln_per_year: float
    available_from_year: int
    status: str
    notes: str


@dataclass(frozen=True)
class InvestmentOption:
    investment_id: str
    name: str
    option_fee_mln: float
    exercise_cost_mln: float
    total_capex_mln: float
    commissioning_rule: str
    fixed_opex_mln_per_year: float
    status: str
    notes: str


@dataclass(frozen=True)
class ConstraintDefinition:
    constraint_id: str
    metric: str
    operator: str
    value: float
    unit: str
    period: str
    scenario: str
    severity: str
    status: str
    description: str

    def is_satisfied(self, actual: float) -> bool:
        if self.operator == "<=":
            return actual <= self.value + 1e-12
        if self.operator == ">=":
            return actual >= self.value - 1e-12
        raise ValueError(f"Unsupported constraint operator: {self.operator}")

    def gap(self, actual: float) -> float:
        if self.operator == "<=":
            return max(0.0, actual - self.value)
        return max(0.0, self.value - actual)


@dataclass(frozen=True)
class CaseData:
    root: Path
    demand: dict[int, DemandRow]
    sources: dict[str, SupplySource]
    source_id_by_name: dict[str, str]
    storage: dict[str, StorageOption]
    investments: dict[str, InvestmentOption]
    constraints: dict[str, ConstraintDefinition]
    status: str = "CASE_INPUT"

    @property
    def years(self) -> tuple[int, ...]:
        return tuple(sorted(self.demand))

    @property
    def start_month(self) -> str:
        return f"{self.years[0]}-01"

    @property
    def end_month(self) -> str:
        return f"{self.years[-1]}-12"

    def source_by_name(self, name: str) -> SupplySource:
        return self.sources[self.source_id_by_name[name]]

