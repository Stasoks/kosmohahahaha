from __future__ import annotations

from kosmohak.domain.case import SupplySource
from kosmohak.workspace.domain import ResearchSourceSpec


def build_research_source(spec: ResearchSourceSpec) -> SupplySource:
    rule = dict(spec.availability_rule)
    available = rule.get("available_from") if rule.get("type") == "calendar" else None
    available_year = int(str(available)[:4]) if available else None
    return SupplySource(
        source_id=spec.source_id,
        name=spec.name,
        capacity_t_per_year=float(spec.capacity_t_per_year),
        variable_cost_mln_per_t=float(spec.variable_cost_mln_per_t),
        reservation_rate_mln_per_t_year_capacity=float(
            spec.reservation_rate_mln_per_t_year_capacity
        ),
        take_or_pay_share=float(spec.take_or_pay_share),
        lead_time_min_value=float(spec.lead_time_min_value),
        lead_time_max_value=float(spec.lead_time_max_value),
        lead_time_unit=spec.lead_time_unit,
        reliability_profile="RESEARCH_METADATA",
        available_from_year=available_year,
        status="TEAM_ASSUMPTION",
        notes=spec.notes,
        availability_rule=rule,
        reliability_metadata=dict(spec.reliability_metadata),
        provenance={
            **spec.provenance,
            "status": "TEAM_ASSUMPTION",
            "scope": "RESEARCH_EXTENSION",
        },
        selected_lead_time_months=spec.selected_lead_time_months,
    )
