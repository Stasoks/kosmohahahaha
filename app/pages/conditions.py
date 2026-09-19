from __future__ import annotations

import math

import pandas as pd
import streamlit as st

from app import runtime
from app.components import render_error
from app.kernel_bridge import case_metadata
from app.state import accept_calculation


SOURCE_COLUMNS = {
    "source_id": "Код",
    "name": "Источник",
    "capacity_t_per_year": "Мощность, т/год",
    "variable_cost_mln_per_t": "Цена, млн/т",
    "reservation_rate_mln_per_t_year_capacity": "Плата за резерв",
    "take_or_pay_share": "Мин. оплачиваемая доля",
    "effective_lead_time_months": "Срок поставки, мес.",
    "reliability_profile": "Надёжность (справочно)",
}


def _recalculate() -> None:
    result = runtime.evaluate(
        st.session_state.plan,
        st.session_state.get("source_overrides", {}),
        st.session_state.get("custom_scenario"),
    )
    accept_calculation(result)


def _source_editor() -> None:
    st.subheader("Характеристики источников")
    st.caption(
        "Редактируется рабочая копия входных данных. Исходные значения организаторов остаются неизменными."
    )

    official = case_metadata()
    effective = case_metadata(
        source_overrides=st.session_state.get("source_overrides", {})
    )
    rows = []
    for source_id, source in effective["sources"].items():
        rows.append(
            {
                "source_id": source_id,
                "name": source["name"],
                "capacity_t_per_year": float(source["capacity_t_per_year"]),
                "variable_cost_mln_per_t": float(source["variable_cost_mln_per_t"]),
                "reservation_rate_mln_per_t_year_capacity": float(
                    source["reservation_rate_mln_per_t_year_capacity"]
                ),
                "take_or_pay_share": float(source["take_or_pay_share"]),
                "effective_lead_time_months": int(source["effective_lead_time_months"]),
                "reliability_profile": source.get("reliability_profile", ""),
            }
        )

    frame = pd.DataFrame(rows).rename(columns=SOURCE_COLUMNS)
    edited = st.data_editor(
        frame,
        hide_index=True,
        width="stretch",
        disabled=["Код", "Источник", "Надёжность (справочно)"],
        column_config={
            "Мощность, т/год": st.column_config.NumberColumn(min_value=0.0, step=1.0),
            "Цена, млн/т": st.column_config.NumberColumn(min_value=0.0, step=0.1),
            "Плата за резерв": st.column_config.NumberColumn(min_value=0.0, step=0.05),
            "Мин. оплачиваемая доля": st.column_config.NumberColumn(
                min_value=0.0, max_value=1.0, step=0.05, format="%.2f"
            ),
            "Срок поставки, мес.": st.column_config.NumberColumn(
                min_value=0, step=1, format="%d"
            ),
        },
        key="source-characteristics-editor",
    )

    left, right = st.columns(2)
    if left.button("Применить и пересчитать", type="primary", width="stretch"):
        try:
            overrides: dict[str, dict] = {}
            by_id = official["sources"]
            for _, row in edited.iterrows():
                source_id = str(row["Код"])
                base = by_id[source_id]
                patch: dict[str, float | int] = {}
                comparisons = (
                    ("Мощность, т/год", "capacity_t_per_year", float),
                    ("Цена, млн/т", "variable_cost_mln_per_t", float),
                    (
                        "Плата за резерв",
                        "reservation_rate_mln_per_t_year_capacity",
                        float,
                    ),
                    ("Мин. оплачиваемая доля", "take_or_pay_share", float),
                )
                for column, field, cast in comparisons:
                    value = cast(row[column])
                    if not math.isclose(value, float(base[field]), rel_tol=0, abs_tol=1e-12):
                        patch[field] = value
                lead = int(row["Срок поставки, мес."])
                if lead != int(base["effective_lead_time_months"]):
                    patch["selected_lead_time_months"] = lead
                if patch:
                    overrides[source_id] = patch

            st.session_state.source_overrides = overrides
            _recalculate()
            st.success(
                "Рабочая копия источников применена. Обычный, стрессовый и пользовательский сценарии пересчитаны."
            )
            st.rerun()
        except Exception as exc:
            render_error(exc, "Не удалось применить характеристики источников")

    if right.button("Вернуть данные организаторов", width="stretch"):
        st.session_state.source_overrides = {}
        try:
            _recalculate()
            st.rerun()
        except Exception as exc:
            render_error(exc, "Не удалось восстановить исходные данные")

    if st.session_state.get("source_overrides"):
        with st.expander("Что изменено относительно исходных данных"):
            st.json(st.session_state.source_overrides)


