from __future__ import annotations

import pandas as pd
import streamlit as st

from app import charts
from app.components import badges, kpi_grid, render_chart, violations
from app.kernel_bridge import case_metadata
from app.view_models import source_names


RUSSIAN_COLUMNS = {
    "year": "Год",
    "month": "Месяц",
    "demand_total_t": "Общий спрос, т",
    "demand_critical_t": "Критический спрос, т",
    "gross_supply_t": "Валовая поставка, т",
    "gross_delivery_t": "Прибытия, т",
    "losses_t": "Потери, т",
    "served_total_t": "Обслужено всего, т",
    "served_critical_t": "Обслужено критического, т",
    "served_noncritical_t": "Обслужено некритического, т",
    "shortage_t": "Дефицит, т",
    "critical_shortage_t": "Критический дефицит, т",
    "shortage_critical_t": "Критический дефицит, т",
    "shortage_noncritical_t": "Некритический дефицит, т",
    "opening_inventory_t": "Открывающий запас, т",
    "closing_inventory_t": "Закрывающий запас, т",
    "reserve_requirement_t": "Требуемый резерв, т",
    "reserve_actual_days": "Фактический резерв, дней",
    "available_inventory_t": "Доступно, т",
    "accepted_delivery_t": "Принято в хранилище, т",
    "active_storage_capacity_t": "Ёмкость, т",
}


def _table(rows: list[dict], columns: list[str]) -> None:
    frame = pd.DataFrame(rows)
    present = [column for column in columns if column in frame]
    st.dataframe(frame[present].rename(columns=RUSSIAN_COLUMNS), hide_index=True, width="stretch")


def render() -> None:
    st.title("Результаты расчёта")
    selected = st.segmented_control(
        "Среда исполнения", ["BASE", "MANDATORY_STRESS"], default="BASE"
    ) or "BASE"
    result = st.session_state.result[selected]
    badges(("DIGITAL_TWIN_RESULT", "result"), (("BASE HARD" if selected == "BASE" else "STRESS BENCHMARKS"), ("case" if selected == "BASE" else "benchmark")))
    kpi_grid(result)
    metadata = case_metadata()
    tabs = st.tabs(["Годовой баланс", "Помесячный баланс", "Источники", "Экономика", "Ограничения"])
    with tabs[0]:
        left, right = st.columns(2)
        with left:
            render_chart(charts.demand_service(result))
        with right:
            render_chart(charts.service(result, selected))
        _table(
            result["annual"],
            [
                "year", "demand_total_t", "demand_critical_t", "gross_supply_t", "losses_t",
                "served_total_t", "served_critical_t", "shortage_t", "critical_shortage_t",
                "opening_inventory_t", "closing_inventory_t", "reserve_requirement_t", "reserve_actual_days",
            ],
        )
    with tabs[1]:
        render_chart(charts.inventory(result))
        _table(
            result["monthly"],
            [
                "month", "opening_inventory_t", "gross_delivery_t", "losses_t",
                "available_inventory_t", "served_critical_t", "served_noncritical_t",
                "shortage_critical_t", "shortage_noncritical_t", "closing_inventory_t",
                "active_storage_capacity_t",
            ],
        )
    with tabs[2]:
        render_chart(charts.supply_mix(result, source_names(metadata)))
        source_columns = [
            "source_id", "source_name", "year", "reserved_capacity_t_per_year",
            "requested_order_t", "feasible_order_t", "gross_delivery_t",
            "unfulfilled_request_t", "utilization", "active_variable_price_mln_per_t",
            "procurement_cost_mln", "reservation_cost_mln", "take_or_pay_effect_mln",
        ]
        st.dataframe(pd.DataFrame(result["sources"])[source_columns], hide_index=True, width="stretch")
    with tabs[3]:
        render_chart(charts.costs(result))
        costs = pd.DataFrame(result["costs"])
        costs["cumulative_total_mln"] = costs.total_cost_mln.cumsum()
        st.dataframe(costs, hide_index=True, width="stretch")
        st.caption("TOP-эффект показан отдельно, когда он ненулевой; total lifecycle cost не сравнивается с лимитом CAPEX 2800.")
    with tabs[4]:
        violations(result, selected)
