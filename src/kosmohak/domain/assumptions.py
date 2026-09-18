from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Any

from kosmohak.domain.case import SupplySource


@dataclass(frozen=True)
class ModelAssumptions:
    raw: dict[str, Any]

    @property
    def real_discount_rate(self) -> float:
        return float(self.raw["real_discount_rate"]["value"])

    @property
    def monthly_demand_allocation(self) -> str:
        return str(self.raw["monthly_demand_allocation"]["value"])

    @property
    def storage_average_method(self) -> str:
        return str(self.raw["storage_average_method"]["value"])

    @property
    def earth_new_project_lead_months(self) -> int:
        return int(self.raw["earth_new_project_lead_months"]["value"])

    @property
    def earth_new_operational_delivery_lag_months(self) -> int:
        return int(self.raw["earth_new_operational_delivery_lag_months"]["value"])

    @property
    def lunar_isru_delivery_lead_months(self) -> int:
        return int(self.raw["lunar_isru_delivery_lead_months"]["value"])

    def source_delivery_lead_months(self, source: SupplySource) -> int:
        if source.source_id == "C":
            return self.earth_new_operational_delivery_lag_months
        if source.source_id == "D":
            return self.lunar_isru_delivery_lead_months
        if source.lead_time_unit == "month":
            if source.lead_time_min_value != source.lead_time_max_value:
                raise ValueError(f"No selected delivery lead-time assumption for {source.source_id}")
            return int(source.lead_time_min_value)
        conversion = self.raw["week_to_model_month_conversion"]
        if source.lead_time_unit == "week" and conversion["rounding"] == "ceil":
            days = source.lead_time_max_value * float(conversion["days_per_week"])
            model_month_days = float(conversion["days_per_model_year"]) / 12.0
            return ceil(days / model_month_days)
        raise ValueError(f"Unsupported lead-time conversion for {source.source_id}")

