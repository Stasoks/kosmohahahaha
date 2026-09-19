"""Reusable Streamlit presentation components."""
from __future__ import annotations

import json
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.formatting import mass, money, percent
from app.kernel_bridge import service_error
from app.view_models import SEVERITY_LABELS, constraint_label, minimum_annual_metrics, top_problems, violations_view


def inject_styles() -> None:
    st.markdown(
        """
<style>
:root { --ink:#17151a; --paper:#fbfafc; --violet:#5b4bff; --purple:#9b72ff; --lav:#dcc5f1; --coral:#fdaead; --green:#278d63; }
.stApp { background:radial-gradient(circle at 92% 0%,rgba(220,197,241,.27),transparent 30rem),var(--paper);color:var(--ink); }
html,body,[class*="css"] { font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
h1,h2,h3 { font-family:Manrope,Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;letter-spacing:-.035em;color:var(--ink); }
[data-testid="stSidebar"] { background:#17151a;border-right:0; }
[data-testid="stSidebar"] p,[data-testid="stSidebar"] label,[data-testid="stSidebar"] h1,[data-testid="stSidebar"] h2,[data-testid="stSidebar"] h3,[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] { color:#f8f7fb; }
[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] *,
[data-testid="stSidebar"] details summary,
[data-testid="stSidebar"] details summary * { color:#d8d2de!important;opacity:1!important; }
[data-testid="stSidebar"] code { color:#ddd2ff!important;background:#28242d!important;border-radius:.3rem;padding:.05rem .25rem; }
[data-testid="stSidebar"] hr { border-color:#3c3542!important;opacity:1!important; }
[data-testid="stSidebar"] input,[data-testid="stSidebar"] textarea { color:#17151a!important;background:#fff!important; }
[data-testid="stSidebar"] [data-baseweb="select"] * { color:#17151a!important;opacity:1!important; }
[data-testid="stSidebar"] [data-baseweb="select"] input { color:#17151a!important; }
[data-testid="stSidebar"] [data-testid="stAlert"] p { color:#17151a!important;opacity:1!important; }
[data-testid="stSidebar"] .stButton button:not([kind="primary"]),
[data-testid="stSidebar"] .stDownloadButton button {
    background:#27232c!important;
    border-color:#4b4352!important;
    color:#f8f7fb!important;
}
[data-testid="stSidebar"] .stButton button:not([kind="primary"]) p,
[data-testid="stSidebar"] .stButton button:not([kind="primary"]) span,
[data-testid="stSidebar"] .stDownloadButton button p,
[data-testid="stSidebar"] .stDownloadButton button span { color:#f8f7fb!important;opacity:1!important; }
[data-testid="stSidebar"] .stButton button:not([kind="primary"]):hover,
[data-testid="stSidebar"] .stDownloadButton button:hover {
    background:#342f3a!important;
    border-color:#70647b!important;
}
[data-testid="stSidebar"] .stButton button[kind="primary"] { background:#5b4bff!important;border-color:#6e61ff!important; }
[data-testid="stSidebar"] .stButton button[kind="primary"] p,
[data-testid="stSidebar"] .stButton button[kind="primary"] span { color:#fff!important;opacity:1!important; }
[data-testid="stSidebar"] button:disabled { opacity:.58!important; }
[data-testid="stSidebar"] .stRadio label { padding:.42rem .6rem;border-radius:.65rem; }
[data-testid="stSidebar"] .stRadio label:hover { background:#28242d; }
.brand { font-size:1.32rem;font-weight:800;margin:.25rem 0 1.25rem;letter-spacing:-.04em; }
.brand b { color:#b89cff; }.brand small { display:block;color:#aaa3b0;font-size:.62rem;letter-spacing:.16em;margin-top:.22rem; }
.eyebrow { font-size:.66rem;font-weight:800;letter-spacing:.14em;text-transform:uppercase;color:#6d6673;margin-bottom:.45rem; }
.hero { border:1px solid #ded9e3;border-radius:1.25rem;padding:1.75rem 2rem;background:linear-gradient(115deg,#fff 48%,#eee6fb);margin-bottom:1rem;position:relative;overflow:hidden; }
.hero:after { content:'✦';position:absolute;right:4%;top:-38%;font-size:11rem;color:rgba(91,75,255,.10);transform:rotate(12deg); }
.hero h1 { font-size:clamp(2rem,4vw,3.8rem);line-height:.97;margin:.15rem 0 .65rem;max-width:850px; }
.hero h1 span { color:var(--violet); }.hero p { max-width:760px;color:#625c67;font-size:1rem;margin-bottom:0; }
.statusbar { display:flex;gap:.55rem;align-items:center;flex-wrap:wrap;margin:.3rem 0 1rem; }
.pill { display:inline-flex;gap:.38rem;align-items:center;padding:.34rem .65rem;border-radius:999px;background:#f1edf5;border:1px solid #ddd5e5;font-size:.72rem;font-weight:750; }
.pill.ok { background:#e5f8ee;border-color:#b9e7ca;color:#17653a; }.pill.warn { background:#fff1ea;border-color:#f5c7b4;color:#9a3e1a; }.pill.blue { background:#eeecff;color:#4939db;border-color:#d5d0ff; }
.badge { display:inline-block;border-radius:999px;padding:.18rem .48rem;margin-right:.25rem;font-size:.62rem;font-weight:800;letter-spacing:.05em;border:1px solid #d8d1df;background:#f5f1f8; }
.badge.case { color:#4939db;background:#eeecff;border-color:#d5d0ff; }.badge.team { color:#9b3e69;background:#fff0f7;border-color:#f1cadc; }.badge.result { color:#17653a;background:#e5f8ee;border-color:#b9e7ca; }.badge.benchmark { color:#8a4b15;background:#fff4df;border-color:#edcf97; }
[data-testid="stMetric"] { border:1px solid #ded9e3;background:rgba(255,255,255,.92);padding:.9rem 1rem;border-radius:.9rem;box-shadow:0 8px 26px rgba(40,30,60,.04);min-height:7.2rem; }
[data-testid="stMetricLabel"] { color:#5d5662;min-height:2.15rem;align-items:flex-start; }
[data-testid="stMetricLabel"] p { font-size:clamp(.72rem,.86vw,.9rem);line-height:1.2;white-space:normal; }
[data-testid="stMetricValue"] { font-weight:760;letter-spacing:-.035em;font-size:clamp(1.12rem,1.65vw,1.75rem);line-height:1.15;white-space:normal;overflow-wrap:anywhere; }
[data-testid="stMetricDelta"] { font-size:.72rem;white-space:normal; }
.block-container { padding-top:1.7rem;max-width:1500px; }
div[data-testid="stPlotlyChart"] { border:1px solid #e2dde7;background:#fff;border-radius:1rem;padding:.2rem; }
div[data-testid="stDataFrame"] { border:1px solid #e2dde7;border-radius:.8rem;overflow:hidden; }
.section-note { padding:.8rem 1rem;border-left:3px solid var(--violet);background:#f0eeff;border-radius:0 .75rem .75rem 0;color:#4a4352;font-size:.88rem;margin:.55rem 0 1rem; }
.warning-note { padding:.8rem 1rem;border-left:3px solid #d06b6b;background:#fff1ea;border-radius:0 .75rem .75rem 0;color:#6f321d;font-size:.88rem;margin:.55rem 0 1rem; }
.problem { border:1px solid #ead6cf;border-left:4px solid #d06b6b;border-radius:.75rem;padding:.8rem;background:#fffaf8;height:100%; }
.problem b { display:block;margin:.12rem 0 .28rem; }.muted { color:#716a76;font-size:.78rem; }
.footer { color:#857e8b;font-size:.7rem;letter-spacing:.07em;border-top:1px solid #e4dfe7;padding-top:1rem;margin-top:2rem; }
.stButton>button,.stDownloadButton>button { border-radius:.65rem;font-weight:700;border-color:#cdc5d6; }
.stButton>button[kind="primary"] { background:var(--violet);border-color:var(--violet); }
[data-testid="stAlert"] { color:#17151a; }
[data-testid="stAlert"] p { color:inherit!important; }
[data-baseweb="popover"],[data-baseweb="menu"],[role="listbox"] { color:#17151a!important;background:#fff!important; }
[data-baseweb="popover"] * ,[data-baseweb="menu"] * ,[role="listbox"] * { color:#17151a!important; }
@media(max-width:900px){.block-container{padding:1rem}.hero{padding:1.25rem}.hero h1{font-size:2.25rem}.hero:after{font-size:7rem}.statusbar{gap:.3rem}}
</style>
""",
        unsafe_allow_html=True,
    )


