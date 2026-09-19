from __future__ import annotations

import copy
import json

import pandas as pd
import streamlit as st

from app import runtime
from app.components import badges, note, render_error
from app.kernel_bridge import case_tables, plan_bytes, plan_from_bytes
from app.state import apply_plan, save_snapshot


def _plans() -> None:
    note("Основной portable workflow — download/upload JSON. Session snapshots исчезнут вместе с сессией Streamlit.")
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
    st.subheader("Снимки текущей browser-сессии")
    cols = st.columns(2)
    if cols[0].button("Сохранить session snapshot", width="stretch"):
        st.toast(f"Сохранено: {save_snapshot()}", icon="✅")
    snapshots = st.session_state.snapshots
    if snapshots:
        selected = cols[1].selectbox("Снимок", list(snapshots))
        if st.button("Открыть snapshot"):
            apply_plan(copy.deepcopy(snapshots[selected]))
            st.rerun()
    else:
        cols[1].info("Снимков нет")


def _case_data() -> None:
    badges(("CASE_INPUT · ТОЛЬКО ЧТЕНИЕ", "case"))
    tables = case_tables()
    st.subheader("Спрос")
    st.dataframe(pd.DataFrame(tables["demand"]), hide_index=True, width="stretch")
    st.subheader("Источники")
    st.dataframe(pd.DataFrame(tables["sources"]), hide_index=True, width="stretch")
    st.subheader("Ограничения")
    st.dataframe(pd.DataFrame(tables["constraints"]), hide_index=True, width="stretch")


def _exports() -> None:
    note(
        "Выгрузки создаются backend exporters из того же SimulationResult: scenario_id, plan_id, периоды, единицы и provenance не пересчитываются во frontend."
    )
    if st.button("Подготовить CSV-файлы", type="primary"):
        try:
            with st.spinner("Формируются BASE, STRESS и comparison CSV…"):
                st.session_state.export_files = runtime.csv_files(st.session_state.calculated_plan)
        except Exception as exc:
            render_error(exc, "CSV не подготовлены")
    files = st.session_state.get("export_files")
    if files:
        for name, payload in files.items():
            st.download_button(
                f"Скачать {name}", payload, name.replace("/", "-"), "text/csv", width="stretch"
            )
    if st.button("Подготовить полный ZIP", type="primary"):
        try:
            with st.spinner("План, обе среды, comparison и risk portfolio…"):
                st.session_state.bundle = runtime.bundle(st.session_state.calculated_plan)
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
    tabs = st.tabs(["Планы", "CASE_INPUT", "Результаты и ZIP"])
    with tabs[0]:
        _plans()
    with tabs[1]:
        _case_data()
    with tabs[2]:
        _exports()
