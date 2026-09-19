from __future__ import annotations

import json

import pandas as pd
import plotly.express as px
import streamlit as st

from app import charts, runtime
from app.components import badges, note, render_chart, render_error
from app.kernel_bridge import risk_catalog, stakeholder_data
from app.state import analysis_is_stale, is_dirty
from app.view_models import abc_comparison, minimum_annual_metrics, stakeholder_scenario_rows


def _stale(value: dict | None) -> None:
    if analysis_is_stale(value):
        st.warning("Результат рассчитан для другого plan_hash и устарел после изменения плана.")


def _risk_tab() -> None:
    badges(("TEAM_ASSUMPTION", "team"), ("IMPACT · DIGITAL_TWIN_RESULT", "result"))
    st.caption("UNKNOWN никогда не превращается в выдуманную вероятность и не попадает в матрицу 5×5.")
    if st.button("Рассчитать портфель рисков", type="primary"):
        try:
            with st.spinner("Каждый риск рассчитывается отдельным прогоном цифрового двойника…"):
                st.session_state.risk_result = runtime.risks(st.session_state.calculated_plan)
        except Exception as exc:
            render_error(exc, "Не удалось рассчитать портфель")
    data = st.session_state.get("risk_result")
    _stale(data)
    if not data:
        st.info("Запустите портфель явно. Открытие страницы не запускает тяжёлые расчёты.")
        return
    register = pd.DataFrame(data["risk_register"])
    columns = st.columns(3)
    columns[0].metric("Рисков", len(register))
    columns[1].metric("С likelihood score", int(register.likelihood_score.notna().sum()))
    columns[2].metric("UNKNOWN", len(data["unknown_likelihood_risks"]))
    known = register.dropna(subset=["likelihood_score"])
    if not known.empty:
        fig = px.scatter(
            known,
            x="likelihood_score",
            y="impact_score",
            size="impact_score",
            color="ordinal_risk_score",
            hover_name="name",
            text="risk_id",
            range_x=[0.5, 5.5],
            range_y=[0.5, 5.5],
            color_continuous_scale=[[0, "#DCC5F1"], [1, "#5B4BFF"]],
            title="Матрица только для обоснованных likelihood score",
        )
        render_chart(charts.style(fig, 420))
    columns = [
        "risk_id", "name", "event", "cause", "period_start", "period_end", "owner",
        "likelihood_status", "likelihood_score", "impact_score", "affected_parameters",
    ]
    st.dataframe(register[columns], hide_index=True, width="stretch")

    selected = st.selectbox(
        "Детальный риск",
        register.risk_id.tolist(),
        index=register.risk_id.tolist().index("R-CORE-OUTAGE") if "R-CORE-OUTAGE" in register.risk_id.tolist() else 0,
        format_func=lambda risk_id: f"{risk_id} · {register.loc[register.risk_id == risk_id, 'name'].iloc[0]}",
    )
    selected_row = next(item for item in data["risk_register"] if item["risk_id"] == selected)
    st.subheader("Причинная цепочка")
    st.code(
        f"{selected_row['event']}\n→ {', '.join(selected_row['affected_parameters'])}\n→ physical / economic effect\n→ violations",
        language=None,
    )
    if st.button("Рассчитать выбранный риск", width="stretch"):
        try:
            with st.spinner("Рассчитывается baseline и risk override…"):
                st.session_state.risk_detail = runtime.risk_detail(st.session_state.calculated_plan, selected)
        except Exception as exc:
            render_error(exc, "Не удалось рассчитать риск")
    detail = st.session_state.get("risk_detail")
    if detail and detail.get("risk", {}).get("risk_id") == selected:
        _stale(detail)
        before = minimum_annual_metrics(detail["baseline"])
        after = minimum_annual_metrics(detail["risk_result"])
        metrics = [
            ("Стоимость, млн", "undiscounted_cost_mln"),
            ("Мин. годовой сервис", "minimum_annual_total_service"),
            ("Мин. критический сервис", "minimum_annual_critical_service"),
            ("Дефицит, т", "total_shortage_t"),
            ("Критический дефицит, т", "critical_shortage_t"),
            ("Hard violations", "hard_violation_count"),
        ]
        table = [
            {"Показатель": label, "До риска": before[key], "В риске": after[key], "Δ": after[key] - before[key]}
            for label, key in metrics
        ]
        st.dataframe(pd.DataFrame(table), hide_index=True, width="stretch")
        st.write("**Применённые overrides**")
        st.dataframe(pd.DataFrame(detail["applied_overrides"]), hide_index=True, width="stretch")

    definition = next(item for item in risk_catalog() if item["risk_id"] == selected)
    mitigation = definition.get("mitigation") or {}
    st.subheader("Мера и остаточный риск")
    st.write(mitigation.get("description", "Мера не задана."))
    if mitigation.get("plan_patch") or mitigation.get("plan_reference"):
        if st.button("Рассчитать меру", type="primary"):
            try:
                with st.spinner("Мера проверяется и пересчитывается в том же risk environment…"):
                    st.session_state.mitigation_result = runtime.mitigation(st.session_state.calculated_plan, selected)
            except Exception as exc:
                render_error(exc, "Не удалось рассчитать меру")
        value = st.session_state.get("mitigation_result")
        if value and value.get("risk_id") == selected:
            _stale(value)
            original = value["original_risk_metrics"]
            residual = value["residual_consequence"]["risk"]
            cols = st.columns(4)
            cols[0].metric("Стоимость меры", f"{value['mitigation_cost_mln']:.1f} млн у.е.")
            cols[1].metric("Дефицит до", f"{original['total_shortage_t']:.2f} т")
            cols[2].metric("Дефицит после", f"{residual['total_shortage_t']:.2f} т")
            cols[3].metric("Residual impact", value["residual_impact"]["impact_score"])
            st.dataframe(
                pd.DataFrame(value["risk_result"].get("violations", [])), hide_index=True, width="stretch"
            )
    else:
        st.info("Мера описана качественно, количественный rerun не задан.")


