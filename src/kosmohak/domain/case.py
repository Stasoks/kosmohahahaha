from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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
    availability_rule: dict[str, Any] = field(default_factory=dict)
    reliability_metadata: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    selected_lead_time_months: int | None = None


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
    horizon_provenance: dict[int, dict[str, Any]] = field(default_factory=dict)
    future_year_assumptions: dict[int, dict[str, Any]] = field(default_factory=dict)
    workspace_provenance: dict[str, Any] = field(default_factory=dict)

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

    def source_capacity(self, source_id: str, month_or_year: str | int) -> float:
        year = int(str(month_or_year)[:4])
        default = self.sources[source_id].capacity_t_per_year
        value = self.future_year_assumptions.get(year, {}).get(
            "source_capacity_assumptions", {}
        ).get(source_id, default)
        return _assumption_value(value)

    def source_price(self, source_id: str, month_or_year: str | int) -> float:
        year = int(str(month_or_year)[:4])
        default = self.sources[source_id].variable_cost_mln_per_t
        value = self.future_year_assumptions.get(year, {}).get(
            "source_price_assumptions", {}
        ).get(source_id, default)
        return _assumption_value(value)

    def source_availability_share(self, source_id: str, month_or_year: str | int) -> float:
        year = int(str(month_or_year)[:4])
        value = self.future_year_assumptions.get(year, {}).get(
            "source_availability_assumptions", {}
        ).get(source_id, 1.0)
        return max(0.0, min(1.0, _assumption_value(value)))

    def constraint_applies(self, constraint_id: str, year: int) -> bool:
        if year not in self.future_year_assumptions:
            return True
        return constraint_id in set(
            self.future_year_assumptions[year].get("applicable_constraints", [])
        )

    @property
    def official_years(self) -> tuple[int, ...]:
        return tuple(
            year
            for year in self.years
            if self.horizon_provenance.get(year, {}).get("scope")
            != "RESEARCH_EXTENSION"
        )

    @property
    def research_years(self) -> tuple[int, ...]:
        return tuple(year for year in self.years if year not in self.official_years)

    @property
    def research_source_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                source_id
                for source_id, source in self.sources.items()
                if source.status != "CASE_INPUT"
            )
        )


def _assumption_value(value: Any) -> float:
    if isinstance(value, dict):
        if "value" not in value:
            raise ValueError("Numeric research assumption mapping must contain value")
        value = value["value"]
    return float(value)
