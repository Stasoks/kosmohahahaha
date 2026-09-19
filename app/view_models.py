"""Pure transformations from backend payloads to UI-ready view models."""
from __future__ import annotations

import copy
from collections import defaultdict
from typing import Any

from app.formatting import yes_no


OFFICIAL_SOURCE_COLORS = {
    "A": "#242129",
    "B": "#5B4BFF",
    "C": "#9B72FF",
    "D": "#DCA4C0",
    "E": "#FDAEAD",
}
RESEARCH_COLORS = (
    "#278D8D",
    "#D07A35",
    "#3976C6",
    "#8B5D33",
    "#2F8F57",
    "#B25385",
    "#667085",
)

CONSTRAINT_LABELS = {
    "BASE_CRITICAL_SERVICE": "Минимальный сервис критического спроса",
    "BASE_TOTAL_SERVICE": "Минимальный общий сервис",
    "CAPEX_2037": "Лимит инвестиций до конца 2037 года",
    "CAPEX_2040": "Общий лимит инвестиций до 2040 года",
    "RESERVE_45D": "Резерв на 45 дней",
    "EMERGENCY_BASE_STREAK": "Ограничение постоянного использования аварийного канала",
    "STRESS_LOSS_LIMIT": "Предел потерь в стрессовом сценарии",
}

SEVERITY_LABELS = {"hard": "Критическое", "benchmark": "Ориентир", "warning": "Предупреждение"}


def constraint_label(value: Any) -> str:
    key = str(value or "")
    return CONSTRAINT_LABELS.get(key, key or "Неизвестное ограничение")


def source_colors(source_ids: list[str] | tuple[str, ...]) -> dict[str, str]:
    result = dict(OFFICIAL_SOURCE_COLORS)
    extra = sorted(item for item in source_ids if item not in result)
    for index, source_id in enumerate(extra):
        result[source_id] = RESEARCH_COLORS[index % len(RESEARCH_COLORS)]
    return {source_id: result[source_id] for source_id in source_ids}


def source_names(metadata: dict[str, Any]) -> dict[str, str]:
    return {
        source_id: str(source.get("name", source_id))
        for source_id, source in metadata["sources"].items()
    }


def minimum_annual_metrics(result: dict[str, Any]) -> dict[str, Any]:
    annual = result.get("annual", [])
    summary = result.get("summary", {})
    capex_2037 = sum(float(row.get("capex_mln", 0)) for row in annual if int(row["year"]) <= 2037)
    capex_total = sum(float(row.get("capex_mln", 0)) for row in annual)
    served = sum(float(row.get("served_total_t", 0)) for row in annual)
    return {
        "valid": bool(summary.get("valid")),
        "minimum_annual_total_service": min(
            (float(row["total_service_level"]) for row in annual), default=0.0
        ),
        "minimum_annual_critical_service": min(
            (float(row["critical_service_level"]) for row in annual), default=0.0
        ),
        "total_shortage_t": float(summary.get("total_shortage_t", 0)),
        "critical_shortage_t": float(summary.get("critical_shortage_t", 0)),
        "minimum_reserve_days": min(
            (float(row["reserve_actual_days"]) for row in annual), default=0.0
        ),
        "capex_through_2037_mln": capex_2037,
        "total_capex_mln": capex_total,
        "undiscounted_cost_mln": float(summary.get("undiscounted_cost_mln", 0)),
        "discounted_cost_mln": float(summary.get("discounted_cost_mln", 0)),
        "cost_per_served_ton_mln": float(summary.get("cost_per_served_ton_mln", 0)),
        "minimum_inventory_t": float(summary.get("minimum_inventory_t", 0)),
        "served_total_t": served,
        "hard_violation_count": int(summary.get("hard_violation_count", 0)),
        "scenario_id": str(summary.get("scenario_id", "")),
    }


