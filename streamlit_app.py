from __future__ import annotations

import copy
import io
import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.kernel_bridge import (
    bundle_bytes,
    case_tables,
    default_plan_raw,
    evaluate,
    plan_hash,
    reverse_stress,
    risks,
    sensitivity,
)

ROOT = Path(__file__).resolve().parent
SAVED = ROOT / "data" / "saved_plans"
SAVED.mkdir(parents=True, exist_ok=True)
YEARS = list(range(2035, 2041))
SOURCE_NAMES = {
    "A": "Earth-Core",
    "B": "Earth-Flex",
    "C": "Earth-New",
    "D": "Lunar-ISRU",
    "E": "Emergency",
}
SOURCE_COLORS = {"A": "#242129", "B": "#5B4BFF", "C": "#9B72FF", "D": "#DCA4C0", "E": "#FDAEAD"}

st.set_page_config(page_title="Космоконтур 2035", page_icon="✦", layout="wide", initial_sidebar_state="expanded")

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Manrope:wght@600;700;800&display=swap');
:root { --ink:#17151a; --paper:#fbfafc; --violet:#5b4bff; --purple:#9b72ff; --lav:#dcc5f1; --pink:#fcdaea; --coral:#fdaead; }
.stApp { background: radial-gradient(circle at 90% 0%, rgba(220,197,241,.27), transparent 28rem), var(--paper); color:var(--ink); }
html, body, [class*="css"] { font-family:Inter,system-ui,sans-serif; }
h1,h2,h3 { font-family:Manrope,Inter,sans-serif; letter-spacing:-.045em; color:var(--ink); }
[data-testid="stSidebar"] { background:#17151a; border-right:0; }
[data-testid="stSidebar"] * { color:#f8f7fb; }
[data-testid="stSidebar"] .stRadio label { padding:.45rem .65rem; border-radius:.65rem; }
[data-testid="stSidebar"] .stRadio label:hover { background:#28242d; }
.brand { font-family:Manrope;font-size:1.32rem;font-weight:800;margin:.25rem 0 1.5rem;letter-spacing:-.04em; }
.brand b { color:#b89cff; } .brand small { display:block;color:#948f9b;font:600 .62rem Inter;letter-spacing:.18em;margin-top:.25rem; }
.eyebrow { font-size:.67rem;font-weight:700;letter-spacing:.16em;text-transform:uppercase;color:#6d6673;margin-bottom:.5rem; }
.hero { border:1px solid #ded9e3;border-radius:1.25rem;padding:2.1rem 2.2rem;background:linear-gradient(115deg,#fff 48%,#eee6fb);margin-bottom:1.25rem;position:relative;overflow:hidden; }
.hero:after { content:'✦';position:absolute;right:4%;top:-20%;font-size:12rem;color:rgba(91,75,255,.10);transform:rotate(12deg); }
.hero h1 { font-size:clamp(2.2rem,5vw,4.6rem);line-height:.94;margin:.2rem 0 .8rem;max-width:850px; }
.hero h1 span { color:#5b4bff; } .hero p { max-width:700px;color:#625c67;font-size:1.05rem; }
.statusbar { display:flex;gap:.6rem;align-items:center;flex-wrap:wrap;margin:.3rem 0 1.2rem; }
.pill { display:inline-flex;gap:.4rem;align-items:center;padding:.34rem .65rem;border-radius:999px;background:#f1edf5;border:1px solid #ddd5e5;font-size:.72rem;font-weight:700; }
.pill.ok { background:#e5f8ee;border-color:#b9e7ca;color:#17653a; }.pill.warn { background:#fff1ea;border-color:#f5c7b4;color:#9a3e1a; }.pill.blue { background:#eeecff;color:#4939db;border-color:#d5d0ff; }
[data-testid="stMetric"] { border:1px solid #ded9e3;background:rgba(255,255,255,.86);padding:1rem 1.05rem;border-radius:1rem;box-shadow:0 8px 30px rgba(40,30,60,.045); }
[data-testid="stMetricLabel"] { color:#6d6673; } [data-testid="stMetricValue"] { font-family:Manrope;font-weight:750;letter-spacing:-.04em; }
.block-container { padding-top:2.1rem;max-width:1500px; }
div[data-testid="stPlotlyChart"] { border:1px solid #e2dde7;background:#fff;border-radius:1rem;padding:.25rem; }
div[data-testid="stDataFrame"] { border:1px solid #e2dde7;border-radius:.8rem;overflow:hidden; }
.section-note { padding:.85rem 1rem;border-left:3px solid #5b4bff;background:#f0eeff;border-radius:0 .75rem .75rem 0;color:#4a4352;font-size:.88rem;margin:.6rem 0 1rem; }
.case { color:#5b4bff;font-size:.64rem;font-weight:800;letter-spacing:.1em; }.team { color:#a34570;font-size:.64rem;font-weight:800;letter-spacing:.1em; }
.scenario-card { border:1px solid #ded9e3;border-radius:1rem;padding:1.1rem;background:#fff;min-height:145px; }
.scenario-card h3 { margin:.15rem 0 .6rem; }.scenario-card b { font-size:1.55rem; }
.chart-key { display:flex;flex-wrap:wrap;gap:.45rem 1rem;margin:-.7rem .3rem 1.1rem;color:#5f5864;font-size:.72rem; }
.chart-key span { display:inline-flex;align-items:center;gap:.35rem;white-space:nowrap; }
.chart-key i { width:.72rem;height:.72rem;border-radius:.15rem;display:inline-block; }
.footer { color:#857e8b;font-size:.7rem;letter-spacing:.08em;border-top:1px solid #e4dfe7;padding-top:1rem;margin-top:2rem; }
.stButton>button, .stDownloadButton>button { border-radius:.65rem;font-weight:700;border-color:#cdc5d6; }
.stButton>button[kind="primary"] { background:#5b4bff;border-color:#5b4bff; }
@media(max-width:700px){.block-container{padding:1rem}.hero{padding:1.25rem}.hero h1{font-size:2.35rem}.hero:after{font-size:7rem}.statusbar{gap:.3rem}}
</style>
""",
    unsafe_allow_html=True,
)


def init_state() -> None:
    if "plan" not in st.session_state:
        st.session_state.plan = default_plan_raw()
    if "result" not in st.session_state:
        with st.spinner("Первый расчёт BASE и MANDATORY_STRESS…"):
            st.session_state.result = evaluate(st.session_state.plan)
    st.session_state.setdefault("saved_hash", plan_hash(st.session_state.plan))
    st.session_state.setdefault("risk_result", None)
    st.session_state.setdefault("sensitivity_result", None)
    st.session_state.setdefault("reverse_result", None)


def money(value: float) -> str:
    return f"{value:,.0f}".replace(",", " ")


def pct(value: float) -> str:
    return f"{100 * value:.1f}%".replace(".", ",")


def chart_layout(fig: go.Figure, height: int = 390) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=58, r=24, t=64, b=94),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#ffffff",
        font=dict(family="Inter", color="#332e37", size=12),
        title=dict(x=.02, xanchor="left", y=.97, yanchor="top", font=dict(size=17)),
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-.20,
            xanchor="left",
            x=0,
            title_text="",
            font=dict(size=11),
        ),
        hoverlabel=dict(bgcolor="#17151a", font_color="white"),
    )
    fig.update_xaxes(gridcolor="#eeeaf1", zeroline=False, automargin=True)
    fig.update_yaxes(gridcolor="#eeeaf1", zeroline=False, automargin=True)
    return fig


def render_chart(fig: go.Figure) -> None:
    st.plotly_chart(
        fig,
        config={"displayModeBar": False, "displaylogo": False, "responsive": True},
    )


def cost_key() -> None:
    items = [("Закупка", "#5b4bff"), ("Резерв", "#9b72ff"), ("CAPEX", "#242129"), ("OPEX", "#dca4c0"), ("Хранение", "#fdaead")]
    html = "".join(f'<span><i style="background:{color}"></i>{label}</span>' for label, color in items)
    st.markdown(f'<div class="chart-key">{html}</div>', unsafe_allow_html=True)


def source_key() -> None:
    html = "".join(f'<span><i style="background:{SOURCE_COLORS[source]}"></i>{source}</span>' for source in SOURCE_NAMES)
    st.markdown(f'<div class="chart-key">{html}</div>', unsafe_allow_html=True)


def annual_df(result: dict) -> pd.DataFrame:
    return pd.DataFrame(result["annual"])


def top_status() -> None:
    result = st.session_state.result
    base = result["BASE"]
    stress = result["MANDATORY_STRESS"]
    current = plan_hash(st.session_state.plan)
    dirty = current != result["plan_hash"]
    hard = sum(v["severity"] == "hard" for v in base["violations"])
    st.markdown(
        '<div class="statusbar">'
        f'<span class="pill {"warn" if dirty else "ok"}">{"● Есть несчитанные изменения" if dirty else "✓ План рассчитан"}</span>'
        f'<span class="pill {"warn" if hard else "ok"}">{"⚠" if hard else "✓"} BASE: {hard} жёстких нарушений</span>'
        f'<span class="pill blue">STRESS: {len(stress["violations"])} сигналов</span>'
        f'<span class="pill">Хэш {result["plan_hash"]}</span></div>',
        unsafe_allow_html=True,
    )


def recalculate() -> None:
    try:
        with st.spinner("Ядро считает BASE и MANDATORY_STRESS…"):
            st.session_state.result = evaluate(st.session_state.plan)
        st.session_state.risk_result = None
        st.session_state.sensitivity_result = None
        st.session_state.reverse_result = None
        st.toast("Оба обязательных сценария пересчитаны", icon="✅")
    except Exception as exc:
        st.error(f"План не рассчитан: {exc}")


def kpis(result: dict) -> None:
    a = annual_df(result)
    total_demand = a.demand_total_t.sum()
    total_served = a.served_total_t.sum()
    crit_demand = a.demand_critical_t.sum()
    crit_served = a.served_critical_t.sum()
    top = st.columns(3)
    top[0].metric("Стоимость", f'{money(result["summary"]["undiscounted_cost_mln"])} млн')
    top[1].metric("PV стоимости", f'{money(result["summary"]["discounted_cost_mln"])} млн')
    top[2].metric("Сервис", pct(total_served / total_demand), f'критический {pct(crit_served / crit_demand)}')
    bottom = st.columns(3)
    bottom[0].metric("Статус", "Валиден" if result["summary"]["valid"] else "Нарушения", f'{len(result["violations"])} сигналов')
    bottom[1].metric("Дефицит", f'{a.shortage_t.sum():.1f} т')
    bottom[2].metric("Финальный запас", f'{a.iloc[-1].closing_inventory_t:.1f} т')


def chart_demand_service(result: dict, title: str = "Спрос, обслуживание и дефицит") -> go.Figure:
    a = annual_df(result)
    fig = go.Figure()
    fig.add_bar(x=a.year, y=a.demand_total_t, name="Спрос", marker_color="#dcc5f1")
    fig.add_bar(x=a.year, y=a.served_total_t, name="Обслужено", marker_color="#5b4bff")
    fig.add_bar(x=a.year, y=a.shortage_t, name="Дефицит", marker_color="#fdaead")
    fig.update_layout(title=title, barmode="group", yaxis_title="тонн")
    return chart_layout(fig)


def chart_inventory(result: dict) -> go.Figure:
    m = pd.DataFrame(result["monthly"])
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=m.month, y=m.opening_inventory_t, name="На начало", line=dict(color="#9b72ff", width=1.5)))
    fig.add_trace(go.Scatter(x=m.month, y=m.closing_inventory_t, name="На конец", fill="tozeroy", line=dict(color="#5b4bff", width=2)))
    fig.add_trace(go.Scatter(x=m.month, y=m.active_storage_capacity_t, name="Ёмкость", line=dict(color="#17151a", dash="dot")))
    fig.update_layout(title="Помесячный физический запас", yaxis_title="тонн")
    return chart_layout(fig)


def chart_sources(result: dict, field: str = "gross_delivery_t") -> go.Figure:
    df = pd.DataFrame(result["sources"])
    fig = px.bar(df, x="year", y=field, color="source_id", barmode="stack", color_discrete_map=SOURCE_COLORS,
                 labels={field: "тонн", "source_id": "Канал", "year": "Год"}, title="Поставки по источникам")
    styled = chart_layout(fig, 350)
    styled.update_layout(showlegend=False, margin=dict(l=58, r=24, t=64, b=46))
    return styled


def chart_costs(result: dict) -> go.Figure:
    df = pd.DataFrame(result["costs"])
    fields = ["procurement_mln", "reservation_mln", "capex_mln", "fixed_opex_mln", "holding_mln"]
    labels = ["Закупка", "Резерв", "CAPEX", "OPEX", "Хранение"]
    colors = ["#5b4bff", "#9b72ff", "#242129", "#dca4c0", "#fdaead"]
    fig = go.Figure()
    for field, label, color in zip(fields, labels, colors):
        fig.add_bar(x=df.year, y=df[field], name=label, marker_color=color)
    fig.update_layout(title="Экономика по категориям", barmode="stack", yaxis_title="млн у.е.")
    styled = chart_layout(fig, 350)
    styled.update_layout(showlegend=False, margin=dict(l=58, r=24, t=64, b=46))
    return styled


def chart_service(result: dict) -> go.Figure:
    a = annual_df(result)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=a.year, y=a.total_service_level * 100, name="Общий сервис", mode="lines+markers", line=dict(color="#5b4bff", width=3)))
    fig.add_trace(go.Scatter(x=a.year, y=a.critical_service_level * 100, name="Критический", mode="lines+markers", line=dict(color="#17151a", width=2)))
    fig.add_hline(y=97, line_dash="dash", line_color="#9b72ff", annotation_text="порог 97%", annotation_position="bottom left")
    fig.add_hline(y=99, line_dash="dot", line_color="#f08383", annotation_text="порог 99%", annotation_position="top left")
    fig.update_layout(title="Уровень обслуживания", yaxis_title="%", yaxis_range=[94, 101.5])
    return chart_layout(fig, 330)


def page_overview() -> None:
    st.markdown('<div class="hero"><div class="eyebrow">КОСМОХАКАТОН 2026 · ОПЕРАТОРСКОЕ РАБОЧЕЕ МЕСТО</div><h1>Топливный контур.<br><span>Решения в цифрах.</span></h1><p>Один план, две обязательные среды и прозрачный путь от заказа до обслуживания спроса.</p></div>', unsafe_allow_html=True)
    top_status()
    selected = st.segmented_control("Сценарий", ["BASE", "MANDATORY_STRESS"], default="BASE", label_visibility="collapsed")
    result = st.session_state.result[selected or "BASE"]
    kpis(result)
    c1, c2 = st.columns([1.18, 1])
    with c1: render_chart(chart_demand_service(result))
    with c2: render_chart(chart_inventory(result))
    c1, c2 = st.columns(2)
    with c1:
        render_chart(chart_sources(result))
        source_key()
    with c2:
        render_chart(chart_costs(result))
        cost_key()
    render_chart(chart_service(result))


def orders_table(raw: dict) -> pd.DataFrame:
    rows = []
    by_source = {x["source_id"]: x for x in raw["decisions"]["supply_orders"]}
    for source in SOURCE_NAMES:
        order = by_source.get(source, {"mode": "annual_even", "values": {}})
        row = {"Канал": source, "Название": SOURCE_NAMES[source], "Режим": order["mode"]}
        for year in YEARS:
            row[str(year)] = round(sum(float(v) for k, v in order["values"].items() if str(k).startswith(str(year))), 3)
        rows.append(row)
    return pd.DataFrame(rows)


def reservations_table(raw: dict) -> pd.DataFrame:
    index = {(x["source_id"], int(x["year"])): x["reserved_capacity_t"] for x in raw["decisions"]["capacity_reservations"]}
    return pd.DataFrame([{"Канал": s, "Название": SOURCE_NAMES[s], **{str(y): float(index.get((s, y), 0)) for y in YEARS}} for s in SOURCE_NAMES])


def apply_supply_tables(raw: dict, order_df: pd.DataFrame, reserve_df: pd.DataFrame) -> None:
    existing = {item["source_id"]: copy.deepcopy(item) for item in raw["decisions"]["supply_orders"]}
    orders = []
    for _, row in order_df.iterrows():
        source, mode = row["Канал"], row["Режим"]
        old = existing.get(source)
        old_totals = {
            year: sum(float(v) for k, v in old.get("values", {}).items() if str(k).startswith(str(year)))
            for year in YEARS
        } if old else {}
        unchanged = old and old.get("mode") == mode and all(abs(old_totals[year] - float(row[str(year)])) < 0.001 for year in YEARS)
        if unchanged:
            orders.append(old)
            continue
        if mode == "monthly":
            values = {f"{year}-{month:02d}": float(row[str(year)]) / 12 for year in YEARS for month in range(1, 13) if float(row[str(year)]) > 0}
        else:
            values = {str(year): float(row[str(year)]) for year in YEARS}
        orders.append({"source_id": source, "mode": mode, "values": values})
    reservations = []
    for _, row in reserve_df.iterrows():
        for year in YEARS:
            value = float(row[str(year)])
            if value > 0:
                reservations.append({"source_id": row["Канал"], "year": year, "reserved_capacity_t": value})
    raw["decisions"]["supply_orders"] = orders
    raw["decisions"]["capacity_reservations"] = reservations


def page_strategy() -> None:
    st.title("Стратегия снабжения")
    st.markdown('<div class="section-note">Редактор меняет только решения оператора. Ядро не оптимизирует и не исправляет план автоматически. Нажмите «Пересчитать», когда изменения готовы.</div>', unsafe_allow_html=True)
    raw = st.session_state.plan
    with st.form("strategy_form"):
        st.subheader("План и закупки")
        c1, c2 = st.columns([1, 2])
        plan_id = c1.text_input("ID плана", raw.get("plan_id", "operator-plan"))
        notes = c2.text_input("Комментарий", raw.get("metadata", {}).get("notes", ""))
        st.caption("Заказано, зарезервировано и доставлено — разные величины. Доставку вычисляет ядро после применения сроков и ограничений.")
        order_df = st.data_editor(
            orders_table(raw), hide_index=True, width="stretch",
            column_config={"Канал": st.column_config.TextColumn(disabled=True), "Название": st.column_config.TextColumn(disabled=True), "Режим": st.column_config.SelectboxColumn(options=["annual_even", "monthly"]), **{str(y): st.column_config.NumberColumn(f"{y}, т", min_value=0.0, step=1.0) for y in YEARS}},
            key="order_editor",
        )
        with st.expander("Резервирование мощности · отдельно от заказов", expanded=False):
            reserve_df = st.data_editor(
                reservations_table(raw), hide_index=True, width="stretch",
                column_config={"Канал": st.column_config.TextColumn(disabled=True), "Название": st.column_config.TextColumn(disabled=True), **{str(y): st.column_config.NumberColumn(f"{y}, т/год", min_value=0.0, step=1.0) for y in YEARS}},
                key="reserve_editor",
            )
        st.subheader("Инвестиции")
        investments = {x["investment_id"]: x for x in raw["decisions"]["investments"]}
        i1, i2, i3 = st.columns(3)
        with i1:
            st.markdown("**ZBO** · 180 млн · 120 т · потери 1,2%  ")
            st.markdown('<span class="case">CASE_INPUT</span>', unsafe_allow_html=True)
            zbo = st.checkbox("Включить ZBO", investments.get("ZBO", {}).get("enabled", False))
            zbo_date = st.text_input("Ввод ZBO (ГГГГ-ММ)", investments.get("ZBO", {}).get("commissioning_month", "2036-01"))
        with i2:
            st.markdown("**Earth-New** · опцион 90 + исполнение 270 млн  ")
            st.markdown('<span class="case">CASE_INPUT</span>', unsafe_allow_html=True)
            earth = st.checkbox("Использовать Earth-New", investments.get("EARTH_NEW", {}).get("enabled", False))
            earth_buy = st.text_input("Покупка опциона", investments.get("EARTH_NEW", {}).get("option_purchase_month", "2035-01"))
            earth_ex = st.text_input("Исполнение опциона", investments.get("EARTH_NEW", {}).get("option_exercise_month", "2035-02"))
        with i3:
            st.markdown("**Lunar-ISRU** · 1 250 млн · доступ с 2038  ")
            st.markdown('<span class="case">CASE_INPUT</span>', unsafe_allow_html=True)
            lunar = st.checkbox("Финансировать Lunar-ISRU", investments.get("LUNAR_ISRU", {}).get("enabled", False))
            lunar_date = st.text_input("Финансирование", investments.get("LUNAR_ISRU", {}).get("funding_month", "2035-03"))
        st.subheader("Начальный запас · подтверждённая закупка")
        stock = raw["decisions"]["initial_stock_acquisition"]
        s1, s2, s3 = st.columns(3)
        stock_source = s1.selectbox("Источник", list(SOURCE_NAMES), index=list(SOURCE_NAMES).index(stock["source_id"]))
        stock_ordered = s2.number_input("Заказано, т", min_value=0.0, value=float(stock["ordered_volume_t"]), step=0.1, format="%.6f")
        stock_reserved = s3.number_input("Зарезервировано, т/год", min_value=0.0, value=float(stock["reserved_capacity_t_per_year"]), step=0.1, format="%.3f")
        s1, s2, s3 = st.columns(3)
        order_date = s1.text_input("Дата заказа", stock["order_date"])
        delivery_date = s2.text_input("Плановая доставка", stock["planned_delivery_date"])
        contract = s3.text_input("Контракт: начало / конец", f'{stock["contract_period_start"]} / {stock["contract_period_end"]}')
        stock_notes = st.text_input("Основание и примечания", stock.get("notes", ""))
        st.subheader("Роль Emergency по годам")
        roles = raw["decisions"]["emergency_role_by_year"]
        role_cols = st.columns(6)
        role_values = {}
        for col, year in zip(role_cols, YEARS):
            role_values[str(year)] = col.selectbox(str(year), ["reserve_only", "planned_supply"], index=["reserve_only", "planned_supply"].index(roles.get(str(year), "reserve_only")), key=f"role_{year}")
        submitted = st.form_submit_button("Применить изменения к плану", type="primary", width="stretch")
    if submitted:
        try:
            updated = copy.deepcopy(raw)
            updated["plan_id"] = plan_id.strip()
            updated.setdefault("metadata", {})["notes"] = notes
            apply_supply_tables(updated, order_df, reserve_df)
            updated["decisions"]["investments"] = [
                {"investment_id": "ZBO", "enabled": zbo, "commissioning_month": zbo_date},
                {"investment_id": "EARTH_NEW", "enabled": earth, "buy_option": earth, "option_purchase_month": earth_buy, "exercise_option": earth, "option_exercise_month": earth_ex},
                {"investment_id": "LUNAR_ISRU", "enabled": lunar, "funding_month": lunar_date},
            ]
            start, end = [part.strip() for part in contract.split("/", 1)]
            updated["decisions"]["initial_stock_acquisition"] = {"source_id": stock_source, "reserved_capacity_t_per_year": stock_reserved, "ordered_volume_t": stock_ordered, "order_date": order_date, "planned_delivery_date": delivery_date, "contract_period_start": start, "contract_period_end": end, "notes": stock_notes, "status": "TEAM_DECISION"}
            updated["decisions"]["emergency_role_by_year"] = role_values
            st.session_state.plan = updated
            st.success("Изменения применены. Расчёт пока прежний — нажмите «Пересчитать оба сценария».")
        except Exception as exc:
            st.error(f"Не удалось применить изменения: {exc}")


def violations_table(result: dict) -> None:
    data = result["violations"]
    if not data:
        st.success("Нарушений и контрольных сигналов нет.")
        return
    df = pd.DataFrame(data)
    severity = st.multiselect("Фильтр по уровню", sorted(df.severity.unique()), default=sorted(df.severity.unique()), key=f"sev_{result['summary']['scenario_id']}")
    shown = df[df.severity.isin(severity)][["severity", "constraint_id", "period", "actual", "operator", "limit", "unit", "human_message"]]
    st.dataframe(shown, hide_index=True, width="stretch")


def page_results() -> None:
    st.title("Результаты расчёта")
    selected = st.segmented_control("Сценарий результатов", ["BASE", "MANDATORY_STRESS"], default="BASE")
    result = st.session_state.result[selected or "BASE"]
    kpis(result)
    tab1, tab2, tab3, tab4 = st.tabs(["Годовой баланс", "Запасы по месяцам", "Источники и потери", "Экономика и нарушения"])
    with tab1:
        c1, c2 = st.columns(2)
        with c1: render_chart(chart_demand_service(result))
        with c2: render_chart(chart_service(result))
        a = annual_df(result)
        st.dataframe(a[["year", "demand_total_t", "served_total_t", "shortage_t", "demand_critical_t", "served_critical_t", "total_service_level", "critical_service_level"]], hide_index=True, width="stretch")
    with tab2:
        render_chart(chart_inventory(result))
        m = pd.DataFrame(result["monthly"])
        st.dataframe(m[["month", "opening_inventory_t", "gross_delivery_t", "losses_t", "accepted_delivery_t", "served_critical_t", "served_noncritical_t", "closing_inventory_t", "active_storage_capacity_t"]], hide_index=True, width="stretch")
    with tab3:
        display = st.radio("Показать", ["requested_order_t", "feasible_order_t", "gross_delivery_t"], horizontal=True, format_func=lambda x: {"requested_order_t":"Запрошено", "feasible_order_t":"Допустимо", "gross_delivery_t":"Доставлено"}[x])
        render_chart(chart_sources(result, display))
        source_key()
        a = annual_df(result)
        loss = go.Figure()
        loss.add_bar(x=a.year, y=a.gross_supply_t, name="Входящий поток", marker_color="#dcc5f1")
        loss.add_bar(x=a.year, y=a.losses_t, name="Потери", marker_color="#fdaead")
        loss.add_trace(go.Scatter(x=a.year, y=a.losses_divided_by_throughput*100, name="Доля потерь, %", yaxis="y2", line=dict(color="#17151a", width=3)))
        loss.update_layout(title="Входящий поток и потери", yaxis2=dict(overlaying="y", side="right", title="%"), barmode="group")
        render_chart(chart_layout(loss))
    with tab4:
        render_chart(chart_costs(result))
        cost_key()
        st.caption(f'Стоимость обслуженной тонны: {result["summary"]["cost_per_served_ton_mln"]:.3f} млн у.е. · дисконтированная: {result["summary"]["discounted_cost_per_served_ton_mln"]:.3f} млн у.е.')
        violations_table(result)


def page_scenarios() -> None:
    st.title("BASE и обязательный стресс")
    st.caption("Один и тот же план исполняется без изменений в двух средах. Масштабы графиков совпадают.")
    base, stress = st.session_state.result["BASE"], st.session_state.result["MANDATORY_STRESS"]
    c1, c2 = st.columns(2)
    for col, title, result in [(c1, "BASE", base), (c2, "MANDATORY_STRESS", stress)]:
        a = annual_df(result)
        with col:
            st.markdown(f'<div class="scenario-card"><div class="eyebrow">{title}</div><h3>{"Расчётный базовый режим" if title=="BASE" else "Обязательное стресс-испытание"}</h3><b>{pct(a.served_total_t.sum()/a.demand_total_t.sum())}</b><br><span>общий сервис · дефицит {a.shortage_t.sum():.1f} т · {len(result["violations"])} сигналов</span></div>', unsafe_allow_html=True)
            render_chart(chart_demand_service(result, "Спрос и обслуживание"))
            render_chart(chart_inventory(result))
    comp = st.session_state.result["comparison"]
    st.subheader("Изменение ключевых показателей")
    rows = [{"Показатель": k, "BASE": v["BASE"], "STRESS": v["MANDATORY_STRESS"], "Разница": v["difference"]} for k, v in comp["summary"].items()]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def page_risks() -> None:
    st.title("Риски")
    st.caption("Реестр TEAM_ASSUMPTION оценивается неизменным цифровым двойником. UNKNOWN не попадает в матрицу вероятности × влияния.")
    if st.button("Рассчитать портфель рисков", type="primary"):
        try:
            with st.spinner("Выполняются детерминированные прогоны рисков…"):
                st.session_state.risk_result = risks(st.session_state.plan)
        except Exception as exc: st.error(str(exc))
    data = st.session_state.risk_result
    if not data:
        st.info("Запустите оценку: ядро рассчитает каждый риск отдельно и не изменит исходный план.")
        return
    register = pd.DataFrame(data["risk_register"])
    c1, c2, c3 = st.columns(3)
    c1.metric("Рисков", len(register)); c2.metric("С известной вероятностью", int(register.likelihood_score.notna().sum())); c3.metric("UNKNOWN", len(data["unknown_likelihood_risks"]))
    known = register.dropna(subset=["likelihood_score"])
    if not known.empty:
        fig = px.scatter(known, x="likelihood_score", y="impact_score", size="impact_score", color="ordinal_risk_score", hover_name="name", text="risk_id", range_x=[.5,5.5], range_y=[.5,5.5], color_continuous_scale=[[0,"#dcc5f1"],[1,"#5b4bff"]], title="Матрица 5 × 5")
        fig.update_traces(textposition="top center")
        render_chart(chart_layout(fig, 430))
    st.dataframe(register[["risk_id", "name", "event", "owner", "likelihood_status", "likelihood_score", "impact_score", "ordinal_risk_score"]], hide_index=True, width="stretch")
    for item in data["risk_register"]:
        with st.expander(f'{item["risk_id"]} · {item["name"]} · влияние {item["impact_score"]}/5'):
            st.write(item["event"])
            c1, c2, c3 = st.columns(3)
            c1.metric("Дефицит, т", f'{item["risk_metrics"]["total_shortage_t"]:.1f}')
            c2.metric("Жёсткие нарушения", item["risk_metrics"]["hard_violation_count"])
            c3.metric("Месяцев с дефицитом", item["risk_metrics"]["months_with_shortage"])
            st.caption(f'Мера: {item.get("mitigation", {}).get("description", "не задана")}')


def page_sensitivity() -> None:
    st.title("Чувствительность и обратный стресс")
    st.caption("Параметр исследования — множитель спроса. Исходный план не меняется.")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Сетка чувствительности")
        values = st.multiselect("Множители", [0.8,0.9,1.0,1.1,1.2,1.3,1.4,1.5], default=[0.9,1.0,1.1,1.2])
        if st.button("Запустить sweep", width="stretch"):
            try:
                with st.spinner("Расчёт точек…"): st.session_state.sensitivity_result = sensitivity(st.session_state.plan, values)
            except Exception as exc: st.error(str(exc))
        if st.session_state.sensitivity_result:
            df = pd.DataFrame(st.session_state.sensitivity_result["points"])
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df.value, y=df.total_service_level*100, name="Сервис, %", mode="lines+markers", line=dict(color="#5b4bff",width=3)))
            fig.add_trace(go.Bar(x=df.value, y=df.total_shortage_t, name="Дефицит, т", yaxis="y2", marker_color="#fdaead", opacity=.7))
            fig.update_layout(title="Ответ системы на рост спроса", yaxis2=dict(overlaying="y", side="right", title="тонн"))
            render_chart(chart_layout(fig))
            st.dataframe(df[["value","valid","total_service_level","total_shortage_t","total_cost_mln","hard_violation_count"]], hide_index=True, width="stretch")
    with c2:
        st.subheader("Обратный стресс")
        start = st.number_input("От", value=1.0, min_value=.5, max_value=3.0, step=.05)
        stop = st.number_input("До", value=1.6, min_value=.5, max_value=3.0, step=.05)
        step = st.number_input("Шаг", value=.05, min_value=.01, max_value=.5, step=.01)
        if st.button("Найти первый отказ", width="stretch"):
            try:
                with st.spinner("Поиск порога…"): st.session_state.reverse_result = reverse_stress(st.session_state.plan,start,stop,step)
            except Exception as exc: st.error(str(exc))
        if st.session_state.reverse_result:
            st.json(st.session_state.reverse_result, expanded=True)


def saved_files() -> list[Path]:
    return sorted(SAVED.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)


def page_data_export() -> None:
    st.title("Данные и экспорт")
    tab1, tab2, tab3 = st.tabs(["Планы", "CASE_INPUT", "Экспорт результатов"])
    with tab1:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Операции с планом")
            save_name = st.text_input("Имя снимка", st.session_state.plan.get("plan_id", "plan"))
            if st.button("Сохранить снимок", type="primary", width="stretch"):
                safe = "".join(c for c in save_name if c.isalnum() or c in "-_") or "plan"
                target = SAVED / f"{datetime.now():%Y%m%d-%H%M%S}-{safe}.json"
                target.write_text(json.dumps(st.session_state.plan, ensure_ascii=False, indent=2), encoding="utf-8")
                st.session_state.saved_hash = plan_hash(st.session_state.plan)
                st.success(f"Сохранено: {target.name}")
            st.download_button("Скачать план JSON", json.dumps(st.session_state.plan, ensure_ascii=False, indent=2), f'{st.session_state.plan["plan_id"]}.json', "application/json", width="stretch")
            if st.button("Создать новый из примера", width="stretch"):
                st.session_state.plan = default_plan_raw(); st.rerun()
            if st.button("Дублировать текущий", width="stretch"):
                st.session_state.plan = copy.deepcopy(st.session_state.plan)
                st.session_state.plan["plan_id"] += "-copy"; st.rerun()
        with c2:
            upload = st.file_uploader("Импорт JSON", type=["json"])
            if upload and st.button("Проверить и открыть импорт"):
                try:
                    imported = json.loads(upload.getvalue().decode("utf-8-sig"))
                    evaluate(imported)
                    st.session_state.plan = imported
                    st.success("План проверен ядром и открыт.")
                except Exception as exc: st.error(f"Импорт отклонён: {exc}")
            files = saved_files()
            if files:
                chosen = st.selectbox("Сохранённые снимки", files, format_func=lambda p: p.name)
                if st.button("Открыть снимок"):
                    st.session_state.plan = json.loads(chosen.read_text(encoding="utf-8")); st.rerun()
            else: st.info("Сохранённых снимков пока нет.")
    with tab2:
        tables = case_tables()
        st.markdown('<span class="case">CASE_INPUT · ТОЛЬКО ЧТЕНИЕ</span>', unsafe_allow_html=True)
        st.subheader("Спрос")
        st.dataframe(pd.DataFrame(tables["demand"]), hide_index=True, width="stretch")
        st.subheader("Источники")
        src = pd.DataFrame(tables["sources"])
        st.dataframe(src[["source_id","name","capacity_t_per_year","variable_cost_mln_per_t","reservation_rate_mln_per_t_year_capacity","take_or_pay_share","lead_time_min_value","lead_time_max_value","lead_time_unit","available_from_year","status"]], hide_index=True, width="stretch")
        st.subheader("Ограничения")
        st.dataframe(pd.DataFrame(tables["constraints"]), hide_index=True, width="stretch")
    with tab3:
        st.write("Комплект ядра содержит план, результаты BASE и MANDATORY_STRESS, сравнение и реестр рисков.")
        if st.button("Подготовить ZIP-комплект", type="primary"):
            try:
                with st.spinner("Формируется воспроизводимый комплект…"):
                    st.session_state.bundle = bundle_bytes(st.session_state.plan)
            except Exception as exc: st.error(str(exc))
        if st.session_state.get("bundle"):
            st.download_button("Скачать ZIP", st.session_state.bundle, f'{st.session_state.plan["plan_id"]}-bundle.zip', "application/zip", width="stretch")
        csv = io.StringIO()
        pd.DataFrame(st.session_state.result["comparison"]["annual"]).to_csv(csv, index=False, sep=";")
        st.download_button("Скачать сравнение CSV", "\ufeff" + csv.getvalue(), "base-vs-stress.csv", "text/csv", width="stretch")


init_state()

with st.sidebar:
    st.markdown('<div class="brand">космо<b>контур</b><small>ORBITAL FUEL SYSTEM</small></div>', unsafe_allow_html=True)
    page = st.radio("Рабочее пространство", ["Обзор", "Стратегия", "Результаты", "Сценарии", "Риски", "Чувствительность", "Данные и экспорт"], label_visibility="collapsed")
    st.divider()
    if st.button("↻ Пересчитать оба сценария", type="primary", width="stretch"):
        recalculate()
    current_hash = plan_hash(st.session_state.plan)
    if current_hash != st.session_state.result["plan_hash"]:
        st.warning("Есть изменения после последнего расчёта")
    else:
        st.success("Результаты актуальны")
    st.caption(f"План: {st.session_state.plan['plan_id']}  ")
    st.caption(f"Последний расчёт: {st.session_state.result['plan_hash']}")
    st.markdown("---")
    st.caption("Ядро kosmohak 0.4.0 · без автоматической оптимизации")

pages = {
    "Обзор": page_overview,
    "Стратегия": page_strategy,
    "Результаты": page_results,
    "Сценарии": page_scenarios,
    "Риски": page_risks,
    "Чувствительность": page_sensitivity,
    "Данные и экспорт": page_data_export,
}
pages[page]()
st.markdown('<div class="footer">КОСМОКОНТУР / STREAMLIT · CASE_INPUT сохраняется отдельно от TEAM_ASSUMPTION · BASE и MANDATORY_STRESS используют один план</div>', unsafe_allow_html=True)

