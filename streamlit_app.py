"""Operator dashboard for the Fuel Space Loop 2035 digital twin."""
from __future__ import annotations

import streamlit as st

from app import runtime
from app.components import inject_styles, render_error
from app.kernel_bridge import plan_bytes, plan_hash
from app.pages import export, overview, research, results, risks, scenarios, strategy
from app.state import accept_calculation, initialize, is_dirty, save_snapshot


st.set_page_config(
    page_title="Космоконтур 2035",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_styles()

try:
    runtime.context()
    initialize(runtime.evaluate)
except Exception as exc:
    render_error(exc, "Приложение не смогло загрузить официальный case context")
    st.stop()


def recalculate() -> None:
    try:
        with st.spinner("Авторитетное ядро рассчитывает BASE и MANDATORY_STRESS…"):
            result = runtime.evaluate(st.session_state.plan)
        accept_calculation(result)
        st.toast("Оба обязательных сценария пересчитаны", icon="✅")
    except Exception as exc:
        render_error(exc, "Не удалось рассчитать план")


PAGES = {
    "Обзор": overview.render,
    "Стратегия": strategy.render,
    "Результаты": results.render,
    "Сценарии": scenarios.render,
    "Риски и чувствительность": risks.render,
    "Исследования": research.render,
    "Данные и экспорт": export.render,
}


with st.sidebar:
    st.markdown(
        '<div class="brand">космо<b>контур</b><small>ORBITAL FUEL OPERATIONS</small></div>',
        unsafe_allow_html=True,
    )
    page = st.radio("Рабочее пространство", list(PAGES), label_visibility="collapsed")
    st.divider()
    current_hash = plan_hash(st.session_state.plan)
    calculated_hash = st.session_state.result["plan_hash"]
    base_summary = st.session_state.result["BASE"]["summary"]
    st.markdown(f"**План:** `{st.session_state.plan.get('plan_id', '—')}`")
    st.caption(f"Сценарий плана: {st.session_state.plan.get('scenario_id', '—')}")
    if is_dirty():
        st.warning("● Есть несчитанные изменения")
    else:
        st.success("✓ Расчёт актуален")
    st.markdown(
        f"**BASE:** {'VALID' if base_summary['valid'] else 'INVALID'}  \n"
        f"Hard violations: {base_summary['hard_violation_count']}"
    )
    if st.button("↻ Пересчитать", type="primary", width="stretch"):
        recalculate()
    cols = st.columns(2)
    if cols[0].button("Снимок", width="stretch", help="Сохранить только в текущей browser-сессии"):
        st.toast(save_snapshot(), icon="💾")
    try:
        cols[1].download_button(
            "JSON",
            plan_bytes(st.session_state.plan),
            f"{st.session_state.plan.get('plan_id', 'plan')}.json",
            "application/json",
            width="stretch",
        )
    except Exception:
        cols[1].caption("JSON после validation")
    st.caption(f"Current hash: {current_hash}  \nCalculated hash: {calculated_hash}")
    st.markdown("---")
    st.caption(
        "UI не изменяет план автоматически. Builder/Advisor создаёт отдельное явно подтверждаемое предложение."
    )


PAGES[page]()

st.markdown(
    '<div class="footer">КОСМОКОНТУР · CASE_INPUT ≠ TEAM_DECISION ≠ TEAM_ASSUMPTION · '
    'все физические и экономические результаты получены kosmohak.service</div>',
    unsafe_allow_html=True,
)
