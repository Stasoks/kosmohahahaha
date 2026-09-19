from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from app import charts, runtime
from app.components import render_chart, render_error
from app.kernel_bridge import input_hash, plan_hash, risk_catalog, stakeholder_data
from app.state import is_dirty
from app.view_models import (
    minimum_annual_metrics,
    risk_stakeholder_impact_rows,
    stakeholder_detail_rows,
    violations_view,
)


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


def _selected_analysis() -> tuple[dict, str]:
    choice = st.session_state.get("analysis-plan-choice", "operator")
    plan = (
        st.session_state.stress_plan
        if choice == "adapted" and st.session_state.get("stress_plan")
        else st.session_state.calculated_plan
    )
    environment_key = st.session_state.get("analysis-environment-choice", "BASE")
    return plan, environment_key


def _stale(value: dict | None) -> bool:
    if not value:
        return False
    analysis_plan, environment_key = _selected_analysis()
    stale = (
        value.get("plan_hash") != plan_hash(analysis_plan)
        or value.get("input_hash", input_hash({}))
        != input_hash(st.session_state.get("source_overrides", {}))
        or value.get("analysis_environment", "BASE") != environment_key
    )
    if stale:
        st.warning(
            "Результат относится к другому плану или среде анализа. "
            "Запустите расчёт заново."
        )
    return stale


def _analysis_controls() -> None:
    choices = {"operator": "Ваш текущий план"}
    if st.session_state.get("stress_plan"):
        choices["adapted"] = "Стратегия, адаптированная под стресс"
    cols = st.columns(2)
    cols[0].selectbox(
        "Анализируемый план",
        list(choices),
        format_func=choices.get,
        key="analysis-plan-choice",
    )
    environment_labels = {
        "BASE": "Обычные условия (BASE)",
        "MANDATORY_STRESS": "Обязательный стресс",
    }
    cols[1].selectbox(
        "Среда анализа",
        list(environment_labels),
        format_func=environment_labels.get,
        key="analysis-environment-choice",
    )
    plan, environment_key = _selected_analysis()
    st.caption(
        f"Анализируется план «{plan.get('plan_id', 'plan')}» в среде "
        f"{environment_labels[environment_key]}. Риски, чувствительность и предел "
        "устойчивости используют именно эту комбинацию."
    )


