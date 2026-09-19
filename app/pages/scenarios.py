from __future__ import annotations

import copy

import pandas as pd
import streamlit as st

from app import charts, runtime
from app.components import badges, note, render_chart, render_error
from app.formatting import mass, money, percentage_points, signed
from app.kernel_bridge import plan_hash, stress_reference_raw
from app.state import is_dirty
from app.view_models import abc_comparison, decision_diff


def _delta_cards(value: dict | None) -> None:
    if not value:
        return
    st.markdown(f"**{value['label']}**")
    columns = st.columns(5)
    columns[0].metric("Мин. сервис", percentage_points(value["total_service_pp"]))
    columns[1].metric("Мин. критический", percentage_points(value["critical_service_pp"]))
    columns[2].metric("Дефицит", signed(value["shortage_t"], "т"))
    columns[3].metric("Критич. дефицит", signed(value["critical_shortage_t"], "т"))
    columns[4].metric("Стоимость", signed(value["cost_mln"], "млн у.е."))


def render() -> None:
    st.title("Сценарная лаборатория")
    badges(("A/B · DIGITAL_TWIN_RESULT", "result"), ("C · TEAM_DECISION", "team"), ("97/99 · RESILIENCE_BENCHMARK", "benchmark"))
    note(
        "A — текущий рассчитанный BASE-план в BASE. B — точно тот же план без изменения решений в MANDATORY_STRESS. "
        "C — отдельная ex-ante scenario-specific альтернатива для известного стресса, а не мгновенное переключение после события."
    )
    if is_dirty():
        st.warning("Есть несчитанные изменения. A/B ниже относятся к последнему подтверждённому plan_hash, а не к форме редактора.")

    with st.expander("Построить новый stress-specific вариант"):
        st.caption("Strategy Builder — bounded deterministic heuristic. Результат не является доказанным global optimum.")
        cols = st.columns(4)
        max_candidates = cols[0].number_input("Кандидаты", 40, 3000, 260, 20)
        beam_width = cols[1].number_input("Beam width", 2, 50, 10, 1)
        iterations = cols[2].number_input("Итерации", 0, 12, 4, 1)
        seed = cols[3].number_input("Seed", 0, 100000, 17, 1)
        if st.button("Построить stress-specific вариант", type="primary", width="stretch"):
            try:
                with st.spinner("Builder исследует ограниченное пространство кандидатов…"):
                    built = runtime.builder(int(max_candidates), int(beam_width), int(iterations), int(seed))
                st.session_state.builder_result = built
                if built["solutions"]:
                    st.session_state.stress_plan = built["solutions"][0]["plan"]
                    st.session_state.abc_result = None
                    st.success("Новый кандидат C построен и выбран для сравнения. Текущий BASE-план не изменён.")
                else:
                    st.warning(f"Builder: {built['status']} · {built.get('failure_reason', '')}")
            except Exception as exc:
                render_error(exc, "Builder не завершил поиск")
        if st.session_state.get("builder_result"):
            data = st.session_state.builder_result
            st.caption(
                f"Статус: {data['status']} · рассчитано кандидатов: {data['evaluated_candidate_count']} · "
                f"итераций: {data['iterations']} · global_optimum_claimed=false"
            )
        if st.button("Вернуть финальный reference C", width="stretch"):
            st.session_state.stress_plan = stress_reference_raw()
            st.session_state.abc_result = None

    try:
        calculated_plan = st.session_state.calculated_plan
        abc_payload = runtime.abc(calculated_plan, st.session_state.stress_plan)
        st.session_state.abc_result = abc_payload
    except Exception as exc:
        render_error(exc, "Не удалось собрать A/B/C")
        return
    view = abc_comparison(abc_payload)
    rows = pd.DataFrame(view["rows"])
    display = rows[
        [
            "case", "label", "valid", "minimum_annual_total_service",
            "minimum_annual_critical_service", "total_shortage_t", "critical_shortage_t",
            "undiscounted_cost_mln", "discounted_cost_mln", "total_capex_mln",
            "minimum_reserve_days", "source_mix_t",
        ]
    ].rename(
        columns={
            "case": "Кейс", "label": "План / среда", "valid": "Valid",
            "minimum_annual_total_service": "Мин. годовой сервис",
            "minimum_annual_critical_service": "Мин. критический сервис",
            "total_shortage_t": "Дефицит, т", "critical_shortage_t": "Крит. дефицит, т",
            "undiscounted_cost_mln": "Lifecycle cost, млн", "discounted_cost_mln": "PV, млн",
            "total_capex_mln": "CAPEX, млн", "minimum_reserve_days": "Мин. резерв, дней",
            "source_mix_t": "Source mix, т",
        }
    )
    st.dataframe(
        display,
        hide_index=True,
        width="stretch",
        column_config={
            "Мин. годовой сервис": st.column_config.NumberColumn(format="percent"),
            "Мин. критический сервис": st.column_config.NumberColumn(format="percent"),
        },
    )
    _delta_cards(view["stress_effect"])
    _delta_cards(view["adaptation_effect"])

    chart_rows = copy.deepcopy(view["rows"])
    for item in chart_rows:
        item["service_pct"] = 100 * item["minimum_annual_total_service"]
    columns = st.columns(3)
    with columns[0]:
        render_chart(charts.abc_metric(chart_rows, "service_pct", "Мин. годовой сервис", "%"))
    with columns[1]:
        render_chart(charts.abc_metric(chart_rows, "total_shortage_t", "Дефицит", "т"))
    with columns[2]:
        render_chart(charts.abc_metric(chart_rows, "undiscounted_cost_mln", "Lifecycle cost", "млн у.е."))

    st.subheader("Что изменилось в решениях")
    if abc_payload.get("stress_plan"):
        diff = decision_diff(abc_payload["base_plan"], abc_payload["stress_plan"])
        st.dataframe(pd.DataFrame(diff), hide_index=True, width="stretch")
        st.caption(
            f"A/B plan_hash: {plan_hash(abc_payload['base_plan'])} · C plan_hash: {plan_hash(abc_payload['stress_plan'])}"
        )
    else:
        st.info("Stress-specific план пока не выбран.")

    st.subheader("Сравнение общих альтернатив")
    try:
        alternatives = runtime.alternatives(calculated_plan)
        render_chart(charts.alternatives(alternatives["plans"]))
        alt = pd.DataFrame(alternatives["plans"])
        st.dataframe(
            alt[[
                "plan_id", "base_valid", "base_cost_mln", "stress_service",
                "stress_shortage_t", "base_capex_mln", "base_minimum_inventory_t", "source_mix_t",
            ]],
            hide_index=True,
            width="stretch",
        )
        st.caption("Выбор зависит от компромисса стоимость / устойчивость. Интерфейс не назначает winner автоматически.")
    except Exception as exc:
        render_error(exc, "Не удалось сравнить альтернативы")
