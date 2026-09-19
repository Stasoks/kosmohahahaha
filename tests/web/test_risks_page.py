from __future__ import annotations

import pytest

pytestmark = pytest.mark.web


def test_risk_workspace_tabs_are_present(app, goto):
    goto("Риски и чувствительность")

    labels = [tab.label for tab in app.tabs]
    for expected in ("Реестр рисков", "Чувствительность", "Предел устойчивости", "Участники"):
        assert expected in labels, f"missing tab {expected!r}: {labels}"


@pytest.mark.slow
def test_risk_portfolio_button_populates_result(app, by_label, goto):
    goto("Риски и чувствительность")
    by_label(app.button, "Рассчитать портфель рисков").click().run()

    assert app.exception == []
    register = app.session_state["risk_result"]["risk_register"]
    assert register
    assert all("impact_score" in entry for entry in register)
    assert app.session_state["risk_result"]["risk_matrix"]


@pytest.mark.slow
def test_sensitivity_sweep_populates_result(app, by_label, goto):
    goto("Риски и чувствительность")
    by_label(app.button, "Проверить нижний, базовый и верхний спрос").click().run()

    assert app.exception == []
    assert app.session_state["sensitivity_result"] is not None
