"""Operator dashboard for the Fuel Space Loop 2035 digital twin."""
from __future__ import annotations

import streamlit as st

from app import runtime
from app.components import inject_styles, render_error
from app.kernel_bridge import plan_bytes, plan_hash, plan_preset_key, plan_preset_raw, plan_presets
from app.pages import conditions, export, overview, research, results, risks, scenarios, strategy
from app.state import accept_calculation, apply_plan, initialize, is_dirty, save_snapshot


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
        with st.spinner("Пересчитываются выбранные условия…"):
            result = runtime.evaluate(
                st.session_state.plan,
                st.session_state.get("source_overrides", {}),
                st.session_state.get("custom_scenario"),
            )
        accept_calculation(result)
        st.toast("Оба сценария пересчитаны", icon="✅")
    except Exception as exc:
        render_error(exc, "Не удалось рассчитать план")


PAGES = {
    "Обзор": overview.render,
    "Исходные условия": conditions.render,
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

    presets = plan_presets()
    preset_by_key = {item["key"]: item for item in presets}
    current_preset = plan_preset_key(st.session_state.plan)
    selector_keys = [item["key"] for item in presets]
    if current_preset is None:
        selector_keys = ["__current__"] + selector_keys

    selected_strategy = st.selectbox(
        "Стратегия",
        selector_keys,
        index=selector_keys.index(current_preset) if current_preset in selector_keys else 0,
        format_func=lambda key: (
            "Текущий пользовательский план"
            if key == "__current__"
            else preset_by_key[key]["label"]
        ),
    )
    if selected_strategy == "__current__":
        st.caption("План был изменён вручную и сейчас не совпадает с сохранёнными вариантами.")
    else:
        st.caption(preset_by_key[selected_strategy]["description"])

    if st.button(
        "Выбрать и пересчитать",
        type="secondary",
        width="stretch",
        disabled=selected_strategy == "__current__",
    ):
        try:
            apply_plan(plan_preset_raw(selected_strategy))
            recalculate()
            st.toast(f"Выбрано: {preset_by_key[selected_strategy]['label']}", icon="✅")
            st.rerun()
        except Exception as exc:
            render_error(exc, "Не удалось переключить стратегию")

    current_hash = plan_hash(st.session_state.plan)
    calculated_hash = st.session_state.result["plan_hash"]
    base_summary = st.session_state.result["BASE"]["summary"]
    current_label = (
        preset_by_key[current_preset]["label"]
        if current_preset in preset_by_key
        else "Пользовательский план"
    )
    st.markdown(f"**Текущая стратегия:** {current_label}")
    if st.session_state.get("source_overrides"):
        st.caption(f"Изменены характеристики источников: {len(st.session_state.source_overrides)}")
    if st.session_state.get("custom_scenario"):
        st.caption(f"Свой сценарий: {st.session_state.custom_scenario.get('name', 'Пользовательский')}")
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
        st.rerun()
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
    with st.expander("Технические сведения"):
        st.caption(f"ID плана: {st.session_state.plan.get('plan_id', '—')}")
        st.caption(f"Текущая версия: {current_hash}  \nРассчитанная версия: {calculated_hash}")


PAGES[page]()

st.markdown(
    '<div class="footer">КОСМОКОНТУР · исходные данные, решения команды и расчётные предположения разделены · '
    'физические и экономические результаты получены единым расчётным ядром</div>',
    unsafe_allow_html=True,
)
