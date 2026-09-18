from __future__ import annotations

from dataclasses import asdict, dataclass, field

from kosmohak.constraints.checker import make_violation
from kosmohak.domain.assumptions import ModelAssumptions
from kosmohak.domain.case import CaseData
from kosmohak.domain.investment import commissioning_dates
from kosmohak.domain.plan import OperatorPlan
from kosmohak.domain.result import Violation
from kosmohak.domain.time import add_months, parse_month
from kosmohak.economics.contracts import contract_cost
from kosmohak.simulation.environment import SimulationEnvironment
from kosmohak.simulation.physics import accept_throughput


def _inclusive_months(start: str, end: str) -> int:
    start_year, start_month = parse_month(start)
    end_year, end_month = parse_month(end)
    return (end_year - start_year) * 12 + end_month - start_month + 1


@dataclass
class PreparatoryResult:
    acquisition_id: str | None
    source_id: str | None
    order_date: str | None
    planned_delivery_date: str | None
    actual_feasible_delivery_date: str | None
    contract_period_start: str | None
    contract_period_end: str | None
    contract_period_fraction: float
    reserved_capacity_t_per_year: float
    requested_order_t: float
    feasible_order_t: float
    unfulfilled_request_t: float
    scenario_underdelivery_t: float
    payable_volume_t: float
    procurement_cost_mln: float
    reservation_cost_mln: float
    take_or_pay_effect_mln: float
    gross_delivery_t: float
    losses_t: float
    net_delivery_t: float
    accepted_delivery_t: float
    overflow_t: float
    opening_inventory_t: float
    provenance: dict
    violations: list[Violation] = field(default_factory=list)

    @classmethod
    def empty(cls) -> "PreparatoryResult":
        return cls(
            acquisition_id=None,
            source_id=None,
            order_date=None,
            planned_delivery_date=None,
            actual_feasible_delivery_date=None,
            contract_period_start=None,
            contract_period_end=None,
            contract_period_fraction=0.0,
            reserved_capacity_t_per_year=0.0,
            requested_order_t=0.0,
            feasible_order_t=0.0,
            unfulfilled_request_t=0.0,
            scenario_underdelivery_t=0.0,
            payable_volume_t=0.0,
            procurement_cost_mln=0.0,
            reservation_cost_mln=0.0,
            take_or_pay_effect_mln=0.0,
            gross_delivery_t=0.0,
            losses_t=0.0,
            net_delivery_t=0.0,
            accepted_delivery_t=0.0,
            overflow_t=0.0,
            opening_inventory_t=0.0,
            provenance={
                "status": "TEAM_DECISION",
                "message": "No initial stock acquisition was requested.",
            },
        )

    @property
    def total_cost_mln(self) -> float:
        return self.procurement_cost_mln + self.reservation_cost_mln

    def to_dict(self) -> dict:
        value = asdict(self)
        value["violations"] = [item.to_dict() for item in self.violations]
        value["total_cost_mln"] = self.total_cost_mln
        return value