def _build_custom_spec(
    *,
    name: str,
    base_scenario: str,
    start_year: int,
    end_year: int,
    total_demand: float,
    critical_demand: float,
    source_frame: pd.DataFrame,
    storage_loss: float,
    storage_capacity: float,
) -> dict:
    start = f"{start_year}-01"
    end = f"{end_year}-12"
    changes: list[dict] = []

    def add(factor: str, value: float, neutral: float, **target) -> None:
        if math.isclose(float(value), float(neutral), rel_tol=0, abs_tol=1e-12):
            return
        changes.append(
            {
                "factor": factor,
                "value": float(value),
                "period_start": start,
                "period_end": end,
                "status": "TEAM_ASSUMPTION",
                **target,
            }
        )

    add("total_demand_multiplier", total_demand, 1.0)
    add("critical_demand_multiplier", critical_demand, 1.0)

    for _, row in source_frame.iterrows():
        source_id = str(row["Код"])
        add("variable_price_multiplier", row["Цена ×"], 1.0, source_id=source_id)
        add("actual_delivery_share", row["Фактическая поставка"], 1.0, source_id=source_id)
        add("availability_share", row["Доступность"], 1.0, source_id=source_id)
        add("additional_lead_time_months", row["Доп. задержка, мес."], 0.0, source_id=source_id)
        add("source_capacity_multiplier", row["Мощность ×"], 1.0, source_id=source_id)
        add("reservation_price_multiplier", row["Резервирование ×"], 1.0, source_id=source_id)

    add("storage_loss_rate_multiplier", storage_loss, 1.0, storage_id="ZBO")
    add("storage_capacity_multiplier", storage_capacity, 1.0, storage_id="ZBO")

    if not changes:
        raise ValueError("Измените хотя бы один параметр пользовательского сценария")
    return {
        "name": name.strip() or "Пользовательский сценарий",
        "base_scenario": base_scenario,
        "period_start": start,
        "period_end": end,
        "factor_changes": changes,
        "status": "TEAM_ASSUMPTION",
    }


