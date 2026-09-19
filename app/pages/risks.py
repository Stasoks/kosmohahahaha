from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from app import charts, runtime
from app.components import render_chart, render_error
from app.kernel_bridge import risk_catalog, stakeholder_data
from app.state import analysis_is_stale, is_dirty
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


def _stale(value: dict | None) -> None:
    if analysis_is_stale(value):
        st.warning("Результат относится к предыдущей версии плана.")