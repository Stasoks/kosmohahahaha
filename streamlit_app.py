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
        with st.spinner("Расчёт обычного и стрессового сценариев…"):
            result = runtime.evaluate(st.session_state.plan)
        accept_calculation(result)
        st.toast("Оба сценария пересчитаны", icon="✅")
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
        '<div class="brand">космо<b>контур</b><small>УПРАВЛЕНИЕ ТОПЛИВНЫМ КОНТУРОМ</small></div>',
        unsafe_allow_html=True,
    )
    page = st.radio("Рабочее пространство", list(PAGES), label_visibility="collapsed")
    st.divider()
    current_hash = plan_hash(st.session_state.plan)
    calculated_hash = st.session_state.result["plan_hash"]
    base_summary = st.session_state.result["BASE"]["summary"]
    st.markdown(f"**План:** `{st.session_state.plan.get('plan_id', '—')}`")
    if is_dirty():
        st.warning("● Есть несчитанные изменения")
    else:
        st.success("✓ Расчёт актуален")
    st.markdown(
        f"**Обычный сценарий:** {'исполним' if base_summary['valid'] else 'неисполним'}  \n"
        f"Критических нарушений: {base_summary['hard_violation_count']}"
    )
    if st.button("↻ Пересчитать", type="primary", width="stretch"):
        recalculate()
    cols = st.columns(2)
    if cols[0].button("Снимок", width="stretch", help="Сохранить в текущем сеансе"):
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
        cols[1].caption("Сначала проверьте план")
    with st.expander("Версии расчёта"):
        st.caption(f"Текущая: {current_hash}  \nРассчитанная: {calculated_hash}")


PAGES[page]()

st.markdown(
    '<div class="footer">КОСМОКОНТУР · исходные данные, решения команды и расчётные предположения разделены · '
    'физические и экономические результаты получены единым расчётным ядром</div>',
    unsafe_allow_html=True,
)