def render_chart(fig: go.Figure) -> None:
    st.plotly_chart(
        fig,
        use_container_width=True,
        config={"displayModeBar": False, "displaylogo": False, "responsive": True},
    )


def badges(*values: tuple[str, str]) -> None:
    html = "".join(f'<span class="badge {kind}">{label}</span>' for label, kind in values)
    st.markdown(html, unsafe_allow_html=True)


def note(text: str, warning: bool = False) -> None:
    css = "warning-note" if warning else "section-note"
    st.markdown(f'<div class="{css}">{text}</div>', unsafe_allow_html=True)


def render_error(exc: Exception | dict[str, Any], title: str = "Не удалось выполнить операцию") -> None:
    value = exc if isinstance(exc, dict) else service_error(exc)
    code = value.get("code", "UNEXPECTED_ERROR")
    field = value.get("field")
    st.error(f"{title}\n\n**{code}** · {value.get('message', '')}")
    if field:
        st.caption(f"Поле: `{field}`")
    if value.get("details"):
        with st.expander("Технические детали"):
            st.json(value["details"])


def results_status(
    result: dict[str, Any],
    current_hash: str,
    calculated_hash: str,
    *,
    dirty_override: bool | None = None,
) -> None:
    summary = result["summary"]
    dirty = current_hash != calculated_hash if dirty_override is None else dirty_override
    st.markdown(
        '<div class="statusbar">'
        f'<span class="pill {"warn" if dirty else "ok"}">{"● ЕСТЬ НЕСЧИТАННЫЕ ИЗМЕНЕНИЯ" if dirty else "✓ РЕЗУЛЬТАТЫ АКТУАЛЬНЫ"}</span>'
        f'<span class="pill {"ok" if summary["valid"] else "warn"}">{"✓ ПЛАН ИСПОЛНИМ" if summary["valid"] else "⚠ ПЛАН НЕИСПОЛНИМ"}</span>'
        f'<span class="pill blue">Критических нарушений: {summary["hard_violation_count"]}</span>'
        f'<span class="pill">Версия {calculated_hash}</span>'
        '</div>',
        unsafe_allow_html=True,
    )


