from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from app import charts, runtime
from app.components import render_chart, render_error
from app.kernel_bridge import risk_catalog, stakeholder_data
from app.state import analysis_is_stale, is_dirty
from app.view_models import minimum_annual_metrics, stakeholder_scenario_rows, violations_view


RISK_TEXT = {
    "R-ISRU-UNDERDELIVERY": ("Недопоставка лунного топлива", "Лунный канал поставляет только 40% доступного объёма", "Незрелость производства и перегрузочных операций"),
    "R-EARTH-PRICE": ("Рост цены земного канала", "Цена Earth-Core растёт на 20%", "Коммерческое изменение цены"),
    "R-CORE-OUTAGE": ("Остановка Earth-Core", "Earth-Core временно недоступен", "Перерыв в работе пускового канала"),
    "R-EARTH-NEW-DELAY": ("Задержка Earth-New", "Ввод Earth-New сдвигается на шесть месяцев", "Задержка интеграции и подготовки"),
    "R-STORAGE-DEGRADATION": ("Деградация хранилища", "Потери активного ZBO возрастают до 2,5%", "Ухудшение состояния оборудования"),
    "R-DEMAND-UPSIDE": ("Рост спроса", "Общий и критический спрос растут на 10%", "Отклонение спроса от базового прогноза"),
    "R-LOGISTICS-DELAY": ("Логистическая задержка", "Срок поставки Earth-Flex увеличивается на три месяца", "Сбой запуска или логистики"),
    "R-CAPEX-OVERRUN": ("Удорожание Lunar-ISRU", "Инвестиции в Lunar-ISRU растут на 25%", "Рост стоимости инвестиционной программы"),
}

PARAMETER_LABELS = {
    "actual_delivery_share": "доля фактической поставки",
    "variable_price_multiplier": "цена поставки",
    "availability_share": "доступность источника",
    "investment_commissioning_delay_months": "задержка ввода",
    "storage_loss_rate_override": "потери при хранении",
    "total_demand_multiplier": "общий спрос",
    "critical_demand_multiplier": "критический спрос",
    "additional_lead_time_months": "срок поставки",
    "capex_multiplier": "инвестиционные затраты",
}

MITIGATION_TEXT = {
    "R-ISRU-UNDERDELIVERY": "Сохранить свободную мощность земных каналов для замещения недопоставки.",
    "R-EARTH-PRICE": "Сравнить более диверсифицированную структуру контрактов.",
    "R-CORE-OUTAGE": "Заранее зарезервировать точечные поставки Earth-Flex на период остановки Earth-Core.",
    "R-EARTH-NEW-DELAY": "Рассмотреть временное увеличение гибких поставок.",
    "R-STORAGE-DEGRADATION": "Рассмотреть дополнительную поставку или перенос обслуживания хранилища.",
    "R-DEMAND-UPSIDE": "Сохранить резерв контрактной мощности; точный объём требует отдельного решения.",
    "R-LOGISTICS-DELAY": "Проверить более раннее размещение заказов.",
    "R-CAPEX-OVERRUN": "Пересмотреть сроки инвестиций после отдельного решения оператора.",
}

STAKEHOLDER_TEXT = {
    "operator": ("Оператор топливного узла", "Непрерывность сервиса, исполнимые контракты, прозрачная стоимость"),
    "critical_consumers": ("Критические потребители", "Приоритетное обслуживание и запас устойчивости на 45 дней"),
    "commercial_consumers": ("Коммерческие потребители", "Предсказуемая доступность топлива"),
    "fuel_suppliers": ("Поставщики топлива", "Загрузка контрактов и достоверное резервирование"),
    "launch_logistics": ("Пусковые и логистические подрядчики", "Стабильный график и видимость мощностей"),
    "financing": ("Инвесторы и финансирующая сторона", "Дисциплина инвестиций и прозрачность стоимости"),
}


def _stale(value: dict | None) -> None:
    if analysis_is_stale(value):
        st.warning("Результат относится к предыдущей версии плана.")


