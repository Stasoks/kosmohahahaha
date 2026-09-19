from __future__ import annotations

import pytest

pytestmark = pytest.mark.web

STALE_MARKER = "несчитанные изменения"


def _stale_text(app) -> str:
    return "\n".join(item.value for item in app.warning if STALE_MARKER in item.value)


def _apply_new_plan_name(app, by_label, name: str):
    app.radio[0].set_value("Стратегия").run()
    by_label(app.text_input, "Название плана").set_value(name).run()
    by_label(app.button, "Применить решения").click().run()


def test_clean_state_is_not_stale(app, goto):
    for page in ("Сценарии", "Риски и чувствительность"):
        goto(page)
        assert not _stale_text(app), f"unexpected stale warning on a clean state on {page}"


def test_uncounted_edit_marks_analysis_stale(app, by_label, goto):
    _apply_new_plan_name(app, by_label, "stale-check")
    goto("Сценарии")

    assert STALE_MARKER in _stale_text(app)


def test_recalculation_clears_stale_state(app, by_label, goto):
    _apply_new_plan_name(app, by_label, "stale-check-2")
    by_label(app.button, "↻ Пересчитать").click().run()

    goto("Сценарии")
    assert not _stale_text(app)