def kpi_grid(
    result: dict[str, Any],
    capex_limits: tuple[float, float] = (1800, 2800),
    *,
    baseline: dict[str, Any] | None = None,
    scenario_id: str = "BASE",
) -> None:
    """Decision-oriented KPI summary with optional deltas to a baseline result."""

    values = minimum_annual_metrics(result)
    base = minimum_annual_metrics(baseline) if baseline is not None else None

    def delta(key: str, *, scale: float = 1.0, suffix: str = "") -> str | None:
        if base is None:
            return None
        value = scale * (float(values[key]) - float(base[key]))
        sign = "+" if value > 0 else ""
        return f"{sign}{value:.1f}{suffix}"

    is_base = scenario_id == "BASE"
    service_label = "требование" if is_base else "ориентир устойчивости"
    status_text = "План исполним" if values["valid"] else "План требует изменений"
    if values["valid"]:
        st.success(
            f"✓ {status_text}. Критических нарушений: {values['hard_violation_count']}."
        )
    else:
        st.error(
            f"⚠ {status_text}. Критических нарушений: {values['hard_violation_count']}."
        )

    st.markdown("#### Обслуживание спроса")
    service = st.columns(4)
    service[0].metric(
        "Минимальный общий сервис",
        percent(values["minimum_annual_total_service"]),
        delta(
            "minimum_annual_total_service",
            scale=100,
            suffix=" п.п. к BASE",
        ),
        help=(
            f"Худший год по доле обслуженного общего спроса. "
            f"Для BASE {service_label}: не ниже 97%."
        ),
    )
    service[1].metric(
        "Минимальный критический сервис",
        percent(values["minimum_annual_critical_service"]),
        delta(
            "minimum_annual_critical_service",
            scale=100,
            suffix=" п.п. к BASE",
        ),
        help=(
            f"Худший год по обслуживанию критических миссий. "
            f"Для BASE {service_label}: не ниже 99%."
        ),
    )
    service[2].metric(
        "Общий дефицит",
        mass(values["total_shortage_t"]),
        delta("total_shortage_t", suffix=" т к BASE"),
        delta_color="inverse",
        help="Суммарный спрос, который план не смог обслужить за весь горизонт.",
    )
    service[3].metric(
        "Критический дефицит",
        mass(values["critical_shortage_t"]),
        delta("critical_shortage_t", suffix=" т к BASE"),
        delta_color="inverse",
        help="Необслуженный критический спрос. Для оператора это наиболее приоритетный дефицит.",
    )

    st.markdown("#### Запас и устойчивость")
    resilience = st.columns(3)
    resilience[0].metric(
        "Минимальный резерв",
        f"{values['minimum_reserve_days']:.1f} дней",
        delta("minimum_reserve_days", suffix=" дн. к BASE"),
        help="Минимальное покрытие спроса запасом. Контрольное значение кейса: 45 дней.",
    )
    resilience[1].metric(
        "Минимальный физический запас",
        mass(values["minimum_inventory_t"]),
        delta("minimum_inventory_t", suffix=" т к BASE"),
        help="Самая низкая величина физического остатка на протяжении горизонта.",
    )
    resilience[2].metric(
        "Критические нарушения",
        str(values["hard_violation_count"]),
        (
            delta("hard_violation_count", suffix=" к BASE")
            if base is not None
            else None
        ),
        delta_color="inverse",
        help="Количество нарушений обязательных ограничений модели.",
    )

    violation_rows = violations_view(result)
    if violation_rows:
        with st.expander(
            f"Показать нарушения и понять, что менять ({len(violation_rows)})",
            expanded=not values["valid"],
        ):
            st.dataframe(
                pd.DataFrame(violation_rows),
                hide_index=True,
                width="stretch",
            )
            st.caption(
                "Смотрите на период, фактическое значение, лимит и разрыв. "
                "Нарушения сервиса обычно исправляются объёмом/структурой поставок; "
                "резерва — запасом или аварийным контрактом; CAPEX — инвестиционными решениями."
            )
    else:
        st.caption("Ограничения: нарушений нет.")

    st.markdown("#### Экономика")
    economics = st.columns(4)
    economics[0].metric(
        "Полная стоимость",
        money(values["undiscounted_cost_mln"]),
        delta("undiscounted_cost_mln", suffix=" млн к BASE"),
        delta_color="inverse",
        help="Все учитываемые расходы стратегии в постоянных ценах кейса.",
    )
    economics[1].metric(
        "Приведённая стоимость",
        money(values["discounted_cost_mln"]),
        delta("discounted_cost_mln", suffix=" млн к BASE"),
        delta_color="inverse",
        help="Стоимость с учётом выбранной ставки дисконтирования.",
    )
    economics[2].metric(
        "CAPEX до 2037",
        f"{values['capex_through_2037_mln']:.0f} / {capex_limits[0]:.0f} млн",
        delta("capex_through_2037_mln", suffix=" млн к BASE"),
        delta_color="inverse",
        help="Инвестиции до конца 2037 года относительно официального лимита.",
    )
    economics[3].metric(
        "CAPEX всего",
        f"{values['total_capex_mln']:.0f} / {capex_limits[1]:.0f} млн",
        delta("total_capex_mln", suffix=" млн к BASE"),
        delta_color="inverse",
        help="Суммарные инвестиции до 2040 года относительно официального лимита 2 800 млн.",
    )

    st.caption(
        f"Сервис: {'обязательные пороги 97%/99%' if is_base else '97%/99% показаны как ориентиры устойчивости, не новые hard-ограничения'}."
    )