def _risk_tab() -> None:
    if st.button("Рассчитать портфель рисков", type="primary"):
        try:
            with st.spinner("Каждый риск рассчитывается отдельным прогоном цифрового двойника…"):
                st.session_state.risk_result = runtime.risks(
                    st.session_state.calculated_plan,
                    st.session_state.get("source_overrides", {}),
                )
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
    columns[1].metric("С оценкой вероятности", int(register.likelihood_score.notna().sum()))
    columns[2].metric("Без оценки вероятности", len(data["unknown_likelihood_risks"]))
    known = register.dropna(subset=["likelihood_score"])
    if not known.empty:
        known = known.copy()
        known["name"] = known.apply(
            lambda row: RISK_TEXT.get(row["risk_id"], (row["name"],))[0], axis=1
        )
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
            title="Матрица рисков с оценённой вероятностью",
        )
        render_chart(charts.style(fig, 420))
    risk_rows = []
    for item in data["risk_register"]:
        name, event, cause = RISK_TEXT.get(item["risk_id"], (item["name"], item["event"], item["cause"]))
        likelihood = item.get("likelihood_score")
        risk_rows.append({
            "Код": item["risk_id"], "Риск": name, "Событие": event, "Причина": cause,
            "Период": f"{item['period_start']} — {item['period_end']}",
            "Вероятность": f"{float(likelihood):g}" if likelihood is not None else "не оценена",
            "Влияние": item["impact_score"],
        })
    st.dataframe(pd.DataFrame(risk_rows), hide_index=True, width="stretch")

    selected = st.selectbox(
        "Детальный риск",
        register.risk_id.tolist(),
        index=register.risk_id.tolist().index("R-CORE-OUTAGE") if "R-CORE-OUTAGE" in register.risk_id.tolist() else 0,
        format_func=lambda risk_id: f"{risk_id} · {RISK_TEXT.get(risk_id, (risk_id,))[0]}",
    )
    selected_row = next(item for item in data["risk_register"] if item["risk_id"] == selected)
    st.subheader("Причинная цепочка")
    _, event, cause = RISK_TEXT.get(
        selected, (selected_row["name"], selected_row["event"], selected_row["cause"])
    )
    parameters = ", ".join(PARAMETER_LABELS.get(item, item) for item in selected_row["affected_parameters"])
    st.code(f"{cause}\n→ {event}\n→ {parameters}\n→ физические и экономические последствия", language=None)
    if st.button("Рассчитать выбранный риск", width="stretch"):
        try:
            with st.spinner("Рассчитываются исходное состояние и последствия риска…"):
                st.session_state.risk_detail = runtime.risk_detail(
                    st.session_state.calculated_plan,
                    selected,
                    st.session_state.get("source_overrides", {}),
                )
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
            ("Критические нарушения", "hard_violation_count"),
        ]
        table = [
            {"Показатель": label, "До риска": before[key], "В риске": after[key], "Δ": after[key] - before[key]}
            for label, key in metrics
        ]
        st.dataframe(pd.DataFrame(table), hide_index=True, width="stretch")
        with st.expander("Изменённые параметры"):
            override_rows = []
            for item in detail["applied_overrides"]:
                override_rows.append({
                    "Параметр": PARAMETER_LABELS.get(item.get("factor"), item.get("factor")),
                    "Источник": item.get("source_id") or item.get("storage_id") or "—",
                    "Значение": item.get("value"),
                    "Начало": item.get("period_start", "—"),
                    "Конец": item.get("period_end", "—"),
                })
            st.dataframe(pd.DataFrame(override_rows), hide_index=True, width="stretch")

    definition = next(item for item in risk_catalog() if item["risk_id"] == selected)
    mitigation = definition.get("mitigation") or {}
    st.subheader("Мера и остаточный риск")
    st.write(MITIGATION_TEXT.get(selected, mitigation.get("description", "Мера не задана.")))
    if mitigation.get("plan_patch"):
        if st.button("Рассчитать меру", type="primary"):
            try:
                with st.spinner("Мера проверяется в тех же условиях риска…"):
                    st.session_state.mitigation_result = runtime.mitigation(
                        st.session_state.calculated_plan,
                        selected,
                        st.session_state.get("source_overrides", {}),
                    )
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
            cols[3].metric("Остаточное влияние", value["residual_impact"]["impact_score"])
            residual_violations = violations_view(value["risk_result"])
            if residual_violations:
                st.dataframe(pd.DataFrame(residual_violations), hide_index=True, width="stretch")
            else:
                st.success("После меры критических нарушений нет.")
    else:
        st.info("Для этой меры количественный пересчёт не задан.")


