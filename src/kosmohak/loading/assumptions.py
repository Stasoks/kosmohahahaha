from __future__ import annotations

import json
from pathlib import Path

from kosmohak.domain.assumptions import ModelAssumptions


class AssumptionsLoader:
    REQUIRED = {
        "earth_new_project_lead_months",
        "earth_new_operational_delivery_lag_months",
        "lunar_isru_delivery_lead_months",
        "real_discount_rate",
        "monthly_demand_allocation",
        "storage_average_method",
        "week_to_model_month_conversion",
    }

    @classmethod
    def load(cls, path: str | Path) -> ModelAssumptions:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if raw.get("status") != "TEAM_ASSUMPTION":
            raise ValueError("Model assumptions must be marked TEAM_ASSUMPTION")
        missing = cls.REQUIRED - raw.keys()
        if missing:
            raise ValueError(f"Missing TEAM_ASSUMPTION values: {sorted(missing)}")
        for key in cls.REQUIRED - {"week_to_model_month_conversion"}:
            if not isinstance(raw[key], dict) or "value" not in raw[key] or "basis" not in raw[key]:
                raise ValueError(f"Assumption {key} must contain value and basis")
        earth_new = int(raw["earth_new_project_lead_months"]["value"])
        lunar = int(raw["lunar_isru_delivery_lead_months"]["value"])
        if not 18 <= earth_new <= 24:
            raise ValueError("Earth-New project lead must be within official 18..24 month range")
        if not 1 <= lunar <= 2:
            raise ValueError("Lunar-ISRU delivery lead must be within official 1..2 month range")
        if float(raw["real_discount_rate"]["value"]) < 0:
            raise ValueError("Discount rate cannot be negative")
        if raw["monthly_demand_allocation"]["value"] != "uniform":
            raise ValueError("Baseline supports only uniform monthly demand allocation")
        if raw["storage_average_method"]["value"] != "trapezoid":
            raise ValueError("Baseline supports only trapezoid storage averaging")
        return ModelAssumptions(raw=raw)

