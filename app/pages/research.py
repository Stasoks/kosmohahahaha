from __future__ import annotations

import copy

import pandas as pd
import streamlit as st

from app import charts, runtime
from app.components import badges, kpi_grid, note, render_chart, render_error, violations
from app.kernel_bridge import (
    case_metadata,
    research_plan_template,
    workspace_add_source,
    workspace_bytes,
    workspace_extend_year,
    workspace_from_bytes,
)
from app.state import reset_research
from app.view_models import source_names


def _next_source_id(metadata: dict) -> str:
    for letter in "FGHIJKLMNOPQRSTUVWXYZ":
        if letter not in metadata["sources"]:
            return letter
    return f"R{len(metadata['sources']) + 1}"


def _add_source() -> None:
    workspace = st.session_state.workspace
    metadata = case_metadata(workspace)
    with st.form("research-source"):
        st.subheader("Добавить исследовательский источник")
        cols = st.columns(3)
        source_id = cols[0].text_input("source_id", _next_source_id(metadata))
        name = cols[1].text_input("Название", "Research source")
        capacity = cols[2].number_input("Мощность, т/год", min_value=0.0, value=25.0)
        cols = st.columns(4)
        price = cols[0].number_input("Переменная цена, млн/т", min_value=0.0, value=8.0)
        reservation = cols[1].number_input("Резерв, млн/(т/год)", min_value=0.0, value=0.2)
        top = cols[2].number_input("TOP share", 0.0, 1.0, 0.0, 0.05)
        unit = cols[3].selectbox("Единица lead time", ["month", "week", "day", "year"])
        cols = st.columns(3)
        lead_min = cols[0].number_input("Lead time min", min_value=0.0, value=4.0)
        lead_max = cols[1].number_input("Lead time max", min_value=0.0, value=4.0)
        selected_lead = cols[2].number_input("Выбранный lead time, мес.", min_value=0, value=4)
        availability_kind = st.selectbox("Правило доступности", ["calendar", "always"])
        available_from = st.text_input("Доступен с (ГГГГ-ММ)", f"{min(metadata['years'])}-01")
        reliability = st.text_input("Reliability metadata", "metadata_only; no automatic derating")
        notes = st.text_area("Примечания", "Research source; not organizer data.")
        cols = st.columns(2)
        basis = cols[0].text_input("Provenance basis", "team research assumption")
        source_ref = cols[1].text_input("Provenance source", f"TEAM:source-{source_id}")
        submitted = st.form_submit_button("Добавить источник в workspace", type="primary", width="stretch")
    if submitted:
        rule = {"type": availability_kind}
        if availability_kind == "calendar":
            rule["available_from"] = available_from
        payload = {
            "source_id": source_id.strip(), "name": name.strip(),
            "capacity_t_per_year": capacity, "variable_cost_mln_per_t": price,
            "reservation_rate_mln_per_t_year_capacity": reservation,
            "take_or_pay_share": top, "lead_time_min_value": lead_min,
            "lead_time_max_value": lead_max, "lead_time_unit": unit,
            "selected_lead_time_months": int(selected_lead) if lead_min != lead_max else None,
            "availability_rule": rule,
            "reliability_metadata": {"semantics": reliability},
            "notes": notes,
            "provenance": {"basis": basis, "source": source_ref},
        }
        try:
            st.session_state.workspace = workspace_add_source(workspace, payload)
            base = st.session_state.research_plan or st.session_state.calculated_plan
            st.session_state.research_plan = research_plan_template(base, st.session_state.workspace)
            st.session_state.research_result = None
            st.success(f"Источник {source_id} добавлен только в research workspace.")
            st.rerun()
        except Exception as exc:
            render_error(exc, "Источник не добавлен")


