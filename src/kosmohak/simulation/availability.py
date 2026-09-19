from __future__ import annotations

from kosmohak.domain.assumptions import ModelAssumptions
from kosmohak.domain.case import CaseData, SupplySource
from kosmohak.domain.investment import commissioning_dates
from kosmohak.domain.plan import OperatorPlan
from kosmohak.simulation.environment import SimulationEnvironment


def source_commissioning_month(
    source: SupplySource,
    plan: OperatorPlan,
    case_data: CaseData,
    assumptions: ModelAssumptions,
    environment: SimulationEnvironment,
    *,
    investment_dates: dict[str, str | None] | None = None,
) -> str | None:
    """Resolve availability from source data, never from a closed A-E switch."""
    rule = dict(source.availability_rule)
    kind = str(rule.get("type", "calendar"))
    if kind == "calendar":
        value = rule.get("available_from")
        if value is None and source.available_from_year is not None:
            value = f"{source.available_from_year}-01"
        return str(value)[:7] if value else None
    if kind == "investment":
        investment_id = str(rule.get("investment_id", ""))
        dates = investment_dates or commissioning_dates(
            plan, case_data, assumptions, environment
        )
        if investment_id not in dates:
            raise ValueError(
                f"Source {source.source_id} references unknown investment {investment_id}"
            )
        return dates[investment_id]
    if kind == "always":
        return "0000-01"
    raise ValueError(
        f"Unsupported availability rule {kind!r} for source {source.source_id}"
    )


def source_commissioning_dates(
    plan: OperatorPlan,
    case_data: CaseData,
    assumptions: ModelAssumptions,
    environment: SimulationEnvironment,
) -> dict[str, str | None]:
    dates = commissioning_dates(plan, case_data, assumptions, environment)
    return {
        source_id: source_commissioning_month(
            source,
            plan,
            case_data,
            assumptions,
            environment,
            investment_dates=dates,
        )
        for source_id, source in case_data.sources.items()
    }
