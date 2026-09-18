from __future__ import annotations

from kosmohak.domain.assumptions import ModelAssumptions
from kosmohak.domain.case import CaseData, ConstraintDefinition
from kosmohak.domain.plan import OperatorPlan
from kosmohak.domain.result import Violation
from kosmohak.economics.investments import InvestmentEvent
from kosmohak.simulation.environment import SimulationEnvironment


def capacity_excess(reserved_t_per_year: float, capacity_t_per_year: float) -> float:
    return max(0.0, reserved_t_per_year - capacity_t_per_year)


def capacity_violation(
    reserved_t_per_year: float,
    capacity_t_per_year: float,
    *,
    source_id: str,
    year: int,
    scenario: str,
) -> Violation | None:
    excess = capacity_excess(reserved_t_per_year, capacity_t_per_year)
    if excess <= 1e-12:
        return None
    return make_violation(
        code="CAPACITY_EXCEEDED",
        constraint_id="STRUCTURAL_SOURCE_CAPACITY",
        severity="hard",
        scenario=scenario,
        period=str(year),
        source_id=source_id,
        actual=reserved_t_per_year,
        operator="<=",
        limit=capacity_t_per_year,
        unit="t/year",
        reason="Reserved capacity exceeds the active environment source capacity.",
        human_message=f"Source {source_id} reservation exceeds capacity by {excess:.3f} t/year.",
    )


def make_violation(
    *,
    code: str,
    constraint_id: str,
    severity: str,
    scenario: str,
    period: str,
    source_id: str | None,
    actual: float | str | None,
    operator: str,
    limit: float | str | None,
    unit: str,
    reason: str,
    human_message: str,
) -> Violation:
    gap: float | None = None
    if isinstance(actual, (int, float)) and isinstance(limit, (int, float)):
        gap = max(0.0, float(actual) - float(limit)) if operator == "<=" else max(0.0, float(limit) - float(actual))
    return Violation(
        code=code,
        constraint_id=constraint_id,
        severity=severity,
        scenario=scenario,
        period=period,
        source_id=source_id,
        actual=actual,
        operator=operator,
        limit=limit,
        unit=unit,
        excess_or_gap=gap,
        reason=reason,
        human_message=human_message,
    )