def _extend_year() -> None:
    workspace = st.session_state.workspace
    metadata = case_metadata(workspace)
    next_year = max(metadata["years"]) + 1
    last_demand = metadata["demand"][-1]
    with st.form("research-year"):
        st.subheader(f"Продлить горизонт: {next_year}")
        st.caption("Год contiguous. Все значения становятся TEAM_ASSUMPTION только после явного подтверждения формы.")
        cols = st.columns(4)
        total = cols[0].number_input("Общий спрос, т", min_value=0.0, value=float(last_demand["base_total_t"]))
        critical = cols[1].number_input("Критический спрос, т", min_value=0.0, value=float(last_demand["base_critical_t"]))
        low = cols[2].number_input("LOW, т", min_value=0.0, value=float(last_demand["low_total_t"]))
        high = cols[3].number_input("HIGH, т", min_value=0.0, value=float(last_demand["high_total_t"]))
        assumptions = pd.DataFrame(
            [
                {
                    "Источник": source_id,
                    "Цена, млн/т": source["variable_cost_mln_per_t"],
                    "Мощность, т/год": source["capacity_t_per_year"],
                    "Доступность 0..1": 1.0,
                    "Reliability interpretation": source.get("reliability_metadata", {}).get("semantics", "metadata_only"),
                }
                for source_id, source in metadata["sources"].items()
            ]
        )
        edited = st.data_editor(
            assumptions,
            hide_index=True,
            width="stretch",
            column_config={
                "Источник": st.column_config.TextColumn(disabled=True),
                "Цена, млн/т": st.column_config.NumberColumn(min_value=0.0),
                "Мощность, т/год": st.column_config.NumberColumn(min_value=0.0),
                "Доступность 0..1": st.column_config.NumberColumn(min_value=0.0, max_value=1.0),
            },
        )
        constraints = st.multiselect(
            "Применимые ограничения",
            list(metadata["constraints"]),
            default=[item for item in ("BASE_TOTAL_SERVICE", "BASE_CRITICAL_SERVICE", "RESERVE_45D") if item in metadata["constraints"]],
        )
        notes_text = st.text_area("Примечания", "Explicit research year; no official extrapolation is claimed.")
        cols = st.columns(2)
        basis = cols[0].text_input("Provenance basis", "explicit team forecast")
        source_ref = cols[1].text_input("Provenance source", f"TEAM:forecast-{next_year}")
        submitted = st.form_submit_button(f"Добавить {next_year}", type="primary", width="stretch")
    if submitted:
        future = {
            "year": next_year,
            "base_total_demand_t": total,
            "base_critical_demand_t": critical,
            "low_total_t": low,
            "high_total_t": high,
            "source_price_assumptions": {str(row["Источник"]): float(row["Цена, млн/т"]) for _, row in edited.iterrows()},
            "source_capacity_assumptions": {str(row["Источник"]): float(row["Мощность, т/год"]) for _, row in edited.iterrows()},
            "source_availability_assumptions": {str(row["Источник"]): float(row["Доступность 0..1"]) for _, row in edited.iterrows()},
            "reliability_assumptions": {str(row["Источник"]): str(row["Reliability interpretation"]) for _, row in edited.iterrows()},
            "applicable_constraints": constraints,
            "notes": notes_text,
            "provenance": {"basis": basis, "source": source_ref},
        }
        try:
            st.session_state.workspace = workspace_extend_year(workspace, future)
            base = st.session_state.research_plan or st.session_state.calculated_plan
            st.session_state.research_plan = research_plan_template(base, st.session_state.workspace)
            st.session_state.research_result = None
            st.success(f"{next_year} добавлен как TEAM_ASSUMPTION.")
            st.rerun()
        except Exception as exc:
            render_error(exc, "Год не добавлен")


