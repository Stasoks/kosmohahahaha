from __future__ import annotations

from typing import Any

from kosmohak.domain.case import CaseData
from kosmohak.domain.time import parse_month
from kosmohak.workspace.domain import FutureYearSpec, ResearchSourceSpec


def _number(value: Any, label: str) -> float:
    if isinstance(value, dict):
        if "value" not in value:
            raise ValueError(f"{label} mapping must contain value")
        value = value["value"]
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc


def _provenance(value: dict[str, Any], label: str) -> None:
    if not value.get("basis") or not value.get("source"):
        raise ValueError(f"{label} provenance requires basis and source")


def validate_source_spec(
    spec: ResearchSourceSpec,
    case_data: CaseData,
    existing_ids: set[str],
    existing_names: set[str],
) -> None:
    if spec.status != "TEAM_ASSUMPTION":
        raise ValueError("Research source status must be TEAM_ASSUMPTION")
    if not spec.source_id or spec.source_id in existing_ids:
        raise ValueError(f"Duplicate or empty research source_id: {spec.source_id!r}")
    if not spec.name or spec.name in existing_names:
        raise ValueError(f"Duplicate or empty research source name: {spec.name!r}")
    values = (
        spec.capacity_t_per_year,
        spec.variable_cost_mln_per_t,
        spec.reservation_rate_mln_per_t_year_capacity,
        spec.lead_time_min_value,
        spec.lead_time_max_value,
    )
    if min(values) < 0 or not 0 <= spec.take_or_pay_share <= 1:
        raise ValueError(f"Invalid nonnegative/TOP parameters for source {spec.source_id}")
    if spec.lead_time_max_value < spec.lead_time_min_value:
        raise ValueError("lead_time_max_value cannot be below lead_time_min_value")
    if spec.lead_time_unit not in {"day", "week", "month", "year"}:
        raise ValueError("Unsupported research source lead_time_unit")
    if (
        spec.lead_time_min_value != spec.lead_time_max_value
        and spec.selected_lead_time_months is None
    ):
        raise ValueError("A lead-time range requires selected_lead_time_months")
    rule = spec.availability_rule
    kind = rule.get("type")
    if kind == "calendar":
        available = str(rule.get("available_from", ""))
        parse_month(available)
    elif kind == "investment":
        if rule.get("investment_id") not in case_data.investments:
            raise ValueError("Research source availability references unknown investment")
    elif kind != "always":
        raise ValueError("availability_rule.type must be calendar, investment, or always")
    _provenance(spec.provenance, f"source {spec.source_id}")


def validate_future_year_spec(
    spec: FutureYearSpec,
    case_data: CaseData,
    source_ids: set[str],
    expected_year: int,
) -> None:
    if spec.status != "TEAM_ASSUMPTION" or spec.scope != "RESEARCH_EXTENSION":
        raise ValueError("Future year must be TEAM_ASSUMPTION / RESEARCH_EXTENSION")
    if spec.year != expected_year:
        raise ValueError(f"Future years must be contiguous; expected {expected_year}")
    if min(spec.base_total_demand_t, spec.base_critical_demand_t, spec.low_total_t, spec.high_total_t) < 0:
        raise ValueError("Future demand values cannot be negative")
    if spec.base_critical_demand_t > spec.base_total_demand_t:
        raise ValueError("Future critical demand cannot exceed total demand")
    mappings = {
        "source_price_assumptions": spec.source_price_assumptions,
        "source_capacity_assumptions": spec.source_capacity_assumptions,
        "source_availability_assumptions": spec.source_availability_assumptions,
        "reliability_assumptions": spec.reliability_assumptions,
    }
    for label, mapping in mappings.items():
        missing = source_ids - set(mapping)
        extra = set(mapping) - source_ids
        if missing or extra:
            raise ValueError(
                f"{label} must explicitly cover every effective source; "
                f"missing={sorted(missing)}, extra={sorted(extra)}"
            )
    for source_id, value in spec.source_price_assumptions.items():
        if _number(value, f"price {source_id}") < 0:
            raise ValueError("Future source prices cannot be negative")
    for source_id, value in spec.source_capacity_assumptions.items():
        if _number(value, f"capacity {source_id}") < 0:
            raise ValueError("Future source capacities cannot be negative")
    for source_id, value in spec.source_availability_assumptions.items():
        share = _number(value, f"availability {source_id}")
        if not 0 <= share <= 1:
            raise ValueError("Future source availability must be within 0..1")
    unknown_constraints = set(spec.applicable_constraints) - set(case_data.constraints)
    if unknown_constraints:
        raise ValueError(f"Unknown future constraints: {sorted(unknown_constraints)}")
    _provenance(spec.provenance, f"future year {spec.year}")
