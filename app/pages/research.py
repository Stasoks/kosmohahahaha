from __future__ import annotations

import copy

import pandas as pd
import streamlit as st

from app import charts, runtime
from app.components import kpi_grid, render_chart, render_error, violations
from app.kernel_bridge import (
    case_metadata,
    research_plan_template,
    workspace_add_source,
    workspace_bytes,
    workspace_extend_year,
    workspace_from_bytes,
)
from app.state import reset_research
from app.view_models import source_names


def _next_source_id(metadata: dict) -> str:
    for letter in "FGHIJKLMNOPQRSTUVWXYZ":
        if letter not in metadata["sources"]:
            return letter
    return f"R{len(metadata['sources']) + 1}"


def _remove_source_from_plan(raw: dict, source_id: str) -> dict:
    updated = copy.deepcopy(raw)
    decisions = updated.setdefault("decisions", {})
    decisions["supply_orders"] = [
        item
        for item in decisions.get("supply_orders", [])
        if str(item.get("source_id")) != str(source_id)
    ]
    decisions["capacity_reservations"] = [
        item
        for item in decisions.get("capacity_reservations", [])
        if str(item.get("source_id")) != str(source_id)
    ]
    stock = decisions.get("initial_stock_acquisition", {})
    if str(stock.get("source_id")) == str(source_id):
        updated["decisions"]["initial_stock_acquisition"] = copy.deepcopy(
            st.session_state.calculated_plan["decisions"].get(
                "initial_stock_acquisition", {}
            )
        )
    return updated


def _remove_years_from_plan(raw: dict, start_year: int) -> dict:
    updated = copy.deepcopy(raw)
    decisions = updated.setdefault("decisions", {})

    for schedule in decisions.get("supply_orders", []):
        values = schedule.get("values", {})
        schedule["values"] = {
            str(period): value
            for period, value in values.items()
            if int(str(period)[:4]) < int(start_year)
        }

    decisions["capacity_reservations"] = [
        item
        for item in decisions.get("capacity_reservations", [])
        if int(item.get("year", 0)) < int(start_year)
    ]

    inventory_policy = decisions.setdefault("inventory_policy", {})
    reserve_policy = inventory_policy.setdefault("reserve_strategy_by_year", {})
    inventory_policy["reserve_strategy_by_year"] = {
        str(year): value
        for year, value in reserve_policy.items()
        if int(year) < int(start_year)
    }

    emergency = decisions.setdefault("emergency_role_by_year", {})
    decisions["emergency_role_by_year"] = {
        str(year): value
        for year, value in emergency.items()
        if int(year) < int(start_year)
    }
    return updated


def _research_year_list(metadata: dict) -> None:
    years = sorted(int(year) for year in metadata.get("research_years", []))
    st.subheader("Добавленные годы")
    if not years:
        st.info("Горизонт пока не продлён дальше официального 2040 года.")
        return

    last_year = max(years)
    st.caption(
        "Расширение горизонта должно оставаться непрерывным. Поэтому удаление не последнего "
        "года также удалит все добавленные годы после него."
    )
    for year in years:
        demand = next(
            (
                item
                for item in metadata.get("demand", [])
                if int(item.get("year")) == year
            ),
            {},
        )
        cols = st.columns([1.2, 1.6, 1.6, 1.2])
        cols[0].markdown(f"**{year}**")
        cols[1].caption(f"спрос {float(demand.get('base_total_t', 0.0)):.1f} т")
        cols[2].caption(
            f"критический {float(demand.get('base_critical_t', 0.0)):.1f} т"
        )
        label = "Удалить" if year == last_year else f"Удалить {year}–{last_year}"
        if cols[3].button(
            label,
            key=f"remove-research-year-{year}",
            help=(
                f"Удалить {year} год из исследовательского горизонта."
                if year == last_year
                else f"Удалить {year} и все более поздние добавленные годы."
            ),
        ):
            try:
                st.session_state.workspace = runtime.workspace_remove_year(
                    st.session_state.workspace,
                    year,
                )
                current_plan = (
                    st.session_state.research_plan
                    or st.session_state.calculated_plan
                )
                cleaned = _remove_years_from_plan(current_plan, year)
                st.session_state.research_plan = research_plan_template(
                    cleaned,
                    st.session_state.workspace,
                )
                st.session_state.research_result = None
                if year == last_year:
                    st.success(f"{year} удалён из исследовательского горизонта.")
                else:
                    st.success(
                        f"Годы {year}–{last_year} удалены, чтобы горизонт остался непрерывным."
                    )
                st.rerun()
            except Exception as exc:
                render_error(exc, "Год не удалён")


