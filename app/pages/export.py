from __future__ import annotations

import copy
import json

import pandas as pd
import streamlit as st

from app import runtime
from app.components import render_error
from app.kernel_bridge import case_tables, plan_bytes, plan_from_bytes
from app.state import apply_plan, save_snapshot
from app.view_models import constraint_label


def _plans() -> None:
    st.caption("Файл JSON можно перенести на другой компьютер. Снимки хранятся только до закрытия текущего сеанса.")
    try:
        payload = plan_bytes(st.session_state.plan)
        st.download_button(
            "Скачать текущий план JSON",
            payload,
            f"{st.session_state.plan.get('plan_id', 'plan')}.json",
            "application/json",
            width="stretch",
        )
    except Exception as exc:
        render_error(exc, "План пока нельзя экспортировать как валидный OperatorPlan")
    upload = st.file_uploader("Загрузить план JSON", type=["json"], key="plan-upload")
    if upload and st.button("Проверить и открыть план", type="primary"):
        try:
            apply_plan(plan_from_bytes(upload.getvalue()))
            st.success("План открыт и помечен как несчитанный.")
            st.rerun()
        except Exception as exc:
            render_error(exc, "План не открыт")
    st.subheader("Снимки текущего сеанса")
    cols = st.columns(2)
    if cols[0].button("Сохранить снимок", width="stretch"):
        st.toast(f"Сохранено: {save_snapshot()}", icon="✅")
    snapshots = st.session_state.snapshots
    if snapshots:
        selected = cols[1].selectbox("Снимок", list(snapshots))
        if st.button("Открыть снимок"):
            apply_plan(copy.deepcopy(snapshots[selected]))
            st.rerun()
    else:
        cols[1].info("Снимков нет")


def _case_data() -> None:
    tables = case_tables(source_overrides=st.session_state.get("source_overrides", {}))
    st.subheader("Спрос")
    demand_columns = {
        "year": "Год", "base_total_t": "Общий спрос, т", "base_critical_t": "Критический спрос, т",
        "low_total_t": "Нижняя оценка, т", "high_total_t": "Верхняя оценка, т",
    }
    demand = pd.DataFrame(tables["demand"])
    st.dataframe(demand[list(demand_columns)].rename(columns=demand_columns), hide_index=True, width="stretch")
    st.subheader("Источники")
    sources = pd.DataFrame(tables["sources"])
    source_columns = {
        "source_id": "Код", "name": "Источник", "capacity_t_per_year": "Мощность, т/год",
        "variable_cost_mln_per_t": "Цена, млн/т",
        "reservation_rate_mln_per_t_year_capacity": "Плата за резерв",
        "take_or_pay_share": "Минимально оплачиваемая доля",
        "lead_time_min_value": "Мин. срок поставки", "lead_time_max_value": "Макс. срок поставки",
        "available_from_year": "Доступен с года",
    }
    shown = [column for column in source_columns if column in sources]
    st.dataframe(sources[shown].rename(columns=source_columns), hide_index=True, width="stretch")
    st.subheader("Ограничения")
    constraints = pd.DataFrame(tables["constraints"])
    constraints["constraint_id"] = constraints["constraint_id"].map(constraint_label)
    constraints["unit"] = constraints["unit"].map({
        "share": "доля", "days": "дни", "years": "годы", "mln_units": "млн у.е.",
    }).fillna(constraints["unit"])
    constraints["period"] = constraints["period"].map({"annual": "ежегодно"}).fillna(constraints["period"])
    constraint_columns = {
        "constraint_id": "Ограничение", "value": "Значение", "operator": "Условие",
        "unit": "Единица", "period": "Период",
    }
    shown = [column for column in constraint_columns if column in constraints]
    st.dataframe(constraints[shown].rename(columns=constraint_columns), hide_index=True, width="stretch")


def _exports() -> None:
    if st.button("Подготовить выгрузки", type="primary"):
        try:
            with st.spinner("Формируются таблицы обычного, стрессового и пользовательского расчётов…"):
                st.session_state.export_files = runtime.csv_files(
                    st.session_state.calculated_plan,
                    st.session_state.get("source_overrides", {}),
                    st.session_state.get("custom_scenario"),
                )
        except Exception as exc:
            render_error(exc, "Выгрузки не подготовлены")
    files = st.session_state.get("export_files")
    if files:
        for name, payload in files.items():
            media_type = "application/json" if name.endswith(".json") else "text/csv"
            st.download_button(
                f"Скачать {name}",
                payload,
                name.replace("/", "-"),
                media_type,
                width="stretch",
            )
    if st.button("Подготовить полный ZIP", type="primary"):
        try:
            with st.spinner("Собираются план, результаты и риски…"):
                st.session_state.bundle = runtime.bundle(
                    st.session_state.calculated_plan,
                    st.session_state.get("source_overrides", {}),
                )
        except Exception as exc:
            render_error(exc, "ZIP не подготовлен")
    if st.session_state.get("bundle"):
        st.download_button(
            "Скачать воспроизводимый ZIP",
            st.session_state.bundle,
            f"{st.session_state.calculated_plan['plan_id']}-bundle.zip",
            "application/zip",
            width="stretch",
        )
    with st.expander("Технический JSON последнего расчёта"):
        st.code(
            json.dumps(st.session_state.result, ensure_ascii=False, indent=2),
            language="json",
        )


def render() -> None:
    st.title("Данные и экспорт")
    tabs = st.tabs(["Планы", "Исходные данные", "Результаты и ZIP"])
    with tabs[0]:
        _plans()
    with tabs[1]:
        _case_data()
    with tabs[2]:
        _exports()
