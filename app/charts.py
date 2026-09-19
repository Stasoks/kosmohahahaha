"""Plotly figures built only from authoritative result rows."""
from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from app.view_models import source_colors


CASE_COLORS = {"A": "#5B4BFF", "B": "#FDAEAD", "C": "#278D8D"}


def style(fig: go.Figure, height: int = 360) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=54, r=22, t=58, b=62),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#ffffff",
        font=dict(family="Inter, system-ui, sans-serif", color="#332e37", size=12),
        title=dict(x=0.02, xanchor="left", y=0.97, font=dict(size=17)),
        legend=dict(orientation="h", yanchor="top", y=-0.18, x=0, title_text=""),
        hoverlabel=dict(bgcolor="#17151a", font_color="white"),
    )
    fig.update_xaxes(gridcolor="#eeeaf1", zeroline=False, automargin=True)
    fig.update_yaxes(gridcolor="#eeeaf1", zeroline=False, automargin=True)
    return fig


def demand_service(result: dict[str, Any]) -> go.Figure:
    df = pd.DataFrame(result["annual"])
    custom = df[["demand_critical_t", "served_critical_t", "critical_shortage_t"]]
    fig = go.Figure()
    for field, label, color in (
        ("demand_total_t", "Общий спрос", "#DCC5F1"),
        ("served_total_t", "Обслужено", "#5B4BFF"),
        ("shortage_t", "Дефицит", "#FDAEAD"),
    ):
        fig.add_bar(
            x=df.year,
            y=df[field],
            name=label,
            marker_color=color,
            customdata=custom,
            hovertemplate=(
                "%{x}<br>" + label + ": %{y:.2f} т"
                "<br>Критический спрос: %{customdata[0]:.2f} т"
                "<br>Критически обслужено: %{customdata[1]:.2f} т"
                "<br>Критический дефицит: %{customdata[2]:.2f} т<extra></extra>"
            ),
        )
    fig.update_layout(title="Хватает ли поставок, чтобы покрыть спрос?", barmode="group", yaxis_title="т")
    return style(fig)


def inventory(result: dict[str, Any]) -> go.Figure:
    monthly = pd.DataFrame(result["monthly"])
    annual = pd.DataFrame(result["annual"]).copy()
    annual["jan"] = annual["year"].astype(str) + "-01"
    annual["reserve_ok"] = annual["reserve_actual_days"].astype(float) >= 45 - 1e-9

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=monthly.month,
            y=monthly.closing_inventory_t,
            name="Физический запас на конец месяца",
            fill="tozeroy",
            line=dict(color="#5B4BFF", width=2),
            hovertemplate="%{x}<br>Запас на конец месяца: %{y:.2f} т<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=monthly.month,
            y=monthly.active_storage_capacity_t,
            name="Доступная ёмкость хранилища",
            line=dict(color="#17151A", dash="dot"),
            hovertemplate="%{x}<br>Ёмкость: %{y:.2f} т<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=annual.jan,
            y=annual.reserve_requirement_t,
            name="Нужно на 45 дней к началу года",
            mode="lines+markers",
            line=dict(color="#9B72FF", dash="dash"),
            marker=dict(size=8),
            hovertemplate="%{x}<br>Требуемый запас: %{y:.2f} т<extra></extra>",
        )
    )

    marker_colors = [
        "#278D63" if bool(ok) else "#D06B6B"
        for ok in annual.reserve_ok
    ]
    marker_symbols = [
        "circle" if bool(ok) else "x"
        for ok in annual.reserve_ok
    ]
    custom = annual[["reserve_actual_days", "reserve_requirement_t"]]
    fig.add_trace(
        go.Scatter(
            x=annual.jan,
            y=annual.opening_inventory_t,
            name="Фактический запас на начало года",
            mode="markers",
            marker=dict(
                color=marker_colors,
                symbol=marker_symbols,
                size=12,
                line=dict(width=1, color="#ffffff"),
            ),
            customdata=custom,
            hovertemplate=(
                "%{x}<br>Запас на начало года: %{y:.2f} т"
                "<br>Покрытие: %{customdata[0]:.1f} дней"
                "<br>Нужно на 45 дней: %{customdata[1]:.2f} т<extra></extra>"
            ),
        )
    )

    zero_rows = monthly[monthly.closing_inventory_t.astype(float) <= 1e-9]
    if not zero_rows.empty:
        first_zero = zero_rows.iloc[0]
        fig.add_annotation(
            x=first_zero.month,
            y=0,
            text="запас исчерпан",
            showarrow=True,
            arrowhead=2,
            ax=0,
            ay=-45,
            font=dict(color="#9A3E1A"),
        )

    fig.update_layout(
        title="Хватает ли физического запаса на 45 дней к началу каждого года?",
        yaxis_title="т",
    )
    return style(fig)

