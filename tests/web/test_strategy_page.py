from __future__ import annotations

import pytest

from app.kernel_bridge import plan_hash, plan_presets

pytestmark = pytest.mark.web


def test_applying_decisions_updates_plan_and_marks_it_dirty(app, by_label):
    app.radio[0].set_value("Стратегия").run()
    by_label(app.text_input, "Название плана").set_value("operator-test").run()
    by_label(app.button, "Применить решения").click().run()

    assert app.exception == []
    assert app.session_state["plan"]["plan_id"] == "operator-test"
    assert app.session_state["result"]["plan_hash"] != plan_hash(app.session_state["plan"])
    assert app.warning, "expected an uncounted-changes warning after applying decisions"


def test_recalculate_accepts_applied_plan(app, by_label):
    app.radio[0].set_value("Стратегия").run()
    by_label(app.text_input, "Название плана").set_value("operator-test-2").run()
    by_label(app.button, "Применить решения").click().run()
    by_label(app.button, "↻ Пересчитать").click().run()

    assert app.exception == []
    assert app.session_state["result"]["plan_hash"] == plan_hash(app.session_state["plan"])
    assert not app.warning


def test_plan_validation_button_reports_status(app, by_label):
    app.radio[0].set_value("Стратегия").run()
    by_label(app.button, "Проверить план").click().run()

    assert app.exception == []
    assert app.session_state["validation_result"] is not None


def test_preset_selection_can_be_applied(app, by_label):
    selector = by_label(app.selectbox, "Стратегия")
    preset_keys = [item["key"] for item in plan_presets()]
    assert len(preset_keys) > 1, "expected at least one built-in preset"
    target = next(key for key in preset_keys if key != selector.value)

    selector.set_value(target).run()
    by_label(app.button, "Выбрать и пересчитать").click().run()

    assert app.exception == []
    assert app.session_state["plan"]["plan_id"] != "final-base-plan"
    assert app.session_state["result"]["plan_hash"] == plan_hash(app.session_state["plan"])