def _research_source_list(metadata: dict) -> None:
    source_ids = list(metadata.get("research_source_ids", []))
    st.subheader("Добавленные вами источники")
    st.caption(
        "Официальные источники A–E являются частью кейса и не удаляются. "
        "Здесь можно удалить только источники, добавленные в рабочую копию."
    )
    if not source_ids:
        st.info("Дополнительных источников пока нет.")
        return

    for source_id in source_ids:
        source = metadata["sources"][source_id]
        cols = st.columns([2.2, 1, 1, 0.8])
        cols[0].markdown(f"**{source_id} · {source['name']}**")
        cols[1].caption(f"{source['capacity_t_per_year']:.1f} т/год")
        cols[2].caption(f"{source['variable_cost_mln_per_t']:.2f} млн/т")
        if cols[3].button("Удалить", key=f"remove-research-source-{source_id}"):
            try:
                st.session_state.workspace = runtime.workspace_remove_source(
                    st.session_state.workspace,
                    source_id,
                )
                current_plan = (
                    st.session_state.research_plan
                    or st.session_state.calculated_plan
                )
                cleaned = _remove_source_from_plan(current_plan, source_id)
                st.session_state.research_plan = research_plan_template(
                    cleaned,
                    st.session_state.workspace,
                )
                st.session_state.research_result = None
                st.success(f"Источник {source_id} удалён из рабочей копии.")
                st.rerun()
            except Exception as exc:
                render_error(exc, "Источник не удалён")


def _add_source() -> None:
    workspace = st.session_state.workspace
    metadata = case_metadata(workspace)
    with st.form("research-source"):
        st.subheader("Добавить новый источник в рабочую копию")
        st.caption(
            "Этот источник существует только в вашем варианте модели и не изменяет "
            "официальные данные кейса."
        )
        cols = st.columns(2)
        source_id = cols[0].text_input("Код источника", _next_source_id(metadata))
        name = cols[1].text_input("Название", "Новый источник")
        capacity = cols[0].number_input(
            "Мощность, т/год",
            min_value=0.0,
            value=25.0,
            help="Максимальный физический объём, который источник может поставить за год.",
        )
        price = cols[1].number_input(
            "Переменная цена, млн/т",
            min_value=0.0,
            value=8.0,
            help="Стоимость одной реально оплачиваемой тонны по этому источнику.",
        )
        cols = st.columns(2)
        reservation = cols[0].number_input(
            "Плата за резерв, млн/(т/год)",
            min_value=0.0,
            value=0.2,
            help="Плата за закреплённую мощность даже до фактического отбора топлива.",
        )
        top = cols[1].number_input(
            "Минимально оплачиваемая доля",
            0.0,
            1.0,
            0.0,
            0.05,
            help="Take-or-pay: доля зарезервированной мощности, которую всё равно надо оплатить.",
        )
        units = {"month": "месяцы", "week": "недели", "day": "дни", "year": "годы"}
        unit = cols[0].selectbox("Единица срока поставки", list(units), format_func=units.get)
        availability_labels = {"calendar": "С заданной даты", "always": "Всегда"}
        availability_kind = cols[1].selectbox(
            "Доступность", list(availability_labels), format_func=availability_labels.get
        )
        cols = st.columns(2)
        lead_min = cols[0].number_input("Минимальный срок поставки", min_value=0.0, value=4.0)
        lead_max = cols[1].number_input("Максимальный срок поставки", min_value=0.0, value=4.0)
        selected_lead = cols[0].number_input("Выбранный срок, мес.", min_value=0, value=4)
        available_from = st.text_input("Доступен с (ГГГГ-ММ)", f"{min(metadata['years'])}-01")
        notes = st.text_area("Примечания", "Дополнительный источник для исследования.")
        submitted = st.form_submit_button("Добавить источник", type="primary", width="stretch")
    if submitted:
        rule = {"type": availability_kind}
        if availability_kind == "calendar":
            rule["available_from"] = available_from
        payload = {
            "source_id": source_id.strip(), "name": name.strip(),
            "capacity_t_per_year": capacity, "variable_cost_mln_per_t": price,
            "reservation_rate_mln_per_t_year_capacity": reservation,
            "take_or_pay_share": top, "lead_time_min_value": lead_min,
            "lead_time_max_value": lead_max, "lead_time_unit": unit,
            "selected_lead_time_months": int(selected_lead) if lead_min != lead_max else None,
            "availability_rule": rule,
            "reliability_metadata": {"semantics": "metadata_only; no automatic derating"},
            "notes": notes,
            "provenance": {"basis": "team research assumption", "source": f"TEAM:source-{source_id}"},
        }
        try:
            st.session_state.workspace = workspace_add_source(workspace, payload)
            base = st.session_state.research_plan or st.session_state.calculated_plan
            st.session_state.research_plan = research_plan_template(base, st.session_state.workspace)
            st.session_state.research_result = None
            st.success(f"Источник {source_id} добавлен в исследовательский вариант.")
            st.rerun()
        except Exception as exc:
            render_error(exc, "Источник не добавлен")


