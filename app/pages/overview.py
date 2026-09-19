from __future__ import annotations

import streamlit as st

from app import charts
from app.components import kpi_grid, problems, render_chart, results_status
from app.kernel_bridge import case_metadata, plan_hash
from app.state import is_dirty
from app.view_models import minimum_annual_metrics, source_names


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
    service_basis = selected
    if selected == "CUSTOM":
        service_basis = result_pair.get("custom_scenario", {}).get("base_scenario", "BASE")
    baseline = result_pair["BASE"] if selected != "BASE" else None
    kpi_grid(
        result,
        limits,
        baseline=baseline,
        scenario_id=service_basis,
    )

    metrics = minimum_annual_metrics(result)
    if selected == "BASE":
        if metrics["valid"]:
            st.info(
                "Что это значит: текущая стратегия проходит обязательные ограничения BASE. "
                "Дальше имеет смысл смотреть, какой ценой достигается запас устойчивости."
            )
        else:
            st.warning(
                "Что это значит: стратегия не проходит BASE. Раскройте блок нарушений выше "
                "и исправляйте именно первое ограничение, а не параметры наугад."
            )
    else:
        base_metrics = minimum_annual_metrics(result_pair["BASE"])
        service_delta = 100 * (
            metrics["minimum_annual_total_service"]
            - base_metrics["minimum_annual_total_service"]
        )
        shortage_delta = metrics["total_shortage_t"] - base_metrics["total_shortage_t"]
        cost_delta = metrics["undiscounted_cost_mln"] - base_metrics["undiscounted_cost_mln"]
        st.info(
            f"По сравнению с обычными условиями: минимальный общий сервис "
            f"{service_delta:+.1f} п.п., дефицит {shortage_delta:+.1f} т, "
            f"стоимость {cost_delta:+.1f} млн у.е. "
            "Эти дельты показывают цену и физический эффект ухудшения условий."
        )
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
        st.caption(
            "Сравните спрос и реально обслуженный объём. Столбец дефицита сразу показывает, "
            "в каком году поставок не хватает."
        )
    with right:
        render_chart(charts.inventory(result))
        st.caption(
            "Фиолетовая область — фактический запас по месяцам. Чёрный пунктир — вместимость. "
            "На январских точках сравниваются фактический запас на начало года и объём, нужный "
            "для 45 дней: зелёная точка проходит требование, красный крест — нет."
        )
    left, right = st.columns(2)
    with left:
        render_chart(charts.supply_mix(result, source_names(metadata)))
        st.caption(
            "Чем больше доля одного источника, тем сильнее план зависит от его доступности и сроков."
        )
    with right:
        render_chart(charts.costs(result))
        st.caption(
            "График показывает, что именно формирует расходы: закупка, резервирование, CAPEX, OPEX и хранение."
        )
    render_chart(charts.service(result, service_basis))
    annual = result.get("annual", [])
    failed_total = [str(row["year"]) for row in annual if float(row["total_service_level"]) < 0.97 - 1e-9]
    failed_critical = [str(row["year"]) for row in annual if float(row["critical_service_level"]) < 0.99 - 1e-9]
    if failed_total or failed_critical:
        st.caption(
            "Вывод по графику: "
            + (f"общий сервис ниже 97% в {', '.join(failed_total)}. " if failed_total else "")
            + (f"критический сервис ниже 99% в {', '.join(failed_critical)}." if failed_critical else "")
        )
    else:
        st.caption(
            "Вывод по графику: во всех годах сервис находится не ниже линий 97% и 99%."
        )
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