def violations_view(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in result.get("violations", []):
        value = copy.deepcopy(item)
        rows.append(
            {
                "Уровень": SEVERITY_LABELS.get(str(value.get("severity", "warning")), "Предупреждение"),
                "Ограничение": constraint_label(value.get("constraint_id") or value.get("code")),
                "Период": value.get("period", "—"),
                "Источник": value.get("source_id") or "—",
                "Факт": value.get("actual"),
                "Условие": value.get("operator", ""),
                "Лимит": value.get("limit"),
                "Разрыв": value.get("excess_or_gap"),
                "Единица": {"share": "доля", "days": "дни", "years": "годы", "mln_units": "млн у.е."}.get(value.get("unit"), value.get("unit", "")),
            }
        )
    return rows


def top_problems(result: dict[str, Any], limit: int = 3) -> list[dict[str, Any]]:
    order = {"hard": 0, "benchmark": 1, "warning": 2}
    values = sorted(
        result.get("violations", []),
        key=lambda item: (
            order.get(str(item.get("severity", "warning")), 3),
            -abs(float(item.get("excess_or_gap", 0) or 0)),
            str(item.get("period", "")),
        ),
    )
    return [copy.deepcopy(item) for item in values[:limit]]


def source_mix(result: dict[str, Any]) -> dict[str, float]:
    output: dict[str, float] = defaultdict(float)
    for row in result.get("sources", []):
        output[str(row["source_id"])] += float(row.get("gross_delivery_t", 0))
    return dict(output)


def abc_comparison(payload: dict[str, Any]) -> dict[str, Any]:
    cases = {
        "A": ("Текущий план · обычные условия", payload.get("A")),
        "B": ("Тот же план · стресс", payload.get("B")),
        "C": ("Адаптированный план · стресс", payload.get("C")),
    }
    rows = []
    metrics: dict[str, dict[str, Any]] = {}
    for key, (label, result) in cases.items():
        if result is None:
            continue
        item = minimum_annual_metrics(result)
        item["source_mix_t"] = source_mix(result)
        metrics[key] = item
        rows.append({"case": key, "label": label, **item})

    def delta(left: str, right: str, label: str) -> dict[str, Any] | None:
        if left not in metrics or right not in metrics:
            return None
        before, after = metrics[left], metrics[right]
        return {
            "label": label,
            "total_service_pp": 100
            * (
                after["minimum_annual_total_service"]
                - before["minimum_annual_total_service"]
            ),
            "critical_service_pp": 100
            * (
                after["minimum_annual_critical_service"]
                - before["minimum_annual_critical_service"]
            ),
            "shortage_t": after["total_shortage_t"] - before["total_shortage_t"],
            "critical_shortage_t": (
                after["critical_shortage_t"] - before["critical_shortage_t"]
            ),
            "cost_mln": after["undiscounted_cost_mln"] - before["undiscounted_cost_mln"],
        }

    return {
        "rows": rows,
        "metrics": metrics,
        "stress_effect": delta("A", "B", "Эффект стресса B − A"),
        "adaptation_effect": delta("B", "C", "Эффект адаптации C − B"),
    }


def _annual_orders(plan: dict[str, Any]) -> dict[tuple[str, int], float]:
    values: dict[tuple[str, int], float] = defaultdict(float)
    for item in plan.get("decisions", {}).get("supply_orders", []):
        source_id = str(item["source_id"])
        for period, amount in item.get("values", {}).items():
            values[(source_id, int(str(period)[:4]))] += float(amount)
    return dict(values)


def _reservations(plan: dict[str, Any]) -> dict[tuple[str, int], float]:
    return {
        (str(item["source_id"]), int(item["year"])): float(item["reserved_capacity_t"])
        for item in plan.get("decisions", {}).get("capacity_reservations", [])
    }


def _investment_summary(value: dict[str, Any]) -> str:
    if not value.get("enabled"):
        return "Не выбран"
    parts = ["Выбран"]
    for field, label in (
        ("option_purchase_month", "покупка опциона"),
        ("option_exercise_month", "исполнение опциона"),
        ("funding_month", "финансирование"),
        ("commissioning_month", "ввод"),
    ):
        if value.get(field):
            parts.append(f"{label}: {value[field]}")
    return "; ".join(parts)


def _decision_summary(key: str, value: dict[str, Any]) -> str:
    if key == "inventory_policy":
        values = value.get("reserve_strategy_by_year", value)
        labels = {"physical": "физический запас", "emergency_contract": "аварийный контракт"}
    else:
        values = value
        labels = {"reserve_only": "только резерв", "planned_supply": "плановые поставки"}
    return "; ".join(f"{year}: {labels.get(mode, mode)}" for year, mode in sorted(values.items()))


def decision_diff(base_plan: dict[str, Any], stress_plan: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    base_decisions = base_plan.get("decisions", {})
    stress_decisions = stress_plan.get("decisions", {})
    base_investments = {
        str(item["investment_id"]): item for item in base_decisions.get("investments", [])
    }
    stress_investments = {
        str(item["investment_id"]): item for item in stress_decisions.get("investments", [])
    }
    for investment_id in sorted(set(base_investments) | set(stress_investments)):
        before = base_investments.get(investment_id, {})
        after = stress_investments.get(investment_id, {})
        if before != after:
            rows.append(
                {
                    "Категория": "Инвестиции",
                    "Объект": investment_id,
                    "Обычный план": _investment_summary(before),
                    "Адаптированный план": _investment_summary(after),
                    "Изменение": "Изменены решение или сроки",
                }
            )
    before_orders, after_orders = _annual_orders(base_plan), _annual_orders(stress_plan)
    for source_id, year in sorted(set(before_orders) | set(after_orders)):
        before, after = before_orders.get((source_id, year), 0.0), after_orders.get((source_id, year), 0.0)
        if abs(before - after) > 1e-8:
            rows.append(
                {
                    "Категория": "Заказы",
                    "Объект": f"{source_id} · {year}",
                    "Обычный план": f"{before:.3f} т",
                    "Адаптированный план": f"{after:.3f} т",
                    "Изменение": f"{after - before:+.3f} т",
                }
            )
    before_res, after_res = _reservations(base_plan), _reservations(stress_plan)
    for source_id, year in sorted(set(before_res) | set(after_res)):
        before, after = before_res.get((source_id, year), 0.0), after_res.get((source_id, year), 0.0)
        if abs(before - after) > 1e-8:
            rows.append(
                {
                    "Категория": "Резерв мощности",
                    "Объект": f"{source_id} · {year}",
                    "Обычный план": f"{before:.3f} т/год",
                    "Адаптированный план": f"{after:.3f} т/год",
                    "Изменение": f"{after - before:+.3f} т/год",
                }
            )
    for key, label in (
        ("inventory_policy", "Политика резерва"),
        ("emergency_role_by_year", "Роль аварийного канала"),
    ):
        before, after = base_decisions.get(key, {}), stress_decisions.get(key, {})
        if before != after:
            rows.append(
                {
                    "Категория": label,
                    "Объект": "по годам",
                    "Обычный план": _decision_summary(key, before),
                    "Адаптированный план": _decision_summary(key, after),
                    "Изменение": "Изменено",
                }
            )
    return rows


def contract_rows(
    plan: dict[str, Any], metadata: dict[str, Any], result: dict[str, Any]
) -> list[dict[str, Any]]:
    orders = _annual_orders(plan)
    reservations = _reservations(plan)
    result_index = {
        (str(row["source_id"]), int(row["year"])): row
        for row in result.get("sources", [])
    }
    roles = plan.get("decisions", {}).get("emergency_role_by_year", {})
    rows = []
    for source_id, source in metadata["sources"].items():
        for year in metadata["years"]:
            calculated = result_index.get((source_id, year), {})
            reserved = reservations.get((source_id, year), 0.0)
            ordered = orders.get((source_id, year), 0.0)
            if not any((reserved, ordered, calculated.get("gross_delivery_t", 0))):
                continue
            lead = f"{source['lead_time_min_value']:g}"
            if source["lead_time_max_value"] != source["lead_time_min_value"]:
                lead += f"–{source['lead_time_max_value']:g}"
            unit = {
                "month": "мес.", "week": "нед.", "day": "дн.", "year": "г.",
            }.get(source["lead_time_unit"], source["lead_time_unit"])
            lead += f" {unit}"
            rows.append(
                {
                    "Источник": f"{source_id} · {source['name']}",
                    "Год": year,
                    "Резерв, т/год": reserved,
                    "Заказ, т": ordered,
                    "Доставлено, т": calculated.get("gross_delivery_t", 0.0),
                    "Срок поставки": lead,
                    "Цена, млн/т": calculated.get(
                        "active_variable_price_mln_per_t", source["variable_cost_mln_per_t"]
                    ),
                    "Плата резерва, млн": calculated.get("reservation_cost_mln", 0.0),
                    "Минимальная оплата": source["take_or_pay_share"],
                    "Роль": {
                        "reserve_only": "Только резерв",
                        "planned_supply": "Плановые поставки",
                    }.get(
                        roles.get(str(year), "reserve_only") if source_id == "E" else "planned_supply",
                        "Не задана",
                    ),
                    "Утилизация": calculated.get("utilization", 0.0),
                    "Ответственный": "не задан организаторами",
                }
            )
    return rows


def investment_timeline(plan: dict[str, Any], metadata: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in plan.get("decisions", {}).get("investments", []):
        investment_id = str(item["investment_id"])
        case = metadata["investments"].get(investment_id, {})
        events = []
        for field, label in (
            ("commissioning_month", "Ввод"),
            ("option_purchase_month", "Покупка опциона"),
            ("option_exercise_month", "Исполнение опциона"),
            ("funding_month", "Финансирование"),
        ):
            if item.get(field):
                events.append(f"{label}: {item[field]}")
        rows.append(
            {
                "Инвестиция": investment_id,
                "Решение принято": bool(item.get("enabled")),
                "События": "; ".join(events) or "—",
                "Инвестиции, млн у.е.": case.get("total_capex_mln", 0.0) if item.get("enabled") else 0.0,
                "Доступность / ввод": {
                    "EARTH_NEW": "Через 18–24 месяца после исполнения опциона",
                    "LUNAR_ISRU": "Финансирование до 2038 года; доступность с 2038 года",
                    "ZBO": "Опция доступна с 2036 года",
                }.get(investment_id, "Не задано"),
                "Зависимость": metadata["sources"].get(
                    next(
                        (
                            source_id
                            for source_id, source in metadata["sources"].items()
                            if source.get("availability_rule", {}).get("investment_id") == investment_id
                        ),
                        "",
                    ),
                    {},
                ).get("name", "Хранилище" if investment_id == "ZBO" else "—"),
                "Комментарий": "Решение не означает мгновенную доступность мощности",
            }
        )
    return rows


def stakeholder_scenario_rows(
    stakeholder_config: dict[str, Any], abc: dict[str, Any]
) -> list[dict[str, Any]]:
    metrics = abc_comparison(abc)["metrics"]
    rows = []
    for participant in stakeholder_config.get("participants", []):
        stakeholder_id = participant["stakeholder_id"]
        row = {
            "Сторона": participant["name"],
            "Интересы": "; ".join(participant.get("interests", [])),
            "Кто несёт затраты": "; ".join(participant.get("cost_bearer", [])) or "не задано",
            "Кто несёт риск": "; ".join(participant.get("risk_bearer", [])) or "не задано",
        }
        for case_id in ("A", "B", "C"):
            item = metrics.get(case_id)
            if item is None:
                row[case_id] = "—"
            elif stakeholder_id == "operator":
                row[case_id] = (
                    f"исполним={yes_no(item['valid'])}; стоимость={item['undiscounted_cost_mln']:.1f}; "
                    f"резерв={item['minimum_reserve_days']:.1f} дн."
                )
            elif stakeholder_id == "critical_consumers":
                row[case_id] = (
                    f"мин. сервис={100*item['minimum_annual_critical_service']:.1f}%; "
                    f"дефицит={item['critical_shortage_t']:.1f} т"
                )
            elif stakeholder_id == "commercial_consumers":
                noncritical = item["total_shortage_t"] - item["critical_shortage_t"]
                row[case_id] = (
                    f"мин. общий сервис={100*item['minimum_annual_total_service']:.1f}%; "
                    f"некритический дефицит={noncritical:.1f} т"
                )
            elif stakeholder_id == "fuel_suppliers":
                row[case_id] = "; ".join(
                    f"{key}={value:.1f} т" for key, value in item["source_mix_t"].items()
                )
            elif stakeholder_id == "financing":
                row[case_id] = (
                    f"инвестиции={item['total_capex_mln']:.1f}; приведённая стоимость={item['discounted_cost_mln']:.1f}"
                )
            else:
                row[case_id] = "Последствия определяются рассчитанными сроками и поставками"
        rows.append(row)
    return rows