def _sensitivity_tab() -> None:
    badges(("CASE_INPUT · LOW/BASE/HIGH", "case"), ("CUSTOM · TEAM_ASSUMPTION", "team"))
    note("Sensitivity меняет один явно указанный параметр и не переписывает TEAM_DECISION.")
    if st.button("Запустить официальный LOW / BASE / HIGH", type="primary"):
        try:
            with st.spinner("Три официальные точки спроса…"):
                st.session_state.sensitivity_result = runtime.official_sensitivity(st.session_state.calculated_plan)
        except Exception as exc:
            render_error(exc, "Не удалось выполнить официальный sweep")
    preset = st.selectbox(
        "Дополнительный preset",
        ["Demand multiplier", "Earth-Flex lead-time delay", "ZBO storage-loss multiplier", "Advanced custom"],
    )
    parameter: str | dict = "demand_multiplier"
    default_values = "0.90, 1.00, 1.05, 1.10, 1.20"
    meaning = "Множитель общего спроса"
    unit = "×"
    if preset == "Earth-Flex lead-time delay":
        parameter = {"name": "earth_flex_lead_time_delay_months", "factor": "additional_lead_time_months", "source_id": "B", "status": "TEAM_ASSUMPTION"}
        default_values, meaning, unit = "0, 1, 2, 3, 4", "Дополнительная задержка Earth-Flex", "месяцев"
    elif preset == "ZBO storage-loss multiplier":
        parameter = {"name": "zbo_loss_multiplier", "factor": "storage_loss_rate_multiplier", "storage_id": "ZBO", "status": "TEAM_ASSUMPTION"}
        default_values, meaning, unit = "1.0, 1.25, 1.5, 2.0", "Множитель активных потерь ZBO", "×"
    elif preset == "Advanced custom":
        cols = st.columns(3)
        name = cols[0].text_input("Parameter name", "custom_parameter")
        factor = cols[1].selectbox("Backend factor", ["total_demand_multiplier", "critical_demand_multiplier", "variable_price_multiplier", "availability_share", "additional_lead_time_months", "source_capacity_multiplier", "storage_loss_rate_multiplier", "storage_capacity_multiplier"])
        target_id = cols[2].text_input("source/storage target_id", "A")
        parameter = {"name": name, "factor": factor, "status": "TEAM_ASSUMPTION"}
        if factor in {"variable_price_multiplier", "availability_share", "additional_lead_time_months", "source_capacity_multiplier"}:
            parameter["source_id"] = target_id
        elif factor in {"storage_loss_rate_multiplier", "storage_capacity_multiplier"}:
            parameter["storage_id"] = target_id
        meaning, unit = "Пользовательский one-factor override", "см. factor"
    values_text = st.text_input("Значения через запятую", default_values)
    st.caption(f"Смысл: {meaning} · единица: {unit} · статус: {'CASE_INPUT' if preset.startswith('Official') else 'TEAM_ASSUMPTION'} · range basis: явный ввод оператора")
    if st.button("Запустить выбранный sweep"):
        try:
            values = [float(item.strip()) for item in values_text.split(",") if item.strip()]
            with st.spinner("Рассчитываются точки чувствительности…"):
                st.session_state.sensitivity_result = runtime.sensitivity(st.session_state.calculated_plan, parameter, values)
        except Exception as exc:
            render_error(exc, "Не удалось выполнить sensitivity")
    result = st.session_state.get("sensitivity_result")
    _stale(result)
    if result:
        points = result["points"]
        left, right = charts.sensitivity_lines(points, str(result["parameter"].get("name", "parameter")))
        render_chart(left)
        render_chart(right)
        frame = pd.DataFrame(points)
        columns = ["value", "valid", "total_service_level", "critical_service_level", "total_shortage_t", "total_cost_mln", "minimum_inventory_t", "hard_violation_count"]
        st.dataframe(frame[columns], hide_index=True, width="stretch")
        if result.get("first_failing_point"):
            st.warning(f"Первая failing-точка в порядке sweep: {result['first_failing_point']['value']}")


