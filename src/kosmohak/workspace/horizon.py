from __future__ import annotations

from kosmohak.domain.case import DemandRow
from kosmohak.workspace.domain import FutureYearSpec


def build_future_demand(spec: FutureYearSpec) -> DemandRow:
    return DemandRow(
        year=spec.year,
        base_total_t=float(spec.base_total_demand_t),
        base_critical_t=float(spec.base_critical_demand_t),
        low_total_t=float(spec.low_total_t),
        high_total_t=float(spec.high_total_t),
        status="TEAM_ASSUMPTION",
    )
