from __future__ import annotations

import pytest

pytestmark = pytest.mark.web


def _apply_new_plan_name(app, by_label, name: str):
    app.radio[0].set_value("Стратегия").run()
    by_label(app.text_input, "Название плана").set_value(name).run()
    by_label(app.button, "Применить решения").click().run()


def test_clean_state_has_no_warnings(app, goto):
    for page in ("Сценарии", "Риски и чувствительность"):
        goto(page)
        assert not app.warning, f"unexpected warning on a clean state on {page}"


def test_uncounted_edit_marks_analysis_stale(app, by_label, goto):
    _apply_new_plan_name(app, by_label, "stale-check")
    goto("Сценарии")

    warnings = "\n".join(item.value for item in app.warning)
    assert "несчитанные изменения" in warnings


def test_recalculation_clears_stale_state(app, by_label, goto):
    _apply_new_plan_name(app, by_label, "stale-check-2")
    by_label(app.button, "↻ Пересчитать").click().run()

    goto("Сценарии")
    assert not app.warning
