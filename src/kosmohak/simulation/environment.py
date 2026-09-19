from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from kosmohak.domain.risk import RiskDefinition
from kosmohak.domain.scenario import Scenario


SUPPORTED_RISK_FACTORS = {
    "total_demand_multiplier",
    "critical_demand_multiplier",
    "actual_delivery_share",
    "availability_share",
    "additional_lead_time_months",
    "lead_time_override_months",
    "source_capacity_multiplier",
    "variable_price_multiplier",
    "variable_price_override",
    "reservation_price_multiplier",
    "reservation_price_override",
    "storage_loss_rate_multiplier",
    "storage_loss_rate_override",
    "storage_capacity_multiplier",
    "investment_commissioning_delay_months",
    "fixed_opex_multiplier",
    "fixed_opex_override",
    "capex_multiplier",
    "capex_override",
}


def _as_month(value: str, *, end: bool = False) -> str:
    if len(value) == 4 and value.isdigit():
        return f"{value}-{'12' if end else '01'}"
    return value[:7]


def _value_for_period(value: Any, month: str) -> float:
    if isinstance(value, dict):
        year = month[:4]
        if month in value:
            return float(value[month])
        if year in value:
            return float(value[year])
        if int(year) in value:
            return float(value[int(year)])
        if "default" in value:
            return float(value["default"])
        raise ValueError(f"No override value for period {month}")
    return float(value)


