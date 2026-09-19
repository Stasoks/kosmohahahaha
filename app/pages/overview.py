from __future__ import annotations

import streamlit as st

from app import charts
from app.components import kpi_grid, problems, render_chart, results_status
from app.kernel_bridge import case_metadata, plan_hash
from app.view_models import source_names


def render() -> None:
    st.markdown(
        '<div class="hero"><div class="eyebrow">КОСМОХАКАТОН 2026 · ЦЕНТР УПРАВЛЕНИЯ</div>'
        '<h1>Топливный контур.<br><span>Решения в цифрах.</span></h1>'
        '<p>Исполнимость, стоимость и устойчивость стратегии — из одного авторитетного расчётного ядра.</p></div>',
        unsafe_allow_html=True,
    )
    result_pair = st.session_state.result
    selected = st.segmented_control(
        "Сценарий",
        ["BASE", "MANDATORY_STRESS"],
        default="BASE",
        format_func=lambda value: "Обычный" if value == "BASE" else "Обязательный стресс",
    ) or "BASE"
    result = result_pair[selected]
    results_status(
        result,
        plan_hash(st.session_state.plan),
        result_pair["plan_hash"],
    )
    metadata = case_metadata()
    limits = (
        metadata["constraints"]["CAPEX_2037"]["value"],
        metadata["constraints"]["CAPEX_2040"]["value"],
    )
    kpi_grid(result, limits)
    left, right = st.columns([1.12, 1])
    with left:
        render_chart(charts.demand_service(result))
    with right:
        render_chart(charts.inventory(result))
    left, right = st.columns(2)
    with left:
        render_chart(charts.supply_mix(result, source_names(metadata)))
    with right:
        render_chart(charts.costs(result))
    render_chart(charts.service(result, selected))
    if selected == "MANDATORY_STRESS":
        st.caption(
            "Линии 97% и 99% в стрессовом сценарии — ориентиры устойчивости, а не дополнительные обязательные ограничения."
        )
    problems(result)
