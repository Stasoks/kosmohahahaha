from __future__ import annotations

import pytest

pytestmark = pytest.mark.web


def test_builder_failure_is_rendered_as_error_not_crash(app, by_label, goto, monkeypatch):
    import app.runtime as runtime

    def boom(*args, **kwargs):
        raise RuntimeError("synthetic builder failure")

    monkeypatch.setattr(runtime, "builder", boom)

    goto("Сценарии")
    by_label(app.button, "Подобрать вариант").click().run()

    assert app.exception == [], "a backend failure must not crash the Streamlit script"
    errors = "\n".join(item.value for item in app.error)
    assert "synthetic builder failure" in errors


def test_research_failure_is_rendered_as_error_not_crash(app, by_label, goto, monkeypatch):
    import app.runtime as runtime

    def boom(*args, **kwargs):
        raise RuntimeError("synthetic research failure")

    monkeypatch.setattr(runtime, "workspace_evaluate", boom)

    goto("Исследования")
    by_label(app.button, "Рассчитать расширенный вариант").click().run()

    assert app.exception == []
    errors = "\n".join(item.value for item in app.error)
    assert "synthetic research failure" in errors