def _risk_tab() -> None:
    analysis_plan, environment_key = _selected_analysis()
    if st.button("Рассчитать портфель рисков", type="primary"):
        try:
            with st.spinner("Каждый риск рассчитывается отдельным прогоном цифрового двойника…"):
                st.session_state.risk_result = runtime.risks(
                    analysis_plan,
                    st.session_state.get("source_overrides", {}),
                    environment_key,
                )
        except Exception as exc:
            render_error(exc, "Не удалось рассчитать портфель")
    data = st.session_state.get("risk_result")
    if data and _stale(data):
        st.info("Нажмите «Рассчитать портфель рисков» для выбранной комбинации.")
        return
    if not data:
        st.info("Запустите портфель явно. Открытие страницы не запускает тяжёлые расчёты.")
        return
    register = pd.DataFrame(data["risk_register"])
    columns = st.columns(3)
    columns[0].metric("Рисков", len(register))
    columns[1].metric("С оценкой вероятности", int(register.likelihood_score.notna().sum()))
    columns[2].metric("Без оценки вероятности", len(data["unknown_likelihood_risks"]))
    impact_rows = []
    for item in data["risk_register"]:
        delta = item.get("quantitative_delta", {})
        costs = delta.get("costs", {})
        impact_rows.append(
            {
                "risk_id": item["risk_id"],
                "risk_name": RISK_TEXT.get(item["risk_id"], (item["name"],))[0],
                "shortage_delta_t": float(delta.get("total_shortage_t", 0.0) or 0.0),
                "critical_shortage_delta_t": float(
                    delta.get("critical_shortage_t", 0.0) or 0.0
                ),
                "cost_delta_mln": float(costs.get("total_cost_mln", 0.0) or 0.0),
                "likelihood": (
                    f"{float(item['likelihood_score']):g}/5"
                    if item.get("likelihood_score") is not None
                    else "не оценена"
                ),
            }
        )
    st.caption(
        "Главный график ранжирует не абстрактный балл, а рассчитанный физический эффект: "
        "на сколько тонн конкретный риск увеличивает дефицит выбранного плана."
    )
    render_chart(charts.risk_impact(impact_rows))
    impact_table = pd.DataFrame(impact_rows).rename(
        columns={
            "risk_name": "Риск",
            "shortage_delta_t": "Δ общего дефицита, т",
            "critical_shortage_delta_t": "Δ критического дефицита, т",
            "cost_delta_mln": "Δ стоимости, млн",
            "likelihood": "Вероятность",
        }
    )
    st.dataframe(
        impact_table[
            [
                "Риск",
                "Δ общего дефицита, т",
                "Δ критического дефицита, т",
                "Δ стоимости, млн",
                "Вероятность",
            ]
        ],
        hide_index=True,
        width="stretch",
    )
    st.caption(
        "Если вероятность «не оценена», риск нельзя честно ранжировать по вероятности × ущерб. "
        "Поэтому на первом экране показаны только рассчитанные последствия."
    )
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
                    analysis_plan,
                    selected,
                    st.session_state.get("source_overrides", {}),
                    environment_key,
                )
        except Exception as exc:
            render_error(exc, "Не удалось рассчитать риск")
    detail = st.session_state.get("risk_detail")
    detail_current = False
    if detail and detail.get("risk", {}).get("risk_id") == selected:
        if _stale(detail):
            st.info("Пересчитайте выбранный риск для текущего плана и среды.")
        else:
            detail_current = True
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
                        analysis_plan,
                        selected,
                        st.session_state.get("source_overrides", {}),
                        environment_key,
                    )
            except Exception as exc:
                render_error(exc, "Не удалось рассчитать меру")
        value = st.session_state.get("mitigation_result")
        if value and value.get("risk_id") == selected:
            if _stale(value):
                st.info("Пересчитайте меру для текущего плана и среды.")
                value = None
            if value:
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

    if detail_current:
        st.subheader("Кто несёт последствия выбранного риска")
        mitigation_value = st.session_state.get("mitigation_result")
        residual_result = None
        if mitigation_value and mitigation_value.get("risk_id") == selected:
            residual_result = mitigation_value.get("risk_result")
        stakeholder_rows = risk_stakeholder_impact_rows(
            stakeholder_data(),
            selected,
            detail["baseline"],
            detail["risk_result"],
            residual_result,
        )
        if stakeholder_rows:
            frame = pd.DataFrame(stakeholder_rows)
            names_by_id = {
                item["name"]: STAKEHOLDER_TEXT.get(
                    item["stakeholder_id"], (item["name"], "")
                )[0]
                for item in stakeholder_data().get("participants", [])
            }
            frame["Сторона"] = frame["Сторона"].map(
                lambda value: names_by_id.get(value, value)
            )
            st.dataframe(frame, hide_index=True, width="stretch")
            st.caption(
                "Денежный ущерб потребителей не монетизируется без входных данных. "
                "Таблица показывает только рассчитанные расходы, физический дефицит, "
                "сервис и явно заданное распределение рисков."
            )


def _sensitivity_tab() -> None:
    analysis_plan, environment_key = _selected_analysis()
    st.info(
        "Что показывает чувствительность: мы меняем только один параметр, а остальные решения "
        "оставляем прежними. Если небольшой сдвиг быстро создаёт дефицит или нарушение, "
        "значит план сильно зависит от этого допущения."
    )
    official_disabled = environment_key != "BASE"
    if st.button(
        "Проверить нижний, базовый и верхний спрос",
        type="primary",
        disabled=official_disabled,
    ):
        try:
            with st.spinner("Три официальные точки спроса…"):
                st.session_state.sensitivity_result = runtime.official_sensitivity(
                    analysis_plan,
                    st.session_state.get("source_overrides", {}),
                )
        except Exception as exc:
            render_error(exc, "Не удалось выполнить проверку")
    if official_disabled:
        st.caption(
            "Официальные LOW/BASE/HIGH проверяются отдельно только поверх BASE. "
            "Для обязательного стресса используйте дополнительную проверку ниже."
        )
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
                    analysis_plan,
                    parameter,
                    values,
                    st.session_state.get("source_overrides", {}),
                    environment_key,
                )
        except Exception as exc:
            render_error(exc, "Не удалось выполнить проверку")
    result = st.session_state.get("sensitivity_result")
    if result and _stale(result):
        st.info("Запустите чувствительность заново для выбранной комбинации.")
        result = None
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
            first = result["first_failing_point"]
            st.warning(
                f"Вывод: первое проверенное значение, при котором план перестаёт проходить "
                f"ограничения — {first['value']}. До этой точки на выбранной сетке план "
                "сохранял исполнимость."
            )
        else:
            st.success(
                "Вывод: на всей заданной сетке этот параметр не довёл план до нарушения. "
                "Это не доказывает устойчивость за пределами проверенного диапазона."
            )


