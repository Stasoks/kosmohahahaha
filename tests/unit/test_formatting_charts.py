"""Unit tests for the presentation helpers used by every page."""
from __future__ import annotations

import pytest

from app import charts, formatting

pytestmark = pytest.mark.kernel


def test_number_uses_russian_separators():
    assert formatting.number(1234567.5, 1) == "1 234 567,5"
    assert formatting.number(0) == "0,0"
    assert formatting.number(None) == "—"


def test_value_helpers_append_units():
    assert formatting.money(12.345) == "12 млн у.е."
    assert formatting.mass(3.2) == "3,2 т"
    assert formatting.capacity(1000) == "1 000,0 т/год"


def test_percent_and_percentage_points():
    assert formatting.percent(0.125) == "12,5%"
    assert formatting.percent(None) == "—"
    assert formatting.percentage_points(2.5) == "+2,5 п.п."
    assert formatting.percentage_points(-2.5) == "-2,5 п.п."


def test_signed_and_yes_no():
    assert formatting.signed(5, "т") == "+5,0 т"
    assert formatting.signed(-5, "т") == "-5,0 т"
    assert formatting.signed(None) == "—"
    assert formatting.yes_no(True) == "Да"
    assert formatting.yes_no(False) == "Нет"


def test_charts_build_from_serialized_result(base_result):
    data = base_result.to_dict()
    figures = {
        "demand_service": charts.demand_service(data),
        "inventory": charts.inventory(data),
        "costs": charts.costs(data),
        "service": charts.service(data, "BASE"),
        "supply_mix": charts.supply_mix(data, {}),
    }
    for name, figure in figures.items():
        assert figure.data, f"{name} produced an empty figure"


def test_sensitivity_lines_return_two_figures(plan, base_scenario, case_data, assumptions):
    from kosmohak.service import run_official_demand_sensitivity

    sensitivity = run_official_demand_sensitivity(plan, base_scenario, case_data, assumptions)
    service_figure, cost_figure = charts.sensitivity_lines(sensitivity.points, "Спрос")
    assert service_figure.data
    assert cost_figure.data
