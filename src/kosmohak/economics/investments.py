from __future__ import annotations

from dataclasses import dataclass

from kosmohak.domain.case import CaseData
from kosmohak.domain.plan import OperatorPlan
from kosmohak.simulation.environment import SimulationEnvironment


@dataclass(frozen=True)
class InvestmentEvent:
    investment_id: str
    event: str
    month: str
    capex_mln: float


def investment_events(
    plan: OperatorPlan,
    case_data: CaseData,
    environment: SimulationEnvironment | None = None,
) -> list[InvestmentEvent]:
    events: list[InvestmentEvent] = []
    zbo = plan.investment("ZBO")
    if zbo.get("enabled"):
        events.append(
            InvestmentEvent(
                "ZBO",
                "commissioning",
                str(zbo["commissioning_month"]),
                case_data.investments["ZBO"].exercise_cost_mln,
            )
        )
    earth_new = plan.investment("EARTH_NEW")
    if earth_new.get("buy_option"):
        events.append(
            InvestmentEvent(
                "EARTH_NEW",
                "option_purchase",
                str(earth_new["option_purchase_month"]),
                case_data.investments["EARTH_NEW"].option_fee_mln,
            )
        )
    if earth_new.get("exercise_option"):
        events.append(
            InvestmentEvent(
                "EARTH_NEW",
                "option_exercise",
                str(earth_new["option_exercise_month"]),
                case_data.investments["EARTH_NEW"].exercise_cost_mln,
            )
        )
    lunar = plan.investment("LUNAR_ISRU")
    if lunar.get("enabled"):
        events.append(
            InvestmentEvent(
                "LUNAR_ISRU",
                "funding",
                str(lunar["funding_month"]),
                case_data.investments["LUNAR_ISRU"].exercise_cost_mln,
            )
        )
    if environment is not None:
        events = [
            InvestmentEvent(
                item.investment_id,
                item.event,
                item.month,
                environment.capex(item.investment_id, item.month, item.capex_mln),
            )
            for item in events
        ]
    return sorted(events, key=lambda item: (item.month, item.investment_id, item.event))