def _extend_year() -> None:
    workspace = st.session_state.workspace
    metadata = case_metadata(workspace)
    next_year = max(metadata["years"]) + 1
    last_demand = metadata["demand"][-1]
    with st.form("research-year"):
        st.subheader(f"Продлить горизонт: {next_year}")
        cols = st.columns(2)
        total = cols[0].number_input("Общий спрос, т", min_value=0.0, value=float(last_demand["base_total_t"]))
        critical = cols[1].number_input("Критический спрос, т", min_value=0.0, value=float(last_demand["base_critical_t"]))
        low = cols[0].number_input("Нижняя оценка, т", min_value=0.0, value=float(last_demand["low_total_t"]))
        high = cols[1].number_input("Верхняя оценка, т", min_value=0.0, value=float(last_demand["high_total_t"]))
        assumptions = pd.DataFrame(
            [
                {
                    "Источник": source_id,
                    "Цена, млн/т": source["variable_cost_mln_per_t"],
                    "Мощность, т/год": source["capacity_t_per_year"],
                    "Доступность 0..1": 1.0,
                }
                for source_id, source in metadata["sources"].items()
            ]
        )
        edited = st.data_editor(
            assumptions,
            hide_index=True,
            width="stretch",
            column_config={
                "Источник": st.column_config.TextColumn(disabled=True),
                "Цена, млн/т": st.column_config.NumberColumn(min_value=0.0),
                "Мощность, т/год": st.column_config.NumberColumn(min_value=0.0),
                "Доступность 0..1": st.column_config.NumberColumn(min_value=0.0, max_value=1.0),
            },
        )
        constraints = [
            item for item in ("BASE_TOTAL_SERVICE", "BASE_CRITICAL_SERVICE", "RESERVE_45D")
            if item in metadata["constraints"]
        ]
        notes_text = st.text_area("Примечания", "Прогноз команды для расширенного горизонта.")
        submitted = st.form_submit_button(f"Добавить {next_year}", type="primary", width="stretch")
    if submitted:
        future = {
            "year": next_year,
            "base_total_demand_t": total,
            "base_critical_demand_t": critical,
            "low_total_t": low,
            "high_total_t": high,
            "source_price_assumptions": {str(row["Источник"]): float(row["Цена, млн/т"]) for _, row in edited.iterrows()},
            "source_capacity_assumptions": {str(row["Источник"]): float(row["Мощность, т/год"]) for _, row in edited.iterrows()},
            "source_availability_assumptions": {str(row["Источник"]): float(row["Доступность 0..1"]) for _, row in edited.iterrows()},
            "reliability_assumptions": {
                source_id: str(source.get("reliability_metadata", {}).get("semantics", "metadata_only"))
                for source_id, source in metadata["sources"].items()
            },
            "applicable_constraints": constraints,
            "notes": notes_text,
            "provenance": {"basis": "explicit team forecast", "source": f"TEAM:forecast-{next_year}"},
        }
        try:
            st.session_state.workspace = workspace_extend_year(workspace, future)
            base = st.session_state.research_plan or st.session_state.calculated_plan
            st.session_state.research_plan = research_plan_template(base, st.session_state.workspace)
            st.session_state.research_result = None
            st.success(f"{next_year} год добавлен в исследовательский вариант.")
            st.rerun()
        except Exception as exc:
            render_error(exc, "Год не добавлен")