def _research_plan_editor() -> None:
    metadata = case_metadata(st.session_state.workspace)
    if st.session_state.research_plan is None:
        st.session_state.research_plan = research_plan_template(
            st.session_state.calculated_plan, st.session_state.workspace
        )
    raw = st.session_state.research_plan
    schedules = {str(item["source_id"]): item for item in raw["decisions"]["supply_orders"]}
    reservations = {
        (str(item["source_id"]), int(item["year"])): float(item["reserved_capacity_t"])
        for item in raw["decisions"].get("capacity_reservations", [])
    }
    orders = []
    reserves = []
    for source_id, source in metadata["sources"].items():
        schedule = schedules.get(source_id, {"values": {}})
        order_row = {"Источник": source_id, "Название": source["name"]}
        reserve_row = {"Источник": source_id, "Название": source["name"]}
        for year in metadata["years"]:
            order_row[str(year)] = sum(
                float(value) for period, value in schedule.get("values", {}).items()
                if int(str(period)[:4]) == year
            )
            reserve_row[str(year)] = reservations.get((source_id, year), 0.0)
        orders.append(order_row)
        reserves.append(reserve_row)
    st.subheader("Решения research-плана")
    st.caption("Применение матрицы — явное преобразование research-копии в annual_even; официальный план не меняется.")
    order_frame = st.data_editor(pd.DataFrame(orders), hide_index=True, width="stretch")
    with st.expander("Capacity reservations"):
        reserve_frame = st.data_editor(pd.DataFrame(reserves), hide_index=True, width="stretch")
    if st.button("Применить research decisions", width="stretch"):
        updated = copy.deepcopy(raw)
        updated["decisions"]["supply_orders"] = [
            {
                "source_id": str(row["Источник"]), "mode": "annual_even",
                "values": {str(year): float(row[str(year)]) for year in metadata["years"]},
            }
            for _, row in order_frame.iterrows()
        ]
        updated["decisions"]["capacity_reservations"] = [
            {"source_id": str(row["Источник"]), "year": year, "reserved_capacity_t": float(row[str(year)])}
            for _, row in reserve_frame.iterrows()
            for year in metadata["years"]
            if float(row[str(year)]) > 0
        ]
        st.session_state.research_plan = updated
        st.session_state.research_result = None
        st.success("Research decisions применены; требуется отдельный расчёт.")
    if st.button("Рассчитать effective case", type="primary", width="stretch"):
        try:
            with st.spinner("Обычный simulator рассчитывает non-destructive effective case…"):
                st.session_state.research_result = runtime.workspace_evaluate(
                    st.session_state.research_plan, st.session_state.workspace
                )
        except Exception as exc:
            render_error(exc, "Research plan не рассчитан")
    result = st.session_state.get("research_result")
    if result:
        st.info(result["notice"])
        kpi_grid(result["BASE"])
        left, right = st.columns(2)
        with left:
            render_chart(charts.demand_service(result["BASE"]))
        with right:
            render_chart(charts.supply_mix(result["BASE"], source_names(metadata)))
        violations(result["BASE"], "research")


def _workspace_io() -> None:
    workspace = st.session_state.workspace
    cols = st.columns(3)
    cols[0].download_button(
        "Скачать workspace JSON",
        workspace_bytes(workspace),
        "kosmohak-workspace.json",
        "application/json",
        width="stretch",
    )
    upload = cols[1].file_uploader("Открыть workspace", type=["json"], label_visibility="collapsed")
    if upload and cols[1].button("Проверить и открыть", width="stretch"):
        try:
            st.session_state.workspace = workspace_from_bytes(upload.getvalue())
            st.session_state.research_plan = research_plan_template(
                st.session_state.calculated_plan, st.session_state.workspace
            )
            st.session_state.research_result = None
            st.rerun()
        except Exception as exc:
            render_error(exc, "Workspace не открыт")
    if cols[2].button("Сбросить к official case", width="stretch"):
        reset_research(st.session_state.calculated_plan)
        st.rerun()


def render() -> None:
    st.title("Исследования")
    note(
        "RESEARCH / TEAM_ASSUMPTION. Официальный кейс не изменяется. Mandatory stress официально определён только "
        "для горизонта кейса; future-year assumptions являются TEAM_ASSUMPTION.",
        warning=True,
    )
    badges(("OFFICIAL CASE · READ-ONLY", "case"), ("WORKSPACE · TEAM_ASSUMPTION", "team"))
    _workspace_io()
    metadata = case_metadata(st.session_state.workspace)
    cols = st.columns(3)
    cols[0].metric("Effective sources", len(metadata["sources"]))
    cols[1].metric("Research sources", len(metadata["research_source_ids"]))
    cols[2].metric("Горизонт", f"{min(metadata['years'])}–{max(metadata['years'])}")
    st.caption(
        f"Research sources: {metadata['research_source_ids'] or 'нет'} · Research years: {metadata['research_years'] or 'нет'}"
    )
    tabs = st.tabs(["Добавить источник", "Продлить горизонт", "Effective case и расчёт"])
    with tabs[0]:
        _add_source()
    with tabs[1]:
        _extend_year()
    with tabs[2]:
        st.dataframe(pd.DataFrame(metadata["demand"]), hide_index=True, width="stretch")
        st.dataframe(pd.DataFrame(metadata["sources"].values()), hide_index=True, width="stretch")
        _research_plan_editor()