def supply_mix(result: dict[str, Any], names: dict[str, str]) -> go.Figure:
    df = pd.DataFrame(result["sources"])
    df["Источник"] = df.source_id.map(lambda value: f"{value} · {names.get(value, value)}")
    colors = source_colors(list(names))
    named_colors = {f"{key} · {value}": colors[key] for key, value in names.items()}
    fig = px.bar(
        df,
        x="year",
        y="gross_delivery_t",
        color="Источник",
        barmode="stack",
        color_discrete_map=named_colors,
        labels={"gross_delivery_t": "Доставлено, т", "year": "Год"},
        title="От каких источников зависит снабжение?",
    )
    fig.update_traces(hovertemplate="%{fullData.name}<br>%{x}: %{y:.2f} т<extra></extra>")
    return style(fig)


def costs(result: dict[str, Any]) -> go.Figure:
    df = pd.DataFrame(result["costs"])
    fields = (
        ("procurement_mln", "Закупка", "#5B4BFF"),
        ("reservation_mln", "Резерв мощности", "#9B72FF"),
        ("capex_mln", "Инвестиции", "#242129"),
        ("fixed_opex_mln", "Постоянные расходы", "#DCA4C0"),
        ("holding_mln", "Хранение", "#FDAEAD"),
        ("take_or_pay_effect_in_procurement_mln", "Доплата до минимума", "#D07A35"),
    )
    fig = go.Figure()
    for field, label, color in fields:
        if field in df and (df[field].abs() > 1e-12).any():
            fig.add_bar(
                x=df.year,
                y=df[field],
                name=label,
                marker_color=color,
                hovertemplate=f"%{{x}}<br>{label}: %{{y:.2f}} млн у.е.<extra></extra>",
            )
    fig.update_layout(title="Из чего складывается стоимость стратегии?", barmode="stack", yaxis_title="млн у.е.")
    return style(fig)


def service(result: dict[str, Any], scenario_id: str) -> go.Figure:
    df = pd.DataFrame(result["annual"])
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df.year,
            y=df.total_service_level * 100,
            name="Общий сервис",
            mode="lines+markers",
            line=dict(color="#5B4BFF", width=3),
            hovertemplate="%{x}: %{y:.2f}%<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df.year,
            y=df.critical_service_level * 100,
            name="Критический сервис",
            mode="lines+markers",
            line=dict(color="#17151A", width=2),
            hovertemplate="%{x}: %{y:.2f}%<extra></extra>",
        )
    )
    label = "обязательный минимум" if scenario_id == "BASE" else "ориентир устойчивости"
    fig.add_hline(y=97, line_dash="dash", line_color="#9B72FF", annotation_text=f"97% · {label}")
    fig.add_hline(y=99, line_dash="dot", line_color="#D06B6B", annotation_text=f"99% · {label}")
    fig.update_layout(title="Выполняются ли требования по сервису каждый год?", yaxis_title="%")
    return style(fig)


