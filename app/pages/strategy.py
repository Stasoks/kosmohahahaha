from __future__ import annotations

import copy
from typing import Any

import pandas as pd
import streamlit as st

from app.components import render_error
from app.kernel_bridge import case_metadata, plan_hash, validate
from app.state import apply_plan, is_dirty
from app.view_models import contract_rows, investment_timeline, source_names


MODE_LABELS = {"annual_even": "Равномерно по году", "monthly": "Помесячно"}
MODE_VALUES = {label: value for value, label in MODE_LABELS.items()}
RESERVE_LABELS = {"physical": "Физический запас", "emergency_contract": "Аварийный контракт"}
ROLE_LABELS = {"reserve_only": "Только резерв", "planned_supply": "Плановые поставки"}


def _annual_orders(raw: dict[str, Any], metadata: dict[str, Any]) -> pd.DataFrame:
    schedules = {str(item["source_id"]): item for item in raw["decisions"]["supply_orders"]}
    rows = []
    for source_id, source in metadata["sources"].items():
        schedule = schedules.get(source_id, {"mode": "annual_even", "values": {}})
        row = {
            "Источник": source_id,
            "Название": source["name"],
            "Распределение": MODE_LABELS.get(schedule.get("mode", "annual_even"), "Равномерно по году"),
            "Применить годовые итоги": False,
        }
        for year in metadata["years"]:
            row[str(year)] = sum(
                float(value)
                for period, value in schedule.get("values", {}).items()
                if int(str(period)[:4]) == year
            )
        rows.append(row)
    return pd.DataFrame(rows)