def _sensitivity_tab() -> None:
    if st.button("Проверить нижний, базовый и верхний спрос", type="primary"):
        try:
            with st.spinner("Три официальные точки спроса…"):
                st.session_state.sensitivity_result = runtime.official_sensitivity(
                    st.session_state.calculated_plan,
                    st.session_state.get("source_overrides", {}),
                )
        except Exception as exc:
            render_error(exc, "Не удалось выполнить проверку")
    preset = st.selectbox(
        "Дополнительная проверка",
        ["Множитель спроса", "Задержка Earth-Flex", "Потери в ZBO", "Другой параметр"],
    )
    parameter: str | dict = "demand_multiplier"
    default_values = "0.90, 1.00, 1.05, 1.10, 1.20"
    meaning = "Множитель общего спроса"
    unit = "×"
    if preset == "Задержка Earth-Flex":
        parameter = {"name": "earth_flex_lead_time_delay_months", "factor": "additional_lead_time_months", "source_id": "B", "status": "TEAM_ASSUMPTION"}
        default_values, meaning, unit = "0, 1, 2, 3, 4", "Дополнительная задержка Earth-Flex", "месяцев"
    elif preset == "Потери в ZBO":
        parameter = {"name": "zbo_loss_multiplier", "factor": "storage_loss_rate_multiplier", "storage_id": "ZBO", "status": "TEAM_ASSUMPTION"}
        default_values, meaning, unit = "1.0, 1.25, 1.5, 2.0", "Множитель активных потерь ZBO", "×"
    elif preset == "Другой параметр":
        factors = {
            "total_demand_multiplier": "Общий спрос",
            "critical_demand_multiplier": "Критический спрос",
            "variable_price_multiplier": "Цена источника",
            "availability_share": "Доступность источника",
            "additional_lead_time_months": "Задержка поставки",
            "source_capacity_multiplier": "Мощность источника",
            "storage_loss_rate_multiplier": "Потери хранилища",
            "storage_capacity_multiplier": "Ёмкость хранилища",
        }
        cols = st.columns(2)
        name = cols[0].text_input("Название проверки", "Пользовательская проверка")
        factor = cols[1].selectbox("Параметр", list(factors), format_func=factors.get)
        target_id = cols[0].text_input("Код источника или хранилища", "A")
        parameter = {"name": name, "factor": factor, "status": "TEAM_ASSUMPTION"}
        if factor in {"variable_price_multiplier", "availability_share", "additional_lead_time_months", "source_capacity_multiplier"}:
            parameter["source_id"] = target_id
        elif factor in {"storage_loss_rate_multiplier", "storage_capacity_multiplier"}:
            parameter["storage_id"] = target_id
        meaning, unit = "Изменение одного выбранного параметра", "зависит от параметра"
    values_text = st.text_input("Значения через запятую", default_values)
    st.caption(f"{meaning}. Единица: {unit}.")
    if st.button("Запустить проверку"):
        try:
            values = [float(item.strip()) for item in values_text.split(",") if item.strip()]
            with st.spinner("Рассчитываются точки чувствительности…"):
                st.session_state.sensitivity_result = runtime.sensitivity(
                    st.session_state.calculated_plan,
                    parameter,
                    values,
                    st.session_state.get("source_overrides", {}),
                )
        except Exception as exc:
            render_error(exc, "Не удалось выполнить проверку")
    result = st.session_state.get("sensitivity_result")
    _stale(result)
    if result:
        points = result["points"]
        left, right = charts.sensitivity_lines(points, str(result["parameter"].get("name", "parameter")))
        render_chart(left)
        render_chart(right)
        frame = pd.DataFrame(points)
        columns = ["value", "valid", "total_service_level", "critical_service_level", "total_shortage_t", "total_cost_mln", "minimum_inventory_t", "hard_violation_count"]
        st.dataframe(
            frame[columns].rename(columns={
                "value": "Значение", "valid": "Исполним",
                "total_service_level": "Общий сервис", "critical_service_level": "Критический сервис",
                "total_shortage_t": "Дефицит, т", "total_cost_mln": "Стоимость, млн",
                "minimum_inventory_t": "Минимальный запас, т", "hard_violation_count": "Нарушения",
            }),
            hide_index=True,
            width="stretch",
            column_config={
                "Общий сервис": st.column_config.NumberColumn(format="percent"),
                "Критический сервис": st.column_config.NumberColumn(format="percent"),
            },
        )
        if result.get("first_failing_point"):
            st.warning(f"Первое неуспешное значение: {result['first_failing_point']['value']}")