def abc_metric(rows: list[dict[str, Any]], field: str, title: str, unit: str) -> go.Figure:
    df = pd.DataFrame(rows).copy()
    labels = {
        "A": "Ваш план<br>обычные условия",
        "B": "Ваш план<br>стресс",
        "C": "Адаптация<br>стресс",
    }
    df["display_case"] = df.case.map(lambda value: labels.get(value, value))
    fig = go.Figure(
        go.Bar(
            x=df.display_case,
            y=df[field],
            marker_color=[CASE_COLORS[item] for item in df.case],
            text=[f"{value:.2f}" for value in df[field]],
            textposition="outside",
            customdata=df.label,
            hovertemplate=f"%{{customdata}}<br>%{{y:.2f}} {unit}<extra></extra>",
        )
    )
    fig.update_layout(title=title, showlegend=False, yaxis_title=unit)
    return style(fig, 320)


def sensitivity_lines(points: list[dict[str, Any]], title: str) -> tuple[go.Figure, go.Figure]:
    df = pd.DataFrame(points).copy()

    numeric_values: list[float] = []
    numeric_axis = True
    for value in df.value:
        try:
            numeric_values.append(float(value))
        except (TypeError, ValueError):
            numeric_axis = False
            break

    if numeric_axis:
        df["plot_value"] = numeric_values
        x_title = title
        service_title = "Когда изменение параметра начинает ухудшать обслуживание?"
    else:
        df["plot_value"] = df.value.astype(str)
        x_title = (
            "Официальный уровень спроса"
            if title == "official_demand_point"
            else title
        )
        service_title = (
            "Как план работает при официальных LOW / BASE / HIGH уровнях спроса?"
            if title == "official_demand_point"
            else "Как меняется обслуживание между проверяемыми вариантами?"
        )

    service_fig = go.Figure()
    service_fig.add_trace(
        go.Scatter(
            x=df.plot_value,
            y=df.total_service_level * 100,
            name="Общий сервис",
            mode="lines+markers",
            line=dict(color="#5B4BFF", width=3),
        )
    )
    service_fig.add_trace(
        go.Scatter(
            x=df.plot_value,
            y=df.critical_service_level * 100,
            name="Критический сервис",
            mode="lines+markers",
            line=dict(color="#17151A", width=2),
        )
    )
    service_fig.add_hrect(
        y0=0,
        y1=97,
        fillcolor="#FDAEAD",
        opacity=0.08,
        line_width=0,
    )
    service_fig.add_hline(
        y=97,
        line_dash="dash",
        annotation_text="97% · общий минимум BASE",
    )
    service_fig.add_hline(
        y=99,
        line_dash="dot",
        annotation_text="99% · критический минимум BASE",
    )

    if numeric_axis:
        if any(abs(value - 1.0) <= 1e-12 for value in numeric_values):
            service_fig.add_vline(
                x=1.0,
                line_dash="dot",
                line_color="#6D6673",
                annotation_text="исходное значение",
            )
        failing = df[df.valid == False]  # noqa: E712
        if not failing.empty:
            service_fig.add_vline(
                x=float(failing.iloc[0].plot_value),
                line_dash="dash",
                line_color="#D06B6B",
                annotation_text="первое нарушение",
            )
    else:
        failing = df[df.valid == False]  # noqa: E712
        if not failing.empty:
            service_fig.add_trace(
                go.Scatter(
                    x=failing.plot_value,
                    y=failing.total_service_level * 100,
                    mode="markers",
                    name="Есть нарушение",
                    marker=dict(
                        color="#D06B6B",
                        symbol="x",
                        size=13,
                    ),
                    hovertemplate="%{x}<br>Этот вариант содержит нарушение<extra></extra>",
                )
            )

    service_fig.update_layout(
        title=service_title,
        xaxis_title=x_title,
        yaxis_title="Сервис, %",
    )

    impact = go.Figure()
    impact.add_trace(
        go.Bar(
            x=df.plot_value,
            y=df.total_shortage_t,
            name="Дефицит, т",
            marker_color="#FDAEAD",
        )
    )
    impact.add_trace(
        go.Scatter(
            x=df.plot_value,
            y=df.total_cost_mln,
            name="Стоимость, млн",
            yaxis="y2",
            mode="lines+markers",
            line=dict(color="#5B4BFF", width=3),
        )
    )
    impact.update_layout(
        title="Как меняются дефицит и стоимость?",
        xaxis_title=x_title,
        yaxis_title="Дефицит, т",
        yaxis2=dict(
            overlaying="y",
            side="right",
            title="Стоимость, млн у.е.",
        ),
    )
    return style(service_fig), style(impact)