def problems(result: dict[str, Any]) -> None:
    values = top_problems(result)
    st.subheader("Основные проблемы")
    if not values:
        st.success("Расчёт не содержит нарушений или предупреждений.")
        return
    columns = st.columns(len(values))
    for column, item in zip(columns, values):
        with column:
            severity = SEVERITY_LABELS.get(str(item.get("severity", "warning")), "Предупреждение")
            column.markdown(
                '<div class="problem">'
                f'<span class="badge">{severity}</span><b>{constraint_label(item.get("constraint_id", item.get("code")))}</b>'
                f'<div>{item.get("period", "—")} · факт {item.get("actual", "—")} {item.get("operator", "")} {item.get("limit", "—")}</div>'
                f'<div class="muted">Отклонение: {item.get("excess_or_gap", "—")} {item.get("unit", "")}</div>'
                '</div>',
                unsafe_allow_html=True,
            )


def violations(result: dict[str, Any], key: str) -> None:
    rows = violations_view(result)
    if not rows:
        st.success("Нарушений и предупреждений нет.")
        return
    frame = pd.DataFrame(rows)
    levels = sorted(frame["Уровень"].unique())
    selected = st.multiselect("Уровень", levels, default=levels, key=f"violations-{key}")
    st.dataframe(frame[frame["Уровень"].isin(selected)], hide_index=True, width="stretch")
    with st.expander("Технические строки нарушений"):
        st.code(json.dumps(result.get("violations", []), ensure_ascii=False, indent=2), language="json")