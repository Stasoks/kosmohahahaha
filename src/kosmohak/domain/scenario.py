from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    label_ru: str
    status: str
    config: dict[str, Any]
    source_path: Path

    @staticmethod
    def _year_value(section: dict[Any, Any], year: int, default: float = 1.0) -> float:
        if year in section:
            return float(section[year])
        if str(year) in section:
            return float(section[str(year)])
        return float(section.get("default", default))

    def demand_multiplier(self, year: int, *, critical: bool = False) -> float:
        key = "critical_demand_multiplier" if critical and "critical_demand_multiplier" in self.config else "demand_multiplier"
        return self._year_value(self.config.get(key, {}), year)

    def variable_price_multiplier(self, source_name: str, year: int) -> float:
        section = self.config.get("variable_price_multiplier", {})
        source_section = section.get(source_name)
        if isinstance(source_section, dict):
            return self._year_value(source_section, year)
        return float(section.get("default", 1.0))

    def actual_delivery_share(self, source_name: str, year: int) -> float:
        section = self.config.get("actual_delivery_share", {})
        source_section = section.get(source_name)
        if isinstance(source_section, dict):
            return self._year_value(source_section, year)
        return float(section.get("default", 1.0))

    @property
    def loss_ceiling(self) -> dict[str, Any]:
        return dict(self.config.get("loss_ceiling", {"enabled": False}))

