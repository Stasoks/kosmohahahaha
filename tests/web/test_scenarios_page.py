from __future__ import annotations

import pytest

pytestmark = pytest.mark.web


def test_scenario_comparison_is_ready(app, goto):
    goto("Сценарии")

    assert app.session_state["abc_result"] is not None
    assert app.session_state["stress_plan"] is not None
    assert len(app.dataframe) >= 2
    assert len(app.get("plotly_chart")) >= 1
    assert not app.warning


def test_reset_to_reference_variant_c(app, by_label, goto):
    goto("Сценарии")
    by_label(app.button, "Вернуть исходный вариант C").click().run()

    assert app.exception == []
    assert app.session_state["stress_plan"]["plan_id"] == "final-stress-adaptation"
    assert app.session_state["abc_result"] is not None


def test_builder_can_run_with_small_search(app, by_label, goto):
    goto("Сценарии")
    by_label(app.checkbox, "Настроить параметры поиска").set_value(True).run()

    by_label(app.number_input, "Число вариантов").set_value(40)
    by_label(app.number_input, "Число итераций").set_value(0)
    app.run()

    by_label(app.button, "Подобрать вариант").click().run()

    assert app.exception == []
    assert app.session_state["builder_result"] is not None
    assert "solutions" in app.session_state["builder_result"]