def _reverse_tab() -> None:
    analysis_plan, environment_key = _selected_analysis()
    st.info(
        "Здесь ищется не «оценка устойчивости», а конкретная граница: какое максимальное "
        "значение параметра план выдерживает на заданной сетке и где появляется первое нарушение."
    )
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
                    analysis_plan,
                    parameter,
                    start,
                    stop,
                    step,
                    st.session_state.get("source_overrides", {}),
                    environment_key,
                )
        except Exception as exc:
            render_error(exc, "Поиск предела не выполнен")
    result = st.session_state.get("reverse_result")
    if result and _stale(result):
        st.info("Запустите поиск предела заново для выбранной комбинации.")
        return
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
    last_safe = result.get("last_safe_value")
    first_fail = result.get("first_failing_value")
    if first_fail is not None:
        st.warning(
            f"Вывод: последнее проверенное безопасное значение — {last_safe}; "
            f"первое неуспешное — {first_fail}. Вертикальная граница на графике показывает "
            "первый обнаруженный отказ, а не теоретический непрерывный предел."
        )
    else:
        st.success(
            "Вывод: в заданном диапазоне первое нарушение не найдено. "
            "Чтобы искать дальше, увеличьте верхнюю границу."
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
        rows = stakeholder_detail_rows(config, abc_payload)
    except Exception as exc:
        render_error(exc, "Не удалось собрать последствия для сторон")
        return

    st.info(
        "Зачем этот блок: он отвечает не на вопрос «кто существует в системе», а на вопрос "
        "«кто именно чувствует последствия стресса и что меняется после адаптации»."
    )
    mode = st.segmented_control(
        "Что сравнить",
        ["stress", "adaptation"],
        default="stress",
        format_func=lambda value: (
            "Обычные условия → стресс без адаптации"
            if value == "stress"
            else "Стресс без адаптации → после адаптации"
        ),
    ) or "stress"

    before_key, after_key = (
        ("A · BASE", "B · тот же план в стрессе")
        if mode == "stress"
        else ("B · тот же план в стрессе", "C · адаптация в стрессе")
    )

    participant_by_name = {
        item.get("name", ""): item for item in config.get("participants", [])
    }
    for row in rows:
        participant = participant_by_name.get(row["Сторона"], {})
        stakeholder_id = participant.get("stakeholder_id", "")
        name = STAKEHOLDER_TEXT.get(
            stakeholder_id,
            (row["Сторона"], ""),
        )[0]
        with st.expander(name, expanded=stakeholder_id in {"operator", "critical_consumers", "commercial_consumers"}):
            cols = st.columns(2)
            cols[0].markdown(f"**До:** {row.get(before_key, '—')}")
            cols[1].markdown(f"**После:** {row.get(after_key, '—')}")
            st.caption(
                f"Интересы: {'; '.join(participant.get('interests', [])) or 'не заданы'}. "
                f"Несёт риск: {'; '.join(participant.get('risk_bearer', [])) or 'не задан'}. "
                f"Несёт затраты: {'; '.join(participant.get('cost_bearer', [])) or 'отдельно не задано'}."
            )

    mitigation = st.session_state.get("mitigation_result")
    if mitigation and not _stale(mitigation):
        st.subheader("Выбранный риск: что изменила мера")
        before = mitigation["original_risk_metrics"]
        after = mitigation["residual_consequence"]["risk"]
        cols = st.columns(3)
        cols[0].metric(
            "Общий дефицит",
            f"{after['total_shortage_t']:.2f} т",
            f"{after['total_shortage_t']-before['total_shortage_t']:+.2f} т после меры",
            delta_color="inverse",
        )
        cols[1].metric(
            "Критический дефицит",
            f"{after['critical_shortage_t']:.2f} т",
            f"{after['critical_shortage_t']-before['critical_shortage_t']:+.2f} т после меры",
            delta_color="inverse",
        )
        cols[2].metric(
            "Критические нарушения",
            str(after["hard_violation_count"]),
            f"{after['hard_violation_count']-before['hard_violation_count']:+d} после меры",
            delta_color="inverse",
        )

def render() -> None:
    st.title("Риски и чувствительность")
    st.caption(
        "Риски отвечают «что будет при конкретном событии», чувствительность — "
        "«от каких допущений план зависит сильнее всего», предел устойчивости — "
        "«где находится первое проверенное значение отказа»."
    )
    if is_dirty():
        st.warning(
            "В форме есть несчитанные изменения. «Текущий план оператора» ниже означает "
            "последнюю пересчитанную версию."
        )
    st.subheader("Параметры анализа")
    _analysis_controls()
    tabs = st.tabs(["Реестр рисков", "Чувствительность", "Предел устойчивости", "Участники"])
    with tabs[0]:
        _risk_tab()
    with tabs[1]:
        _sensitivity_tab()
    with tabs[2]:
        _reverse_tab()
    with tabs[3]:
        _stakeholders_tab()