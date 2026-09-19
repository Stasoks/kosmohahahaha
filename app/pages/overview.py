from __future__ import annotations

import streamlit as st

from app import charts
from app.components import kpi_grid, problems, render_chart, results_status
from app.kernel_bridge import case_metadata, plan_hash
from app.state import is_dirty
from app.view_models import source_names


def render() -> None:
    st.markdown(
        '<div class="hero"><div class="eyebrow">КОСМОХАКАТОН 2026 · ЦЕНТР УПРАВЛЕНИЯ</div>'
        '<h1>Топливный контур.<br><span>Решения в цифрах.</span></h1>'
        '<p>Исполнимость, стоимость и устойчивость стратегии — из одного авторитетного расчётного ядра.</p></div>',
        unsafe_allow_html=True,
    )
    result_pair = st.session_state.result
    scenario_options = ["BASE", "MANDATORY_STRESS"]
    if "CUSTOM" in result_pair:
        scenario_options.append("CUSTOM")
    custom_label = result_pair.get("custom_scenario", {}).get("name", "Пользовательский")
    selected = st.segmented_control(
        "Сценарий",
        scenario_options,
        default="BASE",
        format_func=lambda value: {
            "BASE": "Обычный",
            "MANDATORY_STRESS": "Обязательный стресс",
            "CUSTOM": custom_label,
        }[value],
    ) or "BASE"
    result = result_pair[selected]
    results_status(
        result,
        plan_hash(st.session_state.plan),
        result_pair["plan_hash"],
        dirty_override=is_dirty(),
    )
    metadata = case_metadata(source_overrides=st.session_state.get("source_overrides", {}))
    limits = (
        metadata["constraints"]["CAPEX_2037"]["value"],
        metadata["constraints"]["CAPEX_2040"]["value"],
    )
    kpi_grid(result, limits)
    if (
        selected == "BASE"
        and st.session_state.plan.get("scenario_id") == "MANDATORY_STRESS"
        and not result["summary"].get("valid", False)
    ):
        st.caption(
            "Этот план был подготовлен специально под стрессовый профиль. В обычном сценарии он проверяется без "
            "изменения решений; избыточные поставки могут нарушать ограничения по хранению."
        )
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
    service_basis = selected
    if selected == "CUSTOM":
        service_basis = result_pair.get("custom_scenario", {}).get("base_scenario", "BASE")
    render_chart(charts.service(result, service_basis))
    if service_basis == "MANDATORY_STRESS":
        st.caption(
            "Линии 97% и 99% в стрессовом сценарии — ориентиры устойчивости, а не дополнительные обязательные ограничения."
        )
    if selected == "CUSTOM":
        st.caption(
            "Пользовательский сценарий рассчитан для того же текущего плана. "
            "Изменения сценария накладываются поверх выбранной основы."
        )
    problems(result)
