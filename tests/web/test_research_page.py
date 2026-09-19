from __future__ import annotations

import pytest

from app.kernel_bridge import case_metadata

pytestmark = pytest.mark.web


def _metadata(app):
    return case_metadata(app.session_state["workspace"])


def test_add_source_extends_workspace(app, by_label, goto):
    goto("Исследования")
    before = _metadata(app)["research_source_ids"]

    by_label(app.button, "Добавить источник").click().run()

    assert app.exception == []
    after = _metadata(app)["research_source_ids"]
    assert len(after) == len(before) + 1


def test_extend_horizon_adds_next_year(app, by_label, goto):
    goto("Исследования")
    years = _metadata(app)["years"]
    next_year = max(years) + 1

    by_label(app.button, f"Добавить {next_year}").click().run()

    assert app.exception == []
    assert next_year in _metadata(app)["years"]


def test_reset_research_restores_defaults(app, by_label, goto):
    goto("Исследования")
    by_label(app.button, "Добавить источник").click().run()
    assert _metadata(app)["research_source_ids"], "precondition: a source was added"

    by_label(app.button, "Сбросить изменения").click().run()

    assert app.exception == []
    assert _metadata(app)["research_source_ids"] == []
    assert app.session_state["research_result"] is None


def test_extended_calculation_produces_result(app, by_label, goto):
    goto("Исследования")
    by_label(app.button, "Рассчитать расширенный вариант").click().run()

    assert app.exception == []
    result = app.session_state["research_result"]
    assert result is not None
    assert result["BASE"]["summary"]["valid"] is True