def _reverse_tab() -> None:
    note("Reverse stress — детерминированная сетка, а не непрерывное математическое доказательство порога.")
    preset = st.selectbox("Параметр reverse stress", ["Demand multiplier", "Earth-Flex lead-time delay"])
    if preset == "Demand multiplier":
        parameter: str | dict = "demand_multiplier"
        defaults = (1.0, 1.5, 0.01)
    else:
        parameter = {"name": "earth_flex_lead_time_delay_months", "factor": "additional_lead_time_months", "source_id": "B", "status": "TEAM_ASSUMPTION"}
        defaults = (0.0, 12.0, 1.0)
    cols = st.columns(3)
    start = cols[0].number_input("Начало", value=defaults[0])
    stop = cols[1].number_input("Конец", value=defaults[1])
    step = cols[2].number_input("Шаг", min_value=0.001, value=defaults[2])
    if st.button("Найти первый отказ", type="primary"):
        try:
            with st.spinner("Проверяется упорядоченная сетка…"):
                st.session_state.reverse_result = runtime.reverse(st.session_state.calculated_plan, parameter, start, stop, step)
        except Exception as exc:
            render_error(exc, "Reverse stress не выполнен")
    result = st.session_state.get("reverse_result")
    _stale(result)
    if not result:
        return
    cols = st.columns(3)
    cols[0].metric("Последнее безопасное", result.get("last_safe_value", "—"))
    cols[1].metric("Первое неуспешное", result.get("first_failing_value", "—"))
    violation = result.get("first_violated_constraint") or {}
    cols[2].metric("Первое ограничение", violation.get("constraint_id", "не найдено"))
    if violation:
        st.error(
            f"{violation.get('period')} · actual {violation.get('actual')} {violation.get('operator')} limit {violation.get('limit')} · {violation.get('human_message', '')}"
        )
    render_chart(charts.reverse_zone(result))
    with st.expander("Технические данные"):
        st.json(result)


def _stakeholders_tab() -> None:
    config = stakeholder_data()
    badges(("STAKEHOLDERS · TEAM_ASSUMPTION", "team"), ("CONSEQUENCES · DIGITAL_TWIN_RESULT", "result"))
    try:
        abc_payload = st.session_state.get("abc_result") or runtime.abc(
            st.session_state.calculated_plan, st.session_state.stress_plan
        )
        st.session_state.abc_result = abc_payload
        rows = stakeholder_scenario_rows(config, abc_payload)
    except Exception as exc:
        render_error(exc, "Не удалось собрать последствия для сторон")
        return
    for item in config.get("participants", []):
        with st.expander(item["name"]):
            st.write("**Интересы:**", "; ".join(item.get("interests", [])))
            st.write("**KPI:**", "; ".join(item.get("kpis", [])))
            st.write("**Обязательства:**", "; ".join(item.get("obligations", [])))
            st.write("**Несёт затраты:**", "; ".join(item.get("cost_bearer", [])) or "не задано")
            st.write("**Несёт риск:**", "; ".join(item.get("risk_bearer", [])) or "не задано")
    st.subheader("Рассчитанные последствия A/B/C")
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    mitigation = st.session_state.get("mitigation_result")
    if mitigation:
        st.subheader("Выбранный риск и мера · before / after")
        st.dataframe(
            pd.DataFrame(
                [
                    {"Состояние": "Risk before", **mitigation["original_risk_metrics"]},
                    {"Состояние": "Mitigation after", **mitigation["residual_consequence"]["risk"]},
                ]
            ),
            hide_index=True,
            width="stretch",
        )
    st.caption(config.get("disclaimer", ""))


def render() -> None:
    st.title("Риски и чувствительность")
    if is_dirty():
        st.warning("В форме есть несчитанные изменения. Новые анализы запускаются для последнего подтверждённого плана.")
    tabs = st.tabs(["Реестр рисков", "Sensitivity", "Reverse stress", "Стейкхолдеры"])
    with tabs[0]:
        _risk_tab()
    with tabs[1]:
        _sensitivity_tab()
    with tabs[2]:
        _reverse_tab()
    with tabs[3]:
        _stakeholders_tab()
