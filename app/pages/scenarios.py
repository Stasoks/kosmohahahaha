from __future__ import annotations

import copy

import pandas as pd
import streamlit as st

from app import charts, runtime
from app.components import render_chart, render_error
from app.formatting import mass, money, percentage_points, signed
from app.kernel_bridge import plan_hash, stakeholder_data, stress_reference_raw
from app.state import is_dirty
from app.view_models import (\n    abc_comparison,\n    annual_stress_impact_rows,\n    decision_diff,\n    stakeholder_detail_rows,\n)


def _delta_cards(value: dict | None) -> None:
    if not value:
        return
    st.markdown(f"**{value['label']}**")
    columns = st.columns(3)
    columns[0].metric("Мин. сервис", percentage_points(value["total_service_pp"]))
    columns[1].metric("Мин. критический", percentage_points(value["critical_service_pp"]))
    columns[2].metric("Дефицит", signed(value["shortage_t"], "т"))
    columns = st.columns(2)
    columns[0].metric("Критический дефицит", signed(value["critical_shortage_t"], "т"))
    columns[1].metric("Стоимость", signed(value["cost_mln"], "млн у.е."))


def render() -> None:
    st.title("Сценарная лаборатория")
    st.caption(
        "A — текущий план в обычных условиях; B — тот же план в стрессе; "
        "C — заранее адаптированный план в стрессе."
    )
    if is_dirty():
        st.warning("Есть несчитанные изменения. Сравнение относится к последней рассчитанной версии плана.")

    with st.expander("Подобрать адаптированный план"):
        max_candidates, beam_width, iterations, seed = 260, 10, 4, 17
        if st.checkbox("Настроить параметры поиска"):