@dataclass(frozen=True)
class SimulationEnvironment:
    """Official scenario plus explicitly ordered deterministic research overrides."""

    base_scenario: Scenario
    environment_id: str
    risk_ids: tuple[str, ...] = ()
    overrides: tuple[dict[str, Any], ...] = ()

    @classmethod
    def from_scenario(cls, scenario: Scenario) -> "SimulationEnvironment":
        return cls(base_scenario=scenario, environment_id=scenario.scenario_id)

    @classmethod
    def with_risks(
        cls,
        scenario: Scenario,
        risks: Iterable[RiskDefinition],
    ) -> "SimulationEnvironment":
        risk_values = tuple(risks)
        overrides: list[dict[str, Any]] = []
        for risk_index, risk in enumerate(risk_values, start=1):
            for factor_index, raw_change in enumerate(risk.factor_changes, start=1):
                change = dict(raw_change)
                change.setdefault("period_start", risk.period_start)
                change.setdefault("period_end", risk.period_end)
                change.setdefault("status", risk.status)
                change["risk_id"] = risk.risk_id
                change["application_order"] = len(overrides) + 1
                change["risk_order"] = risk_index
                change["factor_order"] = factor_index
                overrides.append(change)
        risk_ids = tuple(item.risk_id for item in risk_values)
        suffix = "+".join(risk_ids)
        environment_id = scenario.scenario_id if not suffix else f"{scenario.scenario_id}+{suffix}"
        return cls(
            base_scenario=scenario,
            environment_id=environment_id,
            risk_ids=risk_ids,
            overrides=tuple(overrides),
        )

    @property
    def scenario_id(self) -> str:
        return self.environment_id

    @property
    def base_scenario_id(self) -> str:
        return self.base_scenario.scenario_id

    @property
    def status(self) -> str:
        return self.base_scenario.status if not self.risk_ids else "COMPOSED_ENVIRONMENT"

    @property
    def source_path(self):
        return self.base_scenario.source_path

    @property
    def loss_ceiling(self) -> dict[str, Any]:
        return self.base_scenario.loss_ceiling

    def applied_overrides(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self.overrides]

    @staticmethod
    def _target(change: dict[str, Any], key: str, value: str) -> bool:
        target = change.get(key, change.get("target_id"))
        return target is None or str(target) in {"*", value}

    @staticmethod
    def _active(change: dict[str, Any], month: str) -> bool:
        start = _as_month(str(change.get("period_start", "0000-01")))
        end = _as_month(str(change.get("period_end", "9999-12")), end=True)
        return start <= month <= end

    def _changes(
        self,
        factor: str,
        month: str,
        *,
        target_key: str | None = None,
        target_value: str | None = None,
    ) -> list[dict[str, Any]]:
        output = []
        for change in self.overrides:
            if change.get("factor") != factor or not self._active(change, month):
                continue
            if target_key and target_value and not self._target(change, target_key, target_value):
                continue
            output.append(change)
        return output

    def _source_changes(
        self,
        factor: str,
        month: str,
        source_id: str,
        source_name: str | None = None,
    ) -> list[dict[str, Any]]:
        output = []
        for change in self._changes(factor, month):
            target = change.get(
                "source_id",
                change.get("source_name", change.get("target_id")),
            )
            accepted = {"*", source_id}
            if source_name is not None:
                accepted.add(source_name)
            if target is None or str(target) in accepted:
                output.append(change)
        return output

    @staticmethod
    def _change_value(change: dict[str, Any], month: str) -> float:
        for key in ("value", "multiplier", "override", "additional_months"):
            if key in change:
                return _value_for_period(change[key], month)
        raise ValueError(f"Risk factor {change.get('factor')} has no numeric value")

    def _multiply(self, base: float, factor: str, month: str, **target: str) -> float:
        value = base
        for change in self._changes(factor, month, **target):
            value *= self._change_value(change, month)
        return value

    def _override(self, base: float, factor: str, month: str, **target: str) -> float:
        value = base
        for change in self._changes(factor, month, **target):
            value = self._change_value(change, month)
        return value

    def demand_multiplier_for_month(self, month: str, *, critical: bool = False) -> float:
        year = int(month[:4])
        base = self.base_scenario.demand_multiplier(year, critical=critical)
        factor = "critical_demand_multiplier" if critical else "total_demand_multiplier"
        return self._multiply(base, factor, month)

    def demand_multiplier(self, year: int, *, critical: bool = False) -> float:
        return self.demand_multiplier_for_month(f"{year:04d}-01", critical=critical)

    def actual_delivery_share(
        self,
        source_name: str,
        month_or_year: str | int,
        *,
        source_id: str | None = None,
    ) -> float:
        month = f"{month_or_year:04d}-01" if isinstance(month_or_year, int) else _as_month(month_or_year)
        value = self.base_scenario.actual_delivery_share(source_name, int(month[:4]))
        for change in self._source_changes(
            "actual_delivery_share",
            month,
            str(source_id),
            source_name,
        ):
            value = self._change_value(change, month)
        return max(0.0, min(1.0, value))

    def availability_share(self, source_id: str, month: str) -> float:
        return max(
            0.0,
            min(
                1.0,
                self._override(
                    1.0,
                    "availability_share",
                    month,
                    target_key="source_id",
                    target_value=source_id,
                ),
            ),
        )

    def lead_time_months(self, source_id: str, order_month: str, base_months: int) -> int:
        value = float(base_months)
        value = self._override(
            value,
            "lead_time_override_months",
            order_month,
            target_key="source_id",
            target_value=source_id,
        )
        for change in self._changes(
            "additional_lead_time_months",
            order_month,
            target_key="source_id",
            target_value=source_id,
        ):
            value += self._change_value(change, order_month)
        return max(0, int(round(value)))

    def source_capacity(self, source_id: str, month: str, base_capacity: float) -> float:
        return max(
            0.0,
            self._multiply(
                base_capacity,
                "source_capacity_multiplier",
                month,
                target_key="source_id",
                target_value=source_id,
            ),
        )

    def variable_price_for_month(
        self, source_id: str, source_name: str, month: str, base_price: float
    ) -> float:
        year = int(month[:4])
        value = base_price * self.base_scenario.variable_price_multiplier(source_name, year)
        for change in self._source_changes(
            "variable_price_multiplier", month, source_id, source_name
        ):
            value *= self._change_value(change, month)
        for change in self._source_changes(
            "variable_price_override", month, source_id, source_name
        ):
            value = self._change_value(change, month)
        return max(0.0, value)

    def variable_price(self, source_id: str, source_name: str, year: int, base_price: float) -> float:
        """Compatibility display rate; contract charging uses monthly prices."""
        values = [
            self.variable_price_for_month(
                source_id, source_name, f"{year:04d}-{number:02d}", base_price
            )
            for number in range(1, 13)
        ]
        return sum(values) / 12.0

    def reservation_price_for_month(
        self, source_id: str, month: str, base_rate: float
    ) -> float:
        value = base_rate
        for change in self._source_changes(
            "reservation_price_multiplier", month, source_id
        ):
            value *= self._change_value(change, month)
        for change in self._source_changes(
            "reservation_price_override", month, source_id
        ):
            value = self._change_value(change, month)
        return max(0.0, value)

    def reservation_price(self, source_id: str, year: int, base_rate: float) -> float:
        values = [
            self.reservation_price_for_month(
                source_id, f"{year:04d}-{number:02d}", base_rate
            )
            for number in range(1, 13)
        ]
        return sum(values) / 12.0

    def storage_loss_rate(self, storage_id: str, month: str, base_rate: float) -> float:
        value = self._multiply(
            base_rate,
            "storage_loss_rate_multiplier",
            month,
            target_key="storage_id",
            target_value=storage_id,
        )
        value = self._override(
            value,
            "storage_loss_rate_override",
            month,
            target_key="storage_id",
            target_value=storage_id,
        )
        return min(1.0, max(0.0, value))

    def storage_capacity(self, storage_id: str, month: str, base_capacity: float) -> float:
        return max(
            0.0,
            self._multiply(
                base_capacity,
                "storage_capacity_multiplier",
                month,
                target_key="storage_id",
                target_value=storage_id,
            ),
        )

    def commissioning_delay(self, investment_id: str, decision_month: str) -> int:
        value = 0.0
        for change in self._changes(
            "investment_commissioning_delay_months",
            decision_month,
            target_key="investment_id",
            target_value=investment_id,
        ):
            value += self._change_value(change, decision_month)
        return max(0, int(round(value)))

    def fixed_opex(self, investment_id: str, month: str, base_value: float) -> float:
        value = self._multiply(
            base_value,
            "fixed_opex_multiplier",
            month,
            target_key="investment_id",
            target_value=investment_id,
        )
        return max(
            0.0,
            self._override(
                value,
                "fixed_opex_override",
                month,
                target_key="investment_id",
                target_value=investment_id,
            ),
        )

    def capex(self, investment_id: str, month: str, base_value: float) -> float:
        value = self._multiply(
            base_value,
            "capex_multiplier",
            month,
            target_key="investment_id",
            target_value=investment_id,
        )
        return max(
            0.0,
            self._override(
                value,
                "capex_override",
                month,
                target_key="investment_id",
                target_value=investment_id,
            ),
        )


def ensure_environment(value: Scenario | SimulationEnvironment) -> SimulationEnvironment:
    if isinstance(value, SimulationEnvironment):
        return value
    return SimulationEnvironment.from_scenario(value)