def reverse_zone(data: dict[str, Any]) -> go.Figure:
    df = pd.DataFrame(data.get("evaluated_points", []))
    colors = ["#278D8D" if bool(item) else "#D06B6B" for item in df.valid]
    fig = go.Figure(
        go.Scatter(
            x=df.value,
            y=df.total_service_level * 100,
            mode="lines+markers",
            marker=dict(color=colors, size=10),
            line=dict(color="#5B4BFF"),
            hovertemplate="Параметр %{x}<br>Общий сервис %{y:.2f}%<extra></extra>",
        )
    )
    first_fail = data.get("first_failing_value")
    last_safe = data.get("last_safe_value")
    if last_safe is not None:
        fig.add_vrect(
            x0=float(df.value.min()) if not df.empty else last_safe,
            x1=last_safe,
            fillcolor="#278D8D",
            opacity=0.08,
            line_width=0,
            annotation_text="проверенная безопасная зона",
            annotation_position="top left",
        )
    if first_fail is not None:
        fig.add_vline(
            x=first_fail,
            line_dash="dash",
            line_color="#D06B6B",
            annotation_text="первый отказ",
        )
        if not df.empty:
            fig.add_vrect(
                x0=first_fail,
                x1=float(df.value.max()),
                fillcolor="#FDAEAD",
                opacity=0.10,
                line_width=0,
                annotation_text="зона нарушений",
                annotation_position="top right",
            )
    fig.update_layout(
        title="Где план впервые перестаёт выполнять ограничения?",
        xaxis_title="Проверяемое значение параметра",
        yaxis_title="Общий сервис, %",
    )
    return style(fig, 380)

def alternatives(rows: list[dict[str, Any]]) -> go.Figure:
    df = pd.DataFrame(rows).copy()
    df["Дефицит в стрессе, т"] = df.stress_shortage_t
    df["Стоимость, млн"] = df.base_cost_mln
    fig = px.scatter(
        df,
        x="Стоимость, млн",
        y="Дефицит в стрессе, т",
        size="base_capex_mln",
        hover_name="plan_id",
        text="plan_id",
        labels={
            "Стоимость, млн": "Стоимость в BASE, млн у.е.",
            "Дефицит в стрессе, т": "Дефицит того же плана в обязательном стрессе, т",
        },
        title="Сколько стоит устойчивость альтернатив?",
    )
    fig.update_traces(textposition="top center")
    fig.add_hline(
        y=0,
        line_dash="dot",
        line_color="#278D8D",
        annotation_text="без дефицита",
    )
    return style(fig, 430)


def risk_impact(rows: list[dict[str, Any]]) -> go.Figure:
    """Show calculated physical consequence instead of an opaque likelihood matrix."""

    df = pd.DataFrame(rows).copy()
    if df.empty:
        return style(go.Figure(), 320)
    df = df.sort_values(
        ["critical_shortage_delta_t", "shortage_delta_t"],
        ascending=[True, True],
    )
    fig = go.Figure()
    fig.add_bar(
        y=df["risk_name"],
        x=df["shortage_delta_t"],
        name="Доп. общий дефицит, т",
        orientation="h",
        marker_color="#FDAEAD",
    )
    fig.add_bar(
        y=df["risk_name"],
        x=df["critical_shortage_delta_t"],
        name="Доп. критический дефицит, т",
        orientation="h",
        marker_color="#D06B6B",
    )
    fig.update_layout(
        barmode="group",
        title="Какие риски сильнее всего ухудшают физическое снабжение?",
        xaxis_title="Изменение дефицита относительно выбранной среды, т",
        yaxis_title="",
    )
    return style(fig, max(360, 44 * len(df) + 120))