def _research_plan_editor() -> None:
    metadata = case_metadata(st.session_state.workspace)
    if st.session_state.research_plan is None:
        st.session_state.research_plan = research_plan_template(
            st.session_state.calculated_plan, st.session_state.workspace
        )
    raw = st.session_state.research_plan
    schedules = {str(item["source_id"]): item for item in raw["decisions"]["supply_orders"]}
    reservations = {
        (str(item["source_id"]), int(item["year"])): float(item["reserved_capacity_t"])
        for item in raw["decisions"].get("capacity_reservations", [])
    }
    orders = []
    reserves = []
    for source_id, source in metadata["sources"].items():
        schedule = schedules.get(source_id, {"values": {}})
        active = any(
            float(value) > 0
            for value in schedule.get("values", {}).values()
        ) or any(
            reservations.get((source_id, year), 0.0) > 0
            for year in metadata["years"]
        )
        order_row = {
            "Использовать": active,
            "Источник": source_id,
            "Название": source["name"],
        }
        reserve_row = {"Источник": source_id, "Название": source["name"]}
        for year in metadata["years"]:
            order_row[str(year)] = sum(
                float(value) for period, value in schedule.get("values", {}).items()
                if int(str(period)[:4]) == year
            )
            reserve_row[str(year)] = reservations.get((source_id, year), 0.0)
        orders.append(order_row)
        reserves.append(reserve_row)
    st.subheader("Решения расширенного плана")
    st.caption(
        "Чтобы исключить даже официальный источник из этого исследовательского плана, "
        "снимите флажок «Использовать». Сам источник останется в модели и в исходных данных, "
        "но его заказы и резервирование будут обнулены."
    )
    order_frame = st.data_editor(
        pd.DataFrame(orders),
        hide_index=True,
        width="stretch",
        column_config={
            "Использовать": st.column_config.CheckboxColumn(
                help="Снять флажок = не использовать источник в этом исследовательском плане."
            ),
            "Источник": st.column_config.TextColumn(disabled=True),
            "Название": st.column_config.TextColumn(disabled=True),
        },
    )
    with st.expander("Резервирование мощности"):
        reserve_frame = st.data_editor(pd.DataFrame(reserves), hide_index=True, width="stretch")
    if st.button("Применить решения", width="stretch"):
        updated = copy.deepcopy(raw)
        active_sources = {
            str(row["Источник"])
            for _, row in order_frame.iterrows()
            if bool(row.get("Использовать", True))
        }
        updated["decisions"]["supply_orders"] = [
            {
                "source_id": str(row["Источник"]),
                "mode": "annual_even",
                "values": {
                    str(year): (
                        float(row[str(year)])
                        if str(row["Источник"]) in active_sources
                        else 0.0
                    )
                    for year in metadata["years"]
                },
            }
            for _, row in order_frame.iterrows()
        ]
        updated["decisions"]["capacity_reservations"] = [
            {
                "source_id": str(row["Источник"]),
                "year": year,
                "reserved_capacity_t": float(row[str(year)]),
            }
            for _, row in reserve_frame.iterrows()
            for year in metadata["years"]
            if (
                str(row["Источник"]) in active_sources
                and float(row[str(year)]) > 0
            )
        ]
        st.session_state.research_plan = updated
        st.session_state.research_result = None
        st.success("Решения применены; требуется отдельный расчёт.")
    if st.button("Рассчитать расширенный вариант", type="primary", width="stretch"):
        try:
            with st.spinner("Расчёт расширенного варианта…"):
                st.session_state.research_result = runtime.workspace_evaluate(
                    st.session_state.research_plan, st.session_state.workspace
                )
        except Exception as exc:
            render_error(exc, "Расширенный план не рассчитан")
    result = st.session_state.get("research_result")
    if result:
        kpi_grid(result["BASE"])
        left, right = st.columns(2)
        with left:
            render_chart(charts.demand_service(result["BASE"]))
        with right:
            render_chart(charts.supply_mix(result["BASE"], source_names(metadata)))
        violations(result["BASE"], "research")


