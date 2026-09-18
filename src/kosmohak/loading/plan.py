from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from kosmohak.domain.assumptions import ModelAssumptions
from kosmohak.domain.case import CaseData
from kosmohak.domain.plan import OperatorPlan
from kosmohak.domain.time import parse_month


class PlanValidationError(ValueError):
    pass


def _month(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise PlanValidationError(f"{field} must be YYYY-MM")
    try:
        parse_month(value)
    except ValueError as exc:
        raise PlanValidationError(f"{field}: {exc}") from exc
    return value


class PlanLoader:
    @classmethod
    def load(
        cls,
        path: str | Path,
        case_data: CaseData,
        assumptions: ModelAssumptions,
    ) -> OperatorPlan:
        plan_path = Path(path)
        raw = json.loads(plan_path.read_text(encoding="utf-8"))
        schema = json.loads((case_data.root / "schemas" / "plan.schema.json").read_text(encoding="utf-8"))
        errors = sorted(Draft202012Validator(schema).iter_errors(raw), key=lambda item: list(item.path))
        if errors:
            raise PlanValidationError(f"Plan does not match official envelope: {errors[0].message}")
        plan = OperatorPlan.from_dict(raw)
        cls.validate(plan, case_data, assumptions)
        return plan

    @classmethod
    def validate(
        cls, plan: OperatorPlan, case_data: CaseData, assumptions: ModelAssumptions
    ) -> None:
        years = set(case_data.years)
        if plan.metadata.get("status") != "TEAM_DECISION":
            raise PlanValidationError("Plan metadata.status must be TEAM_DECISION")
        if plan.scenario_id not in {"BASE", "MANDATORY_STRESS"}:
            raise PlanValidationError("Plan scenario_id must name an official scenario")

        seen_order_sources: set[str] = set()
        for schedule in plan.supply_orders:
            if schedule.source_id not in case_data.sources:
                raise PlanValidationError(f"Unknown source_id in supply_orders: {schedule.source_id}")
            if schedule.source_id in seen_order_sources:
                raise PlanValidationError(f"Duplicate order schedule for source {schedule.source_id}")
            seen_order_sources.add(schedule.source_id)
            if schedule.mode not in {"monthly", "annual_even"}:
                raise PlanValidationError(f"Invalid order mode for source {schedule.source_id}")
            for period, amount in schedule.values.items():
                if amount < 0:
                    raise PlanValidationError(f"Negative order for source {schedule.source_id} in {period}")
                if schedule.mode == "monthly":
                    month = _month(period, f"order[{schedule.source_id}]")
                    if not case_data.start_month <= month <= case_data.end_month:
                        raise PlanValidationError(f"Order month {month} is outside the official horizon")
                else:
                    try:
                        year = int(period)
                    except ValueError as exc:
                        raise PlanValidationError(f"Invalid order year {period!r}") from exc
                    if year not in years:
                        raise PlanValidationError(f"Order year {year} is outside the official horizon")

        seen_reservations: set[tuple[str, int]] = set()
        for reservation in plan.capacity_reservations:
            key = (reservation.source_id, reservation.year)
            if reservation.source_id not in case_data.sources:
                raise PlanValidationError(f"Unknown source_id in reservation: {reservation.source_id}")
            if reservation.year not in years:
                raise PlanValidationError(f"Reservation year {reservation.year} is outside the official horizon")
            if reservation.reserved_capacity_t < 0:
                raise PlanValidationError(f"Negative reservation for source {reservation.source_id}")
            if key in seen_reservations:
                raise PlanValidationError(f"Duplicate reservation for source {reservation.source_id} in {reservation.year}")
            seen_reservations.add(key)

        investment_ids = [str(item.get("investment_id")) for item in plan.investments]
        if len(set(investment_ids)) != len(investment_ids):
            raise PlanValidationError("Duplicate investment decision")
        unknown_investments = set(investment_ids) - set(case_data.investments)
        if unknown_investments:
            raise PlanValidationError(f"Unknown investments: {sorted(unknown_investments)}")

        zbo = plan.investment("ZBO")
        if zbo.get("enabled"):
            commission = _month(zbo.get("commissioning_month"), "ZBO.commissioning_month")
            if int(commission[:4]) < case_data.storage["ZBO"].available_from_year:
                raise PlanValidationError("ZBO cannot commission before its official availability year")
            if not case_data.start_month <= commission <= case_data.end_month:
                raise PlanValidationError("ZBO commissioning is outside the official horizon")

        earth_new = plan.investment("EARTH_NEW")
        buy = bool(earth_new.get("buy_option"))
        exercise = bool(earth_new.get("exercise_option"))
        if exercise and not buy:
            raise PlanValidationError("Earth-New exercise requires prior option purchase")
        if buy:
            purchase = _month(earth_new.get("option_purchase_month"), "EARTH_NEW.option_purchase_month")
            if not case_data.start_month <= purchase <= case_data.end_month:
                raise PlanValidationError("Earth-New option purchase is outside the official horizon")
        if exercise:
            exercise_month = _month(earth_new.get("option_exercise_month"), "EARTH_NEW.option_exercise_month")
            if purchase >= exercise_month:
                raise PlanValidationError("Earth-New exercise must be after option purchase")
            if not case_data.start_month <= exercise_month <= case_data.end_month:
                raise PlanValidationError("Earth-New option exercise is outside the official horizon")

        lunar = plan.investment("LUNAR_ISRU")
        if lunar.get("enabled"):
            funding = _month(lunar.get("funding_month"), "LUNAR_ISRU.funding_month")
            available_year = case_data.sources["D"].available_from_year
            if int(funding[:4]) >= int(available_year):
                raise PlanValidationError(f"Lunar-ISRU must be funded before {available_year}")
            if funding < case_data.start_month:
                raise PlanValidationError("Lunar-ISRU funding is outside the official horizon")

        legacy_initial = plan.initial_inventory
        legacy_tons = float(legacy_initial.get("tons", 0))
        if legacy_tons < 0:
            raise PlanValidationError("Initial inventory cannot be negative")
        if legacy_tons > 0:
            raise PlanValidationError(
                "Positive initial_inventory is not allowed; use decisions.initial_stock_acquisition"
            )

        acquisition = plan.initial_stock_acquisition
        if acquisition is not None:
            if acquisition.status != "TEAM_DECISION":
                raise PlanValidationError("initial_stock_acquisition.status must be TEAM_DECISION")
            if acquisition.source_id not in case_data.sources:
                raise PlanValidationError("Initial stock acquisition requires a valid source_id")
            if acquisition.ordered_volume_t < 0:
                raise PlanValidationError("Initial stock ordered volume cannot be negative")
            if acquisition.reserved_capacity_t_per_year < 0:
                raise PlanValidationError("Initial stock reservation cannot be negative")
            order_month = _month(acquisition.order_date, "initial_stock_acquisition.order_date")
            _month(
                acquisition.planned_delivery_date,
                "initial_stock_acquisition.planned_delivery_date",
            )
            contract_start = _month(
                acquisition.contract_period_start,
                "initial_stock_acquisition.contract_period_start",
            )
            contract_end = _month(
                acquisition.contract_period_end,
                "initial_stock_acquisition.contract_period_end",
            )
            if contract_end < contract_start:
                raise PlanValidationError("Initial stock contract period end precedes its start")
            if not contract_start <= order_month <= contract_end:
                raise PlanValidationError("Initial stock order_date must be inside its contract period")
            # Physical lead time, availability, capacity and arrival feasibility are
            # deliberately checked by the simulator so an impossible request remains
            # visible as an immutable plan plus structured violations.

        strategies = plan.inventory_policy.get("reserve_strategy_by_year", {})
        for year in case_data.years:
            strategy = strategies.get(str(year), strategies.get(year))
            if strategy not in {"physical", "emergency_contract"}:
                raise PlanValidationError(f"Missing or invalid reserve strategy for {year}")
        for year, role in plan.emergency_role_by_year.items():
            if year not in years or role not in {"reserve_only", "planned_supply"}:
                raise PlanValidationError(f"Invalid Emergency role for {year}")
