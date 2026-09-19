from __future__ import annotations

import pytest

pytestmark = pytest.mark.web


def test_kpis_and_charts_render(app, goto):
    goto("Результаты")

    labels = [metric.label for metric in app.metric]
    assert "Статус" in labels
    assert len(labels) >= 8
    assert len(app.get("plotly_chart")) >= 2


def test_balance_tabs_are_present(app, goto):
    goto("Результаты")

    labels = [tab.label for tab in app.tabs]
    assert "Годовой баланс" in labels
    assert "Помесячный баланс" in labels


def test_can_switch_result_conditions(app, goto):
    goto("Результаты")

    groups = app.button_group
    assert groups, "results scenario selector is not exposed to AppTest"
    selector = groups[0]
    assert len(list(selector.options)) == 2

    selector.set_value("MANDATORY_STRESS").run()

    assert app.exception == []
    assert [metric.label for metric in app.metric]