def _reverse_tab() -> None:
    preset = st.selectbox("Искомый предел", ["Рост спроса", "Задержка Earth-Flex"])
    if preset == "Рост спроса":
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
                st.session_state.reverse_result = runtime.reverse(
                    st.session_state.calculated_plan,
                    parameter,
                    start,
                    stop,
                    step,
                    st.session_state.get("source_overrides", {}),
                )
        except Exception as exc:
            render_error(exc, "Поиск предела не выполнен")
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
            f"Период: {violation.get('period')} · факт: {violation.get('actual')} · "
            f"условие: {violation.get('operator')} {violation.get('limit')}"
        )
    render_chart(charts.reverse_zone(result))
    with st.expander("Технические данные"):
        st.json(result)


def _stakeholders_tab() -> None:
    config = stakeholder_data()
    try:
        abc_payload = st.session_state.get("abc_result") or runtime.abc(
            st.session_state.calculated_plan,
            st.session_state.stress_plan,
            st.session_state.get("source_overrides", {}),
        )
        st.session_state.abc_result = abc_payload
        rows = stakeholder_scenario_rows(config, abc_payload)
    except Exception as exc:
        render_error(exc, "Не удалось собрать последствия для сторон")
        return
    for item in config.get("participants", []):
        name, interests = STAKEHOLDER_TEXT.get(item["stakeholder_id"], (item["name"], ""))
        with st.expander(name):
            st.write("**Интересы:**", interests)
    st.subheader("Рассчитанные последствия A/B/C")
    scenario_rows = pd.DataFrame(rows)
    if not scenario_rows.empty:
        scenario_rows["Сторона"] = [
            STAKEHOLDER_TEXT.get(item["stakeholder_id"], (item["name"], ""))[0]
            for item in config.get("participants", [])
        ]
        st.dataframe(scenario_rows[["Сторона", "A", "B", "C"]], hide_index=True, width="stretch")
    mitigation = st.session_state.get("mitigation_result")
    if mitigation:
        st.subheader("Выбранный риск: до и после меры")
        before = mitigation["original_risk_metrics"]
        after = mitigation["residual_consequence"]["risk"]
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Состояние": "До меры",
                        "Общий дефицит, т": before["total_shortage_t"],
                        "Критический дефицит, т": before["critical_shortage_t"],
                        "Минимальный запас, т": before["minimum_inventory_t"],
                        "Критические нарушения": before["hard_violation_count"],
                    },
                    {
                        "Состояние": "После меры",
                        "Общий дефицит, т": after["total_shortage_t"],
                        "Критический дефицит, т": after["critical_shortage_t"],
                        "Минимальный запас, т": after["minimum_inventory_t"],
                        "Критические нарушения": after["hard_violation_count"],
                    },
                ]
            ),
            hide_index=True,
            width="stretch",
        )


def render() -> None:
    st.title("Риски и чувствительность")
    st.caption(
        "Риски проверяют конкретные неблагоприятные события; чувствительность показывает, "
        "как результат меняется при последовательном изменении одного параметра; предел устойчивости "
        "ищет первое значение, при котором план нарушает ограничение."
    )
    if is_dirty():
        st.warning("В форме есть несчитанные изменения. Новые анализы запускаются для последнего подтверждённого плана.")
    tabs = st.tabs(["Реестр рисков", "Чувствительность", "Предел устойчивости", "Участники"])
    with tabs[0]:
        _risk_tab()
    with tabs[1]:
        _sensitivity_tab()
    with tabs[2]:
        _reverse_tab()
    with tabs[3]:
        _stakeholders_tab()