def _scenario_editor() -> None:
    st.subheader("Пользовательский сценарий")
    st.caption(
        "Сценарий создаётся поверх обычных условий или обязательного стресса. "
        "Официальные сценарии при этом не изменяются."
    )
    metadata = case_metadata(
        source_overrides=st.session_state.get("source_overrides", {})
    )
    years = list(metadata["official_years"] or metadata["years"])
    current = st.session_state.get("custom_scenario") or {}

    cols = st.columns(2)
    name = cols[0].text_input(
        "Название",
        value=str(current.get("name", "Мой сценарий")),
        key="custom-scenario-name",
    )
    base_scenario = cols[1].selectbox(
        "Основа",
        ["BASE", "MANDATORY_STRESS"],
        index=1 if current.get("base_scenario") == "MANDATORY_STRESS" else 0,
        format_func=lambda value: "Обычные условия" if value == "BASE" else "Обязательный стресс",
        key="custom-scenario-base",
    )
    cols = st.columns(2)
    start_year = cols[0].selectbox(
        "С какого года",
        years,
        index=0,
        key="custom-scenario-start",
    )
    end_year = cols[1].selectbox(
        "По какой год",
        years,
        index=len(years) - 1,
        key="custom-scenario-end",
    )
    if end_year < start_year:
        st.error("Конец периода не может быть раньше начала.")
        return

    cols = st.columns(2)
    total_demand = cols[0].number_input(
        "Общий спрос ×",
        min_value=0.0,
        value=1.0,
        step=0.05,
        key="custom-total-demand",
        help="1.10 означает рост общего спроса на 10%.",
    )
    critical_demand = cols[1].number_input(
        "Критический спрос ×",
        min_value=0.0,
        value=1.0,
        step=0.05,
        key="custom-critical-demand",
    )

    st.markdown("**Изменения по каналам снабжения**")
    source_rows = [
        {
            "Код": source_id,
            "Источник": source["name"],
            "Цена ×": 1.0,
            "Фактическая поставка": 1.0,
            "Доступность": 1.0,
            "Доп. задержка, мес.": 0.0,
            "Мощность ×": 1.0,
            "Резервирование ×": 1.0,
        }
        for source_id, source in metadata["sources"].items()
    ]
    source_frame = st.data_editor(
        pd.DataFrame(source_rows),
        hide_index=True,
        width="stretch",
        disabled=["Код", "Источник"],
        column_config={
            "Цена ×": st.column_config.NumberColumn(min_value=0.0, step=0.05),
            "Фактическая поставка": st.column_config.NumberColumn(
                min_value=0.0, max_value=1.0, step=0.05
            ),
            "Доступность": st.column_config.NumberColumn(
                min_value=0.0, max_value=1.0, step=0.05
            ),
            "Доп. задержка, мес.": st.column_config.NumberColumn(min_value=0.0, step=1.0),
            "Мощность ×": st.column_config.NumberColumn(min_value=0.0, step=0.05),
            "Резервирование ×": st.column_config.NumberColumn(min_value=0.0, step=0.05),
        },
        key="custom-source-scenario-editor",
    )

    with st.expander("Хранилище ZBO"):
        cols = st.columns(2)
        storage_loss = cols[0].number_input(
            "Потери ×", min_value=0.0, value=1.0, step=0.05, key="custom-zbo-loss"
        )
        storage_capacity = cols[1].number_input(
            "Ёмкость ×", min_value=0.0, value=1.0, step=0.05, key="custom-zbo-capacity"
        )

    left, right = st.columns(2)
    if left.button("Сохранить и пересчитать сценарий", type="primary", width="stretch"):
        try:
            spec = _build_custom_spec(
                name=name,
                base_scenario=base_scenario,
                start_year=int(start_year),
                end_year=int(end_year),
                total_demand=float(total_demand),
                critical_demand=float(critical_demand),
                source_frame=source_frame,
                storage_loss=float(storage_loss),
                storage_capacity=float(storage_capacity),
            )
            st.session_state.custom_scenario = spec
            _recalculate()
            st.success("Пользовательский сценарий сохранён и рассчитан.")
            st.rerun()
        except Exception as exc:
            render_error(exc, "Не удалось рассчитать пользовательский сценарий")

    if right.button("Удалить пользовательский сценарий", width="stretch"):
        st.session_state.custom_scenario = None
        try:
            _recalculate()
            st.rerun()
        except Exception as exc:
            render_error(exc, "Не удалось удалить пользовательский сценарий")

    custom = st.session_state.get("custom_scenario")
    if custom:
        st.info(
            f"Активен: {custom['name']} · основа: "
            f"{'обычные условия' if custom['base_scenario'] == 'BASE' else 'обязательный стресс'} · "
            f"{custom['period_start']} — {custom['period_end']} · изменений: {len(custom['factor_changes'])}."
        )
        with st.expander("Параметры пользовательского сценария"):
            st.dataframe(pd.DataFrame(custom["factor_changes"]), hide_index=True, width="stretch")


def render() -> None:
    st.title("Исходные условия")
    tabs = st.tabs(["Источники топлива", "Пользовательский сценарий"])
    with tabs[0]:
        _source_editor()
    with tabs[1]:
        _scenario_editor()