class ConstraintChecker:
    def __init__(self, case_data: CaseData, scenario: SimulationEnvironment) -> None:
        self.case_data = case_data
        self.scenario = scenario
        self.violations: list[Violation] = []

    def extend(self, violations: list[Violation]) -> None:
        self.violations.extend(violations)

    def storage_overflow(
        self, month: str, attempted_inventory_t: float, capacity_t: float, overflow_t: float
    ) -> None:
        if overflow_t > 1e-9:
            self.violations.append(
                make_violation(
                    code="STORAGE_CAPACITY_EXCEEDED",
                    constraint_id="STRUCTURAL_STORAGE_CAPACITY",
                    severity="hard",
                    scenario=self.scenario.scenario_id,
                    period=month,
                    source_id=None,
                    actual=attempted_inventory_t,
                    operator="<=",
                    limit=capacity_t,
                    unit="t",
                    reason="Post-loss inflow does not fit in active storage.",
                    human_message=(
                        f"Inventory after arrival would be {attempted_inventory_t:.3f} t; "
                        f"capacity is {capacity_t:.3f} t and {overflow_t:.3f} t is unaccepted."
                    ),
                )
            )

    def initial_storage(self, planned_t: float, accepted_t: float, capacity_t: float) -> None:
        if planned_t > capacity_t + 1e-9:
            self.violations.append(
                make_violation(
                    code="INITIAL_STORAGE_CAPACITY_EXCEEDED",
                    constraint_id="STRUCTURAL_STORAGE_CAPACITY",
                    severity="hard",
                    scenario=self.scenario.scenario_id,
                    period=self.case_data.start_month,
                    source_id=None,
                    actual=planned_t,
                    operator="<=",
                    limit=capacity_t,
                    unit="t",
                    reason="Opening physical inventory exceeds base storage capacity.",
                    human_message=f"Only {accepted_t:.3f} t of {planned_t:.3f} t opening inventory can be stored.",
                )
            )

    def _definition_violation(
        self,
        definition: ConstraintDefinition,
        period: str,
        actual: float,
        message: str,
        *,
        severity: str | None = None,
        code: str | None = None,
        source_id: str | None = None,
    ) -> None:
        if not definition.is_satisfied(actual):
            self.violations.append(
                make_violation(
                    code=code or definition.constraint_id,
                    constraint_id=definition.constraint_id,
                    severity=severity or definition.severity,
                    scenario=self.scenario.scenario_id,
                    period=period,
                    source_id=source_id,
                    actual=actual,
                    operator=definition.operator,
                    limit=definition.value,
                    unit=definition.unit,
                    reason=definition.description,
                    human_message=message,
                )
            )

    def complete(
        self,
        *,
        plan: OperatorPlan,
        assumptions: ModelAssumptions,
        annual: list[dict],
        monthly: list[dict],
        eligibility: dict[tuple[str, int], dict[str, float]],
        investment_events: list[InvestmentEvent],
    ) -> list[Violation]:
        # Source reservation and order feasibility use official per-source limits.
        for source_id, source in self.case_data.sources.items():
            for year in self.case_data.years:
                reserved = plan.reservation(source_id, year)
                info = eligibility[(source_id, year)]
                active_fraction = info["active_fraction"]
                effective_capacity = (
                    info["physical_limit_t"] / active_fraction
                    if active_fraction > 0
                    else source.capacity_t_per_year
                )
                effective_capacity = round(effective_capacity, 12)
                violation = capacity_violation(
                    reserved,
                    effective_capacity,
                    source_id=source_id,
                    year=year,
                    scenario=self.scenario.scenario_id,
                )
                if violation:
                    self.violations.append(violation)
                if info["ordered_t"] > info["contract_limit_t"] + 1e-9:
                    self.violations.append(
                        make_violation(
                            code="ORDER_CAPACITY_EXCEEDED",
                            constraint_id="STRUCTURAL_ORDER_CAPACITY",
                            severity="hard",
                            scenario=self.scenario.scenario_id,
                            period=str(year),
                            source_id=source_id,
                            actual=info["ordered_t"],
                            operator="<=",
                            limit=info["contract_limit_t"],
                            unit="t/year",
                            reason="Ordered volume exceeds active reserved/physical volume.",
                            human_message=(
                                f"Source {source_id} orders are {info['ordered_t']:.3f} t; "
                                f"active contract limit is {info['contract_limit_t']:.3f} t."
                            ),
                        )
                    )
                unavailable = info["ordered_t"] - info["available_ordered_t"]
                if unavailable > 1e-9:
                    self.violations.append(
                        make_violation(
                            code="SOURCE_UNAVAILABLE",
                            constraint_id="STRUCTURAL_SOURCE_AVAILABILITY",
                            severity="hard",
                            scenario=self.scenario.scenario_id,
                            period=str(year),
                            source_id=source_id,
                            actual=unavailable,
                            operator="<=",
                            limit=0.0,
                            unit="t",
                            reason="Orders were placed before source commissioning/availability.",
                            human_message=f"Source {source_id} has {unavailable:.3f} t ordered while unavailable.",
                        )
                    )

        # Service constraints are hard in BASE and explicit resilience benchmarks otherwise.
        critical_def = self.case_data.constraints["BASE_CRITICAL_SERVICE"]
        total_def = self.case_data.constraints["BASE_TOTAL_SERVICE"]
        for row in annual:
            year = str(row["year"])
            severity = "hard" if self.scenario.base_scenario_id == "BASE" else "benchmark"
            self._definition_violation(
                critical_def,
                year,
                row["critical_service_level"],
                f"Critical service is {row['critical_service_level']:.2%}; shortage is {row['critical_shortage_t']:.3f} t.",
                severity=severity,
                code=critical_def.constraint_id if severity == "hard" else "STRESS_CRITICAL_SERVICE_BENCHMARK",
            )
            self._definition_violation(
                total_def,
                year,
                row["total_service_level"],
                f"Total service is {row['total_service_level']:.2%}; shortage is {row['shortage_t']:.3f} t.",
                severity=severity,
                code=total_def.constraint_id if severity == "hard" else "STRESS_TOTAL_SERVICE_BENCHMARK",
            )

        for constraint_id in ("CAPEX_2037", "CAPEX_2040"):
            definition = self.case_data.constraints[constraint_id]
            through_year = int(definition.period.split("_")[-1])
            actual = sum(event.capex_mln for event in investment_events if int(event.month[:4]) <= through_year)
            self._definition_violation(
                definition,
                str(through_year),
                actual,
                f"Cumulative CAPEX through {through_year} is {actual:.3f} mln units.",
            )

        reserve_def = self.case_data.constraints["RESERVE_45D"]
        monthly_by_month = {row["month"]: row for row in monthly}
        emergency_lead = assumptions.source_delivery_lead_months(self.case_data.sources["E"])
        for row in annual:
            year = int(row["year"])
            actual_days = row["reserve_actual_days"]
            if plan.reserve_strategy(year) == "emergency_contract":
                reserved = plan.reservation("E", year)
                role_ok = plan.emergency_role_by_year.get(year) == "reserve_only"
                bridge_supply = row["opening_inventory_t"]
                bridge_demand = 0.0
                for month_number in range(1, emergency_lead + 1):
                    state = monthly_by_month[f"{year:04d}-{month_number:02d}"]
                    bridge_demand += state["demand_total_t"]
                    gross = state["gross_delivery_t"]
                    emergency_gross = state["gross_delivery_by_source"].get("E", 0.0)
                    bridge_supply += state["accepted_delivery_t"] * ((gross - emergency_gross) / gross) if gross else 0.0
                contract_ok = reserved >= row["reserve_requirement_t"] - 1e-12 and role_ok and bridge_supply >= bridge_demand - 1e-12
                actual_days = reserve_def.value if contract_ok else min(actual_days, reserved / row["demand_total_t"] * 365.0 if row["demand_total_t"] else reserve_def.value)
            self._definition_violation(
                reserve_def,
                f"{year}-01",
                actual_days,
                f"Reserve equivalence is {actual_days:.3f} days; required {reserve_def.value:.3f} days.",
            )

        emergency_def = self.case_data.constraints["EMERGENCY_BASE_STREAK"]
        run: list[int] = []
        for year in self.case_data.years:
            if plan.emergency_role_by_year.get(year) == "planned_supply":
                run = run + [year] if run and year == run[-1] + 1 else [year]
                if len(run) == int(emergency_def.value) + 1:
                    self._definition_violation(
                        emergency_def,
                        str(year),
                        float(len(run)),
                        f"Emergency is a base channel for {len(run)} consecutive years ({run[0]}-{year}).",
                        source_id="E",
                    )
            else:
                run = []

        loss = self.scenario.loss_ceiling
        if loss.get("enabled"):
            definition = self.case_data.constraints["STRESS_LOSS_LIMIT"]
            from_year = int(loss["from_year"])
            for row in annual:
                if row["year"] >= from_year:
                    actual = row["losses_divided_by_throughput"]
                    self._definition_violation(
                        definition,
                        str(row["year"]),
                        actual,
                        f"Losses/throughput is {actual:.2%}; ceiling is {definition.value:.2%}.",
                    )

        self.violations.sort(key=lambda item: (item.period, item.code, item.source_id or ""))
        return self.violations
