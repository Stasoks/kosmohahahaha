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
            cols = st.columns(2)
            max_candidates = cols[0].number_input("Число вариантов", 40, 3000, 260, 20)
            iterations = cols[1].number_input("Число итераций", 0, 12, 4, 1)
            beam_width = cols[0].number_input("Ширина поиска", 2, 50, 10, 1)
            seed = cols[1].number_input("Начальное число", 0, 100000, 17, 1)
        if st.button("Подобрать вариант", type="primary", width="stretch"):
            try:
                with st.spinner("Идёт поиск подходящего варианта…"):
                    built = runtime.builder(
                        int(max_candidates),
                        int(beam_width),
                        int(iterations),
                        int(seed),
                        st.session_state.get("source_overrides", {}),
                    )
                st.session_state.builder_result = built
                if built["solutions"]:
                    st.session_state.stress_plan = built["solutions"][0]["plan"]
                    st.session_state.abc_result = None
                    st.success("Вариант C построен и выбран для сравнения. Текущий план не изменён.")
                else:
                    st.warning("Подходящий вариант не найден в заданных пределах поиска.")
            except Exception as exc:
                render_error(exc, "Поиск не завершён")
        if st.button("Вернуть исходный вариант C", width="stretch"):
            st.session_state.stress_plan = stress_reference_raw()
            st.session_state.abc_result = None

    try:
        calculated_plan = st.session_state.calculated_plan
        abc_payload = runtime.abc(
            calculated_plan,
            st.session_state.stress_plan,
            st.session_state.get("source_overrides", {}),
        )
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
            "case": "Вариант", "label": "План и условия", "valid": "Исполним",
            "minimum_annual_total_service": "Мин. годовой сервис",
            "minimum_annual_critical_service": "Мин. критический сервис",
            "total_shortage_t": "Дефицит, т", "critical_shortage_t": "Крит. дефицит, т",
            "undiscounted_cost_mln": "Полная стоимость, млн", "discounted_cost_mln": "Приведённая стоимость, млн",
            "total_capex_mln": "Инвестиции, млн", "minimum_reserve_days": "Мин. резерв, дней",
            "source_mix_t": "Поставки по источникам, т",
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

    st.subheader("Кто несёт последствия стресса")
    st.caption(
        "Критический спрос входит в общий. Поэтому коммерческий дефицит здесь "
        "рассчитывается как общий дефицит минус критический дефицит."
    )
    annual_impacts = annual_stress_impact_rows(abc_payload)
    impact_frame = pd.DataFrame(annual_impacts)
    if not impact_frame.empty:
        stress_years = [
            int(year)
            for year in impact_frame["year"].tolist()
            if int(year) >= 2038
        ]
        selected_year = st.selectbox(
            "Год для распределения последствий",
            stress_years or impact_frame["year"].tolist(),
            index=0,
            key="stakeholder-stress-year",
        )
        selected_impact = next(
            row for row in annual_impacts if int(row["year"]) == int(selected_year)
        )
        cols = st.columns(4)
        cols[0].metric(
            "Коммерческий дефицит",
            mass(selected_impact["stress_commercial_shortage_t"]),
            delta=signed(
                selected_impact["stress_commercial_shortage_t"]
                - selected_impact["base_commercial_shortage_t"],
                "т",
            ),
        )
        cols[1].metric(
            "Критический дефицит",
            mass(selected_impact["stress_critical_shortage_t"]),
            delta=signed(
                selected_impact["stress_critical_shortage_t"]
                - selected_impact["base_critical_shortage_t"],
                "т",
            ),
        )
        cols[2].metric(
            "Расходы оператора",
            money(selected_impact["stress_cost_mln"]),
            delta=signed(selected_impact["stress_cost_delta_mln"], "млн у.е."),
        )
        cols[3].metric(
            "После адаптации: общий дефицит",
            mass(selected_impact["adapted_shortage_t"]),
            delta=signed(
                selected_impact["adapted_shortage_t"]
                - selected_impact["stress_shortage_t"],
                "т",
            ),
        )

        annual_display = impact_frame[
            [
                "year",
                "base_total_demand_t",
                "stress_total_demand_t",
                "stress_commercial_shortage_t",
                "stress_critical_shortage_t",
                "stress_cost_delta_mln",
                "adapted_commercial_shortage_t",
                "adapted_critical_shortage_t",
                "adaptation_cost_delta_mln",
            ]
        ].rename(
            columns={
                "year": "Год",
                "base_total_demand_t": "Спрос BASE, т",
                "stress_total_demand_t": "Спрос STRESS, т",
                "stress_commercial_shortage_t": "Коммерческий дефицит STRESS, т",
                "stress_critical_shortage_t": "Критический дефицит STRESS, т",
                "stress_cost_delta_mln": "Δ стоимости STRESS − BASE, млн",
                "adapted_commercial_shortage_t": "Коммерческий дефицит после адаптации, т",
                "adapted_critical_shortage_t": "Критический дефицит после адаптации, т",
                "adaptation_cost_delta_mln": "Δ стоимости адаптации, млн",
            }
        )
        st.dataframe(annual_display, hide_index=True, width="stretch")

        st.info(
            f"{selected_year}: коммерческий спрос недообслужен на "
            f"{selected_impact['stress_commercial_shortage_t']:.2f} т, "
            f"критический — на {selected_impact['stress_critical_shortage_t']:.2f} т. "
            f"Расчётные расходы оператора относительно BASE изменились на "
            f"{selected_impact['stress_cost_delta_mln']:+.2f} млн у.е. "
            "Денежная стоимость ущерба от необслуженного спроса не рассчитывается: "
            "такого входного параметра в кейсе нет."
        )
        st.warning(
            "Для обязательного стресса недопоставка Lunar-ISRU не создаёт "
            "автоматический возврат платежей. Контур сохраняет рассчитанные "
            "контрактные расходы; отдельные компенсации допустимы только как "
            "явный исследовательский договорный сценарий."
        )

    st.subheader("Интересы, обязательства и распределение риска")
    stakeholders = pd.DataFrame(
        stakeholder_detail_rows(stakeholder_data(), abc_payload)
    )
    if not stakeholders.empty:
        stakeholder_names = {
            "Orbital fuel-node operator": "Оператор топливного узла",
            "Critical consumers": "Критические потребители",
            "Commercial consumers": "Коммерческие потребители",
            "Fuel suppliers": "Поставщики топлива",
            "Launch and logistics suppliers": "Пусковые и логистические подрядчики",
            "Financing and investor side": "Финансирующая сторона / инвесторы",
        }
        stakeholders["Сторона"] = stakeholders["Сторона"].map(
            lambda value: stakeholder_names.get(value, value)
        )
        st.dataframe(stakeholders, hide_index=True, width="stretch")
        st.caption(
            "Столбцы «Кто несёт затраты» и «Какой риск несёт» взяты из явной "
            "карты сторон. Они не превращают недопоставку в выдуманный денежный ущерб."
        )

    if "CUSTOM" in st.session_state.result:
        st.subheader("Текущий план в пользовательском сценарии")
        custom = st.session_state.result["CUSTOM"]
        custom_name = st.session_state.result.get("custom_scenario", {}).get("name", "Пользовательский сценарий")
        base_key = st.session_state.result.get("custom_scenario", {}).get("base_scenario", "BASE")
        baseline = st.session_state.result[base_key]
        from app.view_models import minimum_annual_metrics
        before = minimum_annual_metrics(baseline)
        after = minimum_annual_metrics(custom)
        cols = st.columns(4)
        cols[0].metric("Сценарий", custom_name)
        cols[1].metric("Мин. сервис", f"{after['minimum_annual_total_service']:.1%}")
        cols[2].metric("Дефицит", f"{after['total_shortage_t']:.2f} т")
        cols[3].metric("Стоимость", f"{after['undiscounted_cost_mln']:.1f} млн")
        st.caption(
            f"Относительно основы: Δ сервиса {(after['minimum_annual_total_service']-before['minimum_annual_total_service'])*100:+.2f} п.п. · "
            f"Δ дефицита {after['total_shortage_t']-before['total_shortage_t']:+.2f} т · "
            f"Δ стоимости {after['undiscounted_cost_mln']-before['undiscounted_cost_mln']:+.1f} млн."
        )

    chart_rows = copy.deepcopy(view["rows"])
    for item in chart_rows:
        item["service_pct"] = 100 * item["minimum_annual_total_service"]
    columns = st.columns(3)
    with columns[0]:
        render_chart(charts.abc_metric(chart_rows, "service_pct", "Мин. годовой сервис", "%"))
    with columns[1]:
        render_chart(charts.abc_metric(chart_rows, "total_shortage_t", "Дефицит", "т"))
    with columns[2]:
        render_chart(charts.abc_metric(chart_rows, "undiscounted_cost_mln", "Полная стоимость", "млн у.е."))

    st.subheader("Что изменилось в решениях")
    if abc_payload.get("stress_plan"):
        diff = decision_diff(abc_payload["base_plan"], abc_payload["stress_plan"])
        st.dataframe(pd.DataFrame(diff), hide_index=True, width="stretch")
        with st.expander("Версии сравниваемых планов"):
            st.caption(
                f"A/B: {plan_hash(abc_payload['base_plan'])} · C: {plan_hash(abc_payload['stress_plan'])}"
            )
    else:
        st.info("Адаптированный план пока не выбран.")

    st.subheader("Сравнение общих альтернатив")
    try:
        alternatives = runtime.alternatives(
            calculated_plan,
            st.session_state.get("source_overrides", {}),
        )
        render_chart(charts.alternatives(alternatives["plans"]))
        alt = pd.DataFrame(alternatives["plans"])
        st.dataframe(
            alt[[
                "plan_id", "base_valid", "base_cost_mln", "stress_service",
                "stress_shortage_t", "base_capex_mln", "base_minimum_inventory_t", "source_mix_t",
            ]].rename(columns={
                "plan_id": "План",
                "base_valid": "Исполним в обычных условиях",
                "base_cost_mln": "Стоимость, млн",
                "stress_service": "Сервис в стрессе",
                "stress_shortage_t": "Дефицит в стрессе, т",
                "base_capex_mln": "Инвестиции, млн",
                "base_minimum_inventory_t": "Минимальный запас, т",
                "source_mix_t": "Поставки по источникам, т",
            }),
            hide_index=True,
            width="stretch",
        )
        st.caption("Выбор зависит от компромисса между стоимостью и устойчивостью.")
    except Exception as exc:
        render_error(exc, "Не удалось сравнить альтернативы")