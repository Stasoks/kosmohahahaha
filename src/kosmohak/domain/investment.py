from __future__ import annotations

from kosmohak.domain.assumptions import ModelAssumptions
from kosmohak.domain.case import CaseData
from kosmohak.domain.plan import OperatorPlan
from kosmohak.domain.time import add_months
from kosmohak.simulation.environment import SimulationEnvironment


def commissioning_dates(
    plan: OperatorPlan,
    case_data: CaseData,
    assumptions: ModelAssumptions,
    environment: SimulationEnvironment | None = None,
) -> dict[str, str | None]:
    zbo = plan.investment("ZBO")
    earth_new = plan.investment("EARTH_NEW")
    lunar = plan.investment("LUNAR_ISRU")
    exercise = earth_new.get("option_exercise_month") if earth_new.get("exercise_option") else None
    values = {
        "ZBO": str(zbo["commissioning_month"]) if zbo.get("enabled") else None,
        "EARTH_NEW": add_months(str(exercise), assumptions.earth_new_project_lead_months) if exercise else None,
        "LUNAR_ISRU": f"{case_data.sources['D'].available_from_year}-01" if lunar.get("enabled") else None,
    }
    if environment is None:
        return values
    return {
        investment_id: (
            add_months(month, environment.commissioning_delay(investment_id, month))
            if month is not None
            else None
        )
        for investment_id, month in values.items()
    }


def active_months_in_year(commissioning_month: str | None, year: int) -> int:
    if commissioning_month is None:
        return 0
    commission_year = int(commissioning_month[:4])
    if year < commission_year:
        return 0
    if year > commission_year:
        return 12
    return 13 - int(commissioning_month[5:])
