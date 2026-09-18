from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OrderSchedule:
    source_id: str
    mode: str
    values: dict[str, float]


@dataclass(frozen=True)
class CapacityReservation:
    source_id: str
    year: int
    reserved_capacity_t: float


@dataclass(frozen=True)
class InitialStockAcquisition:
    """A real pre-horizon contract that creates opening physical inventory."""

    source_id: str
    reserved_capacity_t_per_year: float
    ordered_volume_t: float
    order_date: str
    planned_delivery_date: str
    contract_period_start: str
    contract_period_end: str
    notes: str
    status: str


@dataclass(frozen=True)
class OperatorPlan:
    plan_id: str
    scenario_id: str
    supply_orders: tuple[OrderSchedule, ...]
    capacity_reservations: tuple[CapacityReservation, ...]
    investments: tuple[dict[str, Any], ...]
    initial_stock_acquisition: InitialStockAcquisition | None
    inventory_policy: dict[str, Any]
    emergency_role_by_year: dict[int, str]
    metadata: dict[str, Any]
    raw: dict[str, Any]

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "OperatorPlan":
        decisions = raw["decisions"]
        orders = tuple(
            OrderSchedule(
                source_id=str(item["source_id"]),
                mode=str(item["mode"]),
                values={str(key): float(value) for key, value in item.get("values", {}).items()},
            )
            for item in decisions["supply_orders"]
        )
        reservations = tuple(
            CapacityReservation(
                source_id=str(item["source_id"]),
                year=int(item["year"]),
                reserved_capacity_t=float(item["reserved_capacity_t"]),
            )
            for item in decisions["capacity_reservations"]
        )
        initial_raw = decisions.get("initial_stock_acquisition")
        initial_stock = None
        if initial_raw is not None:
            initial_stock = InitialStockAcquisition(
                source_id=str(initial_raw["source_id"]),
                reserved_capacity_t_per_year=float(initial_raw["reserved_capacity_t_per_year"]),
                ordered_volume_t=float(initial_raw["ordered_volume_t"]),
                order_date=str(initial_raw["order_date"]),
                planned_delivery_date=str(initial_raw["planned_delivery_date"]),
                contract_period_start=str(initial_raw["contract_period_start"]),
                contract_period_end=str(initial_raw["contract_period_end"]),
                notes=str(initial_raw.get("notes", "")),
                status=str(initial_raw.get("status", "TEAM_DECISION")),
            )
        return cls(
            plan_id=str(raw["plan_id"]),
            scenario_id=str(raw["scenario_id"]),
            supply_orders=orders,
            capacity_reservations=reservations,
            investments=tuple(dict(item) for item in decisions["investments"]),
            initial_stock_acquisition=initial_stock,
            inventory_policy=dict(decisions["inventory_policy"]),
            emergency_role_by_year={
                int(year): str(role)
                for year, role in decisions.get("emergency_role_by_year", {}).items()
            },
            metadata=dict(raw.get("metadata", {})),
            raw=raw,
        )

    def investment(self, investment_id: str) -> dict[str, Any]:
        return next(
            (item for item in self.investments if item.get("investment_id") == investment_id),
            {"investment_id": investment_id, "enabled": False},
        )

    def reservation(self, source_id: str, year: int) -> float:
        return sum(
            item.reserved_capacity_t
            for item in self.capacity_reservations
            if item.source_id == source_id and item.year == year
        )

    @property
    def initial_inventory(self) -> dict[str, Any]:
        """Legacy input retained only so validation can reject magic positive stock."""
        return dict(self.inventory_policy.get("initial_inventory", {"tons": 0}))

    def reserve_strategy(self, year: int) -> str:
        values = self.inventory_policy.get("reserve_strategy_by_year", {})
        return str(values.get(str(year), values.get(year, "physical")))