def _monthly_orders(raw: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for schedule in raw["decisions"]["supply_orders"]:
        if schedule.get("mode") != "monthly":
            continue
        for month, value in sorted(schedule.get("values", {}).items()):
            rows.append({"Источник": schedule["source_id"], "Месяц": month, "Заказ, т": float(value)})
    return pd.DataFrame(rows, columns=["Источник", "Месяц", "Заказ, т"])


def _reservations(raw: dict[str, Any], metadata: dict[str, Any]) -> pd.DataFrame:
    values = {
        (str(item["source_id"]), int(item["year"])): float(item["reserved_capacity_t"])
        for item in raw["decisions"]["capacity_reservations"]
    }
    return pd.DataFrame(
        [
            {
                "Источник": source_id,
                "Название": source["name"],
                **{str(year): values.get((source_id, year), 0.0) for year in metadata["years"]},
            }
            for source_id, source in metadata["sources"].items()
        ]
    )


def _apply_orders(
    raw: dict[str, Any],
    annual: pd.DataFrame,
    monthly: pd.DataFrame,
    years: list[int],
) -> None:
    existing = {
        str(item["source_id"]): copy.deepcopy(item)
        for item in raw["decisions"]["supply_orders"]
    }
    monthly_values: dict[str, dict[str, float]] = {}
    for _, row in monthly.dropna(how="all").iterrows():
        source_id = str(row.get("Источник", "")).strip()
        month = str(row.get("Месяц", "")).strip()
        if not source_id or not month or pd.isna(row.get("Заказ, т")):
            continue
        monthly_values.setdefault(source_id, {})[month] = float(row["Заказ, т"])

    output = []
    for _, row in annual.iterrows():
        source_id = str(row["Источник"])
        previous = existing.get(source_id, {"source_id": source_id, "mode": "annual_even", "values": {}})
        if source_id in monthly_values and previous.get("mode") == "monthly" and not bool(row["Применить годовые итоги"]):
            output.append({"source_id": source_id, "mode": "monthly", "values": monthly_values[source_id]})
            continue
        if not bool(row["Применить годовые итоги"]):
            output.append(previous)
            continue
        mode = MODE_VALUES.get(str(row["Распределение"]), "annual_even")
        if mode == "monthly":
            values = {
                f"{year}-{month:02d}": float(row[str(year)]) / 12.0
                for year in years
                for month in range(1, 13)
                if float(row[str(year)]) > 0
            }
        else:
            values = {str(year): float(row[str(year)]) for year in years}
        output.append({"source_id": source_id, "mode": mode, "values": values})
    raw["decisions"]["supply_orders"] = output


def _source_cards(metadata: dict[str, Any]) -> None:
    rows = []
    for source_id, source in metadata["sources"].items():
        unit = {"month": "мес.", "week": "нед.", "day": "дн.", "year": "г."}.get(
            source["lead_time_unit"], source["lead_time_unit"]
        )
        rows.append(
            {
                "Источник": f"{source_id} · {source['name']}",
                "Мощность, т/год": source["capacity_t_per_year"],
                "Цена, млн/т": source["variable_cost_mln_per_t"],
                "Плата за резерв": source["reservation_rate_mln_per_t_year_capacity"],
                "Минимальная оплата, %": 100 * source["take_or_pay_share"],
                "Срок поставки": f"{source['lead_time_min_value']:g}–{source['lead_time_max_value']:g} {unit}",
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def render() -> None:
    st.title("Стратегия")
    st.caption("Изменения вступают в силу только после нажатия «Применить», а результаты обновляются после пересчёта.")
    raw = st.session_state.plan
    metadata = case_metadata()
    years = metadata["years"]
    names = source_names(metadata)
    key = plan_hash(raw)

    with st.form(f"strategy-{key}"):
        first, second = st.columns([1, 2])
        plan_id = first.text_input("Название плана", raw.get("plan_id", "operator-plan"))
        notes = second.text_input("Комментарий оператора", raw.get("metadata", {}).get("notes", ""))
        st.caption("Отметьте строку в последнем столбце, чтобы применить изменённые годовые объёмы.")
        annual = st.data_editor(
            _annual_orders(raw, metadata),
            hide_index=True,
            width="stretch",
            column_config={
                "Источник": st.column_config.TextColumn(disabled=True),
                "Название": st.column_config.TextColumn(disabled=True),
                "Распределение": st.column_config.SelectboxColumn(options=list(MODE_VALUES)),
                "Применить годовые итоги": st.column_config.CheckboxColumn(help="Явно преобразовать значения в выбранный режим."),
                **{
                    str(year): st.column_config.NumberColumn(f"{year}, т", min_value=0.0, step=1.0)
                    for year in years
                },
            },
        )
        with st.expander("Расширенный помесячный график", expanded=False):
            st.caption("Строки можно добавлять и удалять. Формат месяца: ГГГГ-ММ.")
            monthly = st.data_editor(
                _monthly_orders(raw),
                hide_index=True,
                num_rows="dynamic",
                width="stretch",
                column_config={
                    "Источник": st.column_config.SelectboxColumn(options=list(names)),
                    "Месяц": st.column_config.TextColumn(),
                    "Заказ, т": st.column_config.NumberColumn(min_value=0.0, step=0.1),
                },
            )
        with st.expander("Резервирование мощности", expanded=False):
            reservations = st.data_editor(
                _reservations(raw, metadata),
                hide_index=True,
                width="stretch",
                column_config={
                    "Источник": st.column_config.TextColumn(disabled=True),
                    "Название": st.column_config.TextColumn(disabled=True),
                    **{
                        str(year): st.column_config.NumberColumn(f"{year}, т/год", min_value=0.0, step=1.0)
                        for year in years
                    },
                },
            )

        with st.expander("Инвестиционные решения", expanded=False):
            investments = {item["investment_id"]: item for item in raw["decisions"]["investments"]}
            cols = st.columns(3)
            with cols[0]:
                zbo = st.checkbox("Хранилище ZBO", investments.get("ZBO", {}).get("enabled", False))
                zbo_date = st.text_input("Месяц ввода ZBO", investments.get("ZBO", {}).get("commissioning_month", "2036-01"))
                st.caption("Инвестиции: 180 млн. Мощность доступна после ввода.")
            with cols[1]:
                earth = st.checkbox("Новый земной канал", investments.get("EARTH_NEW", {}).get("enabled", False))
                earth_buy = st.text_input("Месяц покупки опциона", investments.get("EARTH_NEW", {}).get("option_purchase_month", "2035-01"))
                earth_ex = st.text_input("Месяц исполнения опциона", investments.get("EARTH_NEW", {}).get("option_exercise_month", "2035-02"))
                st.caption("Инвестиции: 90 + 270 млн.")
            with cols[2]:
                lunar = st.checkbox("Лунное производство", investments.get("LUNAR_ISRU", {}).get("enabled", False))
                lunar_date = st.text_input("Месяц финансирования", investments.get("LUNAR_ISRU", {}).get("funding_month", "2035-01"))
                st.caption("Инвестиции: 1 250 млн. Доступность — с 2038 года.")

        stock = raw["decisions"].get("initial_stock_acquisition", {})
        with st.expander("Начальный запас", expanded=False):
            cols = st.columns(3)
            stock_source = cols[0].selectbox(
                "Источник",
                list(names),
                index=list(names).index(stock.get("source_id", next(iter(names)))),
                format_func=lambda value: f"{value} · {names[value]}",
            )
            stock_ordered = cols[1].number_input("Заказано, т", min_value=0.0, value=float(stock.get("ordered_volume_t", 0)), step=0.1)
            stock_reserved = cols[2].number_input("Зарезервировано, т/год", min_value=0.0, value=float(stock.get("reserved_capacity_t_per_year", 0)), step=0.1)
            cols = st.columns(2)
            stock_order_date = cols[0].text_input("Месяц заказа", stock.get("order_date", "2034-01"))
            stock_delivery = cols[1].text_input("Месяц доставки", stock.get("planned_delivery_date", "2035-01"))
            contract_start = cols[0].text_input("Начало контракта", stock.get("contract_period_start", "2034-01"))
            contract_end = cols[1].text_input("Конец контракта", stock.get("contract_period_end", "2034-12"))

        st.subheader("Резерв и аварийные поставки")
        reserve_policy = raw["decisions"].get("inventory_policy", {}).get("reserve_strategy_by_year", {})
        roles = raw["decisions"].get("emergency_role_by_year", {})
        policy_values: dict[str, str] = {}
        role_values: dict[str, str] = {}
        columns = st.columns(min(3, len(years)))
        for index, year in enumerate(years):
            with columns[index % len(columns)]:
                st.markdown(f"**{year}**")
                policy_values[str(year)] = st.selectbox(
                    f"Стратегия резерва {year}",
                    list(RESERVE_LABELS),
                    index=list(RESERVE_LABELS).index(reserve_policy.get(str(year), "physical")),
                    format_func=RESERVE_LABELS.get,
                    key=f"reserve-policy-{key}-{year}",
                )
                role_values[str(year)] = st.selectbox(
                    f"Роль аварийного канала {year}",
                    list(ROLE_LABELS),
                    index=list(ROLE_LABELS).index(roles.get(str(year), "reserve_only")),
                    format_func=ROLE_LABELS.get,
                    key=f"emergency-role-{key}-{year}",
                )
        submitted = st.form_submit_button("Применить решения", type="primary", width="stretch")

    if submitted:
        try:
            updated = copy.deepcopy(raw)
            updated["plan_id"] = plan_id.strip()
            updated.setdefault("metadata", {})["notes"] = notes
            _apply_orders(updated, annual, monthly, years)
            updated["decisions"]["capacity_reservations"] = [
                {"source_id": str(row["Источник"]), "year": year, "reserved_capacity_t": float(row[str(year)])}
                for _, row in reservations.iterrows()
                for year in years
                if float(row[str(year)]) > 0
            ]
            updated["decisions"]["investments"] = [
                ({"investment_id": "EARTH_NEW", "enabled": True, "buy_option": True, "exercise_option": True, "option_purchase_month": earth_buy, "option_exercise_month": earth_ex} if earth else {"investment_id": "EARTH_NEW", "enabled": False, "buy_option": False, "exercise_option": False}),
                ({"investment_id": "LUNAR_ISRU", "enabled": True, "funding_month": lunar_date} if lunar else {"investment_id": "LUNAR_ISRU", "enabled": False}),
                ({"investment_id": "ZBO", "enabled": True, "commissioning_month": zbo_date} if zbo else {"investment_id": "ZBO", "enabled": False}),
            ]
            updated["decisions"]["initial_stock_acquisition"] = {
                "source_id": stock_source,
                "reserved_capacity_t_per_year": stock_reserved,
                "ordered_volume_t": stock_ordered,
                "order_date": stock_order_date,
                "planned_delivery_date": stock_delivery,
                "contract_period_start": contract_start,
                "contract_period_end": contract_end,
                "notes": stock.get("notes", "Начальный запас, оплаченный оператором."),
                "status": "TEAM_DECISION",
            }
            updated["decisions"].setdefault("inventory_policy", {})["reserve_strategy_by_year"] = policy_values
            updated["decisions"]["emergency_role_by_year"] = role_values
            apply_plan(updated)
            st.success("Решения применены. Теперь проверьте и пересчитайте план.")
            st.rerun()
        except Exception as exc:
            render_error(exc, "Не удалось применить решения")

    c1, c2 = st.columns(2)
    if c1.button("Проверить план", width="stretch"):
        st.session_state.validation_result = validate(st.session_state.plan)
    validation = st.session_state.get("validation_result")
    if validation:
        if validation["valid"]:
            st.success("Структура плана валидна. Полная исполнимость определяется расчётом.")
        else:
            for error in validation["errors"]:
                render_error(error, "План не прошёл структурную проверку")
    c2.caption("После проверки нажмите «Пересчитать» слева.")

    with st.expander("Справочник источников и детали контрактов"):
        st.subheader("Источники")
        _source_cards(metadata)
        st.subheader("Контракты")
        if is_dirty():
            st.warning("Таблица относится к последнему расчёту и может быть устаревшей.")
        contract_plan = st.session_state.calculated_plan if is_dirty() else st.session_state.plan
        contracts = contract_rows(contract_plan, metadata, st.session_state.result["BASE"])
        st.dataframe(pd.DataFrame(contracts), hide_index=True, width="stretch")
        st.subheader("Календарь инвестиций")
        st.dataframe(pd.DataFrame(investment_timeline(st.session_state.plan, metadata)), hide_index=True, width="stretch")
