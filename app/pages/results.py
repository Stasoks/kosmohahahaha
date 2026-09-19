from __future__ import annotations

import pandas as pd
import streamlit as st

from app import charts
from app.components import kpi_grid, render_chart, violations
from app.kernel_bridge import case_metadata
from app.view_models import minimum_annual_metrics, source_names


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

SOURCE_COLUMNS = {
    "source_id": "Код",
    "source_name": "Источник",
    "year": "Год",
    "reserved_capacity_t_per_year": "Зарезервировано, т/год",
    "requested_order_t": "Запрошено, т",
    "feasible_order_t": "Допустимый заказ, т",
    "gross_delivery_t": "Доставлено, т",
    "unfulfilled_request_t": "Не выполнено, т",
    "utilization": "Загрузка мощности",
    "active_variable_price_mln_per_t": "Цена, млн/т",
    "procurement_cost_mln": "Закупка, млн",
    "reservation_cost_mln": "Резервирование, млн",
    "take_or_pay_effect_mln": "Доплата до минимума, млн",
}

COST_COLUMNS = {
    "year": "Год",
    "capex_mln": "Инвестиции, млн",
    "fixed_opex_mln": "Постоянные расходы, млн",
    "procurement_mln": "Закупки, млн",
    "reservation_mln": "Резервирование, млн",
    "take_or_pay_effect_in_procurement_mln": "Доплата до минимума, млн",
    "holding_mln": "Хранение, млн",
    "initial_stock_procurement_mln": "Начальный запас, млн",
    "initial_stock_reservation_mln": "Резерв под начальный запас, млн",
    "total_cost_mln": "Всего, млн",
    "discounted_cost_mln": "Приведённая стоимость, млн",
    "cumulative_total_mln": "Накопленная стоимость, млн",
}


def _table(rows: list[dict], columns: list[str]) -> None:
    frame = pd.DataFrame(rows)
    present = [column for column in columns if column in frame]
    st.dataframe(frame[present].rename(columns=RUSSIAN_COLUMNS), hide_index=True, width="stretch")


def render() -> None:
    st.title("Результаты расчёта")
    options = ["BASE", "MANDATORY_STRESS"]
    if "CUSTOM" in st.session_state.result:
        options.append("CUSTOM")
    custom_label = st.session_state.result.get("custom_scenario", {}).get("name", "Пользовательский")
    selected = st.segmented_control(
        "Условия расчёта",
        options,
        default="BASE",
        format_func=lambda value: {
            "BASE": "Обычные",
            "MANDATORY_STRESS": "Обязательный стресс",
            "CUSTOM": custom_label,
        }[value],
    ) or "BASE"
    result_pair = st.session_state.result
    result = result_pair[selected]
    service_basis = selected
    if selected == "CUSTOM":
        service_basis = result_pair.get("custom_scenario", {}).get("base_scenario", "BASE")
    baseline = result_pair["BASE"] if selected != "BASE" else None
    kpi_grid(
        result,
        baseline=baseline,
        scenario_id=service_basis,
    )
    if baseline is not None:
        current = minimum_annual_metrics(result)
        base = minimum_annual_metrics(baseline)
        st.caption(
            f"Сравнение с BASE: сервис "
            f"{100*(current['minimum_annual_total_service']-base['minimum_annual_total_service']):+.1f} п.п. · "
            f"дефицит {current['total_shortage_t']-base['total_shortage_t']:+.1f} т · "
            f"стоимость {current['undiscounted_cost_mln']-base['undiscounted_cost_mln']:+.1f} млн у.е."
        )
    metadata = case_metadata(source_overrides=st.session_state.get("source_overrides", {}))
    tabs = st.tabs(["Годовой баланс", "Помесячный баланс", "Источники", "Экономика", "Ограничения"])
    with tabs[0]:
        left, right = st.columns(2)
        with left:
            render_chart(charts.demand_service(result))
        with right:
            render_chart(charts.service(result, service_basis))
        annual_rows = result.get("annual", [])
        failed_total = [
            str(row["year"])
            for row in annual_rows
            if float(row["total_service_level"]) < 0.97 - 1e-9
        ]
        failed_critical = [
            str(row["year"])
            for row in annual_rows
            if float(row["critical_service_level"]) < 0.99 - 1e-9
        ]
        if failed_total or failed_critical:
            st.info(
                "Как читать график сервиса: линии 97% и 99% показывают контрольные уровни. "
                + (f"Общий сервис ниже 97%: {', '.join(failed_total)}. " if failed_total else "")
                + (f"Критический ниже 99%: {', '.join(failed_critical)}." if failed_critical else "")
            )
        else:
            st.info(
                "Как читать график сервиса: обе линии обслуживания остаются не ниже контрольных уровней во все годы."
            )
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
        source_frame = pd.DataFrame(result["sources"])[source_columns].rename(columns=SOURCE_COLUMNS)
        st.dataframe(
            source_frame,
            hide_index=True,
            width="stretch",
            column_config={"Загрузка мощности": st.column_config.NumberColumn(format="percent")},
        )
    with tabs[3]:
        render_chart(charts.costs(result))
        costs = pd.DataFrame(result["costs"])
        costs["cumulative_total_mln"] = costs.total_cost_mln.cumsum()
        st.dataframe(costs.rename(columns=COST_COLUMNS), hide_index=True, width="stretch")
        st.caption("Доплата до минимального объёма показана отдельно. Полная стоимость не сравнивается с лимитом инвестиций 2 800 млн.")
    with tabs[4]:
        violations(result, selected)