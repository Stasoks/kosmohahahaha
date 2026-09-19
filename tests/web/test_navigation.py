from __future__ import annotations

import pytest

pytestmark = pytest.mark.web


def test_sidebar_lists_every_page(app, pages):
    assert list(app.radio[0].options) == pages


def test_every_page_renders_without_exception(app, pages):
    for page in pages:
        app.radio[0].set_value(page).run()
        assert app.exception == [], f"{page} -> {app.exception}"


EXPECTED_HEADINGS = {
    "Стратегия": "Стратегия",
    "Результаты": "Результаты расчёта",
    "Сценарии": "Сценарная лаборатория",
    "Риски и чувствительность": "Риски и чувствительность",
    "Исследования": "Исследования",
    "Данные и экспорт": "Данные и экспорт",
}


def test_pages_render_expected_headings(app, pages):
    for page in pages:
        app.radio[0].set_value(page).run()
        if page in EXPECTED_HEADINGS:
            assert EXPECTED_HEADINGS[page] in [title.value for title in app.title], page
        else:
            assert app.markdown, "overview rendered no content"