def _workspace_io() -> None:
    workspace = st.session_state.workspace
    cols = st.columns(3)
    cols[0].download_button(
        "Скачать исследование JSON",
        workspace_bytes(workspace),
        "kosmohak-workspace.json",
        "application/json",
        width="stretch",
    )
    upload = cols[1].file_uploader("Открыть исследование", type=["json"], label_visibility="collapsed")
    if upload and cols[1].button("Проверить и открыть", width="stretch"):
        try:
            st.session_state.workspace = workspace_from_bytes(upload.getvalue())
            st.session_state.research_plan = research_plan_template(
                st.session_state.calculated_plan, st.session_state.workspace
            )
            st.session_state.research_result = None
            st.rerun()
        except Exception as exc:
            render_error(exc, "Исследование не открыто")
    if cols[2].button("Сбросить изменения", width="stretch"):
        reset_research(st.session_state.calculated_plan)
        st.rerun()


def render() -> None:
    st.title("Новые источники и горизонт")
    st.caption(
        "Рабочая копия для проверки вариантов, которых нет в официальном кейсе: "
        "дополнительных поставщиков и будущих лет. Контрольный BASE не изменяется."
    )
    _workspace_io()
    metadata = case_metadata(st.session_state.workspace)
    cols = st.columns(3)
    cols[0].metric("Всего источников", len(metadata["sources"]))
    cols[1].metric("Добавлено источников", len(metadata["research_source_ids"]))
    cols[2].metric("Горизонт", f"{min(metadata['years'])}–{max(metadata['years'])}")
    _research_source_list(metadata)
    _research_year_list(metadata)
    tabs = st.tabs(["Добавить источник", "Продлить горизонт", "План и расчёт"])
    with tabs[0]:
        _add_source()
    with tabs[1]:
        _extend_year()
    with tabs[2]:
        with st.expander("Исходные данные расширенного варианта"):
            demand_columns = {
                "year": "Год", "base_total_t": "Общий спрос, т",
                "base_critical_t": "Критический спрос, т", "low_total_t": "Нижняя оценка, т",
                "high_total_t": "Верхняя оценка, т",
            }
            demand = pd.DataFrame(metadata["demand"])
            shown = [column for column in demand_columns if column in demand]
            st.dataframe(demand[shown].rename(columns=demand_columns), hide_index=True, width="stretch")
            sources = pd.DataFrame(metadata["sources"].values())
            source_columns = {
                "source_id": "Код", "name": "Источник",
                "capacity_t_per_year": "Мощность, т/год",
                "variable_cost_mln_per_t": "Цена, млн/т",
                "reservation_rate_mln_per_t_year_capacity": "Плата за резерв",
                "take_or_pay_share": "Минимально оплачиваемая доля",
            }
            shown = [column for column in source_columns if column in sources]
            st.dataframe(sources[shown].rename(columns=source_columns), hide_index=True, width="stretch")
        _research_plan_editor()