def evaluate_preparatory_acquisition(
    plan: OperatorPlan,
    environment: SimulationEnvironment,
    case_data: CaseData,
    assumptions: ModelAssumptions,
) -> PreparatoryResult:
    acquisition = plan.initial_stock_acquisition
    if acquisition is None or acquisition.ordered_volume_t <= 0:
        return PreparatoryResult.empty()

    source = case_data.sources[acquisition.source_id]
    order_month = acquisition.order_date[:7]
    planned_delivery = acquisition.planned_delivery_date[:7]
    period_start = acquisition.contract_period_start[:7]
    period_end = acquisition.contract_period_end[:7]
    period_fraction = _inclusive_months(period_start, period_end) / 12.0
    requested = acquisition.ordered_volume_t
    reserved_period = acquisition.reserved_capacity_t_per_year * period_fraction
    physical_capacity = environment.source_capacity(
        source.source_id,
        planned_delivery,
        source.capacity_t_per_year,
    ) * period_fraction
    contract_limit = min(reserved_period, physical_capacity)
    feasible = min(requested, max(0.0, contract_limit))
    violations: list[Violation] = []

    if acquisition.reserved_capacity_t_per_year > source.capacity_t_per_year + 1e-12:
        violations.append(
            make_violation(
                code="INITIAL_STOCK_RESERVATION_CAPACITY_EXCEEDED",
                constraint_id="STRUCTURAL_SOURCE_CAPACITY",
                severity="hard",
                scenario=environment.scenario_id,
                period=planned_delivery,
                source_id=source.source_id,
                actual=acquisition.reserved_capacity_t_per_year,
                operator="<=",
                limit=source.capacity_t_per_year,
                unit="t/year",
                reason="Preparatory reservation exceeds official source capacity.",
                human_message="Initial-stock reservation exceeds the source capacity.",
            )
        )
    if requested > contract_limit + 1e-12:
        violations.append(
            make_violation(
                code="INITIAL_STOCK_CAPACITY_EXCEEDED",
                constraint_id="STRUCTURAL_INITIAL_STOCK_CAPACITY",
                severity="hard",
                scenario=environment.scenario_id,
                period=planned_delivery,
                source_id=source.source_id,
                actual=requested,
                operator="<=",
                limit=contract_limit,
                unit="t",
                reason="Preparatory requested volume exceeds reserved or physical capacity.",
                human_message=f"Only {feasible:.3f} t of {requested:.3f} t is contractually and physically feasible.",
            )
        )

    base_lead = assumptions.source_delivery_lead_months(source)
    lead = environment.lead_time_months(source.source_id, order_month, base_lead)
    feasible_delivery = add_months(order_month, lead)
    dates = commissioning_dates(plan, case_data, assumptions, environment)
    source_commission = {
        "A": f"{source.available_from_year}-01",
        "B": f"{source.available_from_year}-01",
        "C": dates["EARTH_NEW"],
        "D": dates["LUNAR_ISRU"],
        "E": f"{source.available_from_year}-01",
    }[source.source_id]
    temporal_feasible = True
    if feasible_delivery > planned_delivery:
        temporal_feasible = False
        violations.append(
            make_violation(
                code="INITIAL_STOCK_LEAD_TIME_VIOLATION",
                constraint_id="STRUCTURAL_INITIAL_STOCK_LEAD_TIME",
                severity="hard",
                scenario=environment.scenario_id,
                period=planned_delivery,
                source_id=source.source_id,
                actual=feasible_delivery,
                operator="<=",
                limit=planned_delivery,
                unit="month",
                reason="Preparatory order cannot arrive by its requested delivery date.",
                human_message=f"Earliest delivery is {feasible_delivery}, requested {planned_delivery}.",
            )
        )
    if source_commission is None or planned_delivery < source_commission:
        temporal_feasible = False
        violations.append(
            make_violation(
                code="INITIAL_STOCK_SOURCE_UNAVAILABLE",
                constraint_id="STRUCTURAL_SOURCE_AVAILABILITY",
                severity="hard",
                scenario=environment.scenario_id,
                period=planned_delivery,
                source_id=source.source_id,
                actual=planned_delivery,
                operator=">=",
                limit=source_commission or "not commissioned",
                unit="month",
                reason="Selected source is unavailable for the preparatory delivery.",
                human_message="The selected source cannot physically supply opening inventory by the horizon start.",
            )
        )
    if planned_delivery > case_data.start_month:
        temporal_feasible = False
        violations.append(
            make_violation(
                code="INITIAL_STOCK_LATE_DELIVERY",
                constraint_id="STRUCTURAL_INITIAL_STOCK_TIMING",
                severity="hard",
                scenario=environment.scenario_id,
                period=case_data.start_month,
                source_id=source.source_id,
                actual=planned_delivery,
                operator="<=",
                limit=case_data.start_month,
                unit="month",
                reason="Opening stock must be delivered no later than the first model month.",
                human_message="The preparatory shipment arrives after the simulation starts.",
            )
        )

    feasible_physical = feasible if temporal_feasible else 0.0
    scenario_share = environment.actual_delivery_share(
        source.name,
        planned_delivery,
        source_id=source.source_id,
    )
    availability_share = environment.availability_share(source.source_id, planned_delivery)
    gross_delivery = feasible_physical * scenario_share * availability_share
    scenario_underdelivery = feasible_physical - gross_delivery

    storage = case_data.storage["BASE"]
    loss_rate = environment.storage_loss_rate(storage.storage_id, case_data.start_month, storage.loss_rate_on_throughput)
    capacity = environment.storage_capacity(storage.storage_id, case_data.start_month, storage.capacity_t)
    flow = accept_throughput(0.0, gross_delivery, loss_rate, capacity)
    if flow.overflow_t > 1e-12:
        violations.append(
            make_violation(
                code="INITIAL_STORAGE_CAPACITY_EXCEEDED",
                constraint_id="STRUCTURAL_STORAGE_CAPACITY",
                severity="hard",
                scenario=environment.scenario_id,
                period=case_data.start_month,
                source_id=source.source_id,
                actual=flow.net_delivery_t,
                operator="<=",
                limit=capacity,
                unit="t",
                reason="Net preparatory delivery exceeds opening storage capacity.",
                human_message=f"{flow.overflow_t:.3f} t of preparatory fuel cannot be accepted.",
            )
        )

    financing_year = case_data.years[0]
    price = environment.variable_price(
        source.source_id,
        source.name,
        financing_year,
        source.variable_cost_mln_per_t,
    )
    reservation_rate = environment.reservation_price(
        source.source_id,
        financing_year,
        source.reservation_rate_mln_per_t_year_capacity,
    )
    contract = contract_cost(
        ordered_volume_t=requested,
        reserved_capacity_period_t=reserved_period,
        take_or_pay_share=source.take_or_pay_share,
        variable_price_mln_per_t=price,
        annual_reserved_capacity_t=acquisition.reserved_capacity_t_per_year,
        reservation_rate_mln_per_t_year_capacity=reservation_rate,
        period_fraction=period_fraction,
    )
    return PreparatoryResult(
        acquisition_id=f"{plan.plan_id}:INITIAL_STOCK",
        source_id=source.source_id,
        order_date=order_month,
        planned_delivery_date=planned_delivery,
        actual_feasible_delivery_date=feasible_delivery,
        contract_period_start=period_start,
        contract_period_end=period_end,
        contract_period_fraction=period_fraction,
        reserved_capacity_t_per_year=acquisition.reserved_capacity_t_per_year,
        requested_order_t=requested,
        feasible_order_t=feasible_physical,
        unfulfilled_request_t=requested - feasible_physical,
        scenario_underdelivery_t=scenario_underdelivery,
        payable_volume_t=contract.payable_volume_t,
        procurement_cost_mln=contract.variable_payment_mln,
        reservation_cost_mln=contract.reservation_payment_mln,
        take_or_pay_effect_mln=contract.take_or_pay_effect_mln,
        gross_delivery_t=flow.gross_delivery_t,
        losses_t=flow.losses_t,
        net_delivery_t=flow.net_delivery_t,
        accepted_delivery_t=flow.accepted_delivery_t,
        overflow_t=flow.overflow_t,
        opening_inventory_t=flow.accepted_delivery_t,
        provenance={
            "status": "TEAM_DECISION",
            "opening_inventory": "PREPARATORY_SHIPMENT",
            "shipment": f"{plan.plan_id}:INITIAL_STOCK",
            "order": {
                "source_id": source.source_id,
                "order_date": order_month,
                "requested_order_t": requested,
            },
            "contract": {
                "period_start": period_start,
                "period_end": period_end,
                "reserved_capacity_t_per_year": acquisition.reserved_capacity_t_per_year,
            },
            "cost_financial_year": financing_year,
            "price_source": "CASE_INPUT supply_sources.csv plus explicit environment overrides",
        },
        violations=violations,
    )
